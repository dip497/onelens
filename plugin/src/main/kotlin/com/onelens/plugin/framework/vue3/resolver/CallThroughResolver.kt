package com.onelens.plugin.framework.vue3.resolver

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.lang.javascript.psi.JSReturnStatement
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
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.UsesComposableEdge
import com.onelens.plugin.export.UsesStoreEdge
import com.onelens.plugin.framework.vue3.Vue3Context
import com.onelens.plugin.framework.vue3.collectors.VuexStoreCollector
import java.nio.file.Paths
import com.onelens.plugin.framework.jscommon.smartRead

/**
 * Post-pass that walks every Component (and Composable) and emits:
 *   - `USES_STORE` edges when a `useXStore()` call resolves to a Pinia `defineStore`.
 *   - `USES_STORE {indirect=true}` edges via 1-hop call-through. If the caller invokes
 *     `useXMethods()` which in turn calls `useXStore()`, the edge is emitted with
 *     `via = "useXMethods"`.
 *   - `USES_COMPOSABLE` edges for any `useY()` call that resolves to a non-store
 *     composable registered in [Vue3Context.composables].
 *
 * The resolver uses textual lookups over the already-collected Vue3Context rather than
 * re-running PSI resolve — that keeps the pass O(calls × stores) without touching the
 * JSResolve cache. Trade-off: same-name collisions across files are grouped together,
 * but the graph cost of that is a small over-count rather than missing edges.
 */
object CallThroughResolver {
    private val LOG = logger<CallThroughResolver>()

    /** Vuex binding helpers. Vue 2's equivalent of a `useXStore()` call. */
    private val VUEX_MAP_HELPERS = setOf("mapState", "mapGetters", "mapActions", "mapMutations")

    /** Cheap text probe — avoids a PSI parse on every non-component JS file. */
    private fun bindsVuexNamespace(vf: com.intellij.openapi.vfs.VirtualFile): Boolean = try {
        vf.inputStream.use { it.readNBytes(4096).decodeToString() }.contains("createNamespacedHelpers")
    } catch (_: Throwable) {
        false
    }

    /**
     * Namespace string in argument 0 of a Vuex binding helper.
     *
     * Handles the plain literal (`'userGroup'`) and the partially-dynamic
     * template (`` `status/${Constants.TASK}` ``) by taking the static prefix
     * before the first interpolation — `status/…` still identifies the parent
     * module, which is the edge worth having. A fully dynamic argument yields
     * null and emits no edge rather than a wrong one.
     */
    private fun namespaceArg(call: JSCallExpression): String? {
        val arg = call.argumentList?.arguments?.firstOrNull() ?: return null
        (arg as? com.intellij.lang.javascript.psi.JSLiteralExpression)
            ?.takeIf { it.isQuotedLiteral }
            ?.let { return it.stringValue }
        val text = arg.text
        if (!text.startsWith("`")) return null
        val staticPrefix = text.removePrefix("`").substringBefore("\${").trim('/', ' ')
        return staticPrefix.ifBlank { null }
    }

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) return
        if (ctx.stores.isEmpty() && ctx.composables.isEmpty()) {
            LOG.info("CallThroughResolver: no stores or composables collected — skipping")
            return
        }

        // Fast lookup structures. Store export names (`useUserStore`) and composable
        // names (`useCounter`) are unique project-wide in well-organised repos; if they
        // collide the first-registered wins (best effort).
        val storeByName = ctx.stores.associateBy { it.name }
        // Vuex lookup is normalised (case + separators stripped) because a repo
        // routinely registers `user-group/` as the namespace `userGroup`.
        // `associateBy` is last-wins, so any collision silently drops a store from
        // resolution — log it rather than let edges quietly point at the survivor.
        val storeByNamespace = ctx.stores.associateBy { VuexStoreCollector.namespaceKey(it.name) }
        if (storeByNamespace.size < ctx.stores.size) {
            val dupes = ctx.stores.groupBy { VuexStoreCollector.namespaceKey(it.name) }
                .filterValues { it.size > 1 }
                .map { (k, v) -> "$k <- ${v.map { s -> s.fqn }}" }
            LOG.warn("Vuex namespace collisions (last wins, edges may point at the wrong store): $dupes")
        }
        val composableByName = ctx.composables.associateBy { it.name }

        // File-path → ComponentData index. Replaces the O(files × components) linear
        // scans (`.any { it.filePath == relative }` / `.first { it.filePath == relative }`)
        // that ran per file AND per call expression with O(1) HashMap lookups.
        val componentByPath = ctx.components.associateBy { it.filePath }
        val composablePaths: Set<String> = ctx.composables.map { it.filePath }.toSet()

        // Also build a view "file → defineStore exports" so we can detect wrappers that
        // internally invoke a store from the same file they live in.
        val storeFiles: Set<String> = ctx.stores.map { it.filePath }.toSet()

        val ftm = FileTypeManager.getInstance()
        val types = listOfNotNull(
            ftm.getFileTypeByExtension("vue").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = ctx.workspace.scope(project)
        val psiManager = PsiManager.getInstance(project)

        val emittedStoreEdges = HashSet<Triple<String, String, Boolean>>()
        val emittedComposableEdges = HashSet<Pair<String, String>>()

        val allFiles = smartRead(project) { types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        for (vf in allFiles) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            // Map file path → caller fqn. For components the fqn is the component's
            // symbolic name; for composable/store files we use file::fn form, matching
            // how the collectors emit fqns.
            val componentName = vf.name.removeSuffix(".vue")
            val component = componentByPath[relative]
            val fileIsComponent = component != null
            val fileIsComposable = relative in composablePaths
            // Vue 2 binds Vuex namespaces in plain helper modules, not in the
            // components themselves — a real codebase put all 44
            // `createNamespacedHelpers` calls in `state/modules/<ns>/helpers.js`
            // and none in a `.vue` file. Restricting the walk to components and
            // composables therefore found zero binding sites. Cheap text probe so
            // the extra files cost a read, not a PSI parse.
            val fileBindsVuex = !fileIsComponent && !fileIsComposable &&
                ctx.vueMajor == 2 && bindsVuexNamespace(vf)
            if (!fileIsComponent && !fileIsComposable && !fileBindsVuex) continue

            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val calls = PsiTreeUtil.findChildrenOfType(psi, JSCallExpression::class.java)
                for (call in calls) {
                    val ref = call.methodExpression as? JSReferenceExpression ?: continue
                    val name = ref.referenceName ?: continue

                    // Vuex (Vue 2). Two binding forms, both keyed on a namespace
                    // string literal in argument 0:
                    //   `...mapState('user', ['profile'])`   — inline helper
                    //   `createNamespacedHelpers('userGroup')` — bound helpers
                    // The second dominates in real codebases (a 2100-SFC repo used
                    // it at all 44 call sites and the inline form at none), so
                    // handling only the first would emit zero edges there.
                    // Non-namespaced `mapState(['x'])` has no store to point at and
                    // is skipped rather than guessed.
                    if (name in VUEX_MAP_HELPERS || name == "createNamespacedHelpers") {
                        val namespace = namespaceArg(call)
                        val store = namespace?.let { storeByNamespace[VuexStoreCollector.namespaceKey(it)] }
                        if (store != null) {
                            // In a helper module the caller is the module itself, not a
                            // component. The component→helper→store hop needs the import
                            // graph, which is built AFTER this resolver runs — see PROGRESS V7.
                            val callerFqn = component?.let { "${it.filePath}::${it.name}" }
                                ?: "$relative::${vf.nameWithoutExtension}"
                            val key = Triple(callerFqn, store.id, false)
                            if (emittedStoreEdges.add(key)) {
                                ctx.usesStore += UsesStoreEdge(
                                    callerFqn = callerFqn,
                                    storeId = store.id,
                                    storeFqn = store.fqn,
                                    indirect = false,
                                    via = null
                                )
                            }
                        }
                        continue
                    }

                    if (!name.startsWith("use")) continue

                    val callerFqn = if (fileIsComponent && component != null) {
                        // Component fqn matches SfcScriptSetupCollector: just the name
                        "${component.filePath}::${component.name}"
                    } else {
                        val fn = PsiTreeUtil.getParentOfType(call, JSFunction::class.java, true)
                        "$relative::${fn?.name ?: componentName}"
                    }

                    // Direct store use — handle and skip composable branch.
                    val directStore = storeByName[name]
                    if (directStore != null) {
                        val key = Triple(callerFqn, directStore.id, false)
                        if (emittedStoreEdges.add(key)) {
                            ctx.usesStore += UsesStoreEdge(
                                callerFqn = callerFqn,
                                storeId = directStore.id,
                                storeFqn = directStore.fqn,
                                indirect = false,
                                via = null
                            )
                        }
                        continue
                    }

                    // Composable-as-wrapper (1-hop): check the composable's body for
                    // store references we know about.
                    composableByName[name]?.let { composable ->
                        // Plain USES_COMPOSABLE edge.
                        val compKey = callerFqn to composable.fqn
                        if (emittedComposableEdges.add(compKey)) {
                            ctx.usesComposable += UsesComposableEdge(
                                callerFqn = callerFqn,
                                composableFqn = composable.fqn
                            )
                        }
                        // Indirect store edges: scan the composable's body text for any
                        // store's export name. This is the 1-hop call-through — not a
                        // full PSI resolve, but accurate enough for the wrapper pattern
                        // the plan's P1-10 locks us into.
                        val body = composable.body.orEmpty()
                        if (body.isBlank()) return@let
                        for (store in ctx.stores) {
                            if (body.contains("${store.name}(")) {
                                val key = Triple(callerFqn, store.id, true)
                                if (emittedStoreEdges.add(key)) {
                                    ctx.usesStore += UsesStoreEdge(
                                        callerFqn = callerFqn,
                                        storeId = store.id,
                                        storeFqn = store.fqn,
                                        indirect = true,
                                        via = composable.name
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
        bridgeComponentsToStores(ctx, emittedStoreEdges)

        LOG.info(
            "CallThroughResolver: ${ctx.usesStore.size} USES_STORE edges " +
                "(${ctx.usesStore.count { it.indirect }} indirect), " +
                "${ctx.usesComposable.size} USES_COMPOSABLE edges"
        )
    }

    /**
     * Vue 2 component → helper → store, the 2-hop that makes "which components use
     * this store" answerable.
     *
     * Vue 2 codebases do not bind Vuex in the component. They bind it once per
     * module in a helper (`createNamespacedHelpers('userGroup')` inside
     * `state/modules/user-group/helpers.js`), export the resulting computed/methods
     * maps, and spread those into components. So the direct pass above attributes
     * every edge to a helper module and NOT ONE to a component — which leaves the
     * headline frontend query returning nothing useful.
     *
     * This walks the already-collected import graph: any component importing from a
     * file that binds a namespace gets an indirect edge to that store, `via` the
     * helper. Mirrors the existing composable-as-wrapper 1-hop, using imports rather
     * than a body-text scan because the binding and the use are in different files.
     */
    private fun bridgeComponentsToStores(
        ctx: Vue3Context,
        emitted: HashSet<Triple<String, String, Boolean>>,
    ) {
        if (ctx.vueMajor != 2) return

        // helper filePath → the store it binds, from the edges just emitted.
        val componentPaths = ctx.components.associateBy { it.filePath }
        val storeByFqn = ctx.stores.associateBy { it.fqn }
        val bindingHelpers: Map<String, List<com.onelens.plugin.export.StoreData>> = ctx.usesStore
            .filter { it.callerFqn.substringBeforeLast("::") !in componentPaths }
            .mapNotNull { edge ->
                storeByFqn[edge.storeFqn]?.let { edge.callerFqn.substringBeforeLast("::") to it }
            }
            .groupBy({ it.first }, { it.second })
        if (bindingHelpers.isEmpty()) return

        // Import targets are written as authored — often extensionless. Expand the
        // same candidate set the Python loader uses so `@state/x/helpers` matches
        // `src/state/x/helpers.js`.
        val modulePaths = ctx.modules.mapTo(HashSet()) { it.filePath }
        fun resolve(target: String): String? {
            if (target in bindingHelpers) return target
            for (ext in EXT_CANDIDATES) {
                val c = target + ext
                if (c in bindingHelpers) return c
            }
            return null
        }

        var added = 0
        for (imp in ctx.imports) {
            val component = componentPaths[imp.sourceModule] ?: continue
            val helperPath = resolve(imp.targetModule) ?: continue
            val callerFqn = "${component.filePath}::${component.name}"
            for (store in bindingHelpers.getValue(helperPath)) {
                val key = Triple(callerFqn, store.id, true)
                if (!emitted.add(key)) continue
                ctx.usesStore += UsesStoreEdge(
                    callerFqn = callerFqn,
                    storeId = store.id,
                    storeFqn = store.fqn,
                    indirect = true,
                    via = helperPath.substringAfterLast('/'),
                )
                added++
            }
        }
        LOG.info("CallThroughResolver: $added component→helper→store edges " +
            "(${bindingHelpers.size} binding helpers, ${modulePaths.size} modules)")
    }

    private val EXT_CANDIDATES = listOf(".js", ".ts", ".mjs", "/index.js", "/index.ts")
}
