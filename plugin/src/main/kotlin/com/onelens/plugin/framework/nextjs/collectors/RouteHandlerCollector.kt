package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.HandlesEdge
import com.onelens.plugin.export.NextEndpointData
import com.onelens.plugin.export.RouteHandlerData
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * App-Router API route handlers: files named `route.(ts|tsx|js|jsx)` under `app/`.
 * A named export whose name is an HTTP verb ({GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS})
 * becomes a [RouteHandlerData] + reused `Endpoint` node ("<METHOD>:<urlPath>") + a
 * HANDLES edge. urlPath is computed the same way [RouteTreeCollector] computes it for
 * the containing directory (shared [NextPsiUtil.computeUrl]).
 *
 * Zero-target-safe: a repo with no `route.*` files emits nothing.
 */
object RouteHandlerCollector {
    private val LOG = logger<RouteHandlerCollector>()

    private val VERBS = setOf("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
    private val EXTS = setOf("tsx", "jsx", "ts", "js")

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping route-handler collection — dumb mode")
            return
        }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorPath(it.path) }
                .filter { it.nameWithoutExtension == "route" && (it.extension?.lowercase() ?: "") in EXTS }
        }
        val psiManager = PsiManager.getInstance(project)
        val seenEndpoints = HashSet<String>()
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            val segs = relative.split('/')
            val appIdx = segs.indexOf("app")
            if (appIdx < 0) continue
            val afterApp = segs.subList(appIdx + 1, segs.size - 1) // dir segments under app/, minus route.*
            val urlPath = NextPsiUtil.computeUrl(afterApp).urlPath
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                for ((verb, fn) in namedVerbExports(psi)) {
                    val fqn = "$relative::$verb"
                    ctx.routeHandlers += RouteHandlerData(
                        fqn = fqn, filePath = relative, httpMethod = verb, urlPath = urlPath,
                        lineStart = NextPsiUtil.lineNumber(doc, fn.textRange.startOffset),
                        lineEnd = NextPsiUtil.lineNumber(doc, fn.textRange.endOffset),
                        body = NextPsiUtil.bodyText(fn),
                    )
                    val endpointFqn = "$verb:$urlPath"
                    if (seenEndpoints.add(endpointFqn)) {
                        ctx.endpoints += NextEndpointData(fqn = endpointFqn, method = verb, path = urlPath)
                    }
                    ctx.handles += HandlesEdge(endpointFqn = endpointFqn, handlerFqn = fqn)
                }
            }
        }
        LOG.info("RouteHandlerCollector: ${ctx.routeHandlers.size} handlers, ${ctx.endpoints.size} endpoints")
    }

    /** Exported top-level `function GET` / `const POST = () => …` keyed by HTTP verb. */
    private fun namedVerbExports(file: PsiFile): List<Pair<String, JSFunction>> {
        val out = mutableListOf<Pair<String, JSFunction>>()
        val seen = HashSet<String>()
        for (fn in PsiTreeUtil.findChildrenOfType(file, JSFunction::class.java)) {
            val name = NextPsiUtil.functionName(fn) ?: continue
            if (name !in VERBS) continue
            if (!NextPsiUtil.isTopLevel(fn)) continue
            if (!NextPsiUtil.isExported(fn)) continue
            if (seen.add(name)) out += name to fn
        }
        return out
    }
}
