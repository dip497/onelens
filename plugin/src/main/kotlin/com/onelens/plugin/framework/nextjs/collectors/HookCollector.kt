package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSReferenceExpression
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
import com.onelens.plugin.export.CustomHookData
import com.onelens.plugin.export.HookData
import com.onelens.plugin.export.UsesHookEdge
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.isTestFile
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * Collects custom hook definitions (exported top-level `function useX` / `const useX =
 * () => …`) and `use*` call sites. Each distinct hook name → one [HookData] with an
 * `origin` of "custom" (matches a collected custom hook), "react" (builtin list), or
 * "library" (everything else). A [UsesHookEdge] links the enclosing
 * Page/Layout/ReactComponent/CustomHook to the Hook (skipped when there is no enclosing
 * symbol). Must run after the Route + Component collectors so the enclosing set exists.
 */
object HookCollector {
    private val LOG = logger<HookCollector>()

    private val EXTS = setOf("tsx", "jsx", "ts", "js")
    private val USE_RE = Regex("""^use[A-Z]""")
    private val REACT_HOOKS = setOf(
        "useState", "useEffect", "useMemo", "useCallback", "useRef", "useContext",
        "useReducer", "useLayoutEffect", "useTransition", "useId", "useOptimistic",
        "useActionState", "useFormStatus",
    )

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping hook collection — dumb mode")
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

        // Pass 1 — custom hook definitions.
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            val isTest = isTestFile(relative)
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                for (fn in PsiTreeUtil.findChildrenOfType(psi, JSFunction::class.java)) {
                    val name = NextPsiUtil.functionName(fn) ?: continue
                    if (!USE_RE.containsMatchIn(name)) continue
                    if (!NextPsiUtil.isTopLevel(fn)) continue
                    if (!NextPsiUtil.isExported(fn)) continue
                    val fqn = "$relative::$name"
                    if (ctx.customHooks.any { it.fqn == fqn }) continue
                    ctx.customHooks += CustomHookData(
                        fqn = fqn, name = name, filePath = relative,
                        isAsync = NextPsiUtil.isAsync(fn),
                        lineStart = NextPsiUtil.lineNumber(doc, fn.textRange.startOffset),
                        lineEnd = NextPsiUtil.lineNumber(doc, fn.textRange.endOffset),
                        body = if (isTest) null else NextPsiUtil.bodyText(fn),
                    )
                }
            }
        }

        // Enclosing-symbol set + custom-hook name set now that pass 1 is done.
        val enclosing = HashSet<String>().apply {
            ctx.pages.forEach { add(it.fqn) }
            ctx.layouts.forEach { add(it.fqn) }
            ctx.components.forEach { add(it.fqn) }
            ctx.customHooks.forEach { add(it.fqn) }
        }
        val customNames = ctx.customHooks.mapTo(HashSet()) { it.name }
        val hookOrigins = LinkedHashMap<String, String>() // name -> origin
        val seenEdges = HashSet<Pair<String, String>>()

        // Pass 2 — use* call sites.
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                for (call in PsiTreeUtil.findChildrenOfType(psi, JSCallExpression::class.java)) {
                    val callee = call.methodExpression as? JSReferenceExpression ?: continue
                    if (callee.qualifier != null) continue // only bare `useX(...)`
                    val name = callee.referenceName ?: continue
                    if (!USE_RE.containsMatchIn(name)) continue
                    hookOrigins.getOrPut(name) {
                        when {
                            name in customNames -> "custom"
                            name in REACT_HOOKS -> "react"
                            else -> "library"
                        }
                    }
                    val source = NextPsiUtil.enclosingSymbolFqn(call, relative, enclosing) ?: continue
                    if (seenEdges.add(source to name)) {
                        ctx.usesHook += UsesHookEdge(sourceFqn = source, hookName = name)
                    }
                }
            }
        }
        hookOrigins.forEach { (name, origin) -> ctx.hooks += HookData(name = name, origin = origin) }
        LOG.info(
            "HookCollector: customHooks=${ctx.customHooks.size}, hooks=${ctx.hooks.size}, " +
                "usesHook=${ctx.usesHook.size}"
        )
    }
}
