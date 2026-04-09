package com.onelens.plugin.export

import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.OneLensConstants
import com.onelens.plugin.export.collectors.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
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

        val basePath = project.basePath ?: return ExportResult.Error("Project has no base path")

        // Step 1/7: Classes
        indicator?.text = "Step 1/7: Collecting classes..."
        indicator?.fraction = 0.0
        val classes = ClassCollector.collect(project)
        LOG.info("Collected ${classes.size} classes")

        // Step 2/7: Methods & Fields
        indicator?.text = "Step 2/7: Collecting methods & fields (${classes.size} classes)..."
        indicator?.fraction = 0.15
        val members = MemberCollector.collect(project, classes)
        LOG.info("Collected ${members.methods.size} methods, ${members.fields.size} fields")

        // Step 3/7: Call Graph (heaviest step)
        indicator?.text = "Step 3/7: Resolving call graph..."
        indicator?.fraction = 0.30
        val callGraph = CallGraphCollector.collect(project, classes)
        LOG.info("Collected ${callGraph.size} call edges")

        // Step 4/7: Inheritance
        indicator?.text = "Step 4/7: Collecting inheritance & overrides..."
        indicator?.fraction = 0.60
        val inheritance = InheritanceCollector.collect(project, classes)
        LOG.info("Collected ${inheritance.edges.size} inheritance edges, ${inheritance.overrides.size} overrides")

        // Step 5/7: Modules
        indicator?.text = "Step 5/7: Collecting modules..."
        indicator?.fraction = 0.75
        val modules = ModuleCollector.collect(project)
        LOG.info("Collected ${modules.size} modules")

        // Step 6/7: Annotations
        indicator?.text = "Step 6/7: Collecting annotations..."
        indicator?.fraction = 0.80
        val annotations = AnnotationCollector.collect(project, classes)
        LOG.info("Collected ${annotations.size} annotation usages")

        // Step 7/7: Spring (optional)
        indicator?.text = "Step 7/7: Collecting Spring beans & endpoints..."
        indicator?.fraction = 0.90
        val spring = if (config.includeSpring) {
            SpringCollector.collect(project)
        } else null

        val diagnostics = if (config.includeDiagnostics) {
            DiagnosticsCollector.collect(project)
        } else emptyList()

        val durationMs = System.currentTimeMillis() - startTime

        // Assemble export document
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
            inheritance = inheritance.edges,
            methodOverrides = inheritance.overrides,
            spring = spring,
            modules = modules,
            annotations = annotations,
            diagnostics = diagnostics,
            stats = ExportStats(
                classCount = classes.size,
                methodCount = members.methods.size,
                fieldCount = members.fields.size,
                callEdgeCount = callGraph.size,
                inheritanceEdgeCount = inheritance.edges.size,
                overrideCount = inheritance.overrides.size,
                springBeanCount = spring?.beans?.size ?: 0,
                endpointCount = spring?.endpoints?.size ?: 0,
                moduleCount = modules.size,
                annotationUsageCount = annotations.size,
                diagnosticCount = diagnostics.size,
                exportDurationMs = durationMs
            )
        )

        // Write JSON
        indicator?.text = "Writing JSON export..."
        indicator?.fraction = 0.95
        val outputDir = config.outputPath
        Files.createDirectories(outputDir)
        val fileName = "${project.name}-full-${System.currentTimeMillis()}.json"
        val outputFile = outputDir.resolve(fileName)
        Files.writeString(outputFile, json.encodeToString(document))

        // Update state
        val state = ExportState.getInstance(project)
        state.state.lastExportTimestamp = System.currentTimeMillis()
        state.state.lastExportPath = outputFile.toString()

        LOG.info("Full export complete: $outputFile (${durationMs}ms)")

        // Auto-import into graph DB if onelens CLI is available
        if (config.autoImport) {
            val importResult = syncToGraph(outputFile, project.name, config)
            if (importResult != null) {
                LOG.info("Auto-import: $importResult")
            }
        }

        return ExportResult.Success(outputFile, document.stats)
    }

    /**
     * Run `onelens import` to sync the exported JSON into the graph DB.
     * Auto-installs onelens CLI via uv if not found.
     * Returns the CLI output, or null if setup failed.
     */
    fun syncToGraph(exportFile: Path, graphName: String, config: ExportConfig): String? {
        // Auto-setup: ensure onelens CLI is installed
        val cliPath = PythonEnvManager.getOneLensCli(config.onelensSourcePath)
        if (cliPath == null) {
            LOG.warn("Could not set up OneLens CLI — Python or uv not found")
            return null
        }

        try {
            val command = mutableListOf(
                cliPath, "import", exportFile.toString(),
                "--graph", graphName,
                "--backend", config.graphBackend,
                "--clear"
            )

            LOG.info("Running: ${command.joinToString(" ")}")

            val process = ProcessBuilder(command)
                .redirectErrorStream(true)
                .start()

            val output = process.inputStream.bufferedReader().readText()
            val exitCode = process.waitFor()

            return if (exitCode == 0) {
                "Import successful: $output"
            } else {
                LOG.warn("Import failed (exit $exitCode): $output")
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

    sealed class ExportResult {
        data class Success(val path: Path, val stats: ExportStats) : ExportResult()
        data class Error(val message: String) : ExportResult()
    }
}
