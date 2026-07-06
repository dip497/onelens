package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSXmlLiteralExpression
import com.intellij.openapi.editor.Document
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil

/**
 * Small PSI helpers shared by [RouteTreeCollector] and [ReactComponentCollector].
 * All calls assume they run inside a ReadAction.
 */
internal object NextPsiUtil {
    const val MAX_BODY_CHARS = 2000

    /** 1-based line number for [offset], or 0 when unavailable. */
    fun lineNumber(doc: Document?, offset: Int): Int {
        if (doc == null) return 0
        if (offset < 0 || offset > doc.textLength) return 0
        return doc.getLineNumber(offset) + 1
    }

    /** True when [element]'s subtree contains at least one JSX element / fragment. */
    fun containsJsx(element: PsiElement): Boolean =
        PsiTreeUtil.findChildOfType(element, JSXmlLiteralExpression::class.java) != null

    /** True when [element] itself is or renders JSX (walks up to a JSFunction is caller's job). */
    fun isPascalCase(name: String): Boolean =
        name.isNotEmpty() && name[0].isUpperCase() && name.all { it.isLetterOrDigit() || it == '_' }

    private val JSX_TAG_RE = Regex("""<([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?)""")

    /**
     * PascalCase JSX element identifiers rendered anywhere in [element]'s subtree.
     * `<Foo>` → "Foo"; member tags `<Foo.Bar>` reduce to the head "Foo" (the imported
     * binding). Lowercase/DOM tags (`<div>`, `<span>`) are dropped.
     *
     * Uses the JSX PSI ([JSXmlLiteralExpression]) when available and ALSO a textual
     * scan of the element source — on some platform/stub states the JSX PSI is elided
     * (the same reason [ReactComponentCollector] keeps a textual detection fallback), and
     * a PSI-only tag walk then silently yields zero `RENDERS` edges.
     */
    fun jsxTagNames(element: PsiElement): Set<String> {
        val out = LinkedHashSet<String>()
        for (jsx in PsiTreeUtil.findChildrenOfType(element, JSXmlLiteralExpression::class.java)) {
            val head = jsx.name?.substringBefore('.')?.trim() ?: continue
            if (isPascalCase(head)) out += head
        }
        for (m in JSX_TAG_RE.findAll(element.text)) {
            val head = m.groupValues[1].substringBefore('.').trim()
            if (isPascalCase(head)) out += head
        }
        return out
    }

    /** `async` modifier of a JSFunction, robust to arrow / expression forms. */
    fun isAsync(fn: JSFunction): Boolean =
        fn.text.substringBefore("(").contains("async") || fn.isAsync

    /** Function source text, truncated to [MAX_BODY_CHARS]. */
    fun bodyText(fn: JSFunction): String = fn.text.take(MAX_BODY_CHARS)
}
