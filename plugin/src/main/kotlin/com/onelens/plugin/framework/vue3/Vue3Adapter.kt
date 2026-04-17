package com.onelens.plugin.framework.vue3

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.Vue3Data
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.Collector
import com.onelens.plugin.framework.CollectorOutput
import com.onelens.plugin.framework.FrameworkAdapter
import com.onelens.plugin.framework.vue3.collectors.ApiCallCollector
import com.onelens.plugin.framework.vue3.collectors.ComposableCollector
import com.onelens.plugin.framework.vue3.collectors.LazyRouteCollector
import com.onelens.plugin.framework.vue3.collectors.PiniaStoreCollector
import com.onelens.plugin.framework.vue3.collectors.SfcScriptSetupCollector
import com.onelens.plugin.framework.vue3.resolver.CallThroughResolver
import com.onelens.plugin.framework.vue3.resolver.ModuleNameBinder
import com.onelens.plugin.framework.vue3.resolver.SymlinkResolver
import com.onelens.plugin.framework.vue3.resolver.ViteAliasResolver
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

        val base = project.basePath ?: return false
        val baseDir = File(base)
        val pkgJsons = buildList {
            add(File(baseDir, "package.json"))
            baseDir.listFiles()?.filter { it.isDirectory }?.forEach {
                add(File(it, "package.json"))
            }
        }
        return pkgJsons.any { it.exists() && looksLikeVue3(it) }
    }

    /**
     * One composite collector drives a shared [Vue3Context]. Splitting into many small
     * [Collector]s for Vue would require each to re-enumerate `.vue` / `.js` files,
     * which is wasteful on a 1500+ file frontend. The sub-collector objects
     * (SfcScriptSetupCollector, PiniaStoreCollector, ComposableCollector) stay
     * independently testable.
     */
    override fun collectors(): List<Collector> = listOf(Vue3Collector())

    private fun looksLikeVue3(pkg: File): Boolean = try {
        // Cheap regex over package.json — avoid a JSON parser here so the probe stays
        // fast on large monorepos. Matches `"vue": "^3…" | "~3…" | "3.x"` inside either
        // dependencies or devDependencies.
        VUE_DEP_PATTERN.containsMatchIn(pkg.readText())
    } catch (_: Throwable) {
        false
    }

    companion object {
        private val LOG = logger<Vue3Adapter>()
        private val VUE_DEP_PATTERN = Regex(""""vue"\s*:\s*"[\^~]?3(\.\d|\.\w+)""")
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
        val base = project.basePath?.let(Paths::get) ?: return emptyOutput()

        val aliases = ViteAliasResolver.resolveFromBase(base)
        val symlinks = try {
            SymlinkResolver.scan(project)
        } catch (_: Throwable) {
            emptyList()
        }
        val vueCtx = Vue3Context(projectBase = base, aliases = aliases, symlinks = symlinks)
        lastContext = vueCtx

        val indicator = ctx.indicator
        val baseFraction = ctx.progressFraction

        indicator?.text = "Vue 3: components (.vue files)…"
        indicator?.fraction = baseFraction
        SfcScriptSetupCollector.collect(project, vueCtx)

        indicator?.text = "Vue 3: Pinia stores…"
        indicator?.fraction = baseFraction + 0.15
        PiniaStoreCollector.collect(project, vueCtx)

        indicator?.text = "Vue 3: composables…"
        indicator?.fraction = baseFraction + 0.25
        ComposableCollector.collect(project, vueCtx)

        indicator?.text = "Vue 3: routes…"
        indicator?.fraction = baseFraction + 0.32
        LazyRouteCollector.collect(project, vueCtx)

        indicator?.text = "Vue 3: API calls…"
        indicator?.fraction = baseFraction + 0.40
        ApiCallCollector.collect(project, vueCtx)

        indicator?.text = "Vue 3: binding parametric URLs…"
        indicator?.fraction = baseFraction + 0.44
        ModuleNameBinder.bind(project, vueCtx)

        indicator?.text = "Vue 3: store / composable edges (1-hop)…"
        indicator?.fraction = baseFraction + 0.46
        CallThroughResolver.collect(project, vueCtx)

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
