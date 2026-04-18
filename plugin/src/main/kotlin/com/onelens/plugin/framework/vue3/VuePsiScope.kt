package com.onelens.plugin.framework.vue3

import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil

/**
 * Returns the PSI roots a collector should traverse.
 *
 * `.vue` files embed `<script>` / `<script setup>` as `JSEmbeddedContent`
 * nodes. On stub-backed trees `PsiTreeUtil.findChildrenOfType(vueFile, …)`
 * silently misses declarations inside those blocks — a dogfood on a
 * 1500+ file Vue 3 repo produced zero imports / zero defineProps hits
 * before we switched to the Vue plugin's own entry point.
 *
 * Mirrors the pattern `org.jetbrains.vuejs.inspections.VueExtractComponentDataBuilder`
 * uses internally: `findModule(file, setup=true/false)` yields a
 * `JSExecutionScope` that stub-aware walks descend into correctly.
 *
 * For plain `.js` / `.ts` the file itself is the traversal root — same
 * as before.
 */
object VuePsiScope {
    fun scriptRoots(file: PsiFile): List<PsiElement> = try {
        if (file.javaClass.name == "org.jetbrains.vuejs.lang.html.VueFile") {
            val setup = org.jetbrains.vuejs.index.findModule(file, true)
            val normal = org.jetbrains.vuejs.index.findModule(file, false)
            listOfNotNull(setup, normal)
        } else {
            listOf(file)
        }
    } catch (_: Throwable) {
        listOf(file)
    }

    inline fun <reified T : PsiElement> findAll(file: PsiFile): List<T> =
        scriptRoots(file).flatMap { PsiTreeUtil.findChildrenOfType(it, T::class.java) }
}
