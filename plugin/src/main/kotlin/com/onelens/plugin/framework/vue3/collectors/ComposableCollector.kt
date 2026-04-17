package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReturnStatement
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
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
        val files = jsTypes.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
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

        // Two shapes to pick up: named function decls, and `const useX = (...) => {...}`.
        val functions = PsiTreeUtil.findChildrenOfType(file, JSFunction::class.java)
            .filter { it.name?.matches(COMPOSABLE_NAME) == true }

        for (fn in functions) {
            val name = fn.name ?: continue
            // Enforce "returns something" — at least one ReturnStatement OR an arrow
            // function expression body.
            val returns = PsiTreeUtil.findChildrenOfType(fn, JSReturnStatement::class.java)
            val isArrowWithExpressionBody = fn.text.contains("=>") && !fn.text.contains("=> {")
            if (returns.isEmpty() && !isArrowWithExpressionBody) continue

            out += ComposableData(
                name = name,
                fqn = "$relative::$name",
                filePath = relative,
                body = fn.text.take(MAX_BODY_CHARS)
            )
        }

        // Also pick up `const useX = defineHookLike(...)` that the JSFunction scan misses
        // because the RHS isn't a JSFunction (it's a call returning one). Cheap scan:
        // look for top-level JSVariable whose name matches and whose value is a call.
        val vars = PsiTreeUtil.findChildrenOfType(file, JSVariable::class.java)
            .filter { it.name?.matches(COMPOSABLE_NAME) == true }
        for (v in vars) {
            val name = v.name ?: continue
            // Already captured as a JSFunction? Skip duplicates.
            if (out.any { it.name == name }) continue
            val value = v.initializerOrStub as? com.intellij.psi.PsiElement ?: continue
            // Value must be a call — otherwise it's likely a plain store import reference.
            if (value !is JSCallExpression && value !is JSObjectLiteralExpression) continue
            out += ComposableData(
                name = name,
                fqn = "$relative::$name",
                filePath = relative,
                body = v.text.take(MAX_BODY_CHARS)
            )
        }

        return out
    }
}
