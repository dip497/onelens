package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSFunctionExpression
import com.intellij.lang.javascript.psi.JSVariable
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
import com.onelens.plugin.export.ReactComponentData
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.isTestFile
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import com.onelens.plugin.framework.nextjs.RenderSite
import java.nio.file.Paths

/**
 * Emits a [ReactComponentData] for every exported function / arrow whose body renders
 * JSX. JSX detection is PSI-native: a [com.intellij.lang.javascript.psi.JSXmlLiteralExpression]
 * anywhere in the symbol's subtree (see [NextPsiUtil.containsJsx]). A textual fallback
 * (PascalCase name + `</` / `/>` / `<Xxx` in the body) covers the rare case where the
 * JSX PSI is stub-elided.
 *
 * Also records a [RenderSite] per component so [RendersResolver] can derive
 * (Component -[:RENDERS]-> Component) edges once the full component set + imports exist.
 *
 * isClient comes from [NextjsContext.clientModules] (DirectiveCollector runs first);
 * isServer = !isClient. Vendored dirs are skipped. `.vue` files are ignored.
 */
object ReactComponentCollector {
    private val LOG = logger<ReactComponentCollector>()
    private val EXTS = setOf("tsx", "jsx", "ts", "js")
    private val JSX_TEXT_HINT = Regex("""</|/>|<[A-Z]""")

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping React component collection — dumb mode")
            return
        }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorPath(it.path) }
                .filter { (it.extension?.lowercase() ?: "") in EXTS }
        }
        val psiManager = PsiManager.getInstance(project)
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            val isClient = ctx.isClient(relative)
            val isTest = isTestFile(relative)
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                collectFromFile(psi, relative, isClient, isTest, doc, ctx)
            }
        }
        LOG.info("ReactComponentCollector: ${ctx.components.size} components")
    }

    private fun collectFromFile(
        file: PsiFile,
        relative: String,
        isClient: Boolean,
        isTest: Boolean,
        doc: com.intellij.openapi.editor.Document?,
        ctx: NextjsContext,
    ) {
        val emittedNames = HashSet<String>()

        // Named `export function Foo()` / `export const Foo = () => …` where the
        // JSFunction itself carries the name (function declarations).
        for (fn in PsiTreeUtil.findChildrenOfType(file, JSFunction::class.java)) {
            val name = fn.name ?: continue
            if (!isTopLevel(fn)) continue
            if (!isExported(fn)) continue
            if (!rendersJsx(fn, name)) continue
            if (!emittedNames.add(name)) continue
            emit(fn, name, relative, isClient, isTest, doc, isArrow(fn), ctx)
        }

        // `export const Foo = () => …` — the arrow is the initializer, the name is on
        // the variable.
        for (v in PsiTreeUtil.findChildrenOfType(file, JSVariable::class.java)) {
            val name = v.name ?: continue
            if (!isTopLevel(v)) continue
            if (!isExported(v)) continue
            if (name in emittedNames) continue
            val init = v.initializerOrStub ?: continue
            // Only a function-valued `const Foo = (…) => …` / `= function …` can be a
            // component. Requiring a function initializer avoids false positives on
            // non-function PascalCase consts (config objects, lookup maps like `OP_META`,
            // `DEFAULT_WIDGETS`) whose body text happens to contain `<`/`</`/`/>`.
            val fnInit = when (init) {
                is JSFunction -> init
                is JSFunctionExpression -> init
                else -> null
            } ?: continue
            if (!rendersJsx(fnInit, name)) continue
            if (!emittedNames.add(name)) continue
            val fqn = "$relative::$name"
            ctx.components += ReactComponentData(
                fqn = fqn, name = name, filePath = relative,
                isDefaultExport = isDefaultExport(v), isClient = isClient, isServer = !isClient,
                kind = "arrow",
                lineStart = NextPsiUtil.lineNumber(doc, v.textRange.startOffset),
                lineEnd = NextPsiUtil.lineNumber(doc, v.textRange.endOffset),
                body = v.text.take(NextPsiUtil.MAX_BODY_CHARS), isTest = isTest,
            )
            val tags = fnInit?.let { NextPsiUtil.jsxTagNames(it) } ?: NextPsiUtil.jsxTagNames(v)
            ctx.renderSites += RenderSite(fqn, relative, tags)
        }
    }

    private fun emit(
        fn: JSFunction,
        name: String,
        relative: String,
        isClient: Boolean,
        isTest: Boolean,
        doc: com.intellij.openapi.editor.Document?,
        arrow: Boolean,
        ctx: NextjsContext,
    ) {
        val fqn = "$relative::$name"
        ctx.components += ReactComponentData(
            fqn = fqn, name = name, filePath = relative,
            isDefaultExport = isDefaultExport(fn), isClient = isClient, isServer = !isClient,
            kind = if (arrow) "arrow" else "function",
            lineStart = NextPsiUtil.lineNumber(doc, fn.textRange.startOffset),
            lineEnd = NextPsiUtil.lineNumber(doc, fn.textRange.endOffset),
            body = NextPsiUtil.bodyText(fn), isTest = isTest,
        )
        ctx.renderSites += RenderSite(fqn, relative, NextPsiUtil.jsxTagNames(fn))
    }

    private fun rendersJsx(fn: JSFunction, name: String): Boolean =
        NextPsiUtil.containsJsx(fn) ||
            (NextPsiUtil.isPascalCase(name) && JSX_TEXT_HINT.containsMatchIn(fn.text))

    private fun isArrow(fn: JSFunction): Boolean = try {
        fn.isArrowFunction
    } catch (_: Throwable) {
        false
    }

    private fun isTopLevel(element: PsiElement): Boolean {
        var parent: PsiElement? = element.parent
        while (parent != null && parent !is PsiFile) {
            if (parent is JSFunction && parent !== element) return false
            parent = parent.parent
        }
        return true
    }

    private fun isExported(element: PsiElement): Boolean {
        var cursor: PsiElement? = element
        while (cursor != null && cursor !is PsiFile) {
            val txt = cursor.text.orEmpty().trimStart()
            if (txt.startsWith("export ") || txt.startsWith("export\n") ||
                txt.startsWith("export{") || txt.startsWith("export*") ||
                txt.startsWith("export default ")
            ) return true
            cursor = cursor.parent
        }
        return false
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
