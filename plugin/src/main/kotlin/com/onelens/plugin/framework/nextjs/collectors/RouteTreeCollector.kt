package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.BoundaryOfEdge
import com.onelens.plugin.export.ChildOfEdge
import com.onelens.plugin.export.HasLayoutEdge
import com.onelens.plugin.export.HasPageEdge
import com.onelens.plugin.export.LayoutData
import com.onelens.plugin.export.NextRouteData
import com.onelens.plugin.export.PageData
import com.onelens.plugin.export.SpecialFileData
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.isTestFile
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import com.onelens.plugin.framework.nextjs.RenderSite
import com.intellij.openapi.vfs.VirtualFile
import java.nio.file.Paths

/**
 * Walks the Next.js App Router file tree (`app/`, plus a best-effort pass over a
 * legacy `pages/` router) under the workspace scope and emits:
 *   - [NextRouteData] per route directory (PK = urlPath),
 *   - [PageData] / [LayoutData] / [SpecialFileData] for the route files present,
 *   - HAS_PAGE / HAS_LAYOUT / BOUNDARY_OF / CHILD_OF edges.
 *
 * urlPath is derived from the segment chain under `app/`: route groups `(group)` are
 * stripped, parallel `@slot` segments dropped, `[param]` → `:param`,
 * `[...slug]`/`[[...slug]]` → `*slug`. The app root is `/`.
 *
 * Route handlers (`route.ts`) are P3 — ignored here. Function bodies (isAsync /
 * lineStart / lineEnd / body) are read via PSI inside a ReadAction. isClient comes
 * from [NextjsContext.clientModules] (populated by [DirectiveCollector], which must
 * run first). Vendored dirs are skipped via [JsFileTypes.isVendorPath].
 */
object RouteTreeCollector {
    private val LOG = logger<RouteTreeCollector>()

    private val EXTS = setOf("tsx", "jsx", "ts", "js")
    private val SPECIAL_KINDS = setOf("loading", "error", "not-found", "global-error", "template")

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping route-tree collection — dumb mode")
            return
        }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorPath(it.path) }
        }
        val psiManager = PsiManager.getInstance(project)

        // ---- App Router: group route files by their route directory ----
        // relDir -> (segmentsAfterApp) + list of (kind, VirtualFile)
        val appDirs = LinkedHashMap<String, MutableList<Pair<String, VirtualFile>>>()
        val segmentsByDir = HashMap<String, List<String>>()
        for (vf in files) {
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            val base = vf.nameWithoutExtension
            val ext = vf.extension?.lowercase() ?: continue
            if (ext !in EXTS) continue
            val kind = when {
                base == "page" -> "page"
                base == "layout" -> "layout"
                base in SPECIAL_KINDS -> base
                else -> continue // includes route.* (P3), and non-route files
            }
            val segs = relative.split('/')
            val appIdx = segs.indexOf("app")
            if (appIdx < 0 || appIdx == segs.size - 1) continue
            val relDir = segs.subList(0, segs.size - 1).joinToString("/")
            val afterApp = segs.subList(appIdx + 1, segs.size - 1) // dir segments under app/
            appDirs.getOrPut(relDir) { mutableListOf() }.add(kind to vf)
            segmentsByDir[relDir] = afterApp
        }

        // Emit routes + nodes for each app route directory (dedup routes by urlPath).
        val routesByUrl = LinkedHashMap<String, NextRouteData>()
        val childUrlByDir = HashMap<String, String>() // relDir -> urlPath (for CHILD_OF)
        for ((relDir, entries) in appDirs) {
            ProgressManager.checkCanceled()
            val segs = segmentsByDir[relDir] ?: emptyList()
            val url = computeUrl(segs)
            childUrlByDir[relDir] = url.urlPath
            if (!routesByUrl.containsKey(url.urlPath)) {
                routesByUrl[url.urlPath] = NextRouteData(
                    urlPath = url.urlPath,
                    segmentDir = relDir,
                    dynamic = url.paramNames.isNotEmpty(),
                    paramNames = url.paramNames,
                    group = url.group,
                    isRoot = url.urlPath == "/",
                )
            }
            for ((kind, vf) in entries) {
                emitRouteFile(project, psiManager, ctx, vf, kind, url.urlPath)
            }
        }
        ctx.routes += routesByUrl.values

        // CHILD_OF: link each route dir to the nearest ancestor route dir.
        val dirSet = childUrlByDir.keys
        for ((relDir, childUrl) in childUrlByDir) {
            var parent = parentDir(relDir)
            while (parent != null) {
                val parentUrl = childUrlByDir[parent]
                if (parentUrl != null && parent in dirSet && parentUrl != childUrl) {
                    ctx.childOf += ChildOfEdge(childUrlPath = childUrl, parentUrlPath = parentUrl)
                    break
                }
                parent = parentDir(parent)
            }
        }

        // ---- Legacy pages/ router (best-effort: Route + Page only) ----
        collectPagesRouter(project, psiManager, ctx, files)

        LOG.info(
            "RouteTreeCollector: routes=${ctx.routes.size}, pages=${ctx.pages.size}, " +
                "layouts=${ctx.layouts.size}, specialFiles=${ctx.specialFiles.size}"
        )
    }

    private fun emitRouteFile(
        project: Project,
        psiManager: PsiManager,
        ctx: NextjsContext,
        vf: VirtualFile,
        kind: String,
        urlPath: String,
    ) {
        ProgressManager.checkCanceled()
        val relative = ctx.relativize(Paths.get(vf.path))
        if (relative.isEmpty()) return
        val isClient = ctx.isClient(relative)
        val isTest = isTestFile(relative)
        ReadAction.run<Throwable> {
            val psi = psiManager.findFile(vf) ?: return@run
            val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
            val fn = findDefaultExportFn(psi)
            val lineStart = fn?.let { NextPsiUtil.lineNumber(doc, it.textRange.startOffset) } ?: 0
            val lineEnd = fn?.let { NextPsiUtil.lineNumber(doc, it.textRange.endOffset) } ?: 0
            when (kind) {
                "page" -> {
                    val fqn = "$relative::default"
                    ctx.pages += PageData(
                        fqn = fqn, filePath = relative, urlPath = urlPath,
                        isAsync = fn?.let { NextPsiUtil.isAsync(it) } ?: false,
                        isClient = isClient, lineStart = lineStart, lineEnd = lineEnd,
                        body = fn?.let { NextPsiUtil.bodyText(it) }, isTest = isTest,
                    )
                    ctx.hasPage += HasPageEdge(urlPath = urlPath, pageFqn = fqn)
                    fn?.let { ctx.renderSites += RenderSite(fqn, relative, NextPsiUtil.jsxTagNames(it)) }
                }
                "layout" -> {
                    val fqn = "$relative::default"
                    ctx.layouts += LayoutData(
                        fqn = fqn, filePath = relative, urlPath = urlPath,
                        isRoot = urlPath == "/", isClient = isClient,
                        lineStart = lineStart, lineEnd = lineEnd,
                        body = fn?.let { NextPsiUtil.bodyText(it) }, isTest = isTest,
                    )
                    ctx.hasLayout += HasLayoutEdge(urlPath = urlPath, layoutFqn = fqn)
                    fn?.let { ctx.renderSites += RenderSite(fqn, relative, NextPsiUtil.jsxTagNames(it)) }
                }
                else -> {
                    val fqn = "$relative::default"
                    ctx.specialFiles += SpecialFileData(
                        fqn = fqn, filePath = relative, urlPath = urlPath, kind = kind,
                        isClient = isClient, lineStart = lineStart, lineEnd = lineEnd,
                    )
                    ctx.boundaryOf += BoundaryOfEdge(specialFqn = fqn, urlPath = urlPath)
                }
            }
        }
    }

    private fun collectPagesRouter(
        project: Project,
        psiManager: PsiManager,
        ctx: NextjsContext,
        files: List<VirtualFile>,
    ) {
        val seenUrls = ctx.routes.mapTo(HashSet()) { it.urlPath }
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            val ext = vf.extension?.lowercase() ?: continue
            if (ext !in EXTS) continue
            val base = vf.nameWithoutExtension
            if (base.startsWith("_")) continue // _app, _document, _error
            val segs = relative.split('/')
            val pagesIdx = segs.indexOf("pages")
            if (pagesIdx < 0 || pagesIdx == segs.size - 1) continue
            // Skip API routes (P3 route handlers) and app-router files already handled.
            val after = segs.subList(pagesIdx + 1, segs.size)
            if (after.firstOrNull() == "api") continue
            if (segs.contains("app")) continue
            // Build url segments: dir segments + filename (dropping `index`).
            val dirSegs = after.subList(0, after.size - 1)
            val fileSeg = if (base == "index") emptyList() else listOf(base)
            val url = computeUrl(dirSegs + fileSeg)
            if (url.urlPath in seenUrls) continue
            seenUrls += url.urlPath
            ctx.routes += NextRouteData(
                urlPath = url.urlPath, segmentDir = segs.subList(0, segs.size - 1).joinToString("/"),
                dynamic = url.paramNames.isNotEmpty(), paramNames = url.paramNames,
                group = url.group, isRoot = url.urlPath == "/",
            )
            val isClient = ctx.isClient(relative)
            val isTest = isTestFile(relative)
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                val fn = findDefaultExportFn(psi) ?: return@run
                val fqn = "$relative::default"
                ctx.pages += PageData(
                    fqn = fqn, filePath = relative, urlPath = url.urlPath,
                    isAsync = NextPsiUtil.isAsync(fn), isClient = isClient,
                    lineStart = NextPsiUtil.lineNumber(doc, fn.textRange.startOffset),
                    lineEnd = NextPsiUtil.lineNumber(doc, fn.textRange.endOffset),
                    body = NextPsiUtil.bodyText(fn), isTest = isTest,
                )
                ctx.hasPage += HasPageEdge(urlPath = url.urlPath, pageFqn = fqn)
                ctx.renderSites += RenderSite(fqn, relative, NextPsiUtil.jsxTagNames(fn))
            }
        }
    }

    // ---- url computation ----

    private data class UrlResult(val urlPath: String, val paramNames: List<String>, val group: String?)

    private fun computeUrl(segments: List<String>): UrlResult {
        val filtered = mutableListOf<String>()
        val params = mutableListOf<String>()
        var group: String? = null
        for (seg in segments) {
            when {
                seg.isEmpty() -> {}
                seg.startsWith("(") && seg.endsWith(")") -> group = seg
                seg.startsWith("@") -> {} // parallel route slot — dropped from path
                seg.startsWith("[[...") && seg.endsWith("]]") -> {
                    val name = seg.removePrefix("[[...").removeSuffix("]]")
                    params += name; filtered += "*$name"
                }
                seg.startsWith("[...") && seg.endsWith("]") -> {
                    val name = seg.removePrefix("[...").removeSuffix("]")
                    params += name; filtered += "*$name"
                }
                seg.startsWith("[") && seg.endsWith("]") -> {
                    val name = seg.removePrefix("[").removeSuffix("]")
                    params += name; filtered += ":$name"
                }
                else -> filtered += seg
            }
        }
        val url = if (filtered.isEmpty()) "/" else "/" + filtered.joinToString("/")
        return UrlResult(url, params, group)
    }

    private fun parentDir(dir: String): String? {
        val idx = dir.lastIndexOf('/')
        return if (idx <= 0) null else dir.substring(0, idx)
    }

    // ---- default export function resolution ----

    /**
     * Best-effort default-export component function: prefers an explicit
     * `export default function`, then a top-level function whose body renders JSX
     * (covers `const Page = () => <.../>; export default Page`), then any top-level fn.
     */
    private fun findDefaultExportFn(file: PsiFile): JSFunction? {
        val fns = PsiTreeUtil.findChildrenOfType(file, JSFunction::class.java)
            .filter { isTopLevel(it) }
        fns.firstOrNull { isDefaultExport(it) }?.let { return it }
        fns.firstOrNull { NextPsiUtil.containsJsx(it) }?.let { return it }
        return fns.firstOrNull()
    }

    private fun isTopLevel(element: PsiElement): Boolean {
        var parent: PsiElement? = element.parent
        while (parent != null && parent !is PsiFile) {
            if (parent is JSFunction && parent !== element) return false
            parent = parent.parent
        }
        return true
    }

    private fun isDefaultExport(element: PsiElement): Boolean {
        var cursor: PsiElement? = element
        while (cursor != null && cursor !is PsiFile) {
            if (cursor.text.orEmpty().trimStart().startsWith("export default")) return true
            cursor = cursor.parent
        }
        return false
    }
}
