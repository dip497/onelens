package com.onelens.plugin.framework.workspace

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import org.yaml.snakeyaml.Yaml
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Discovers the active [Workspace] for a project:
 *
 *   1. `onelens.workspace.yaml` at project base → parsed explicit workspace.
 *   2. Otherwise → implicit single-root around `project.basePath`.
 *
 * YAML schema (v1) — matches `docs/workspaces.md`:
 *
 * ```yaml
 * version: 1
 * name: myapp
 * graph: myapp
 * roots:
 *   - path: .
 *     buildTool: maven
 *   - path: ../myapp-plugins
 *     buildTool: maven
 * policies:
 *   duplicateFqn: merge
 *   pagerankPerApp: true
 * ```
 */
object WorkspaceLoader {

    private val LOG = logger<WorkspaceLoader>()
    private const val CONFIG_NAME = "onelens.workspace.yaml"

    /**
     * Main entry point. Always returns a workspace — explicit YAML if present,
     * implicit single-root fallback otherwise. Throws on a project with no base
     * path (`project.basePath == null`), which the entry-boundary callers
     * (`ExportService`, `ExportFullAction`, `DeltaExportService`) guard once
     * each so downstream code never sees null.
     */
    fun load(project: Project): Workspace {
        val basePath = requireNotNull(project.basePath) {
            "Project '${project.name}' has no base path — cannot resolve workspace"
        }
        val baseDir = Paths.get(basePath)
        val configFile = baseDir.resolve(CONFIG_NAME)
        if (Files.isRegularFile(configFile)) {
            try {
                val parsed = parseYaml(configFile, baseDir)
                LOG.info("Loaded workspace '${parsed.name}' from $configFile (${parsed.roots.size} roots)")
                return parsed
            } catch (e: Exception) {
                LOG.warn("Failed to parse $configFile: ${e.message} — falling back to implicit workspace", e)
            }
        }
        return Workspace.implicit(project)
    }

    private fun parseYaml(file: Path, baseDir: Path): Workspace {
        val raw: Map<String, Any?> = Files.newBufferedReader(file).use { reader ->
            @Suppress("UNCHECKED_CAST")
            (Yaml().load(reader) as? Map<String, Any?>)
                ?: throw IllegalArgumentException("Top-level YAML must be a mapping")
        }

        val version = (raw["version"] as? Number)?.toInt() ?: 1
        if (version != 1) {
            throw IllegalArgumentException("Unsupported workspace version: $version (expected 1)")
        }

        val name = (raw["name"] as? String)
            ?: throw IllegalArgumentException("`name` is required in $CONFIG_NAME")
        val graphId = (raw["graph"] as? String) ?: name

        @Suppress("UNCHECKED_CAST")
        val rootEntries = (raw["roots"] as? List<Any?>)
            ?: throw IllegalArgumentException("`roots` is required and must be a list")
        if (rootEntries.isEmpty()) {
            throw IllegalArgumentException("`roots` must contain at least one entry")
        }

        val roots = rootEntries.mapIndexed { idx, entry ->
            parseRoot(entry, baseDir, idx)
        }

        @Suppress("UNCHECKED_CAST")
        val policies = (raw["policies"] as? Map<String, Any?>)?.let { parsePolicies(it) }
            ?: Workspace.Policies()

        @Suppress("UNCHECKED_CAST")
        val snapshots = (raw["snapshots"] as? Map<String, Any?>)?.let { parseSnapshots(it) }

        return Workspace(
            name = name,
            graphId = graphId,
            roots = roots,
            policies = policies,
            snapshots = snapshots,
            configFile = file,
        )
    }

    private fun parseSnapshots(map: Map<String, Any?>): Workspace.SnapshotsConfig? {
        val repo = map["repo"] as? String ?: return null
        return Workspace.SnapshotsConfig(repo = repo)
    }

    private fun parseRoot(entry: Any?, baseDir: Path, idx: Int): Workspace.Root {
        @Suppress("UNCHECKED_CAST")
        val map = entry as? Map<String, Any?>
            ?: throw IllegalArgumentException("roots[$idx] must be a mapping")
        val pathStr = map["path"] as? String
            ?: throw IllegalArgumentException("roots[$idx].path is required")
        // Resolve relative paths against the workspace yaml's directory, then
        // normalise — this is what makes `../sibling-repo` work.
        val resolved = baseDir.resolve(pathStr).normalize().toAbsolutePath()
        val buildTool = (map["buildTool"] as? String) ?: "auto"
        @Suppress("UNCHECKED_CAST")
        val include = (map["include"] as? List<String>) ?: emptyList()
        return Workspace.Root(path = resolved, buildTool = buildTool, include = include)
    }

    private fun parsePolicies(map: Map<String, Any?>): Workspace.Policies {
        return Workspace.Policies(
            duplicateFqn = (map["duplicateFqn"] as? String) ?: "merge",
            deltaTracker = (map["deltaTracker"] as? String) ?: "git-multi",
            pagerankPerApp = (map["pagerankPerApp"] as? Boolean) ?: false,
        )
    }
}
