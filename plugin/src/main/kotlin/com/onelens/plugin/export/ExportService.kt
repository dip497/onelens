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
        publish(OneLensEvent.Info("Full export starting for ${project.name}"))

        val basePath = project.basePath ?: return ExportResult.Error("Project has no base path")

        // Discover active adapters. EP lookup falls back to a hard-coded list when the
        // extension point hasn't been registered yet (e.g. in tests or if the config-file
        // split isn't loaded). This keeps the existing Java path working unchanged.
        val adapters = discoverAdapters(project, config)
        val activeIds = adapters.map { it.id }
        LOG.info("Active framework adapters: ${activeIds.joinToString(",")}")

        val springResult: SpringBootCollectionResult? = run {
            val springAdapter = adapters.firstOrNull { it is SpringBootAdapter } ?: return@run null
            val collector = springAdapter.collectors().firstOrNull() as? SpringBootCollector ?: return@run null
            collector.collect(CollectContext(project = project, indicator = indicator, progressFraction = 0.0))
            collector.lastResult
        }
        // Legacy behavior preserved when no Spring adapter active: empty Java section.
        val classes = springResult?.classes ?: emptyList()
        val members = MembersFrom(springResult)
        val callGraph = springResult?.callGraph ?: emptyList()
        val inheritanceEdges = springResult?.inheritance ?: emptyList()
        val overrideEdges = springResult?.methodOverrides ?: emptyList()
        val modules = springResult?.modules ?: emptyList()
        val annotations = springResult?.annotations ?: emptyList()
        val spring = if (config.includeSpring) springResult?.spring else null
        val diagnostics = if (config.includeDiagnostics) {
            springResult?.diagnostics ?: emptyList()
        } else emptyList()

        val durationMs = System.currentTimeMillis() - startTime

        // Assemble export document — legacy top-level keys preserved for the existing
        // Python importer. New `adapters` + `vue3` subdoc land alongside (unused in
        // Phase A; populated once Vue3Adapter ships).
        val document = ExportDocument(
            version = OneLensConstants.EXPORT_VERSION,
            exportType = "full",
            timestamp = Instant.now().toString(),
            project = ProjectInfo(
                name = project.name,
                basePath = basePath,
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
                diagnosticCount = diagnostics.size,
                exportDurationMs = durationMs
            ),
            adapters = activeIds.ifEmpty { listOf("spring-boot") }
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
        val fileName = "${project.name}-full-${System.currentTimeMillis()}.json"
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
        publish(OneLensEvent.SyncComplete(
            graphName = project.name,
            classes = document.stats.classCount,
            methods = document.stats.methodCount,
            callEdges = document.stats.callEdgeCount,
            isDelta = false,
            durationMs = durationMs,
        ))

        // Auto-import into graph DB if onelens CLI is available
        if (config.autoImport) {
            val importResult = syncToGraph(outputFile, project.name, config)
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
            val command = mutableListOf(
                cliPath, "import_graph", exportFile.toString(),
                "--graph", graphName,
                "--backend", config.graphBackend,
                "--context"
            )
            if (isFull) {
                command += "--clear"
            }

            LOG.info("Running: ${command.joinToString(" ")}")
            publish(OneLensEvent.Info("$ ${command.joinToString(" ")}"))

            val process = ProcessBuilder(command)
                .redirectErrorStream(true)
                .start()

            // Stream stdout line-by-line so the tool window console updates
            // live during the 30s–20min import (PageRank + embedding pass).
            val output = StringBuilder()
            process.inputStream.bufferedReader().use { reader ->
                while (true) {
                    val line = reader.readLine() ?: break
                    output.appendLine(line)
                    publish(OneLensEvent.Info(line))
                }
            }
            val exitCode = process.waitFor()

            return if (exitCode == 0) {
                "Import successful: $output"
            } else {
                LOG.warn("Import failed (exit $exitCode): $output")
                publish(OneLensEvent.Error("CLI import failed (exit $exitCode)"))
                "Import failed (exit $exitCode): $output"
            }
        } catch (e: java.io.IOException) {
            LOG.warn("Failed to run onelens CLI: ${e.message}")
            return null
        } catch (e: Exception) {
            LOG.warn("Auto-import failed: ${e.message}")
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
