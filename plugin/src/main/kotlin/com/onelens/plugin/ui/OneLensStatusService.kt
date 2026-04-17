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
    val falkordbReachable: Boolean,
    val falkordbHost: String = "localhost",
    val falkordbPort: Int = 17532,
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
        val falkor = isPortOpen("localhost", 17532, 800)
        val uv = locateUv()
        val venv = venvDir.toFile().exists()
        val cli = venvDir.resolve("bin").resolve("onelens").toFile().takeIf { it.exists() }?.absolutePath
        val modal = if (venv) venvHasPackage("modal") else null
        // With the remote backend, models live on Modal — we can't probe
        // from here without an extra CLI round-trip, so leave it unknown.
        val modelsCached: Boolean? = null

        val exports = listExports()
        val exportsSize = exports.sumOf { it.length() }
        val venvSize = if (venv) dirSize(venvDir) else 0L
        // Size just this project's graph drawer (one subdir per graph);
        // falls back to the whole context dir if the per-graph dir is absent.
        val projectContextDir = contextDir.resolve(project.name)
        val chromaSize = when {
            projectContextDir.toFile().exists() -> dirSize(projectContextDir)
            contextDir.toFile().exists() -> dirSize(contextDir)
            else -> 0L
        }

        return OneLensStatus(
            falkordbReachable = falkor,
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
            graphName = project.name,
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
