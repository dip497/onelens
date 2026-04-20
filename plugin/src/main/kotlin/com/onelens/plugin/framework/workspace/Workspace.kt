package com.onelens.plugin.framework.workspace

import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.GlobalSearchScopesCore
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Adapter-agnostic indexing unit. Generalises `project.basePath` + `projectScope(project)`
 * so a single export can span N Maven/Gradle module trees, sibling repos, or mixed stacks
 * (JVM + Vue3).
 *
 * Three root-level contracts:
 *   - [scope] — GlobalSearchScope union across every root directory. Collectors must use
 *     this instead of `GlobalSearchScope.projectScope(project)`; only files under a
 *     workspace root participate in the export.
 *   - [relativePath] — stable project-relative string for a `VirtualFile` or absolute
 *     path string. Used for `filePath` fields in ClassData / ComponentData / etc.
 *   - [id] — graph name. Falls back to `workspace.name`, else IntelliJ project name.
 *
 * Explicit multi-root config comes from `onelens.workspace.yaml`; absent that, an
 * implicit single-root workspace around `project.basePath` is returned — preserves
 * existing single-module behaviour byte-for-byte.
 */
data class Workspace(
    val name: String,
    val graphId: String,
    val roots: List<Root>,
    val policies: Policies = Policies(),
    /** Optional release-snapshots config — enables Snapshots tool window when set. */
    val snapshots: SnapshotsConfig? = null,
    /** Source of the definition, for logs/diagnostics. Null = implicit fallback. */
    val configFile: Path? = null,
) {
    data class SnapshotsConfig(
        /** GitHub repo in `<org>/<name>` form that hosts release snapshots. */
        val repo: String,
    )

    data class Root(
        /** Canonical absolute path. */
        val path: Path,
        /** "maven" | "gradle" | "vue" | "auto" (detect from files). */
        val buildTool: String = "auto",
        /** Optional glob includes — e.g. a list like `[ '* /pom.xml' ]` for sibling-repo roots. */
        val include: List<String> = emptyList(),
    )

    data class Policies(
        /** merge | warn | error | suffix-by-module. Loader-side honoured. */
        val duplicateFqn: String = "merge",
        val deltaTracker: String = "git-multi",
        val pagerankPerApp: Boolean = false,
    )

    /**
     * GlobalSearchScope union across every root directory. Uses
     * [GlobalSearchScopesCore.directoriesScope] so IntelliJ's index infra handles
     * containment via its own file-based index — no manual VFS child walking, no
     * `IndexNotReadyException` risk during dumb mode (the scope itself never
     * queries indexes; the collectors that USE it do, but that's guarded at the
     * entry boundary via `DumbService.waitForSmartMode`).
     */
    fun scope(project: Project): GlobalSearchScope {
        val vfs = LocalFileSystem.getInstance()
        val rootDirs = roots.mapNotNull { vfs.findFileByPath(it.path.toString()) }
            .filter { it.isDirectory }
            .toTypedArray()
        if (rootDirs.isEmpty()) {
            // Lost every root (deleted / permission). Falling back to projectScope
            // would quietly mis-scope a multi-root workspace; error out loudly
            // instead so the user learns their yaml points at nothing real.
            return GlobalSearchScope.EMPTY_SCOPE
        }
        return GlobalSearchScopesCore.directoriesScope(project, true, *rootDirs)
    }

    /**
     * Project-relative path string. Tries each root in order; first prefix match
     * wins. Absolute paths outside every root fall through unchanged (external
     * library sources stay absolute). Canonicalises separators to `/`.
     */
    fun relativePath(file: VirtualFile): String = relativePath(file.path)

    fun relativePath(absolute: String): String {
        val normalized = absolute.replace('\\', '/')
        for (root in roots) {
            val rootStr = root.path.toString().replace('\\', '/')
            if (normalized == rootStr) return ""
            val prefix = "$rootStr/"
            if (normalized.startsWith(prefix)) {
                return normalized.substring(prefix.length)
            }
        }
        return normalized.removePrefix("/")
    }

    /** Predicate: does any root contain [absolute]? Used for delta filtering. */
    fun contains(absolute: String): Boolean {
        val normalized = absolute.replace('\\', '/')
        return roots.any { r ->
            val rs = r.path.toString().replace('\\', '/')
            normalized == rs || normalized.startsWith("$rs/")
        }
    }

    /** Primary root — first entry. Used as the base for ProjectInfo.basePath. */
    val primaryRoot: Path get() = roots.first().path

    companion object {
        /**
         * Implicit single-root workspace built from `project.basePath`. Zero-config
         * default — existing single-repo users see no change. Throws on a project
         * with no base path because we have nothing meaningful to scope against;
         * callers handle that at the entry boundary (one place, not every
         * collector).
         */
        fun implicit(project: Project): Workspace {
            val base = requireNotNull(project.basePath) {
                "Project '${project.name}' has no base path — cannot build a workspace"
            }
            return Workspace(
                name = project.name,
                graphId = project.name,
                roots = listOf(Root(path = Paths.get(base), buildTool = "auto")),
                configFile = null,
            )
        }
    }
}
