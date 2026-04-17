package com.onelens.plugin.framework.vue3

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.openapi.application.ReadAction
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * Phase 0 PoC — verify `org.jetbrains.plugins.vue` exposes PSI access sufficient
 * to extract component props, emits, composable returns, and Pinia store shape.
 * Pass criteria: each assertion succeeds against a fixture SFC.
 *
 * This is not a finished collector; it probes APIs we plan to rely on in Phase B.
 * A failure here means the Vue plugin hides what we need and we must pivot to the
 * regex/JS-AST fallback documented in the plan.
 */
class VuePsiPoCTest : BasePlatformTestCase() {

    override fun getTestDataPath(): String = "src/test/resources/vue-fixtures"

    /**
     * Minimum viable probe: open a .vue file, find the <script setup> embedded JS,
     * locate the `defineProps` call and its argument literal.
     */
    fun testDefinePropsIsCallable() {
        val file = myFixture.configureByFile("SimpleProps.vue")
        val defineProps = findCall(file, "defineProps")
        assertNotNull("defineProps call must be resolvable via JSCallExpression walk", defineProps)
        val argText = defineProps!!.argumentList?.arguments?.firstOrNull()?.text.orEmpty()
        assertTrue("defineProps arg should contain prop names", argText.contains("title"))
        assertTrue(argText.contains("count"))
        assertTrue(argText.contains("active"))
    }

    fun testDefineEmitsIsCallable() {
        val file = myFixture.configureByFile("SimpleProps.vue")
        val defineEmits = findCall(file, "defineEmits")
        assertNotNull("defineEmits call must be resolvable", defineEmits)
        val argText = defineEmits!!.argumentList?.arguments?.firstOrNull()?.text.orEmpty()
        assertTrue("emits should list 'update'", argText.contains("update"))
        assertTrue("emits should list 'close'", argText.contains("close"))
    }

    fun testDefineExposeIsCallable() {
        val file = myFixture.configureByFile("SimpleProps.vue")
        val defineExpose = findCall(file, "defineExpose")
        assertNotNull("defineExpose call must be resolvable", defineExpose)
    }

    /**
     * Cross-file resolution: component imports a composable; does PSI resolve the
     * call-site to the function definition in the other file?
     */
    fun testComposableImportResolves() {
        myFixture.copyFileToProject("useCounter.js")
        myFixture.copyFileToProject("userStore.js")
        val file = myFixture.configureByFile("UsesComposable.vue")
        val useCounterCall = findCall(file, "useCounter")
        assertNotNull("useCounter() call must exist", useCounterCall)
        val resolved = useCounterCall!!.methodExpression?.reference?.resolve()
        assertNotNull("useCounter should resolve to its definition in useCounter.js", resolved)
        assertTrue("resolved target should be a function", resolved is JSFunction)
    }

    fun testPiniaDefineStoreShape() {
        myFixture.copyFileToProject("useCounter.js")
        val file = myFixture.configureByFile("userStore.js")
        val defineStoreCall = findCall(file, "defineStore")
        assertNotNull("defineStore call must be locatable", defineStoreCall)
        val args = defineStoreCall!!.argumentList?.arguments.orEmpty()
        assertTrue("defineStore must have >= 2 args (id, options)", args.size >= 2)
        val idText = args[0].text
        assertTrue("first arg is the store id literal 'user'", idText.contains("user"))
    }

    /**
     * Template-string URL extraction feasibility — can we detect axios.post and the
     * template path it receives? This underpins ApiCallCollector.
     */
    fun testAxiosCallIsWalkable() {
        val file = myFixture.configureByFile("ApiCalls.vue")
        val post = findCall(file, "post")
        assertNotNull("axios.post call present", post)
        val firstArgText = post!!.argumentList?.arguments?.firstOrNull()?.text.orEmpty()
        assertTrue(
            "first arg should be a template string containing /${'$'}{moduleName}/search",
            firstArgText.contains("moduleName") && firstArgText.contains("search/byqual")
        )
    }

    private fun findCall(file: PsiFile, calleeName: String): JSCallExpression? {
        return ReadAction.compute<JSCallExpression?, Throwable> {
            PsiTreeUtil.findChildrenOfType(file, JSCallExpression::class.java)
                .firstOrNull { call ->
                    val callee = call.methodExpression?.text.orEmpty()
                    callee == calleeName || callee.endsWith(".$calleeName")
                }
        }
    }
}
