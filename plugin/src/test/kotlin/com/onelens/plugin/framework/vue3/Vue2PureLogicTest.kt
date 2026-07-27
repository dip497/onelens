package com.onelens.plugin.framework.vue3

import com.onelens.plugin.framework.vue3.collectors.VuexStoreCollector
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Pure-logic tests for the Vue 2 path — no IntelliJ platform fixture, so they run
 * in ~1 s instead of the ~45 s a `BasePlatformTestCase` costs.
 *
 * These pin the two decisions that are easy to get silently wrong: which major a
 * `package.json` declares (a wrong answer runs the wrong collectors and yields an
 * empty graph) and how a Vuex file path becomes a namespace (a wrong answer
 * collapses distinct stores onto one node).
 */
class Vue2PureLogicTest {

    // --- version detection -------------------------------------------------

    private fun pkg(vueRange: String) = """{"dependencies":{"vue":"$vueRange"}}"""

    @Test
    fun `detects vue 2 across the npm range forms seen in the wild`() {
        listOf("^2.6.14", "~2.7.0", "2.6.11", ">=2.6.0", ">= 2.7.14", "2.7.x").forEach {
            assertEquals("range '$it' must read as Vue 2", 2, major(pkg(it)))
        }
    }

    @Test
    fun `detects vue 3 unchanged`() {
        listOf("^3.4.0", "~3.0.11", "3.5.32", ">=3.2.0").forEach {
            assertEquals("range '$it' must read as Vue 3", 3, major(pkg(it)))
        }
    }

    @Test
    fun `unparseable or absent vue dependency yields null, never a guessed major`() {
        // A wrong major is worse than no detection: it runs the wrong collectors
        // and produces an empty component graph that still exits 0.
        assertNull("no vue dep", major("""{"dependencies":{"react":"^18.0.0"}}"""))
        assertNull("dist-tag", major(pkg("latest")))
        assertNull("wildcard", major(pkg("*")))
        assertNull("git url", major(pkg("github:vuejs/vue")))
        assertNull("empty file", major(""))
    }

    @Test
    fun `vue-adjacent packages do not decide the major`() {
        // "@vue/compat": "^3" ships in Vue 2→3 migration builds alongside a real
        // Vue 2 dep; matching on it would flip the whole export to the Vue 3
        // collectors. The pattern is anchored to the exact "vue" key.
        val migrating = """{"dependencies":{"vue":"^2.7.14","@vue/compat":"^3.2.0"}}"""
        assertEquals(2, major(migrating))
    }

    @Test
    fun `mixed monorepo prefers Vue 3 so a working Vue 3 export never downgrades`() {
        // Regression: detection used to be `any { looksLikeVue3 }`, so a repo with a
        // Vue 3 app anywhere exported as Vue 3. Taking the FIRST match instead made
        // the answer depend on File.listFiles() order — unsorted and filesystem
        // dependent — so the same monorepo could silently swap Pinia collection for
        // Vuex on another machine, dropping every Pinia store.
        val majors = setOf(2, 3)
        assertEquals("3 must win when both are present", 3, pick(majors))
        assertEquals(2, pick(setOf(2)))
        assertEquals(3, pick(setOf(3)))
    }

    /** Mirrors the selection rule in `Vue3Adapter.detectMajor`. */
    private fun pick(majors: Set<Int>): Int? = when {
        majors.isEmpty() -> null
        3 in majors -> 3
        else -> majors.min()
    }

    @Test
    fun `protocol-prefixed ranges resolve, because a null major silently runs Vue 3`() {
        // Regression: `detectMajor() ?: 3` means an unparsed range does not fail —
        // it runs the Vue 3 collectors over a Vue 2 repo and yields an empty graph.
        // pnpm workspaces and npm aliases are common enough to hit this.
        assertEquals(2, major(pkg("workspace:^2.6.14")))
        assertEquals(3, major(pkg("workspace:^3.4.0")))
        assertEquals(2, major(pkg("npm:2.7.16")))
    }

    private fun major(text: String) = Vue3Adapter.vueMajorFromPackageJson(text)

    // --- Vuex namespace derivation ----------------------------------------

    @Test
    fun `vuex module name mirrors the directory namespace`() {
        assertEquals("user", name("src/store/user/index.js"))
        assertEquals("admin/roles", name("src/store/admin/roles.js"))
        assertEquals("tickets", name("src/store/tickets.js"))
        assertEquals("root", name("src/store/index.js"))
    }

    @Test
    fun `plural stores directory is treated the same as singular`() {
        assertEquals("user", name("src/stores/user/index.js"))
    }

    @Test
    fun `same-named modules in different directories stay distinct`() {
        // This is the whole reason Store merges on fqn rather than name. Vuex
        // namespaces are directory-derived, so "user" is a near-guaranteed
        // collision across features.
        val a = name("src/store/user/index.js")
        val b = name("src/store/admin/user.js")
        assertEquals("user", a)
        assertEquals("admin/user", b)
        // Distinct namespaces AND distinct fqns downstream.
        assert(a != b) { "namespaces must differ, else the two stores collapse" }
    }

    @Test
    fun `typescript and mjs store modules resolve the same as js`() {
        assertEquals("user", name("src/store/user/index.ts"))
        assertEquals("cart", name("src/store/cart.mjs"))
    }

    @Test
    fun `generic module filenames name themselves after their directory`() {
        // Regression: a real 2100-SFC Vue 2 codebase keeps all 44 Vuex modules at
        // `state/modules/<ns>/module.js`. Falling back to the filename named every
        // one of them the literal string "module", which collapsed all 44
        // namespaces into one and produced zero USES_STORE edges.
        assertEquals("user-group", name("src/state/modules/user-group/module.js"))
        assertEquals("location", name("src/state/modules/location/module.js"))
        assertEquals("user-group/technician", name("src/state/modules/user-group/technician/module.js"))
    }

    @Test
    fun `the last store marker anchors the namespace, not the first`() {
        // `src/state/modules/…` contains BOTH `state/` and `modules/`. Anchoring on
        // the first would yield "modules/location" instead of "location".
        assertEquals("location", name("src/state/modules/location/module.js"))
    }

    @Test
    fun `namespace lookup survives kebab vs camel drift`() {
        // Directories are kebab-case, registered namespaces are camelCase
        // (`user-group/` → `createNamespacedHelpers('userGroup')`). Comparing raw
        // strings misses every store; the normalised key must match.
        val fromDirectory = VuexStoreCollector.namespaceKey("user-group")
        val fromCallSite = VuexStoreCollector.namespaceKey("userGroup")
        assertEquals("kebab dir must match camel namespace", fromDirectory, fromCallSite)

        assertEquals(
            "nested namespaces normalise per segment",
            VuexStoreCollector.namespaceKey("user-group/technician"),
            VuexStoreCollector.namespaceKey("userGroup/technician"),
        )
        // Distinct namespaces must still NOT collide after normalisation.
        assert(VuexStoreCollector.namespaceKey("userGroup") != VuexStoreCollector.namespaceKey("userGroups"))
    }

    private fun name(path: String) = VuexStoreCollector.moduleName(path)
}
