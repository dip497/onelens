package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * Detects a module-level React Server Components directive — `"use client"` (or
 * `"use server"`) as the module's first statement — and records every client module's
 * repo-relative filePath on [NextjsContext.clientModules].
 *
 * Runs FIRST among the P2 collectors so Page / Layout / SpecialFile / ReactComponent
 * nodes can consult [NextjsContext.isClient] when they are emitted. `isServer = !isClient`
 * (App Router default is a server component). A module-level `"use server"` marks all
 * exports as server actions — that is P3; for P2 it simply leaves `isClient = false`.
 *
 * Detection is textual on the file's leading bytes (comments / whitespace skipped),
 * which is robust across JS-plugin PSI-stub variations and cheap — no full parse.
 */
object DirectiveCollector {
    private val LOG = logger<DirectiveCollector>()

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping directive collection — dumb mode")
            return
        }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorFile(it, ctx) }
        }
        val psiManager = PsiManager.getInstance(project)
        for (vf in files) {
            ProgressManager.checkCanceled()
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                if (!firstStatementIs(psi.text, "use client")) return@run
                val relative = ctx.relativize(Paths.get(vf.path))
                if (relative.isNotEmpty()) ctx.clientModules += relative
            }
        }
        LOG.info("DirectiveCollector: ${ctx.clientModules.size} 'use client' modules")
    }

    /**
     * True when [directive] is the module's first statement (a bare string literal),
     * after skipping leading whitespace, line comments and block comments.
     */
    private fun firstStatementIs(text: String, directive: String): Boolean {
        var i = 0
        val n = text.length
        while (i < n) {
            val c = text[i]
            when {
                c.isWhitespace() -> i++
                c == '/' && i + 1 < n && text[i + 1] == '/' -> {
                    i += 2
                    while (i < n && text[i] != '\n') i++
                }
                c == '/' && i + 1 < n && text[i + 1] == '*' -> {
                    i += 2
                    while (i + 1 < n && !(text[i] == '*' && text[i + 1] == '/')) i++
                    i += 2
                }
                else -> {
                    // First non-trivia char must open a string literal matching the directive.
                    if (c != '"' && c != '\'') return false
                    val expected = "$c$directive$c"
                    return text.regionMatches(i, expected, 0, expected.length)
                }
            }
        }
        return false
    }
}
