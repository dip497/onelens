package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.onelens.plugin.export.InterceptsEdge
import com.onelens.plugin.export.MiddlewareData
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * Emits a [MiddlewareData] for each `middleware.(ts|js)` (Next.js allows one at the
 * project root or the app root). `matchers` are the string literals in
 * `export const config = { matcher: [...] }`. An INTERCEPTS edge is emitted only when a
 * matcher literally equals or prefixes a collected [Route][com.onelens.plugin.export.NextRouteData].
 *
 * Zero-target-safe: no middleware file → nothing emitted.
 */
object MiddlewareCollector {
    private val LOG = logger<MiddlewareCollector>()

    private val EXTS = setOf("ts", "js")
    private val MATCHER_BLOCK = Regex("""matcher\s*:\s*(\[[^\]]*\]|['"`][^'"`]*['"`])""")
    private val STRING_LIT = Regex("""['"`]([^'"`]+)['"`]""")

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping middleware collection — dumb mode")
            return
        }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorFile(it, ctx) }
                .filter { it.nameWithoutExtension == "middleware" && (it.extension?.lowercase() ?: "") in EXTS }
        }
        if (files.isEmpty()) return
        val routeUrls = ctx.routes.map { it.urlPath }
        val psiManager = PsiManager.getInstance(project)
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            // ponytail: only root / app-root middleware is honoured by Next.js; a nested
            // segment count > 1 (excluding a leading src/) is almost certainly not it.
            val depth = relative.split('/').filterNot { it == "src" }.size
            if (depth > 2) continue
            val text = ReadAction.compute<String, Throwable> {
                psiManager.findFile(vf)?.text ?: ""
            }
            if (!text.contains("middleware")) continue
            val matchers = MATCHER_BLOCK.find(text)?.let { m ->
                STRING_LIT.findAll(m.groupValues[1]).map { it.groupValues[1] }.toList()
            }.orEmpty()
            val fqn = "$relative::middleware"
            ctx.middlewares += MiddlewareData(fqn = fqn, filePath = relative, matchers = matchers)
            for (matcher in matchers) {
                for (url in routeUrls) {
                    if (url == matcher || url.startsWith(matcher)) {
                        ctx.intercepts += InterceptsEdge(middlewareFqn = fqn, urlPath = url)
                    }
                }
            }
        }
        LOG.info("MiddlewareCollector: ${ctx.middlewares.size} middleware, ${ctx.intercepts.size} intercepts")
    }
}
