package com.onelens.plugin.framework.vue3.resolver

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
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
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.UsesComposableEdge
import com.onelens.plugin.export.UsesStoreEdge
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

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
        val composableByName = ctx.composables.associateBy { it.name }

        // Also build a view "file → defineStore exports" so we can detect wrappers that
        // internally invoke a store from the same file they live in.
        val storeFiles: Set<String> = ctx.stores.map { it.filePath }.toSet()

        val ftm = FileTypeManager.getInstance()
        val types = listOfNotNull(
            ftm.getFileTypeByExtension("vue").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = GlobalSearchScope.projectScope(project)
        val psiManager = PsiManager.getInstance(project)

        val emittedStoreEdges = HashSet<Triple<String, String, Boolean>>()
        val emittedComposableEdges = HashSet<Pair<String, String>>()

        for (vf in types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            // Map file path → caller fqn. For components the fqn is the component's
            // symbolic name; for composable/store files we use file::fn form, matching
            // how the collectors emit fqns.
            val componentName = vf.name.removeSuffix(".vue")
            val fileIsComponent = ctx.components.any { it.filePath == relative }
            val fileIsComposable = ctx.composables.any { it.filePath == relative }
            if (!fileIsComponent && !fileIsComposable) continue

            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val calls = PsiTreeUtil.findChildrenOfType(psi, JSCallExpression::class.java)
                for (call in calls) {
                    val ref = call.methodExpression as? JSReferenceExpression ?: continue
                    val name = ref.referenceName ?: continue
                    if (!name.startsWith("use")) continue

                    val callerFqn = if (fileIsComponent) {
                        // Component fqn matches SfcScriptSetupCollector: just the name
                        ctx.components.first { it.filePath == relative }.let {
                            "${it.filePath}::${it.name}"
                        }
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
        LOG.info(
            "CallThroughResolver: ${ctx.usesStore.size} USES_STORE edges " +
                "(${ctx.usesStore.count { it.indirect }} indirect), " +
                "${ctx.usesComposable.size} USES_COMPOSABLE edges"
        )
    }
}
