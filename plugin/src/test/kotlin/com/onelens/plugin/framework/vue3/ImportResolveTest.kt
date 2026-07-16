package com.onelens.plugin.framework.vue3

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.openapi.application.ReadAction
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Verifies that JSReferenceExpression.resolve() correctly navigates through:
 *   (c) barrel re-exports
 *   (d) Vue SFC <script setup> imports
 *   (e) namespace star imports (ns.alpha)
 *   (f) aliased imports (alpha as renamed)
 *
 * Pass criteria: every resolve() lands on the original `export function alpha`
 * declaration in a.js — NOT on a re-export specifier, NOT null.
 *
 * Failure modes are recorded as the actual resolved element type + text so the
 * caller can diagnose whether the resolver stops at a re-export node, a specifier,
 * or returns null.
 */
class ImportResolveTest : BasePlatformTestCase() {

    override fun getTestDataPath(): String = "src/test/resources/vue-fixtures"

    /**
     * Copy all fixture files that form the import chain into the test project so
     * the JS resolver can cross-reference them.
     */
    override fun setUp() {
        super.setUp()
        listOf("a.js", "b.js", "c.js", "d.vue", "e.js", "f.js").forEach {
            myFixture.copyFileToProject(it)
        }
    }

    // -------------------------------------------------------------------------
    // Case C: import { alpha } from './b' where b.js re-exports from a.js
    // -------------------------------------------------------------------------
    fun testCaseC_barrelReExportResolvesToOriginal() {
        val file = myFixture.configureByFile("c.js")
        val resolved = resolveFirstCall(file, "alpha")
        val verdict = describeResolution(resolved)
        assertTrue(
            "Case C (barrel re-export): expected JSFunction for 'alpha' in a.js, got: $verdict",
            resolved is JSFunction
        )
        val fnName = ReadAction.compute<String?, Throwable> { (resolved as JSFunction).name }
        assertEquals("Case C: resolved function name must be 'alpha'", "alpha", fnName)
    }

    // -------------------------------------------------------------------------
    // Case D: Vue SFC <script setup> import { alpha } from './a'; alpha()
    // -------------------------------------------------------------------------
    fun testCaseD_vueSfcScriptSetupResolvesToOriginal() {
        val file = myFixture.configureByFile("d.vue")
        val resolved = resolveFirstCall(file, "alpha")
        val verdict = describeResolution(resolved)
        assertTrue(
            "Case D (Vue SFC <script setup>): expected JSFunction for 'alpha' in a.js, got: $verdict",
            resolved is JSFunction
        )
        val fnName = ReadAction.compute<String?, Throwable> { (resolved as JSFunction).name }
        assertEquals("Case D: resolved function name must be 'alpha'", "alpha", fnName)
    }

    // -------------------------------------------------------------------------
    // Case E: import * as ns from './a'; ns.alpha()
    // The call is `ns.alpha()` — the reference is the qualifier `ns.alpha` whose
    // right-hand member `alpha` should resolve to the function in a.js.
    // -------------------------------------------------------------------------
    fun testCaseE_namespaceStarImportResolvesToOriginal() {
        val file = myFixture.configureByFile("e.js")
        // For ns.alpha() the callee text is "ns.alpha"; we look for a call whose
        // callee ends with ".alpha"
        val resolved = resolveCallByCalleeContains(file, "alpha")
        val verdict = describeResolution(resolved)
        assertTrue(
            "Case E (namespace star import ns.alpha): expected JSFunction for 'alpha' in a.js, got: $verdict",
            resolved is JSFunction
        )
        val fnName = ReadAction.compute<String?, Throwable> { (resolved as JSFunction).name }
        assertEquals("Case E: resolved function name must be 'alpha'", "alpha", fnName)
    }

    // -------------------------------------------------------------------------
    // Case F: import { alpha as renamed } from './a'; renamed()
    // -------------------------------------------------------------------------
    fun testCaseF_aliasedImportResolvesToOriginal() {
        val file = myFixture.configureByFile("f.js")
        val resolved = resolveFirstCall(file, "renamed")
        val verdict = describeResolution(resolved)
        assertTrue(
            "Case F (aliased import 'renamed'): expected JSFunction for 'alpha' in a.js, got: $verdict",
            resolved is JSFunction
        )
        val fnName = ReadAction.compute<String?, Throwable> { (resolved as JSFunction).name }
        assertEquals("Case F: resolved function name must be 'alpha'", "alpha", fnName)
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /**
     * Find the first JSCallExpression whose callee text equals [calleeName],
     * then resolve the callee reference and return the target PsiElement.
     */
    private fun resolveFirstCall(file: PsiFile, calleeName: String): PsiElement? {
        return ReadAction.compute<PsiElement?, Throwable> {
            val call = PsiTreeUtil.findChildrenOfType(file, JSCallExpression::class.java)
                .firstOrNull { it.methodExpression?.text == calleeName }
                ?: return@compute null
            call.methodExpression?.reference?.resolve()
        }
    }

    /**
     * Like resolveFirstCall but matches callee text that *contains* [fragment].
     * Used for ns.alpha() where the callee text is "ns.alpha".
     */
    private fun resolveCallByCalleeContains(file: PsiFile, fragment: String): PsiElement? {
        return ReadAction.compute<PsiElement?, Throwable> {
            val call = PsiTreeUtil.findChildrenOfType(file, JSCallExpression::class.java)
                .firstOrNull { it.methodExpression?.text?.contains(fragment) == true }
                ?: return@compute null
            call.methodExpression?.reference?.resolve()
        }
    }

    /** Returns a short human-readable description of a nullable PsiElement for error messages. */
    private fun describeResolution(element: PsiElement?): String {
        if (element == null) return "null"
        return ReadAction.compute<String, Throwable> {
            "${element.javaClass.simpleName}(text=${element.text.take(60)})"
        }
    }
}
