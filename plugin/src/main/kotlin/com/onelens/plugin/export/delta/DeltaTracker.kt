package com.onelens.plugin.export.delta

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vcs.changes.ChangeListManager
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.onelens.plugin.export.ExportState
import java.io.File

/**
 * Tracks which files have changed since the last export.
 *
 * Uses three sources (in priority order):
 * 1. Git diff: committed changes since last export's git hash
 * 2. ChangeListManager: uncommitted changes (working tree + staged)
 * 3. VFS timestamps: fallback if no VCS
 *
 * Returns a ChangedFiles result with added/modified/deleted file paths.
 */
object DeltaTracker {

    private val LOG = logger<DeltaTracker>()

    data class ChangedFiles(
        val modified: List<String>,   // Changed or added .java files (relative paths)
        val deleted: List<String>,    // Deleted .java files (relative paths)
        val isFullReexport: Boolean   // True if we can't determine delta (first export, etc.)
    ) {
        val hasChanges: Boolean get() = modified.isNotEmpty() || deleted.isNotEmpty()
        val totalChanges: Int get() = modified.size + deleted.size
    }

    /**
     * Determine which Java files changed since the last export.
     */
    fun getChangedFiles(project: Project): ChangedFiles {
        val state = ExportState.getInstance(project)
        val basePath = project.basePath ?: return fullReexport("No project base path")

        // No previous export → full re-export needed
        if (state.state.lastExportTimestamp == 0L) {
            return fullReexport("No previous export found")
        }

        val lastGitHash = state.state.lastGitHash
        val lastTimestamp = state.state.lastExportTimestamp

        // Try git diff first (most accurate)
        if (lastGitHash.isNotEmpty()) {
            val gitResult = getGitChanges(basePath, lastGitHash)
            if (gitResult != null) {
                // Also add uncommitted changes from ChangeListManager
                val uncommitted = getUncommittedChanges(project, basePath)
                val allModified = (gitResult.modified + uncommitted.modified).distinct()
                val allDeleted = (gitResult.deleted + uncommitted.deleted).distinct()

                LOG.info("Delta: ${allModified.size} modified, ${allDeleted.size} deleted (git + uncommitted)")
                return ChangedFiles(
                    modified = allModified,
                    deleted = allDeleted,
                    isFullReexport = false
                )
            }
        }

        // Fallback: use ChangeListManager only (uncommitted changes)
        val uncommitted = getUncommittedChanges(project, basePath)
        if (uncommitted.hasChanges) {
            LOG.info("Delta (uncommitted only): ${uncommitted.modified.size} modified, ${uncommitted.deleted.size} deleted")
            return uncommitted
        }

        // Fallback: VFS timestamp comparison
        return getVfsChanges(project, basePath, lastTimestamp)
    }

    /**
     * Get current git HEAD hash for storing in export state.
     */
    fun getCurrentGitHash(basePath: String): String {
        return try {
            val process = ProcessBuilder("git", "rev-parse", "HEAD")
                .directory(File(basePath))
                .redirectErrorStream(true)
                .start()
            val hash = process.inputStream.bufferedReader().readText().trim()
            process.waitFor()
            if (hash.length == 40) hash else ""
        } catch (_: Exception) {
            ""
        }
    }

    /**
     * Use git diff to find changes since last export.
     */
    private fun getGitChanges(basePath: String, sinceHash: String): ChangedFiles? {
        return try {
            // Get modified/added files
            val diffProcess = ProcessBuilder(
                "git", "diff", "--name-status", sinceHash, "HEAD"
            )
                .directory(File(basePath))
                .redirectErrorStream(true)
                .start()

            val output = diffProcess.inputStream.bufferedReader().readText()
            val exitCode = diffProcess.waitFor()

            if (exitCode != 0) {
                LOG.warn("git diff failed (exit $exitCode): $output")
                return null
            }

            val modified = mutableListOf<String>()
            val deleted = mutableListOf<String>()

            for (line in output.lines()) {
                if (line.isBlank()) continue
                val parts = line.split("\t", limit = 2)
                if (parts.size < 2) continue

                val status = parts[0].trim()
                val filePath = parts[1].trim()

                // Only track Java files
                if (!filePath.endsWith(".java")) continue

                when {
                    status.startsWith("D") -> deleted.add(filePath)
                    status.startsWith("A") || status.startsWith("M") || status.startsWith("R") -> modified.add(filePath)
                }
            }

            ChangedFiles(modified = modified, deleted = deleted, isFullReexport = false)
        } catch (e: Exception) {
            LOG.warn("git diff failed: ${e.message}")
            null
        }
    }

    /**
     * Get uncommitted changes from IntelliJ's ChangeListManager.
     * This includes staged + unstaged changes (what you see in Commit panel).
     */
    private fun getUncommittedChanges(project: Project, basePath: String): ChangedFiles {
        val modified = mutableListOf<String>()
        val deleted = mutableListOf<String>()

        try {
            val changeListManager = ChangeListManager.getInstance(project)
            for (change in changeListManager.allChanges) {
                val afterPath = change.afterRevision?.file?.path
                val beforePath = change.beforeRevision?.file?.path

                when (change.type) {
                    com.intellij.openapi.vcs.changes.Change.Type.NEW,
                    com.intellij.openapi.vcs.changes.Change.Type.MODIFICATION,
                    com.intellij.openapi.vcs.changes.Change.Type.MOVED -> {
                        if (afterPath != null && afterPath.endsWith(".java")) {
                            val relative = afterPath.removePrefix(basePath).removePrefix("/")
                            modified.add(relative)
                        }
                    }
                    com.intellij.openapi.vcs.changes.Change.Type.DELETED -> {
                        if (beforePath != null && beforePath.endsWith(".java")) {
                            val relative = beforePath.removePrefix(basePath).removePrefix("/")
                            deleted.add(relative)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            LOG.debug("ChangeListManager not available: ${e.message}")
        }

        return ChangedFiles(modified = modified, deleted = deleted, isFullReexport = false)
    }

    /**
     * Fallback: compare VFS timestamps against last export timestamp.
     */
    private fun getVfsChanges(project: Project, basePath: String, sinceTimestamp: Long): ChangedFiles {
        val modified = mutableListOf<String>()

        val baseDir = LocalFileSystem.getInstance().findFileByPath(basePath) ?: return fullReexport("Cannot find project dir")

        fun walk(dir: VirtualFile) {
            for (child in dir.children) {
                if (child.isDirectory) {
                    if (child.name != ".git" && child.name != "build" && child.name != "target") {
                        walk(child)
                    }
                } else if (child.name.endsWith(".java") && child.timeStamp > sinceTimestamp) {
                    val relative = child.path.removePrefix(basePath).removePrefix("/")
                    modified.add(relative)
                }
            }
        }

        walk(baseDir)
        LOG.info("VFS delta: ${modified.size} files modified since last export")
        return ChangedFiles(modified = modified, deleted = emptyList(), isFullReexport = false)
    }

    private fun fullReexport(reason: String): ChangedFiles {
        LOG.info("Full re-export needed: $reason")
        return ChangedFiles(modified = emptyList(), deleted = emptyList(), isFullReexport = true)
    }
}
