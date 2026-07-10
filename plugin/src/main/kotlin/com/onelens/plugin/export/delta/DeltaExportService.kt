package com.onelens.plugin.export.delta

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.onelens.plugin.OneLensConstants
import com.onelens.plugin.export.*
import com.onelens.plugin.export.collectors.*
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.nextjs.NextjsAdapter
import com.onelens.plugin.framework.nextjs.NextjsCollector
import com.onelens.plugin.framework.workspace.Workspace
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.encodeToStream
import java.nio.file.Files
import java.nio.file.Path

/**
 * Produces delta JSON exports containing only changes since last export.
 *
 * For each changed file:
 *   - Collects classes, methods, fields, calls, inheritance for classes in that file
 *   - Marks deleted classes/methods from removed files
 *
 * For each deleted file:
 *   - Looks up what classes were in that file (from previous export state)
 *   - Adds their FQNs to the deleted list
 */
object DeltaExportService {

    private val LOG = logger<DeltaExportService>()

    private val json = Json {
        prettyPrint = true
        encodeDefaults = true
    }

    @Serializable
    data class DeltaDocument(
        val version: String,
        val exportType: String = "delta",
        val timestamp: String,
        val basedOnTimestamp: String,
        val changedFiles: List<String>,
        /**
         * Same workspace header the full export emits. The Python importer resolves the
         * `wing` stamp as `workspace.graphId ?: graph_name`, so a delta WITHOUT this header
         * falls back to the `--graph` argument and stamps a DIFFERENT wing than the full
         * import did. Wing-scoped replaces then delete nothing and re-insert under the wrong
         * wing, leaving stale nodes behind (verified: a removed component survived a delta).
         */
        val workspace: com.onelens.plugin.export.WorkspaceInfo? = null,
        val deleted: DeletedSection,
        val upserted: UpsertedSection,
        // Spring beans / endpoints / injections are cross-class by nature
        // (bean A injects bean B), so per-class filtering loses edges. We
        // ship a full re-scan on every delta — the Python side treats this
        // as "replace all Spring data". Cost is cheap: AnnotatedElementsSearch
        // is indexed. Modules are small + rarely change; same treatment.
        val spring: SpringData? = null,
        val modules: List<ModuleData> = emptyList(),
        // JPA + tests are cross-class (RELATES_TO between entities, TESTS
        // derived from CALLS, MOCKS→SpringBean) so they get the same full
        // re-scan + replace-all treatment as Spring. Without this a modified
        // @Entity / test class DETACH-deletes and re-MERGEs as a plain
        // :Class/:Method, silently losing its :JpaEntity / :TestCase label
        // and every JPA / test edge on each delta.
        val jpa: JpaData? = null,
        val tests: List<TestCaseData> = emptyList(),
        val mockBeans: List<TestBeanBinding> = emptyList(),
        val spyBeans: List<TestBeanBinding> = emptyList(),
        // Adapters that contributed to this delta. Python importer inspects this
        // to decide which subgraphs to replace. `nextjs` present when the Next
        // adapter re-collected its whole subgraph (see below).
        val adapters: List<String> = listOf("spring-boot"),
        val nextjs: NextjsData? = null,
        val stats: DeltaStats
    )

    @Serializable
    data class DeletedSection(
        val classes: List<String> = emptyList(),
        val methods: List<String> = emptyList(),
        val fields: List<String> = emptyList(),
    )

    @Serializable
    data class UpsertedSection(
        val classes: List<ClassData> = emptyList(),
        val methods: List<MethodData> = emptyList(),
        val fields: List<FieldData> = emptyList(),
        val callGraph: List<CallEdge> = emptyList(),
        val inheritance: List<InheritanceEdge> = emptyList(),
        val methodOverrides: List<OverrideEdge> = emptyList(),
        val annotations: List<AnnotationUsage> = emptyList(),
        val enumConstants: List<EnumConstantData> = emptyList(),
        val dataFlow: DataFlowData? = null,
    )

    @Serializable
    data class DeltaStats(
        val changedFileCount: Int = 0,
        val deletedClassCount: Int = 0,
        val upsertedClassCount: Int = 0,
        val upsertedMethodCount: Int = 0,
        val upsertedCallEdgeCount: Int = 0,
        val exportDurationMs: Long = 0
    )

    /**
     * Export only changes since last export.
     *
     * @return Path to delta JSON file, or null if no changes detected
     */
    fun exportDelta(project: Project, config: ExportConfig): DeltaResult {
        if (project.basePath == null) return DeltaResult.Error("No project base path")
        val state = ExportState.getInstance(project)

        // 1. Detect changed files
        val changedFiles = DeltaTracker.getChangedFiles(project)

        if (changedFiles.isFullReexport) {
            return DeltaResult.NeedFullExport("No previous export state — full export needed")
        }

        if (!changedFiles.hasChanges) {
            return DeltaResult.NoChanges
        }

        return exportDeltaForFiles(project, config, changedFiles.modified, changedFiles.deleted)
    }

    /**
     * Export delta for a specific list of changed files.
     * Called by exportDelta() and by AutoSyncService.
     */
    fun exportDeltaForFiles(
        project: Project,
        config: ExportConfig,
        modifiedFiles: List<String>,
        deletedFiles: List<String> = emptyList()
    ): DeltaResult {
        val startTime = System.currentTimeMillis()
        if (project.basePath == null) return DeltaResult.Error("No project base path")
        // Delta collectors hit the PSI index through JavaPsiFacade.findClass etc.
        // Wait for smart mode once at the entry boundary rather than scattering
        // `DumbService.isDumb` guards across every collector (see ExportService).
        com.intellij.openapi.project.DumbService.getInstance(project).waitForSmartMode()
        val workspace = try {
            WorkspaceLoader.load(project)
        } catch (e: Exception) {
            return DeltaResult.Error("Could not resolve workspace: ${e.message}")
        }
        val state = ExportState.getInstance(project)

        if (state.state.lastExportTimestamp == 0L) {
            return DeltaResult.NeedFullExport("No previous export — full export needed first")
        }

        LOG.info("Delta: ${modifiedFiles.size} modified, ${deletedFiles.size} deleted files")

        // 2. For deleted files: find what classes were in them (from file hashes map keys)
        val deletedClasses = mutableListOf<String>()
        val deletedMethods = mutableListOf<String>()
        val deletedFields = mutableListOf<String>()

        // We track file→classes mapping in state.fileHashes (key=filePath, value=comma-separated FQNs)
        for (deletedFile in deletedFiles) {
            val classFqns = state.state.fileHashes[deletedFile]
                ?.split(",")?.filter { it.isNotEmpty() } ?: continue
            deletedClasses.addAll(classFqns)
        }

        // 3. For modified files: re-collect classes in those files
        val affectedClasses = ReadAction.compute<List<ClassData>, Throwable> {
            collectClassesFromFiles(project, modifiedFiles, workspace)
        }

        // 4. Collect members, calls, inheritance for affected classes.
        // Each collector is guarded independently — parity with the full path
        // (SpringBootAdapter). This is the 5-s auto-sync hot path; a single PSI
        // hiccup in one collector must degrade that collector's output, not
        // abort the whole delta. ProcessCanceledException is a control-flow
        // signal and MUST propagate, so it is rethrown before the catch.
        val members = guardCollect("members") {
            MemberCollector.collect(project, affectedClasses, workspace)
        } ?: MemberResult(emptyList(), emptyList(), emptyList())
        val callGraph = guardCollect("callGraph") {
            CallGraphCollector.collect(project, affectedClasses, workspace)
        } ?: emptyList()
        val inheritance = guardCollect("inheritance") {
            InheritanceCollector.collect(project, affectedClasses, workspace)
        } ?: InheritanceResult(emptyList(), emptyList())
        val annotations = guardCollect("annotations") {
            AnnotationCollector.collect(project, affectedClasses, workspace)
        } ?: emptyList()
        val dataFlow = guardCollect("data-flow") {
            DataFlowCollector.collect(project, affectedClasses, workspace)
        }

        // 4b. Spring + modules: full re-scan (indexed, cheap). Per-class
        // filtering would miss cross-class injection edges and newly-added
        // @RestController / @Service annotations on changed files.
        val spring = if (config.includeSpring) {
            try { SpringCollector.collect(project, workspace) } catch (e: Throwable) {
                LOG.warn("Delta Spring collection failed: ${e.message}"); null
            }
        } else null
        val modules = try { ModuleCollector.collect(project, workspace) } catch (e: Throwable) {
            LOG.warn("Delta module collection failed: ${e.message}"); emptyList()
        }
        // JPA + tests: full re-scan + replace-all (same rationale as Spring).
        val jpa = if (config.includeSpring) {
            try { JpaCollector.collect(project, workspace) } catch (e: Throwable) {
                LOG.warn("Delta JPA collection failed: ${e.message}"); null
            }
        } else null
        val testResult = try { TestCollector.collect(project, workspace) } catch (e: Throwable) {
            LOG.warn("Delta test collection failed: ${e.message}")
            TestCollector.Result(emptyList(), emptyList(), emptyList())
        }

        // 4c. Next.js: re-collect the WHOLE subgraph and let the importer replace it.
        // ponytail: full Next re-collect (~3s) instead of a scoped delta — the slow
        // part of an export is IntelliJ indexing, not JS collection, so scoping the
        // collection buys nothing yet. Upgrade to per-file scoped delta only when
        // collection time, not indexing time, dominates. A .tsx-only change resolves
        // no Java classes (PsiJavaFile filter above), so the Java sections stay empty
        // while `nextjs` carries the change — a valid delta, not NoChanges.
        var nextData: NextjsData? = null
        val activeAdapters = mutableListOf("spring-boot")
        // Report Vue when it is present even though delta does not (yet) collect it.
        // The importer's `_replace_nextjs` uses `"vue3" not in adapters` to decide whether
        // the SHARED JsModule/JsFunction/ApiCall labels are safe to wing-delete. Omitting
        // "vue3" here made that guard unreachable, so a Next delta on a Vue+Next graph
        // DETACH DELETEd Vue's JS subgraph. Never drop this without fixing the importer.
        try {
            if (com.onelens.plugin.framework.vue3.Vue3Adapter().detect(project)) {
                activeAdapters.add("vue3")
            }
        } catch (e: Throwable) {
            LOG.warn("Vue detection during delta failed; assuming no Vue: ${e.message}")
        }
        try {
            if (NextjsAdapter().detect(project)) {
                val nextCtx = CollectContext(
                    project = project,
                    indicator = null,
                    progressFraction = 0.5,
                    workspace = workspace,
                )
                val collector = NextjsCollector()
                collector.collect(nextCtx)
                nextData = collector.lastContext?.snapshot()
                if (nextData != null) activeAdapters.add("nextjs")
            }
        } catch (e: Throwable) {
            LOG.warn("Delta Next.js collection failed (Java delta unaffected): ${e.message}")
        }

        // Also add modified files' old classes to deleted (they'll be replaced by upserted)
        for (modifiedFile in modifiedFiles) {
            val oldClassFqns = state.state.fileHashes[modifiedFile]
                ?.split(",")?.filter { it.isNotEmpty() } ?: continue
            deletedClasses.addAll(oldClassFqns)
        }

        val durationMs = System.currentTimeMillis() - startTime

        // 5. Build delta document
        val delta = DeltaDocument(
            version = OneLensConstants.EXPORT_VERSION,
            timestamp = java.time.Instant.now().toString(),
            basedOnTimestamp = java.time.Instant.ofEpochMilli(state.state.lastExportTimestamp).toString(),
            changedFiles = modifiedFiles + deletedFiles,
            // Must match the full export's header exactly — the importer derives the `wing`
            // stamp from `workspace.graphId`. See the KDoc on DeltaDocument.workspace.
            workspace = com.onelens.plugin.export.WorkspaceInfo(
                name = workspace.name,
                graphId = workspace.graphId,
                roots = workspace.roots.map { it.path.toString() },
                duplicateFqnPolicy = workspace.policies.duplicateFqn,
                configFile = workspace.configFile?.toString(),
            ),
            deleted = DeletedSection(
                classes = deletedClasses.distinct(),
                methods = deletedMethods,
                fields = deletedFields,
            ),
            upserted = UpsertedSection(
                classes = affectedClasses,
                methods = members.methods,
                fields = members.fields,
                callGraph = callGraph,
                inheritance = inheritance.edges,
                methodOverrides = inheritance.overrides,
                annotations = annotations,
                enumConstants = members.enumConstants,
                dataFlow = dataFlow,
            ),
            spring = spring,
            modules = modules,
            jpa = jpa,
            tests = testResult.tests,
            mockBeans = testResult.mockBeans,
            spyBeans = testResult.spyBeans,
            adapters = activeAdapters,
            nextjs = nextData,
            stats = DeltaStats(
                changedFileCount = modifiedFiles.size + deletedFiles.size,
                deletedClassCount = deletedClasses.distinct().size,
                upsertedClassCount = affectedClasses.size,
                upsertedMethodCount = members.methods.size,
                upsertedCallEdgeCount = callGraph.size,
                exportDurationMs = durationMs
            )
        )

        // 6. Write delta JSON
        val outputDir = config.outputPath
        Files.createDirectories(outputDir)
        val fileName = "${workspace.graphId}-delta-${System.currentTimeMillis()}.json"
        val outputFile = outputDir.resolve(fileName)
        // Stream JSON to disk to avoid OOM on large deltas.
        Files.newOutputStream(outputFile).use { out ->
            @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
            json.encodeToStream(delta, out)
        }

        // 7. Update state — git hash tracked against workspace primary root.
        val newHash = DeltaTracker.getCurrentGitHash(workspace.primaryRoot.toString())
        state.state.lastExportTimestamp = System.currentTimeMillis()
        state.state.lastExportPath = outputFile.toString()
        if (newHash.isNotEmpty()) state.state.lastGitHash = newHash

        // Update file→classes mapping: clear modified files first, then rebuild from fresh collection
        for (modifiedFile in modifiedFiles) {
            state.state.fileHashes.remove(modifiedFile)
        }
        for (deletedFile in deletedFiles) {
            state.state.fileHashes.remove(deletedFile)
        }
        // Rebuild mapping from freshly collected classes
        for (cls in affectedClasses) {
            val existing = state.state.fileHashes.getOrDefault(cls.filePath, "")
            state.state.fileHashes[cls.filePath] = if (existing.isEmpty()) cls.fqn else "$existing,${cls.fqn}"
        }

        LOG.info("Delta export complete: $outputFile (${durationMs}ms)")
        return DeltaResult.Success(outputFile, delta.stats)
    }

    /**
     * Run one collector, degrading to null on failure instead of aborting the
     * whole delta. ProcessCanceledException (and other ControlFlowException)
     * MUST propagate — swallowing it breaks IntelliJ cancellation — so it is
     * rethrown before the generic catch.
     */
    private inline fun <T> guardCollect(name: String, block: () -> T): T? =
        try {
            block()
        } catch (ce: com.intellij.openapi.progress.ProcessCanceledException) {
            throw ce
        } catch (e: Throwable) {
            LOG.warn("Delta $name collection failed: ${e.message}")
            null
        }

    /**
     * Collect ClassData for classes found in specific files. Relative paths are
     * resolved against each workspace root in order — first hit wins. This is
     * what lets a delta on a sibling-repo root work without the caller having
     * to know which root the file lives in.
     */
    private fun collectClassesFromFiles(
        project: Project,
        filePaths: List<String>,
        workspace: Workspace
    ): List<ClassData> {
        val result = mutableListOf<ClassData>()
        val psiManager = PsiManager.getInstance(project)
        val fs = com.intellij.openapi.vfs.LocalFileSystem.getInstance()

        for (relativePath in filePaths) {
            val virtualFile = workspace.roots.asSequence()
                .map { root -> root.path.resolve(relativePath).toString() }
                .mapNotNull { fs.findFileByPath(it) }
                .firstOrNull() ?: continue
            val psiFile = psiManager.findFile(virtualFile) as? PsiJavaFile ?: continue

            for (psiClass in psiFile.classes) {
                val fqn = psiClass.qualifiedName ?: continue
                val filePath = relativePath

                result.add(ClassData(
                    fqn = fqn,
                    name = psiClass.name ?: "",
                    kind = getKind(psiClass),
                    modifiers = ClassCollector.extractModifiers(psiClass.modifierList),
                    genericParams = psiClass.typeParameters.map { it.name ?: "?" },
                    filePath = filePath,
                    lineStart = 0, // Skip line numbers for delta (saves time)
                    lineEnd = 0,
                    packageName = psiFile.packageName,
                    enclosingClass = psiClass.containingClass?.qualifiedName,
                    superClass = psiClass.superClass?.qualifiedName?.takeIf { it != "java.lang.Object" },
                    interfaces = psiClass.implementsListTypes.mapNotNull { it.resolve()?.qualifiedName },
                    annotations = ClassCollector.extractAnnotations(psiClass.modifierList)
                ))

                // Also collect inner classes
                collectInnerClasses(psiClass, filePath, psiFile.packageName, result)
            }
        }

        return result
    }

    private fun collectInnerClasses(
        psiClass: PsiClass,
        filePath: String,
        packageName: String,
        result: MutableList<ClassData>
    ) {
        for (inner in psiClass.innerClasses) {
            val fqn = inner.qualifiedName ?: continue
            result.add(ClassData(
                fqn = fqn,
                name = inner.name ?: "",
                kind = getKind(inner),
                modifiers = ClassCollector.extractModifiers(inner.modifierList),
                filePath = filePath,
                lineStart = 0,
                packageName = packageName,
                enclosingClass = psiClass.qualifiedName,
                superClass = inner.superClass?.qualifiedName?.takeIf { it != "java.lang.Object" },
                interfaces = inner.interfaces.mapNotNull { it.qualifiedName },
                annotations = ClassCollector.extractAnnotations(inner.modifierList)
            ))
            collectInnerClasses(inner, filePath, packageName, result)
        }
    }

    private fun getKind(psiClass: PsiClass): String = when {
        psiClass.isInterface -> "INTERFACE"
        psiClass.isEnum -> "ENUM"
        psiClass.isAnnotationType -> "ANNOTATION_TYPE"
        psiClass.isRecord -> "RECORD"
        psiClass.hasModifierProperty("abstract") -> "ABSTRACT_CLASS"
        else -> "CLASS"
    }

    sealed class DeltaResult {
        data class Success(val path: Path, val stats: DeltaStats) : DeltaResult()
        data class Error(val message: String) : DeltaResult()
        data class NeedFullExport(val reason: String) : DeltaResult()
        data object NoChanges : DeltaResult()
    }
}
