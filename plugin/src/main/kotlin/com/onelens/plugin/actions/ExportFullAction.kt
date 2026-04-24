package com.onelens.plugin.actions

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.DumbAwareAction
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.DumbService
import com.onelens.plugin.OneLensConstants
import com.onelens.plugin.export.ExportConfig
import com.onelens.plugin.export.ExportService
import com.onelens.plugin.export.ExportState
import com.onelens.plugin.export.delta.DeltaExportService
import com.onelens.plugin.export.delta.DeltaTracker
import com.onelens.plugin.framework.workspace.Workspace
import com.onelens.plugin.framework.workspace.WorkspaceLoader

/**
 * Smart sync action — automatically decides between full export and delta.
 *
 * Logic:
 *   1. No previous export → full export
 *   2. Branch changed → full export
 *   3. No changes → "Already up to date"
 *   4. Changes detected → delta export
 *   5. Too many changes (>30%) → full export (faster)
 *
 * After export, auto-imports into graph DB via `onelens` CLI.
 */
/**
 * [DumbAwareAction] so IntelliJ doesn't grey out the Sync Graph button during
 * indexing. The action itself still bails cleanly if invoked mid-indexing (see
 * the `DumbService.isDumb` guard in [actionPerformed]) and the deeper sync path
 * calls `waitForSmartMode()` before running PSI-heavy collectors. Without
 * `DumbAware`, non-DumbAware actions sometimes stay stuck-disabled after a
 * failed click during indexing — the user reported exactly that.
 */
class ExportFullAction : DumbAwareAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        if (DumbService.isDumb(project)) {
            notify(project, "OneLens: IDE is still indexing. Please wait.", NotificationType.WARNING)
            return
        }

        val coordinator = com.onelens.plugin.export.SyncCoordinator.getInstance()
        if (!coordinator.tryAcquire()) {
            notify(project, "OneLens: A sync is already running. Stop it from the Background Tasks widget first.", NotificationType.WARNING)
            return
        }
        // Wrap ProgressManager.run so a submission failure (rejected task,
        // RuntimeException before run() starts) does not leak the
        // coordinator slot — onFinished() only fires if the task actually
        // executed, so a throw on submit would strand `running=true` until
        // IDE restart.
        val task = object : Task.Backgroundable(project, "OneLens: Syncing Graph", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = false
                val service = ApplicationManager.getApplication().getService(ExportService::class.java)
                val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
                val config = ExportConfig(
                    buildSemanticIndex = settings.buildSemanticIndex,
                    graphBackend = settings.graphBackend,
                )
                val state = ExportState.getInstance(project)
                // Workspace is authoritative; primary root carries the git hash
                // we track for delta. Secondary roots = known C1.1 limitation.
                val workspace = try {
                    WorkspaceLoader.load(project)
                } catch (_: Exception) { return }
                val basePath = workspace.primaryRoot.toString()

                // Decide: full or delta?
                val hasPreviousExport = state.state.lastExportTimestamp > 0
                val lastExportExists = state.state.lastExportPath.isNotEmpty() &&
                    java.io.File(state.state.lastExportPath).exists()

                if (!hasPreviousExport || !lastExportExists) {
                    // First time OR last export file missing → full export
                    state.state.lastExportTimestamp = 0  // reset stale state
                    state.state.lastGitHash = ""
                    state.state.fileHashes.clear()
                    indicator.text = "Full export — collecting all code intelligence..."
                    doFullExport(service, project, workspace, config, indicator)
                    return
                }

                // Check if branch changed
                val currentHash = DeltaTracker.getCurrentGitHash(basePath)
                val lastBranch = state.state.lastGitHash
                if (currentHash.isNotEmpty() && lastBranch.isNotEmpty()) {
                    // Check if last hash is still an ancestor of current HEAD
                    val isAncestor = try {
                        val proc = ProcessBuilder("git", "merge-base", "--is-ancestor", lastBranch, currentHash)
                            .directory(java.io.File(basePath))
                            .start()
                        proc.waitFor() == 0
                    } catch (_: Exception) { true }

                    if (!isAncestor) {
                        // Branch was reset/rebased/switched → full export
                        indicator.text = "Branch changed — full re-export..."
                        notify(project, "Branch changed since last export. Running full sync.", NotificationType.INFORMATION)
                        doFullExport(service, project, workspace, config, indicator)
                        return
                    }
                }

                // Check for changes
                indicator.text = "Checking for changes..."
                val changedFiles = DeltaTracker.getChangedFiles(project)

                if (changedFiles.isFullReexport) {
                    indicator.text = "Full re-export needed..."
                    doFullExport(service, project, workspace, config, indicator)
                    return
                }

                if (!changedFiles.hasChanges) {
                    notify(project, "OneLens: Already up to date. No changes since last export.", NotificationType.INFORMATION)
                    return
                }

                // Too many changes? Full export is faster
                val totalProjectFiles = workspace.roots.sumOf { countJavaFiles(it.path.toString()) }
                if (totalProjectFiles > 0 && changedFiles.totalChanges.toFloat() / totalProjectFiles > 0.30) {
                    indicator.text = "${changedFiles.totalChanges} files changed (>30%) — full re-export..."
                    doFullExport(service, project, workspace, config, indicator)
                    return
                }

                // Delta export
                indicator.text = "Delta sync: ${changedFiles.totalChanges} files changed..."
                doDeltaExport(project, workspace, config, indicator)
            }
            override fun onFinished() {
                coordinator.release()
            }
            override fun onCancel() {
                coordinator.killActive()
                com.onelens.plugin.ui.OneLensEvents.publish(com.onelens.plugin.ui.OneLensEvent.Warn("Sync cancelled by user"))
            }
        }
        try {
            ProgressManager.getInstance().run(task)
        } catch (t: Throwable) {
            coordinator.release()
            throw t
        }
    }

    private fun doFullExport(
        service: ExportService,
        project: com.intellij.openapi.project.Project,
        workspace: Workspace,
        config: ExportConfig,
        indicator: ProgressIndicator
    ) {
        val result = service.exportFull(project, config, indicator)

        // Store git hash against the primary root + graph id from workspace.
        val state = ExportState.getInstance(project)
        val gitHash = DeltaTracker.getCurrentGitHash(workspace.primaryRoot.toString())
        if (gitHash.isNotEmpty()) state.state.lastGitHash = gitHash
        state.state.lastGraphName = workspace.graphId

        when (result) {
            is ExportService.ExportResult.Success -> {
                // Store file→class mapping for future delta
                storeFileClassMapping(result.path, state)

                val stats = result.stats
                notify(project,
                    "OneLens Sync Complete (full)\n" +
                        "${stats.classCount} classes, ${stats.methodCount} methods, ${stats.callEdgeCount} calls\n" +
                        "${stats.inheritanceEdgeCount} inheritance, ${stats.overrideCount} overrides" +
                        (if (stats.springBeanCount > 0) "\n${stats.springBeanCount} beans, ${stats.endpointCount} endpoints" else ""),
                    NotificationType.INFORMATION
                )
            }
            is ExportService.ExportResult.Error -> {
                notify(project, "OneLens Sync Failed: ${result.message}", NotificationType.ERROR)
            }
        }
    }

    private fun doDeltaExport(
        project: com.intellij.openapi.project.Project,
        workspace: Workspace,
        config: ExportConfig,
        indicator: ProgressIndicator
    ) {
        val result = DeltaExportService.exportDelta(project, config)

        when (result) {
            is DeltaExportService.DeltaResult.Success -> {
                // Auto-import delta — use workspace.graphId so a multi-repo export
                // lands in the same graph the full import created.
                val service = ApplicationManager.getApplication().getService(ExportService::class.java)
                val importResult = service.syncToGraph(result.path, workspace.graphId, config.copy(autoImport = true), isFull = false, projectBasePath = project.basePath)

                val stats = result.stats
                notify(project,
                    "OneLens Sync Complete (delta)\n" +
                        "${stats.changedFileCount} files changed\n" +
                        "${stats.upsertedClassCount} classes updated, ${stats.deletedClassCount} deleted\n" +
                        "${stats.upsertedCallEdgeCount} call edges updated",
                    NotificationType.INFORMATION
                )
            }
            is DeltaExportService.DeltaResult.NeedFullExport -> {
                indicator.text = "Delta not possible — running full export..."
                val service = ApplicationManager.getApplication().getService(ExportService::class.java)
                doFullExport(service, project, workspace, config, indicator)
            }
            is DeltaExportService.DeltaResult.NoChanges -> {
                notify(project, "OneLens: Already up to date.", NotificationType.INFORMATION)
            }
            is DeltaExportService.DeltaResult.Error -> {
                notify(project, "OneLens Delta Failed: ${result.message}", NotificationType.ERROR)
            }
        }
    }

    /**
     * After full export, store file→classes mapping so delta can know what to delete.
     */
    private fun storeFileClassMapping(exportPath: java.nio.file.Path, state: ExportState) {
        try {
            val data = kotlinx.serialization.json.Json.decodeFromString<com.onelens.plugin.export.ExportDocument>(
                java.nio.file.Files.readString(exportPath)
            )
            state.state.fileHashes.clear()
            for (cls in data.classes) {
                val existing = state.state.fileHashes.getOrDefault(cls.filePath, "")
                state.state.fileHashes[cls.filePath] = if (existing.isEmpty()) cls.fqn else "$existing,${cls.fqn}"
            }
        } catch (e: Exception) {
            // Non-critical — delta will still work, just can't detect deleted classes
        }
    }

    private fun countJavaFiles(basePath: String): Int {
        return try {
            val proc = ProcessBuilder("find", basePath, "-name", "*.java", "-type", "f")
                .start()
            val count = proc.inputStream.bufferedReader().readLines().size
            proc.waitFor()
            count
        } catch (_: Exception) { 0 }
    }

    private fun notify(project: com.intellij.openapi.project.Project, message: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup(OneLensConstants.NOTIFICATION_GROUP)
            .createNotification("OneLens", message, type)
            .notify(project)
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
