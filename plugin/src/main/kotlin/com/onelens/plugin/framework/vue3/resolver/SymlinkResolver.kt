package com.onelens.plugin.framework.vue3.resolver

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.LocalFileSystem
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Detects symlinked directories under `src/` whose target lives outside the IntelliJ
 * project's content roots. A real-world example shape we verified against:
 * `src/ui -> ../<sibling-ui-lib>/src` — a sibling repo's source tree that participates
 * in the runtime graph but the IDE won't index unless it's a content root.
 *
 * Phase B Week 1 deliverable: detect + classify. UI balloon that asks the user to add
 * the target as a content root lives in a separate startup activity so tests remain
 * headless.
 */
object SymlinkResolver {
    private val LOG = logger<SymlinkResolver>()

    data class SymlinkEntry(
        /** Symlink path inside the project (e.g. `src/ui`). */
        val linkPath: Path,
        /** Canonical target the link resolves to. */
        val realTarget: Path,
        /** True if [realTarget] is inside an existing IntelliJ content root. */
        val insideContentRoot: Boolean
    )

    /**
     * Walks `src/` (one level deep — symlinks are typically at the top of `src`) and
     * returns everything that is a symlink. Deeper walks aren't worth it: large repos
     * pay too much for rare links. If a collector later needs a deep scan, add an
     * opt-in flag.
     */
    fun scan(project: Project): List<SymlinkEntry> {
        val base = project.basePath ?: return emptyList()
        val srcDir = Paths.get(base, "src")
        if (!Files.isDirectory(srcDir)) return emptyList()

        val roots = contentRoots(project)
        val results = mutableListOf<SymlinkEntry>()
        Files.newDirectoryStream(srcDir).use { stream ->
            for (entry in stream) {
                if (!Files.isSymbolicLink(entry)) continue
                val real = try {
                    entry.toRealPath()
                } catch (_: Throwable) {
                    // Broken symlink — skip; Vue collectors will treat the path as external.
                    LOG.warn("Broken symlink skipped: $entry")
                    continue
                }
                val inside = roots.any { real.startsWith(it) }
                results += SymlinkEntry(entry, real, inside)
            }
        }
        return results
    }

    /**
     * Returns true if any symlink target is outside the project's content roots.
     * Used by the startup balloon to decide whether to prompt the user.
     */
    fun hasOutOfTreeTargets(project: Project): Boolean =
        scan(project).any { !it.insideContentRoot }

    private fun contentRoots(project: Project): List<Path> {
        val vfs = ProjectRootManager.getInstance(project).contentRoots
        return vfs.mapNotNull { file ->
            try { Paths.get(file.path) } catch (_: Throwable) { null }
        }
    }

    /** Convenience: for callers that only want the [LocalFileSystem] representation. */
    fun asVirtualFile(target: Path) = LocalFileSystem.getInstance().findFileByIoFile(target.toFile())
}
