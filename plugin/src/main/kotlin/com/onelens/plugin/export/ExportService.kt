package com.onelens.plugin.export

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.OneLensConstants
import com.onelens.plugin.export.collectors.*
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.FrameworkAdapter
import com.onelens.plugin.framework.springboot.SpringBootAdapter
import com.onelens.plugin.framework.springboot.SpringBootCollectionResult
import com.onelens.plugin.framework.springboot.SpringBootCollector
import com.onelens.plugin.framework.vue3.Vue3Collector
import com.onelens.plugin.framework.vue3.Vue3Context
import com.onelens.plugin.framework.workspace.Workspace
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import com.onelens.plugin.ui.OneLensEvent
import com.onelens.plugin.ui.OneLensEventBus
import com.onelens.plugin.ui.OneLensState
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.encodeToStream
import java.nio.file.Files
import java.nio.file.Path
import java.time.Instant

/**
 * Orchestrates full and delta exports of code intelligence data.
 */
@Service(Service.Level.APP)
class ExportService {

    companion object {
        private val LOG = logger<ExportService>()

        private val json = Json {
            prettyPrint = true
            encodeDefaults = true
        }

        internal fun publish(event: OneLensEvent) {
            try {
                ApplicationManager.getApplication().messageBus
                    .syncPublisher(OneLensEventBus.TOPIC).onEvent(event)
            } catch (_: Throwable) { /* tool window not subscribed yet — safe to drop */ }
        }
    }

    /**
     * Run a full export of the project's code intelligence.
     * Executes all collectors and writes a complete JSON file.
     */
    fun exportFull(
        project: Project,
        config: ExportConfig,
        indicator: com.intellij.openapi.progress.ProgressIndicator? = null
    ): ExportResult {
        val startTime = System.currentTimeMillis()
        LOG.info("Starting full export for project: ${project.name}")
        publish(OneLensEvent.StatusChange(OneLensState.SYNCING))

        if (project.basePath == null) return ExportResult.Error("Project has no base path")

        // Block until IntelliJ indexes are ready. Every JVM collector hits
        // `JavaPsiFacade.findClass`, `PsiShortNamesCache`, or
        // `AnnotatedElementsSearch` inside a plain ReadAction — those throw
        // `IndexNotReadyException` if the project is still in dumb mode.
        // Per JetBrains threading docs: wait for smart mode once at the entry
        // boundary, not per-collector. Safe from a background thread.
        indicator?.text = "Waiting for indexes…"
        com.intellij.openapi.project.DumbService.getInstance(project).waitForSmartMode()

        // Resolve workspace once at the entry boundary: explicit
        // `onelens.workspace.yaml` if present, else implicit single-root. Every
        // collector downstream treats the workspace as authoritative — nothing
        // falls back to `project.basePath` / `projectScope(project)`.
        val workspace = try {
            WorkspaceLoader.load(project)
        } catch (e: Exception) {
            return ExportResult.Error("Could not resolve workspace: ${e.message}")
        }
        LOG.info("Workspace '${workspace.name}' with ${workspace.roots.size} root(s); graphId='${workspace.graphId}'")
        publish(OneLensEvent.Info("Full export starting for graph '${workspace.graphId}' (${workspace.roots.size} root(s))"))

        // Discover active adapters. EP lookup falls back to a hard-coded list when the
        // extension point hasn't been registered yet (e.g. in tests or if the config-file
        // split isn't loaded). This keeps the existing Java path working unchanged.
        val adapters = discoverAdapters(project, config)
        val activeIds = adapters.map { it.id }
        LOG.info("Active framework adapters: ${activeIds.joinToString(",")}")

        // Run every active adapter's collectors. Each adapter's composite collector
        // is expected to hold its typed state in a `lastResult` / `lastContext`
        // side-channel the SPI doesn't formalize yet (P1 debt — see ADR-010).
        // ExportService then pulls the structured data out of the concrete
        // collector type and merges it into the legacy top-level keys.
        var springResult: SpringBootCollectionResult? = null
        var vueCtx: Vue3Context? = null
        for (adapter in adapters) {
            val fraction = when (adapter) {
                is SpringBootAdapter -> 0.0
                else -> 0.5   // Vue + future adapters start at the half-way mark
            }
            val ctx = CollectContext(
                project = project,
                indicator = indicator,
                progressFraction = fraction,
                workspace = workspace,
            )
            for (collector in adapter.collectors()) {
                try {
                    collector.collect(ctx)
                } catch (e: Throwable) {
                    LOG.warn("Adapter '${adapter.id}' collector '${collector.id}' failed: ${e.message}", e)
                    publish(OneLensEvent.Error("Adapter ${adapter.id} failed: ${e.message}"))
                }
                when (collector) {
                    is SpringBootCollector -> springResult = collector.lastResult
                    is Vue3Collector -> vueCtx = collector.lastContext
                }
            }
        }

        // Legacy top-level keys: populated from Spring if present, empty otherwise.
        val classes = springResult?.classes ?: emptyList()
        val members = MembersFrom(springResult)
        val callGraph = springResult?.callGraph ?: emptyList()
        val inheritanceEdges = springResult?.inheritance ?: emptyList()
        val overrideEdges = springResult?.methodOverrides ?: emptyList()
        val modules = springResult?.modules ?: emptyList()
        val annotations = springResult?.annotations ?: emptyList()
        val enumConstants = springResult?.enumConstants ?: emptyList()
        val spring = if (config.includeSpring) springResult?.spring else null
        val jpa = if (config.includeSpring) springResult?.jpa else null
        val tests = springResult?.tests ?: emptyList()
        val mockBeans = springResult?.mockBeans ?: emptyList()
        val spyBeans = springResult?.spyBeans ?: emptyList()
        val diagnostics = if (config.includeDiagnostics) {
            springResult?.diagnostics ?: emptyList()
        } else emptyList()
        val vue3Data = vueCtx?.snapshot()

        val springApps = springResult?.apps ?: emptyList()
        val springPackages = springResult?.packages ?: emptyList()

        // Vue3 App = one per Vue root detected in the workspace. Packages = one per
        // top-level `src/<segment>` folder. Lightweight — just reads the filesystem;
        // no PSI. Lets `(App)-[:CONTAINS]->(Component|Store|Module)` land in the
        // graph without a heavy Vue3-side collector change for Phase C2.
        val vueApps = mutableListOf<AppData>()
        val vuePackages = mutableListOf<PackageData>()
        if (vueCtx != null) {
            for (root in workspace.roots) {
                val rootDir = root.path.toFile()
                val pkgJson = java.io.File(rootDir, "package.json")
                if (!pkgJson.isFile) continue
                val vueRootName = rootDir.name.ifBlank { workspace.name }
                val appId = "app:vue3:${workspace.relativePath(rootDir.absolutePath).ifBlank { vueRootName }}"
                val srcDir = java.io.File(rootDir, "src")
                val topLevelSegments = if (srcDir.isDirectory) {
                    srcDir.listFiles { f -> f.isDirectory }?.map { it.name } ?: emptyList()
                } else emptyList()
                vueApps += AppData(
                    id = appId,
                    name = vueRootName,
                    type = "vue3",
                    rootPath = rootDir.absolutePath,
                    scanPackages = topLevelSegments,
                )
                for (seg in topLevelSegments) {
                    val pkgId = "vue:$vueRootName:$seg"
                    vuePackages += PackageData(id = pkgId, name = seg, parentId = null, appId = appId)
                }
            }
        }

        val apps = springApps + vueApps
        val packages = springPackages + vuePackages

        val durationMs = System.currentTimeMillis() - startTime

        // Assemble export document — legacy top-level keys preserved for the existing
        // Python importer. New `adapters` + `vue3` subdoc land alongside (unused in
        // Phase A; populated once Vue3Adapter ships).
        val document = ExportDocument(
            version = OneLensConstants.EXPORT_VERSION,
            exportType = "full",
            timestamp = Instant.now().toString(),
            project = ProjectInfo(
                name = workspace.name,
                basePath = workspace.primaryRoot.toString(),
            ),
            workspace = WorkspaceInfo(
                name = workspace.name,
                graphId = workspace.graphId,
                roots = workspace.roots.map { it.path.toString() },
                duplicateFqnPolicy = workspace.policies.duplicateFqn,
                configFile = workspace.configFile?.toString(),
            ),
            classes = classes,
            methods = members.methods,
            fields = members.fields,
            callGraph = callGraph,
            inheritance = inheritanceEdges,
            methodOverrides = overrideEdges,
            spring = spring,
            modules = modules,
            annotations = annotations,
            enumConstants = enumConstants,
            jpa = jpa,
            apps = apps,
            packages = packages,
            tests = tests,
            mockBeans = mockBeans,
            spyBeans = spyBeans,
            diagnostics = diagnostics,
            stats = ExportStats(
                classCount = classes.size,
                methodCount = members.methods.size,
                fieldCount = members.fields.size,
                callEdgeCount = callGraph.size,
                inheritanceEdgeCount = inheritanceEdges.size,
                overrideCount = overrideEdges.size,
                springBeanCount = spring?.beans?.size ?: 0,
                endpointCount = spring?.endpoints?.size ?: 0,
                moduleCount = modules.size,
                annotationUsageCount = annotations.size,
                enumConstantCount = enumConstants.size,
                diagnosticCount = diagnostics.size,
                exportDurationMs = durationMs
            ),
            adapters = activeIds.ifEmpty { listOf("spring-boot") },
            vue3 = vue3Data,
        )

        // Write JSON — stream directly to disk. `encodeToString(document)`
        // materializes the entire document as one String in memory, which
        // OOMs on large projects (590K call edges, 73K methods was enough
        // to blow past a default 2 GB Xmx). `encodeToStream` writes token
        // by token to an OutputStream — memory bounded by the current
        // node, not the whole graph.
        indicator?.text = "Writing JSON export..."
        indicator?.fraction = 0.95
        val outputDir = config.outputPath
        Files.createDirectories(outputDir)
        val fileName = "${workspace.graphId}-full-${System.currentTimeMillis()}.json"
        val outputFile = outputDir.resolve(fileName)
        Files.newOutputStream(outputFile).use { out ->
            @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
            json.encodeToStream(document, out)
        }

        // Update state
        val state = ExportState.getInstance(project)
        state.state.lastExportTimestamp = System.currentTimeMillis()
        state.state.lastExportPath = outputFile.toString()

        LOG.info("Full export complete: $outputFile (${durationMs}ms)")
        publish(OneLensEvent.Info("Full export complete: $outputFile (${durationMs}ms)"))
        val v = document.vue3
        val vueNodeCount = (v?.components?.size ?: 0) + (v?.composables?.size ?: 0) +
            (v?.stores?.size ?: 0) + (v?.routes?.size ?: 0) + (v?.apiCalls?.size ?: 0)
        val vueEdgeCount = (v?.usesStore?.size ?: 0) + (v?.usesComposable?.size ?: 0) +
            (v?.dispatches?.size ?: 0) + (v?.callsApi?.size ?: 0) +
            (v?.imports?.size ?: 0)
        publish(OneLensEvent.SyncComplete(
            graphName = workspace.graphId,
            classes = document.stats.classCount,
            methods = document.stats.methodCount,
            callEdges = document.stats.callEdgeCount,
            isDelta = false,
            durationMs = durationMs,
            vueNodes = vueNodeCount,
            vueEdges = vueEdgeCount,
            jsModules = v?.modules?.size ?: 0,
            jsFunctions = v?.functions?.size ?: 0,
            activeAdapters = document.adapters,
        ))

        // Auto-import into graph DB if onelens CLI is available
        if (config.autoImport) {
            val importResult = syncToGraph(outputFile, workspace.graphId, config, projectBasePath = project.basePath)
            if (importResult != null) {
                LOG.info("Auto-import: $importResult")
                publish(OneLensEvent.Info("CLI import: $importResult"))
            }
        }

        publish(OneLensEvent.StatusChange(OneLensState.READY))
        return ExportResult.Success(outputFile, document.stats)
    }

    /**
     * Run `onelens import` to sync the exported JSON into the graph DB.
     * Auto-installs onelens CLI via uv if not found.
     * Returns the CLI output, or null if setup failed.
     */
    fun syncToGraph(
        exportFile: Path,
        graphName: String,
        config: ExportConfig,
        isFull: Boolean = true,
        projectBasePath: String? = null,
    ): String? {
        // Auto-setup: ensure onelens CLI is installed
        val cliPath = PythonEnvManager.getOneLensCli(config.onelensSourcePath)
        if (cliPath == null) {
            LOG.warn("Could not set up OneLens CLI — Python or uv not found")
            return null
        }

        // Preflight: verify FalkorDB is reachable. Without this the CLI
        // fails with an opaque connection error that only surfaces in
        // idea.log. Better to bail early with a clear message the user
        // can act on. `falkordblite` backend is embedded and doesn't
        // need a server — skip the check there.
        if (config.graphBackend == "falkordb" && !isFalkorDbReachable(config)) {
            LOG.warn(
                "FalkorDB not reachable at ${config.falkordbHost}:${config.falkordbPort}. " +
                    "Start it: docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest"
            )
            return "FalkorDB is not running. Start it with:\n" +
                "docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest\n" +
                "Or switch --backend to falkordblite in OneLens settings for an embedded DB."
        }

        try {
            // `import_graph` auto-detects full vs delta from the export header.
            // `--context` triggers ChromaDB semantic layer: graph + embeddings.
            //   Full: ~30s graph + ~20 min embedding (first time only)
            //   Delta: ~seconds (only changed methods re-embed via deterministic IDs)
            // `--clear` wipes the graph before import — full path only; passing
            // it on delta would destroy the graph.
            // Post-unification CLI shape (2025-01+): tools live under
            // `call-tool <onelens_*>` instead of flat verbs. `onelens_import`
            // still auto-detects full vs delta from the export header.
            val command = mutableListOf(
                cliPath, "call-tool", "onelens_import",
                "--export-path", exportFile.toString(),
                "--graph", graphName,
                "--backend", config.graphBackend,
            )
            // `--context` triggers the ChromaDB semantic layer (Qwen3 + mxbai).
            // Graph-only mode skips it → ~30 s full sync, structural queries only.
            if (config.buildSemanticIndex) {
                command += "--context"
            }
            if (isFull) {
                command += "--clear"
            }

            // Fast path — if the MCP HTTP server is running (started by
            // AutoSyncStartupActivity when semantic is on), invoke the tool
            // directly over HTTP. Skips Python cold-start + TRT engine
            // reload + onnxruntime re-init. Cold-path fallback to the CLI
            // subprocess if the server is down or the call errors.
            val mcp = com.onelens.plugin.mcp.OneLensMcpService.getInstance()
            if (mcp.isReachable()) {
                publish(OneLensEvent.Info("→ MCP call onelens_import (${mcp.endpoint})"))
                val args = mutableMapOf<String, Any?>(
                    "export_path" to exportFile.toString(),
                    "graph" to graphName,
                    "backend" to config.graphBackend,
                    "context" to config.buildSemanticIndex,
                    "clear" to isFull,
                )
                val result = com.onelens.plugin.mcp.OneLensMcpClient.callToolStructured("onelens_import", args)
                if (result != null) {
                    return "Import successful (MCP): $result"
                }
                LOG.warn("MCP call failed, falling back to CLI subprocess")
                publish(OneLensEvent.Info("MCP call failed — falling back to cold CLI"))
            }

            LOG.info("Running: ${command.joinToString(" ")}")
            publish(OneLensEvent.Info("$ ${command.joinToString(" ")}"))

            val pb = ProcessBuilder(command).redirectErrorStream(true)
            // Route embedder / reranker selection through env vars so every
            // `onelens import_graph` and `onelens retrieve` call picks up
            // whichever backend the user chose on the Semantic settings
            // screen. See python/src/onelens/context/embed_backends/__init__.py.
            val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
            val env = pb.environment()
            // Tell `onelens_retrieve` where to resolve project-relative
            // file paths. Without this env, snippet reads silently return
            // empty strings (the graph stores paths like
            //   main_service/domain_service/.../Foo.java
            // but the CLI subprocess has no cwd context). See
            // python/src/onelens/context/retrieval.py::_read_snippet.
            projectBasePath?.let { env["ONELENS_PROJECT_ROOT"] = it }
            when (settings.embedderBackend.lowercase()) {
                "local" -> {
                    // Local embed + local rerank (both via onnxruntime). TRT
                    // auto-enables when `tensorrt-cu12` is importable — no
                    // env flag; the pip install IS the opt-in.
                    env["ONELENS_EMBED_BACKEND"] = "local"
                    env["ONELENS_RERANK_BACKEND"] = "local"
                }
                "openai" -> {
                    // Cloud BYOK. API key lives in PasswordSafe; pull it at
                    // exec time so it never lands on disk. Reranker = noop
                    // (OpenAI has no rerank standard — the user can swap to
                    // "modal" via env if they want cross-encoder reorder).
                    env["ONELENS_EMBED_BACKEND"] = "openai"
                    env["ONELENS_RERANK_BACKEND"] = "none"
                    env["ONELENS_EMBED_BASE_URL"] = settings.openaiBaseUrl
                    env["ONELENS_EMBED_MODEL"] = settings.openaiEmbedModel
                    env["ONELENS_EMBED_DIM"] = settings.openaiEmbedDim.toString()
                    com.onelens.plugin.settings.OpenAiSecrets.get()?.let {
                        env["ONELENS_EMBED_API_KEY"] = it
                    }
                }
                else -> {
                    // Dev/legacy path (e.g. "modal") — pass through as-is so
                    // power users can still override via ONELENS_EMBED_BACKEND.
                    env["ONELENS_EMBED_BACKEND"] = settings.embedderBackend
                }
            }
            val process = pb.start()
            val coordinator = SyncCoordinator.getInstance()
            coordinator.setActiveProcess(process)

            // Stream stdout on a daemon thread so the main thread can poll
            // the ProgressIndicator for cancellation — `readLine()` blocks
            // until EOF and there's no interruptible variant on the JVM.
            val output = StringBuilder()
            val reader = Thread({
                try {
                    process.inputStream.bufferedReader().use { r ->
                        while (true) {
                            val line = r.readLine() ?: break
                            synchronized(output) { output.appendLine(line) }
                            publish(OneLensEvent.Info(line))
                        }
                    }
                } catch (_: Exception) { /* stream closed on kill */ }
            }, "onelens-cli-stdout").apply { isDaemon = true; start() }

            val indicator = com.intellij.openapi.progress.ProgressManager.getInstance().progressIndicator
            while (process.isAlive) {
                if (indicator?.isCanceled == true) {
                    publish(OneLensEvent.Warn("Cancelled — killing onelens CLI (pid ${process.pid()})"))
                    // Two-phase kill: SIGTERM first so Python child can
                    // flush Chroma batches + release CUDA contexts
                    // cleanly; SIGKILL only if it ignores us after 10 s.
                    // Re-read descendants between phases because embedder
                    // workers can fork grandchildren after the first
                    // snapshot — a single kill of the initial list leaks
                    // those and pins GPU memory.
                    process.descendants().forEach { it.destroy() }
                    process.destroy()
                    if (!process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)) {
                        publish(OneLensEvent.Warn("CLI did not exit on SIGTERM — sending SIGKILL"))
                        process.descendants().forEach { it.destroyForcibly() }
                        process.destroyForcibly()
                        process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)
                    }
                    runCatching { process.inputStream.close() }
                    reader.join(2000)
                    coordinator.setActiveProcess(null)
                    coordinator.release()
                    throw com.intellij.openapi.progress.ProcessCanceledException()
                }
                process.waitFor(200, java.util.concurrent.TimeUnit.MILLISECONDS)
            }
            val exitCode = process.exitValue()
            reader.join(1000)
            coordinator.setActiveProcess(null)

            return if (exitCode == 0) {
                "Import successful: $output"
            } else {
                LOG.warn("Import failed (exit $exitCode): $output")
                publish(OneLensEvent.Error("CLI import failed (exit $exitCode)"))
                "Import failed (exit $exitCode): $output"
            }
        } catch (e: com.intellij.openapi.progress.ProcessCanceledException) {
            throw e  // Let IntelliJ route to the Backgroundable's cancel path
        } catch (e: java.io.IOException) {
            LOG.warn("Failed to run onelens CLI: ${e.message}")
            SyncCoordinator.getInstance().setActiveProcess(null)
            return null
        } catch (e: Exception) {
            LOG.warn("Auto-import failed: ${e.message}")
            SyncCoordinator.getInstance().setActiveProcess(null)
            return null
        }
    }

    /**
     * TCP ping FalkorDB. Fast (~1-5ms on localhost miss; ~20ms remote).
     * Used as a preflight — if the DB isn't listening, syncing fails with
     * an opaque error deep in the CLI. Better to bail early with a message
     * the user can act on.
     */
    private fun isFalkorDbReachable(config: ExportConfig): Boolean {
        return try {
            java.net.Socket().use { sock ->
                sock.connect(
                    java.net.InetSocketAddress(config.falkordbHost, config.falkordbPort),
                    800
                )
                true
            }
        } catch (_: Exception) {
            false
        }
    }

    sealed class ExportResult {
        data class Success(val path: Path, val stats: ExportStats) : ExportResult()
        data class Error(val message: String) : ExportResult()
    }

    /**
     * Locate registered framework adapters. Falls back to a direct instantiation of
     * [SpringBootAdapter] when the extension point is empty — this happens if
     * `framework-springboot.xml` isn't loaded (Java module absent) or in unit tests
     * where the platform EP registry isn't populated for our EP id. Detection still
     * applies, so a non-Java project simply yields an empty list.
     */
    private fun discoverAdapters(
        project: Project,
        config: ExportConfig
    ): List<FrameworkAdapter> {
        val fromEp = try {
            FrameworkAdapter.EP_NAME.extensionList
        } catch (_: Throwable) {
            emptyList()
        }
        val candidates = if (fromEp.isNotEmpty()) fromEp else listOf(SpringBootAdapter())
        return candidates.filter { it.detect(project) }
    }

    /**
     * Tiny helper so ExportService.exportFull can treat a nullable
     * [SpringBootCollectionResult] as if it always produced empty method / field
     * lists (back-compat for non-Java projects).
     */
    private data class MembersFrom(val result: SpringBootCollectionResult?) {
        val methods: List<MethodData> get() = result?.methods ?: emptyList()
        val fields: List<FieldData> get() = result?.fields ?: emptyList()
    }
}
