package com.onelens.plugin.framework.vue3

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.Vue3Data
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.Collector
import com.onelens.plugin.framework.CollectorOutput
import com.onelens.plugin.framework.FrameworkAdapter
import com.onelens.plugin.framework.jscommon.ApiCallCollector
import com.onelens.plugin.framework.jscommon.JsModuleCollector
import com.onelens.plugin.framework.jscommon.ModuleNameBinder
import com.onelens.plugin.framework.jscommon.SymlinkResolver
import com.onelens.plugin.framework.jscommon.ViteAliasResolver
import com.onelens.plugin.framework.vue3.collectors.ComposableCollector
import com.onelens.plugin.framework.vue3.collectors.LazyRouteCollector
import com.onelens.plugin.framework.vue3.collectors.OptionsApiCollector
import com.onelens.plugin.framework.vue3.collectors.PiniaStoreCollector
import com.onelens.plugin.framework.vue3.collectors.SfcScriptSetupCollector
import com.onelens.plugin.framework.vue3.collectors.VuexStoreCollector
import com.onelens.plugin.framework.vue3.resolver.CallThroughResolver
import com.onelens.plugin.settings.OneLensSettings
import kotlinx.serialization.json.Json
import java.io.File
import java.nio.file.Paths

/**
 * Adapter for Vue 3 frontend projects. Detects via `package.json` — `dependencies.vue`
 * pinned to a `^3` / `~3` / `3.x.y` range.
 *
 * Phase B (in progress): collector list starts empty and fills in week by week.
 *   - Week 1: this skeleton + resolver infra (no collectors yet)
 *   - Week 2: SfcScriptSetupCollector, PiniaStoreCollector, ComposableCollector
 *   - Week 3: LazyRouteCollector, BaseModuleRouteCollector, ApiCallCollector
 *   - Week 4+: CallThroughResolver, ModuleNameBinder wiring
 */
class Vue3Adapter : FrameworkAdapter {
    override val id: String = "vue3"
    override val jsonKey: String = "vue3"

    override fun detect(project: Project): Boolean {
        val override = OneLensSettings.getInstance().vueAdapterEnabled
        if (override != null) return override
        return detectMajor(project) != null
    }

    /**
     * Detected Vue major version (2 or 3), or null when this is not a Vue project.
     *
     * Vue 2 and Vue 3 share one adapter: the SFC file type, the PSI tree, the
     * vue-router route-record shape and the ES module graph are the same, so
     * only the component and store collectors differ. The major picks which of
     * those two run — see [Vue3Collector.collect].
     *
     * On a mixed monorepo (one Vue 2 app + one Vue 3 app) **3 wins**, because
     * `ExportService` dispatches on a single `lastContext` and one export run
     * therefore has one active Vue context. Preferring 3 is not arbitrary: it
     * keeps a repo that exported as Vue 3 before this feature existing exporting
     * as Vue 3. Taking the first match instead would depend on
     * `File.listFiles()` order — unsorted, filesystem-dependent — so the same
     * repo could silently swap Pinia collection for Vuex on a different machine.
     * Export the apps as separate graphs to cover both properly.
     */
    fun detectMajor(project: Project): Int? {
        val base = project.basePath ?: return null
        val baseDir = File(base)
        val pkgJsons = buildList {
            add(File(baseDir, "package.json"))
            baseDir.listFiles()?.filter { it.isDirectory }?.sortedBy { it.name }?.forEach {
                add(File(it, "package.json"))
            }
        }
        val majors = pkgJsons.asSequence()
            .filter { it.exists() }
            .mapNotNull(::vueMajorOf)
            .toSet()
        return when {
            majors.isEmpty() -> null
            3 in majors -> 3
            else -> majors.min()
        }
    }

    /**
     * One composite collector drives a shared [Vue3Context]. Splitting into many small
     * [Collector]s for Vue would require each to re-enumerate `.vue` / `.js` files,
     * which is wasteful on a 1500+ file frontend. The sub-collector objects
     * (SfcScriptSetupCollector, PiniaStoreCollector, ComposableCollector) stay
     * independently testable.
     */
    override fun collectors(): List<Collector> = listOf(Vue3Collector())

    private fun vueMajorOf(pkg: File): Int? = try {
        vueMajorFromPackageJson(pkg.readText())
    } catch (_: Throwable) {
        null
    }

    companion object {
        private val LOG = logger<Vue3Adapter>()

        /**
         * Vue major declared in a `package.json`'s text, or null if absent.
         *
         * Cheap regex rather than a JSON parser so the probe stays fast on large
         * monorepos, where it runs once per package.json. Split out from the
         * file read so it is directly testable without a fixture.
         */
        fun vueMajorFromPackageJson(text: String): Int? =
            VUE_DEP_PATTERN.find(text)?.groupValues?.get(1)?.toIntOrNull()

        /**
         * Captures the Vue major. Covers the npm range forms seen in the wild
         * (`^2.6.14`, `~2.7.0`, `2.6.11`, `>=2.6.0`, `>= 3.0`) plus an optional
         * protocol prefix (`workspace:^2.6.14` in pnpm workspaces, `npm:2.7.16`).
         * The protocol case matters more than it looks: an unparsed range yields
         * null, and a null major falls back to 3 — silently running the Vue 3
         * collectors over a Vue 2 repo for an empty-graph result.
         *
         * Requires a following `.`, so a bare `"vue": "2"` is the only miss, and
         * `"latest"` / `"*"` / git URLs correctly yield null rather than a guess.
         */
        private val VUE_DEP_PATTERN = Regex(""""vue"\s*:\s*"(?:[a-z-]+:)?[\^~>=<\s]*([23])\.""")
    }
}

class Vue3Collector : Collector {
    override val id: String = "vue3.all"
    override val label: String = "Vue 3"

    var lastContext: Vue3Context? = null
        private set

    private val vueJson = Json { encodeDefaults = true }

    override fun collect(ctx: CollectContext): CollectorOutput {
        val project = ctx.project
        val workspace = ctx.workspace
        // Prefer workspace primary root so a multi-root config with a Vue app as the
        // second root still produces correct relative paths. Implicit single-root
        // workspace yields the same base as `project.basePath` did before.
        val base = workspace?.primaryRoot
            ?: project.basePath?.let(Paths::get)
            ?: return emptyOutput()

        val aliases = ViteAliasResolver.resolveFromBase(base)
        val symlinks = try {
            SymlinkResolver.scan(project)
        } catch (_: Throwable) {
            emptyList()
        }
        val vueMajor = Vue3Adapter().detectMajor(project) ?: 3
        val vueCtx = Vue3Context(
            projectBase = base,
            aliases = aliases,
            symlinks = symlinks,
            workspace = workspace,
            vueMajor = vueMajor,
        )
        lastContext = vueCtx

        val indicator = ctx.indicator
        val baseFraction = ctx.progressFraction
        val timings = StringBuilder()
        fun timed(label: String, fraction: Double, block: () -> Unit) {
            indicator?.text = "Vue 3: $label…"
            indicator?.fraction = fraction
            val start = System.nanoTime()
            block()
            val ms = (System.nanoTime() - start) / 1_000_000
            timings.append("  $label: ${ms}ms\n")
        }

        // `<script setup>` runs on BOTH majors — Vue 2.7 backported the macros,
        // so a 2.x repo can hold both styles. OptionsApiCollector then picks up
        // whatever is left; it skips any file with a `<script setup>` block, so
        // the two can never emit the same component twice.
        timed("components (.vue files)", baseFraction) {
            SfcScriptSetupCollector.collect(project, vueCtx)
            if (vueMajor == 2) OptionsApiCollector.collect(project, vueCtx)
        }
        timed(if (vueMajor == 2) "Vuex stores" else "Pinia stores", baseFraction + 0.15) {
            if (vueMajor == 2) {
                VuexStoreCollector.collect(project, vueCtx)
            } else {
                PiniaStoreCollector.collect(project, vueCtx)
            }
        }
        // Composables are a Vue 3 / 2.7-composition-api concept. On Vue 2 the
        // collector finds nothing in practice, but it is cheap and a 2.7 repo
        // using @vue/composition-api gets real results — so run it either way.
        timed("composables", baseFraction + 0.25) {
            ComposableCollector.collect(project, vueCtx)
        }
        timed("routes", baseFraction + 0.32) {
            LazyRouteCollector.collect(project, vueCtx)
        }
        timed("API calls", baseFraction + 0.40) {
            ApiCallCollector.collect(project, vueCtx)
        }
        timed("binding parametric URLs", baseFraction + 0.44) {
            ModuleNameBinder.bind(project, vueCtx)
        }
        // JsModuleCollector MUST run before CallThroughResolver: the Vue 2
        // component→helper→store hop reads `ctx.imports` to find which helper
        // module a component pulls its Vuex bindings from. Nothing in the module
        // collector depends on store/composable edges, so the swap is safe.
        timed("JS modules + functions + imports", baseFraction + 0.46) {
            JsModuleCollector.collect(project, vueCtx)
        }
        timed("store / composable edges (1-hop)", baseFraction + 0.48) {
            CallThroughResolver.collect(project, vueCtx)
        }

        // Log per-collector timings so export bottlenecks are visible without
        // a profiler. Goes to stderr (visible in headless run logs).
        System.err.println("[onelens] Vue$vueMajor collector timings:\n$timings")

        val snapshot: Vue3Data = vueCtx.snapshot()
        val nodeCount = snapshot.components.size + snapshot.composables.size +
            snapshot.stores.size + snapshot.routes.size + snapshot.apiCalls.size
        val edgeCount = snapshot.usesStore.size + snapshot.usesComposable.size +
            snapshot.dispatches.size + snapshot.callsApi.size

        val subdoc = vueJson.encodeToJsonElement(Vue3Data.serializer(), snapshot)
        return CollectorOutput(data = subdoc, nodeCount = nodeCount, edgeCount = edgeCount)
    }

    private fun emptyOutput(): CollectorOutput = CollectorOutput(
        data = kotlinx.serialization.json.JsonObject(emptyMap()),
        nodeCount = 0,
        edgeCount = 0
    )
}
