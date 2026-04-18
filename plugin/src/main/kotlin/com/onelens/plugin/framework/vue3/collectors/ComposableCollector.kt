package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReturnStatement
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.util.Computable
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.ComposableData
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Detects Vue composables via the `useX` naming convention. A composable is:
 *   1. A function whose name starts with `use` followed by an uppercase letter
 *      (`useUser`, `useNotifications`) — this excludes `user(...)` / `used(...)`.
 *   2. Defined at module scope (top-level `function useX()` or `const useX = ...`).
 *   3. Returns something — an object literal, a ref, or a tuple. No-return functions
 *      aren't composables in the Vue sense.
 *
 * The collector intentionally does NOT try to validate "returns refs/computed" deeply;
 * false positives are preferable to missing real composables. The graph reader can
 * inspect the body text if ranking matters.
 *
 * Pinia stores (also `useXStore`) are emitted separately by [PiniaStoreCollector] and
 * excluded here via a simple filename probe — if the file contains `defineStore`, the
 * export is considered a store, not a composable.
 */
object ComposableCollector {
    private val LOG = logger<ComposableCollector>()
    private const val MAX_BODY_CHARS = 2000
    private val COMPOSABLE_NAME = Regex("""^use[A-Z]\w*$""")

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping Composable collection — dumb mode")
            return
        }
        val ftm = FileTypeManager.getInstance()
        val jsTypes = listOfNotNull(
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("mjs").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = GlobalSearchScope.projectScope(project)
        val files = DumbService.getInstance(project).runReadActionInSmartMode(
            Computable { jsTypes.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        )
        val psiManager = PsiManager.getInstance(project)

        for (vf in files) {
            ProgressManager.checkCanceled()
            val composables = ReadAction.compute<List<ComposableData>, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute emptyList()
                // Skip files that define Pinia stores — [PiniaStoreCollector] owns them.
                if (psi.text.contains("defineStore(")) return@compute emptyList()
                extract(psi, ctx)
            }
            ctx.composables += composables
        }
        LOG.info("ComposableCollector: ${ctx.composables.size} composables")
    }

    private fun extract(file: PsiFile, ctx: Vue3Context): List<ComposableData> {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val out = mutableListOf<ComposableData>()
        val seen = mutableSetOf<String>()

        // Two shapes to pick up: named function decls, and `const useX = (...) => {...}`.
        //
        // Stub trees on `.vue` / imported `.js` files expose JSFunction children for
        // every `useX` CALL target the resolver can reach, not just locally declared
        // functions. A dogfood on a 1500+ component repo produced 378 copies of
        // `useI18n` — one per file that *uses* it — because `PsiTreeUtil`/`findAll`
        // collected phantom function stubs from the stub index. Structural
        // gating below restricts emission to actual declarations in THIS file:
        //   1. The function's containingFile must equal `file` (no cross-file
        //      stub phantoms).
        //   2. Its parent chain must terminate at the file (top-level),
        //      optionally through an export statement or a `const ... =` variable.
        //   3. It must have a materialized body block or an expression body
        //      (stub-only references return null for `block`).
        val functions = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSFunction>(file)
            .filter { it.name?.matches(COMPOSABLE_NAME) == true }

        for (fn in functions) {
            val name = fn.name ?: continue
            if (!isLocalTopLevelDecl(fn, file)) continue
            // Enforce "returns something" — at least one ReturnStatement OR an arrow
            // function expression body.
            val returns = PsiTreeUtil.findChildrenOfType(fn, JSReturnStatement::class.java)
            val isArrowWithExpressionBody = fn.text.contains("=>") && !fn.text.contains("=> {")
            if (returns.isEmpty() && !isArrowWithExpressionBody) continue
            if (!seen.add(name)) continue
            out += ComposableData(
                name = name,
                fqn = "$relative::$name",
                filePath = relative,
                body = fn.text.take(MAX_BODY_CHARS)
            )
        }

        // Also pick up `const useX = defineHookLike(...)` that the JSFunction scan
        // misses because the RHS isn't a JSFunction. Same structural gate: the
        // JSVariable itself must be local and top-level; its value must be a call
        // or object literal (rules out `const useI18n = useI18n` re-exports that
        // would otherwise show up here once per importing file).
        val vars = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSVariable>(file)
            .filter { it.name?.matches(COMPOSABLE_NAME) == true }
        for (v in vars) {
            val name = v.name ?: continue
            if (name in seen) continue
            if (!isLocalTopLevelDecl(v, file)) continue
            val value = v.initializerOrStub as? com.intellij.psi.PsiElement ?: continue
            if (value !is JSCallExpression && value !is JSObjectLiteralExpression) continue
            seen += name
            out += ComposableData(
                name = name,
                fqn = "$relative::$name",
                filePath = relative,
                body = v.text.take(MAX_BODY_CHARS)
            )
        }

        return out
    }

    /**
     * Structural gate matching the JsModuleCollector convention. An element is a
     * local top-level declaration only when:
     *
     * - Its `containingFile` is exactly [file] (guards against stub phantoms
     *   pulled in via the cross-file stub index — which was the source of the
     *   `useI18n × 378` explosion).
     * - Its enclosing-function ancestor chain is empty up to the file (nested
     *   helpers inside another function are private, not module exports).
     */
    private fun isLocalTopLevelDecl(
        element: com.intellij.psi.PsiElement,
        file: PsiFile
    ): Boolean {
        if (element.containingFile?.virtualFile?.path != file.virtualFile?.path) return false
        var parent: com.intellij.psi.PsiElement? = element.parent
        while (parent != null && parent !is PsiFile) {
            if (parent is JSFunction && parent !== element) return false
            parent = parent.parent
        }
        return true
    }
}
