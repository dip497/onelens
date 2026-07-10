package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSBlockStatement
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
import com.onelens.plugin.export.ExposedByEdge
import com.onelens.plugin.export.ServerActionData
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * Emits [ServerActionData] for React Server Actions:
 *   - module scope: the file's first statement is `"use server"` → every exported
 *     top-level function is an action (`scope="module"`).
 *   - inline: a function whose FIRST body statement is `"use server"` (`scope="inline"`).
 *
 * `EXPOSED_BY` edge → the enclosing / same-file Page or ReactComponent when one exists,
 * else omitted. Zero-target-safe: a repo with no `"use server"` emits nothing.
 * Runs after Route/Component collectors so the owner set is populated.
 */
object ServerActionCollector {
    private val LOG = logger<ServerActionCollector>()

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping server-action collection — dumb mode")
            return
        }
        val ownerFqns = HashSet<String>().apply {
            ctx.pages.forEach { add(it.fqn) }
            ctx.components.forEach { add(it.fqn) }
        }
        val ownersByFile = (ctx.pages.map { it.filePath to it.fqn } +
            ctx.components.map { it.filePath to it.fqn }).groupBy({ it.first }, { it.second })

        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorPath(it.path) }
        }
        val psiManager = PsiManager.getInstance(project)
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                if (!psi.text.contains("use server")) return@run // cheap gate
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                val moduleScope = firstStatementIsUseServer(psi.text)
                for (fn in PsiTreeUtil.findChildrenOfType(psi, JSFunction::class.java)) {
                    val isModule = moduleScope && NextPsiUtil.isTopLevel(fn) && NextPsiUtil.isExported(fn)
                    val isInline = !moduleScope && bodyStartsWithUseServer(fn)
                    if (!isModule && !isInline) continue
                    val name = NextPsiUtil.functionName(fn) ?: "default"
                    val fqn = "$relative::$name"
                    ctx.serverActions += ServerActionData(
                        fqn = fqn, name = name, filePath = relative,
                        scope = if (isModule) "module" else "inline",
                        isAsync = NextPsiUtil.isAsync(fn),
                        lineStart = NextPsiUtil.lineNumber(doc, fn.textRange.startOffset),
                        lineEnd = NextPsiUtil.lineNumber(doc, fn.textRange.endOffset),
                        body = NextPsiUtil.bodyText(fn),
                    )
                    val owner = NextPsiUtil.enclosingSymbolFqn(fn, relative, ownerFqns)
                        ?: ownersByFile[relative]?.firstOrNull()
                    if (owner != null && owner != fqn) {
                        ctx.exposedBy += ExposedByEdge(actionFqn = fqn, ownerFqn = owner)
                    }
                }
            }
        }
        LOG.info("ServerActionCollector: ${ctx.serverActions.size} server actions")
    }

    /** True when the function's first body statement is a bare `"use server"` string literal. */
    private fun bodyStartsWithUseServer(fn: JSFunction): Boolean {
        val block = fn.block as? JSBlockStatement ?: return false
        val first = block.statements.firstOrNull() ?: return false
        val t = first.text.trim().trimEnd(';').trim()
        return t == "\"use server\"" || t == "'use server'"
    }

    /** True when the module's first statement is a bare `"use server"` string literal. */
    private fun firstStatementIsUseServer(text: String): Boolean {
        var i = 0
        val n = text.length
        while (i < n) {
            val c = text[i]
            when {
                c.isWhitespace() -> i++
                c == '/' && i + 1 < n && text[i + 1] == '/' -> { i += 2; while (i < n && text[i] != '\n') i++ }
                c == '/' && i + 1 < n && text[i + 1] == '*' -> {
                    i += 2; while (i + 1 < n && !(text[i] == '*' && text[i + 1] == '/')) i++; i += 2
                }
                else -> {
                    if (c != '"' && c != '\'') return false
                    val expected = "${c}use server$c"
                    return text.regionMatches(i, expected, 0, expected.length)
                }
            }
        }
        return false
    }
}
