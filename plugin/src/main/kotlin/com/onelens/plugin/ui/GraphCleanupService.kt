package com.onelens.plugin.ui

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.logger
import com.onelens.plugin.mcp.OneLensMcpService
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.io.path.deleteRecursively

/**
 * Destructive project-cleanup operations exposed from the Status tab's
 * "Danger zone" section. Each method is idempotent — missing paths are
 * silent no-ops — and returns a [CleanupResult] the UI can surface.
 *
 * Scope is ~/.onelens/ only; nothing under the user's project dir is
 * touched. Every operation that invalidates an in-memory MCP server
 * (delete graph, reset semantic) also restarts the server so the next
 * sync comes up against fresh state.
 */
@Service(Service.Level.APP)
class GraphCleanupService {

    companion object {
        private val LOG = logger<GraphCleanupService>()
        private val ONELENS_HOME: Path = Paths.get(System.getProperty("user.home"), ".onelens")
        fun getInstance(): GraphCleanupService = ApplicationManager.getApplication().service()
    }

    data class CleanupResult(val description: String, val bytesFreed: Long)

    /** Delete every JSON export for [graph] in ~/.onelens/exports/. */
    fun clearExports(graph: String): CleanupResult {
        val dir = ONELENS_HOME.resolve("exports")
        if (!Files.isDirectory(dir)) return CleanupResult("No exports directory", 0L)
        val matching = Files.list(dir).use { stream ->
            stream.toList().filter {
                val n = it.fileName.toString()
                n.startsWith("$graph-") && n.endsWith(".json")
            }
        }
        var bytes = 0L
        for (p in matching) {
            bytes += runCatching { Files.size(p) }.getOrDefault(0L)
            runCatching { Files.deleteIfExists(p) }
        }
        LOG.info("Cleared ${matching.size} exports for '$graph' ($bytes bytes)")
        return CleanupResult("${matching.size} export(s)", bytes)
    }

    /**
     * Wipe the FalkorDB Lite rdb + graph dir + auto-sync baseline marker.
     * Stops the MCP server first to release its file handles on the rdb.
     * Caller is responsible for re-syncing — this leaves the graph empty.
     */
    @OptIn(kotlin.io.path.ExperimentalPathApi::class)
    fun deleteGraph(graph: String): CleanupResult {
        // MCP holds the rdb open through FalkorDB Lite. Stop before delete
        // so the OS can actually release the inode on Linux.
        val mcp = OneLensMcpService.getInstance()
        val wasRunning = mcp.isRunning
        mcp.stop()

        val dir = ONELENS_HOME.resolve("graphs").resolve(graph)
        val result = if (!Files.isDirectory(dir)) {
            CleanupResult("No graph directory", 0L)
        } else {
            val size = sumTree(dir)
            try { dir.deleteRecursively() } catch (e: Exception) {
                LOG.warn("Could not fully delete $dir: ${e.message}")
            }
            LOG.info("Deleted graph '$graph' (~$size bytes)")
            CleanupResult("graph dir", size)
        }

        // Restart MCP if it was running AND semantic is still enabled —
        // otherwise the user is left with "Semantic: on · MCP not running"
        // until they next sync, which is surprising after a cleanup op.
        if (wasRunning &&
            com.onelens.plugin.settings.OneLensSettings.getInstance().state.buildSemanticIndex) {
            mcp.start()
        }
        return result
    }

    /**
     * Wipe the ChromaDB collection for [graph] + the shared TRT engine
     * cache. Forces the next semantic sync to rebuild embeddings AND
     * rebuild the TRT fp16 engine (since engine files are weight-bound).
     */
    @OptIn(kotlin.io.path.ExperimentalPathApi::class)
    fun resetSemantic(graph: String): CleanupResult {
        val mcp = OneLensMcpService.getInstance()
        val wasRunning = mcp.isRunning
        mcp.stop()

        var bytes = 0L
        val ctxDir = ONELENS_HOME.resolve("context").resolve(graph)
        if (Files.isDirectory(ctxDir)) {
            bytes += sumTree(ctxDir)
            runCatching { ctxDir.deleteRecursively() }
        }
        val trtCache = ONELENS_HOME.resolve("trt-cache")
        if (Files.isDirectory(trtCache)) {
            bytes += sumTree(trtCache)
            runCatching { trtCache.deleteRecursively() }
        }
        LOG.info("Reset semantic state for '$graph' ($bytes bytes)")

        // Re-warm MCP so subsequent sync picks up hot providers again —
        // TRT engines will rebuild on first call (cache was just wiped),
        // but at least the Python process + models stay loaded.
        if (wasRunning &&
            com.onelens.plugin.settings.OneLensSettings.getInstance().state.buildSemanticIndex) {
            mcp.start()
        }
        return CleanupResult("ChromaDB + TRT cache", bytes)
    }

    private fun sumTree(root: Path): Long = runCatching {
        Files.walk(root).use { stream ->
            stream.filter { Files.isRegularFile(it) }
                .mapToLong { runCatching { Files.size(it) }.getOrDefault(0L) }
                .sum()
        }
    }.getOrDefault(0L)
}
