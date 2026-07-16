package com.onelens.plugin.snapshots

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.CapturingProcessHandler
import com.intellij.execution.process.ProcessOutput
import com.intellij.openapi.components.Service
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.PythonEnvManager
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

// Orchestrates OneLens release-snapshot operations. Local-only publish +
// local scan. Delegates bundling to the Python CLI.
// Platform's InstanceContainer inspects the JVM constructor signature and
// refuses anything outside `()` / `(Project)` / `(CoroutineScope)` /
// `(Project, CoroutineScope)`. The previous `(Project, CoroutineScope)`
// compiled but reflective lookup failed at runtime after we pulled Ktor
// (different kotlinx-coroutines-core in the plugin classpath → the
// `CoroutineScope` class the platform binds is not the one the compiler
// picked). Drop the scope param — nothing here used it.
@Service(Service.Level.PROJECT)
class SnapshotManager(
    private val project: Project,
) {

    // Scan ~/.onelens/bundles for onelens-snapshot-<graph>-<tag>.tgz archives.
    fun listPublished(graph: String): List<PublishedBundle> {
        val dir = Paths.get(System.getProperty("user.home"), ".onelens", "bundles")
        if (!Files.isDirectory(dir)) return emptyList()
        val prefix = "onelens-snapshot-$graph-"
        return Files.list(dir).use { paths ->
            paths.toList()
                .filter {
                    Files.isRegularFile(it) &&
                        it.fileName.toString().startsWith(prefix) &&
                        it.fileName.toString().endsWith(".tgz")
                }
                .map { p ->
                    val name = p.fileName.toString()
                    val tag = name.removePrefix(prefix).removeSuffix(".tgz")
                    PublishedBundle(
                        graph = graph,
                        tag = tag,
                        tgzPath = p.toString(),
                        tgzBytes = Files.size(p),
                        lastModified = Files.getLastModifiedTime(p).toMillis(),
                    )
                }
                .sortedByDescending { it.lastModified }
        }
    }

    // Install a published tgz into ~/.onelens/graphs/<graph>@<tag>/ via the
    // onelens CLI (same code path as remote pull, just repo=local).
    fun install(bundle: PublishedBundle, indicator: ProgressIndicator): ProcessOutput {
        val cli = PythonEnvManager.getOneLensCli() ?: throw IllegalStateException(
            "onelens CLI not installed. Run OneLens → Setup / Reinstall first."
        )
        val cmd = GeneralCommandLine(
            cli, "call-tool", "onelens_snapshots_pull",
            "--graph", bundle.graph,
            "--tag", bundle.tag,
            "--repo", "local",
        ).apply { charset = Charsets.UTF_8 }
        indicator.text = "Installing ${bundle.graph}@${bundle.tag}"
        return CapturingProcessHandler(cmd).runProcess(10 * 60 * 1000, true)
    }

    // Scan ~/.onelens/graphs for directories matching <graph>@<tag>.
    fun listLocal(graph: String): List<LocalSnapshot> {
        val home = Paths.get(System.getProperty("user.home"), ".onelens", "graphs")
        if (!Files.isDirectory(home)) return emptyList()
        val prefix = "$graph@"
        return Files.list(home).use { paths ->
            paths.toList()
                .filter { Files.isDirectory(it) && it.fileName.toString().startsWith(prefix) }
                .mapNotNull { toLocal(graph, it) }
                .sortedByDescending { it.lastModified }
        }
    }

    private fun toLocal(graph: String, dir: Path): LocalSnapshot? {
        val tag = dir.fileName.toString().substringAfter("$graph@")
        val rdb = dir.resolve("$graph@$tag.rdb")
        if (!Files.isRegularFile(rdb) || Files.size(rdb) < 10_000) return null
        return LocalSnapshot(
            graph = graph,
            tag = tag,
            rdbPath = rdb.toString(),
            rdbBytes = Files.size(rdb),
            lastModified = Files.getLastModifiedTime(rdb).toMillis(),
        )
    }

    data class PublishArgs(
        val graph: String,
        val tag: String,
        val includeEmbeddings: Boolean,
    )

    // Runs onelens call-tool onelens_snapshot_publish with backend=local.
    fun publish(args: PublishArgs, indicator: ProgressIndicator): ProcessOutput {
        val cli = PythonEnvManager.getOneLensCli() ?: throw IllegalStateException(
            "onelens CLI not installed. Run OneLens → Setup / Reinstall first."
        )
        val cmd = GeneralCommandLine(
            cli, "call-tool", "onelens_snapshot_publish",
            "--graph", args.graph,
            "--tag", args.tag,
            "--backend", "local",
        ).apply {
            // Cyclopts boolean flags: presence = true, don't pass "true" as a
            // separate token or parsing fails with `Unused Tokens: ['true']`.
            if (args.includeEmbeddings) addParameter("--include-embeddings")
            charset = Charsets.UTF_8
        }
        indicator.text = "Publishing snapshot ${args.graph}@${args.tag}"
        return CapturingProcessHandler(cmd).runProcess(30 * 60 * 1000, true)
    }

    companion object {
        fun getInstance(project: Project): SnapshotManager =
            project.getService(SnapshotManager::class.java)
    }
}
