package com.onelens.plugin.framework.vue3

import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.onelens.plugin.framework.vue3.collectors.ApiCallCollector
import com.onelens.plugin.framework.vue3.collectors.ComposableCollector
import com.onelens.plugin.framework.vue3.collectors.LazyRouteCollector
import com.onelens.plugin.framework.vue3.collectors.PiniaStoreCollector
import com.onelens.plugin.framework.vue3.collectors.SfcScriptSetupCollector
import com.onelens.plugin.framework.vue3.resolver.CallThroughResolver
import com.onelens.plugin.framework.vue3.resolver.ModuleNameBinder
import java.nio.file.Paths

/**
 * End-to-end smoke tests for the three Week-2 collectors. Exercises the full path:
 * FileTypeIndex → PSI → data extraction → Vue3Context population. Not exhaustive —
 * deep prop/store shape tests belong next to each collector's test fixture.
 */
class Vue3CollectorsSmokeTest : BasePlatformTestCase() {

    override fun getTestDataPath(): String = "src/test/resources/vue-fixtures"

    override fun setUp() {
        super.setUp()
        // Copy every fixture into the test project so FileTypeIndex finds them.
        listOf(
            "SimpleProps.vue",
            "UsesComposable.vue",
            "ApiCalls.vue",
            "useCounter.js",
            "userStore.js",
            "ticket-routes.js",
            "config.js"
        ).forEach { myFixture.copyFileToProject(it) }
    }

    private fun ctx(): Vue3Context {
        val base = Paths.get(project.basePath ?: "/tmp")
        return Vue3Context(projectBase = base, aliases = emptyMap(), symlinks = emptyList())
    }

    fun testSfcCollectorFindsAllVueFiles() {
        val ctx = ctx()
        SfcScriptSetupCollector.collect(project, ctx)
        // Three .vue fixtures copied in — SimpleProps, UsesComposable, ApiCalls.
        assertEquals("expected 3 Component nodes", 3, ctx.components.size)

        val simpleProps = ctx.components.firstOrNull { it.name == "SimpleProps" }
        assertNotNull("SimpleProps component must be present", simpleProps)
        assertEquals(3, simpleProps!!.props.size)
        assertTrue("title prop must be captured", simpleProps.props.any { it.name == "title" })
        assertTrue("active prop must be required", simpleProps.props.first { it.name == "active" }.required)
        assertEquals(listOf("update", "close"), simpleProps.emits)
        assertEquals(listOf("reset"), simpleProps.exposes)
        assertTrue("script setup body captured", simpleProps.body?.contains("defineProps") == true)
    }

    fun testPiniaCollectorExtractsStore() {
        val ctx = ctx()
        PiniaStoreCollector.collect(project, ctx)
        assertEquals("userStore.js contains one defineStore", 1, ctx.stores.size)
        val store = ctx.stores[0]
        assertEquals("user", store.id)
        assertEquals("useUserStore", store.name)
        assertEquals("options", store.style)
        assertTrue("name state key captured", store.state.contains("name"))
        assertTrue("isLoggedIn getter captured", store.getters.contains("isLoggedIn"))
        assertTrue("fetchProfile action captured", store.actions.contains("fetchProfile"))
    }

    fun testRouteCollectorExpandsInterpolatedNames() {
        val ctx = ctx()
        LazyRouteCollector.collect(project, ctx)
        // 1 parent + 3 children = 4 routes in ticket-routes.js
        assertEquals(4, ctx.routes.size)

        // Interpolations from config.js must be substituted.
        assertTrue("route name uses resolved prefix",
            ctx.routes.any { it.name == "ticket" || it.name == "ticket.view" })

        val view = ctx.routes.first { it.name == "ticket.view" }
        assertEquals(":id", view.path)
        assertEquals("./views/view.vue", view.componentRef)
        assertNotNull("nested route must carry parent", view.parentName)

        // DISPATCHES edges emitted for every componentRef.
        assertTrue("dispatch edge for list-view emitted",
            ctx.dispatches.any { it.componentRef == "./views/list-view.vue" })
    }

    fun testApiCallCollectorExtractsLiteralAndTemplate() {
        val ctx = ctx()
        ApiCallCollector.collect(project, ctx)
        // ApiCalls.vue has two axios calls — one template (`/${moduleName}/...`) and one template with `${id}`.
        assertTrue("at least 2 ApiCall nodes", ctx.apiCalls.size >= 2)

        val templateOne = ctx.apiCalls.firstOrNull { it.path.contains("search/byqual") }
        assertNotNull("search/byqual call captured", templateOne)
        assertEquals("POST", templateOne!!.method)
        assertTrue("parametric flag set for template URL", templateOne.parametric)
        assertEquals("moduleName", templateOne.binding)

        val byId = ctx.apiCalls.firstOrNull { it.path.contains("\${id}") || it.path.contains("/tickets/") }
        assertNotNull("getById call captured", byId)
        assertEquals("GET", byId!!.method)

        // CALLS_API edge emitted per ApiCall.
        assertTrue("calls-api edges present", ctx.callsApi.size >= 2)
    }

    fun testModuleNameBinderResolvesLiteralConst() {
        val ctx = ctx()
        ApiCallCollector.collect(project, ctx)
        val beforeCount = ctx.apiCalls.size
        ModuleNameBinder.bind(project, ctx)
        // Binder adds a non-parametric variant for `const moduleName = 'tickets'`.
        assertTrue("binder should add at least one resolved variant", ctx.apiCalls.size > beforeCount)
        assertTrue("resolved literal path present",
            ctx.apiCalls.any { !it.parametric && it.path.contains("/tickets/search/byqual") })
    }

    fun testCallThroughResolverEmitsDirectAndIndirectEdges() {
        val ctx = ctx()
        SfcScriptSetupCollector.collect(project, ctx)
        PiniaStoreCollector.collect(project, ctx)
        ComposableCollector.collect(project, ctx)
        CallThroughResolver.collect(project, ctx)

        // UsesComposable.vue directly calls useUserStore → direct USES_STORE edge.
        assertTrue(
            "direct USES_STORE edge to user store from UsesComposable",
            ctx.usesStore.any { !it.indirect && it.storeId == "user" }
        )
        // UsesComposable.vue calls useCounter → USES_COMPOSABLE edge.
        assertTrue(
            "USES_COMPOSABLE edge to useCounter",
            ctx.usesComposable.any { it.composableFqn.endsWith("::useCounter") }
        )
    }

    fun testComposableCollectorFindsUseCounter() {
        val ctx = ctx()
        ComposableCollector.collect(project, ctx)
        // useCounter.js has one composable. userStore.js is filtered out
        // because it defines a Pinia store.
        assertTrue("useCounter must be detected", ctx.composables.any { it.name == "useCounter" })
        val useCounter = ctx.composables.first { it.name == "useCounter" }
        assertTrue("fqn includes file path + name", useCounter.fqn.endsWith("::useCounter"))
        assertTrue("body includes ref()", useCounter.body?.contains("ref(") == true)
    }
}
