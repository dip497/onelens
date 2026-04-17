package com.onelens.plugin.framework.vue3

import com.onelens.plugin.export.ApiCallData
import com.onelens.plugin.export.CallsApiEdge
import com.onelens.plugin.export.ComponentData
import com.onelens.plugin.export.ComposableData
import com.onelens.plugin.export.DispatchesEdge
import com.onelens.plugin.export.ImportsEdge
import com.onelens.plugin.export.JsFunctionData
import com.onelens.plugin.export.JsModuleData
import com.onelens.plugin.export.RouteData
import com.onelens.plugin.export.StoreData
import com.onelens.plugin.export.UsesComposableEdge
import com.onelens.plugin.export.UsesStoreEdge
import com.onelens.plugin.export.Vue3Data
import java.nio.file.Path

/**
 * Mutable accumulator shared across Vue 3 collectors within a single export run.
 * Each collector appends to its section — the adapter snapshots the final state into
 * [Vue3Data] at the end. Keeping this mutable and shared avoids (a) double-walking the
 * project file tree, and (b) awkward merge logic across many small [CollectorOutput]s.
 */
class Vue3Context(
    val projectBase: Path,
    val aliases: Map<String, Path>,
    val symlinks: List<com.onelens.plugin.framework.vue3.resolver.SymlinkResolver.SymlinkEntry>
) {
    val components: MutableList<ComponentData> = mutableListOf()
    val composables: MutableList<ComposableData> = mutableListOf()
    val stores: MutableList<StoreData> = mutableListOf()
    val routes: MutableList<RouteData> = mutableListOf()
    val apiCalls: MutableList<ApiCallData> = mutableListOf()
    val usesStore: MutableList<UsesStoreEdge> = mutableListOf()
    val usesComposable: MutableList<UsesComposableEdge> = mutableListOf()
    val dispatches: MutableList<DispatchesEdge> = mutableListOf()
    val callsApi: MutableList<CallsApiEdge> = mutableListOf()
    // Phase B2 business-logic layer
    val modules: MutableList<JsModuleData> = mutableListOf()
    val functions: MutableList<JsFunctionData> = mutableListOf()
    val imports: MutableList<ImportsEdge> = mutableListOf()

    fun snapshot(): Vue3Data = Vue3Data(
        components = components.toList(),
        composables = composables.toList(),
        stores = stores.toList(),
        routes = routes.toList(),
        apiCalls = apiCalls.toList(),
        usesStore = usesStore.toList(),
        usesComposable = usesComposable.toList(),
        dispatches = dispatches.toList(),
        callsApi = callsApi.toList(),
        modules = modules.toList(),
        functions = functions.toList(),
        imports = imports.toList()
    )

    /** Make a file path relative to [projectBase]. Falls back to absolute path string on failure. */
    fun relativize(abs: Path): String = try {
        projectBase.relativize(abs).toString().replace('\\', '/')
    } catch (_: Throwable) {
        abs.toString()
    }
}
