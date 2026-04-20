package com.onelens.plugin.ui

import com.intellij.openapi.components.Service
import com.intellij.openapi.project.Project
import java.io.File
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Snapshot of the OneLens environment that the tool window renders.
 *
 * Each field is computed synchronously but cheaply; callers run us on a pooled
 * thread from the UI refresh action.
 */
data class OneLensStatus(
    val backend: String,               // "falkordblite" | "falkordb"
    val falkordbReachable: Boolean,    // lite: rdb exists; docker: TCP probe
    val falkordbHost: String = "localhost",
    val falkordbPort: Int = 17532,
    val liteRdbPath: String? = null,   // lite only — path to graph's .rdb
    val liteRdbSizeBytes: Long = 0L,
    val uvPath: String?,
    val venvExists: Boolean,
    val cliPath: String?,
    val modalAvailable: Boolean?,     // null = not checked (no venv yet); false = modal SDK missing
    val modelsCached: Boolean?,        // reported by remote app; null = unknown from local
    val exportsSizeBytes: Long,
    val venvSizeBytes: Long,
    val chromaSizeBytes: Long,
    val exportCount: Int,
    val lastExportTimestamp: Long?,
    val graphName: String?,
    val semanticEnabled: Boolean = false,
)

@Service(Service.Level.PROJECT)
class OneLensStatusService(private val project: Project) {

    private val onelensHome: Path = Paths.get(System.getProperty("user.home"), ".onelens")
    private val venvDir: Path = onelensHome.resolve("venv")
    private val exportsDir: Path = onelensHome.resolve("exports")
    // ChromaDB persists to `~/.onelens/context/<graph>/` (see
    // python/src/onelens/context/config.py). One dir per graph name.
    private val contextDir: Path = onelensHome.resolve("context")

    fun snapshot(): OneLensStatus {
        val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
        val backend = settings.graphBackend
        val uv = locateUv()
        val venv = venvDir.toFile().exists()
        val cli = venvDir.resolve("bin").resolve("onelens").toFile().takeIf { it.exists() }?.absolutePath
        val modal = if (venv) venvHasPackage("modal") else null
        // With the remote backend, models live on Modal — we can't probe
        // from here without an extra CLI round-trip, so leave it unknown.
        val modelsCached: Boolean? = null

        // Derive graph name from the workspace (explicit `onelens.workspace.yaml`
        // or implicit single-root fallback). Falls back to project.name only if
        // workspace resolution fails at session start.
        val graphId = try {
            com.onelens.plugin.framework.workspace.WorkspaceLoader.load(project).graphId
        } catch (_: Exception) { project.name }

        val exports = listExports()
        val exportsSize = exports.sumOf { it.length() }
        val venvSize = if (venv) dirSize(venvDir) else 0L
        // Size just this graph's drawer (one subdir per graph); falls back to
        // the whole context dir if the per-graph dir is absent.
        val projectContextDir = contextDir.resolve(graphId)
        val chromaSize = when {
            projectContextDir.toFile().exists() -> dirSize(projectContextDir)
            contextDir.toFile().exists() -> dirSize(contextDir)
            else -> 0L
        }

        // Backend health: lite probes the on-disk rdb; docker probes the port.
        val liteRdb = onelensHome.resolve("graphs").resolve(graphId).resolve("$graphId.rdb").toFile()
        val liteRdbExists = liteRdb.exists() && liteRdb.length() > 0
        val reachable = when (backend) {
            "falkordblite" -> liteRdbExists
            else -> isPortOpen("localhost", 17532, 800)
        }

        return OneLensStatus(
            backend = backend,
            falkordbReachable = reachable,
            liteRdbPath = liteRdb.absolutePath.takeIf { backend == "falkordblite" },
            liteRdbSizeBytes = if (liteRdbExists) liteRdb.length() else 0L,
            uvPath = uv,
            venvExists = venv,
            cliPath = cli,
            modalAvailable = modal,
            modelsCached = modelsCached,
            exportsSizeBytes = exportsSize,
            venvSizeBytes = venvSize,
            chromaSizeBytes = chromaSize,
            exportCount = exports.size,
            lastExportTimestamp = exports.maxOfOrNull { it.lastModified() },
            graphName = graphId,
            semanticEnabled = settings.buildSemanticIndex,
        )
    }

    private fun isPortOpen(host: String, port: Int, timeoutMs: Int): Boolean = try {
        Socket().use { it.connect(InetSocketAddress(host, port), timeoutMs); true }
    } catch (_: Exception) { false }

    private fun locateUv(): String? {
        val home = System.getProperty("user.home")
        val candidates = listOf(
            "$home/.local/bin/uv", "$home/.cargo/bin/uv",
            "/usr/local/bin/uv", "/usr/bin/uv",
            "/home/linuxbrew/.linuxbrew/bin/uv", "$home/.linuxbrew/bin/uv",
        )
        return candidates.firstOrNull { File(it).canExecute() }
    }

    private fun venvHasPackage(name: String): Boolean {
        // Cheap heuristic: check `venv/lib/python*/site-packages/<name>` dir.
        // Avoid running the venv's python to stay off the UI thread's critical path.
        val siteDirs = venvDir.resolve("lib").toFile().listFiles { f -> f.isDirectory && f.name.startsWith("python") }
            ?: return false
        return siteDirs.any { File(it, "site-packages/$name").exists() }
    }

    // Dropped checkModelsCached — with the remote backend, weights live on
    // Modal (or the OpenAI-compat provider). Locally there's nothing to probe.

    private fun listExports(): List<File> {
        val dir = exportsDir.toFile()
        if (!dir.exists()) return emptyList()
        return dir.listFiles { f -> f.isFile && f.name.endsWith(".json") }?.toList() ?: emptyList()
    }

    private fun dirSize(path: Path): Long = try {
        Files.walk(path).use { s -> s.filter { Files.isRegularFile(it) }.mapToLong { Files.size(it) }.sum() }
    } catch (_: Exception) { 0L }

    companion object {
        fun getInstance(project: Project): OneLensStatusService =
            project.getService(OneLensStatusService::class.java)
    }
}
