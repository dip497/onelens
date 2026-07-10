package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSVariable
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

    /** True when no JSFunction lies between [element] and the file — i.e. a module-level declaration. */
    fun isTopLevel(element: PsiElement): Boolean {
        var parent: PsiElement? = element.parent
        while (parent != null && parent !is com.intellij.psi.PsiFile) {
            if (parent is JSFunction && parent !== element) return false
            parent = parent.parent
        }
        return true
    }

    /** Textual `export …` probe up the ancestor chain (robust to JS-plugin PSI variations). */
    fun isExported(element: PsiElement): Boolean {
        var cursor: PsiElement? = element
        while (cursor != null && cursor !is com.intellij.psi.PsiFile) {
            val txt = cursor.text.orEmpty().trimStart()
            if (txt.startsWith("export ") || txt.startsWith("export\n") ||
                txt.startsWith("export{") || txt.startsWith("export*") ||
                txt.startsWith("export default ")
            ) return true
            cursor = cursor.parent
        }
        return false
    }

    /** Declared name of a function: its own name, else the name of the `const X = () => …` it initialises. */
    fun functionName(fn: JSFunction): String? =
        fn.name ?: PsiTreeUtil.getParentOfType(fn, JSVariable::class.java, true)?.name

    /**
     * Fqn ("<relative>::<name>") of the nearest enclosing declared symbol that is in
     * [known]. Walks up JSFunction / JSVariable ancestors; falls back to
     * "<relative>::default" when that is a known symbol (default-export page/component).
     */
    fun enclosingSymbolFqn(element: PsiElement, relative: String, known: Set<String>): String? {
        var cursor: PsiElement? = element.parent
        while (cursor != null) {
            val name = when (cursor) {
                is JSFunction -> functionName(cursor)
                is JSVariable -> cursor.name
                else -> null
            }
            if (name != null) {
                val fqn = "$relative::$name"
                if (fqn in known) return fqn
            }
            cursor = cursor.parent
        }
        return "$relative::default".takeIf { it in known }
    }

    /** Result of mapping an App-Router segment chain to a REST-style URL. */
    data class UrlResult(val urlPath: String, val paramNames: List<String>, val group: String?)

    /**
     * Maps App-Router directory segments (below `app/`) to a URL path. Route groups
     * `(group)` are stripped, parallel `@slot` segments dropped, `[param]` → `:param`,
     * `[...slug]`/`[[...slug]]` → `*slug`. Empty chain → "/". Shared by
     * [RouteTreeCollector] and [RouteHandlerCollector].
     */
    fun computeUrl(segments: List<String>): UrlResult {
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
}
