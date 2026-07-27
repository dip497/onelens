package com.onelens.plugin.framework.vue3

import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.onelens.plugin.framework.vue3.collectors.OptionsApiCollector
import com.onelens.plugin.framework.vue3.collectors.SfcScriptSetupCollector
import com.onelens.plugin.framework.vue3.collectors.VuexStoreCollector
import com.onelens.plugin.framework.vue3.resolver.CallThroughResolver
import java.nio.file.Paths

/**
 * Real-PSI tests for the Vue 2 path: FileTypeIndex → PSI → data extraction.
 *
 * The pure-logic suite ([Vue2PureLogicTest]) pins the regexes; this one pins the
 * thing regexes cannot prove — that the IntelliJ Vue plugin actually parses a
 * Vue 2 Options-API SFC into the PSI shapes the collectors walk.
 */
class Vue2CollectorsSmokeTest : BasePlatformTestCase() {

    override fun getTestDataPath(): String = "src/test/resources/vue-fixtures"

    override fun setUp() {
        super.setUp()
        listOf(
            "vue2/OptionsCard.vue",
            "vue2/Hybrid.vue",
            "vue2/store/user/index.js",
            "vue2/store/settings.js",
        ).forEach { myFixture.copyFileToProject(it) }
    }

    private fun ctx(major: Int = 2): Vue3Context = Vue3Context(
        projectBase = Paths.get(project.basePath ?: "/tmp"),
        aliases = emptyMap(),
        symlinks = emptyList(),
        workspace = com.onelens.plugin.framework.workspace.WorkspaceLoader.load(project),
        vueMajor = major,
    )

    fun testOptionsApiComponentIsExtracted() {
        val ctx = ctx()
        OptionsApiCollector.collect(project, ctx)

        val card = ctx.components.firstOrNull { it.name == "UserCard" }
        assertNotNull("Options-API component must be collected — this is the whole Vue 2 gap", card)
        // `name:` option wins over the filename (OptionsCard.vue → UserCard).
        assertEquals("UserCard", card!!.name)
        assertFalse("Options API is not script-setup", card.scriptSetup)
        assertTrue("fqn is filePath::name", card.fqn.endsWith("OptionsCard.vue::UserCard"))

        // Props share the Vue 3 parser — object form with type/required/default.
        assertEquals(3, card.props.size)
        assertTrue("title prop captured", card.props.any { it.name == "title" })
        assertTrue("active must be required", card.props.first { it.name == "active" }.required)
        assertEquals("0", card.props.first { it.name == "count" }.defaultValue)

        // Vue 2.6 has no `emits` option — the $emit call sites are the declaration.
        assertEquals(listOf("save", "close"), card.emits)

        assertEquals(listOf("formMixin", "tableMixin"), card.mixins)
        assertTrue("script body captured for embedding", card.body?.contains("mapActions") == true)
    }

    fun testScriptSetupFileIsNotDoubleCollectedOnVue2() {
        // Vue 2.7 repos hold both styles. SfcScriptSetupCollector claims the
        // `<script setup>` file; OptionsApiCollector must skip it, or the
        // importer MERGEs two nodes onto one fqn and one silently wins.
        val ctx = ctx()
        SfcScriptSetupCollector.collect(project, ctx)
        val afterSfc = ctx.components.size
        assertTrue("script-setup fixture must be collected", ctx.components.any { it.name == "Hybrid" })

        OptionsApiCollector.collect(project, ctx)

        assertEquals(
            "Hybrid.vue must appear exactly once",
            1, ctx.components.count { it.name == "Hybrid" }
        )
        assertTrue("Options pass still adds UserCard", ctx.components.size > afterSfc)
        assertEquals(
            "no duplicate fqns across the two collectors",
            ctx.components.size, ctx.components.map { it.fqn }.toSet().size
        )
    }

    fun testVuexModuleIsExtracted() {
        val ctx = ctx()
        VuexStoreCollector.collect(project, ctx)

        val store = ctx.stores.firstOrNull { it.name == "user" }
        assertNotNull("namespaced Vuex module must be collected", store)
        assertEquals("vuex", store!!.style)
        assertTrue("fqn is filePath::name", store.fqn.endsWith("index.js::user"))

        // `state: () => ({…})` factory must be unwrapped, not read as a function.
        assertTrue("state keys unwrapped from factory", store.state.contains("profile"))
        assertTrue("token state key", store.state.contains("token"))
        assertTrue("getter captured", store.getters.contains("isLoggedIn"))
        assertTrue("action captured", store.actions.contains("fetchProfile"))
        // Mutations are Vuex-only — Pinia dropped them, so this field is the
        // one piece of the Vuex shape with no Vue 3 counterpart.
        assertTrue("mutation captured", store.mutations.contains("SET_PROFILE"))
        assertTrue("second mutation captured", store.mutations.contains("SET_TOKEN"))
    }

    fun testNonStoreFileInStoreDirIsRejectedOnShape() {
        // Residence in store/ only makes a file a CANDIDATE. Accepting on
        // location alone would emit junk Store nodes for every config file.
        val ctx = ctx()
        VuexStoreCollector.collect(project, ctx)
        assertNull(
            "settings.js declares one weak section and must not be a Store",
            ctx.stores.firstOrNull { it.filePath.endsWith("settings.js") }
        )
    }

    fun testMapHelpersEmitUsesStoreEdges() {
        val ctx = ctx()
        OptionsApiCollector.collect(project, ctx)
        VuexStoreCollector.collect(project, ctx)
        CallThroughResolver.collect(project, ctx)

        // `...mapState('user', […])` / `...mapActions('user', […])` in UserCard
        // resolve to the `user` namespace — Vue 2's equivalent of useXStore().
        val edge = ctx.usesStore.firstOrNull { it.storeId == "user" }
        assertNotNull("mapState/mapActions must produce a USES_STORE edge", edge)
        assertTrue("edge points at the fqn-keyed store", edge!!.storeFqn.endsWith("index.js::user"))
        assertFalse("map helpers are a direct use", edge.indirect)
        assertTrue("caller is the component", edge.callerFqn.contains("UserCard"))
    }
}
