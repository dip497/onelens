package com.onelens.plugin.autosync

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.util.Alarm
import com.onelens.plugin.export.ExportConfig
import com.onelens.plugin.export.ExportService
import com.onelens.plugin.export.delta.DeltaExportService
import com.onelens.plugin.settings.OneLensSettings
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Project-level service that manages auto-sync lifecycle.
 *
 * Listens for .java file changes (via AutoSyncFileListener), debounces them,
 * then runs a delta export + import in the background.
 */
@Service(Service.Level.PROJECT)
class AutoSyncService(private val project: Project) : Disposable {

    companion object {
        private val LOG = logger<AutoSyncService>()
    }

    private val alarm = Alarm(Alarm.ThreadToUse.POOLED_THREAD, this)
    private val pendingChangedFiles = mutableSetOf<String>()
    @Volatile private var enabled = false
    private val syncing = AtomicBoolean(false)

    fun isEnabled(): Boolean = enabled

    fun enable() {
        enabled = true
        LOG.info("Auto-sync enabled for ${project.name}")
    }

    fun disable() {
        enabled = false
        alarm.cancelAllRequests()
        synchronized(pendingChangedFiles) {
            pendingChangedFiles.clear()
        }
        LOG.info("Auto-sync disabled for ${project.name}")
    }

    /**
     * Called by AutoSyncFileListener when a .java file changes.
     * Accumulates paths and resets the debounce timer.
     */
    fun onJavaFileChanged(relativePath: String) {
        if (!enabled || syncing.get()) return

        synchronized(pendingChangedFiles) {
            pendingChangedFiles.add(relativePath)
        }

        val debounceMs = OneLensSettings.getInstance().state.autoSyncDebounceMs.toLong()
        alarm.cancelAllRequests()
        alarm.addRequest(::triggerSync, debounceMs)
    }

    private fun triggerSync() {
        if (!syncing.compareAndSet(false, true)) return

        // Don't sync while IDE is indexing — PSI data isn't ready
        if (DumbService.isDumb(project)) {
            syncing.set(false)
            // Retry after dumb mode ends
            DumbService.getInstance(project).runWhenSmart { onJavaFileChanged("") }
            return
        }

        val filesToSync: List<String>
        synchronized(pendingChangedFiles) {
            if (pendingChangedFiles.isEmpty()) {
                syncing.set(false)
                return
            }
            filesToSync = pendingChangedFiles.toList()
            pendingChangedFiles.clear()
        }

        LOG.info("Auto-sync triggered: ${filesToSync.size} files changed")

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "OneLens: Auto-syncing", true) {
            override fun run(indicator: ProgressIndicator) {
                try {
                    indicator.text = "Auto-syncing ${filesToSync.size} changed files..."
                    val config = ExportConfig()
                    val result = DeltaExportService.exportDeltaForFiles(project, config, filesToSync)

                    when (result) {
                        is DeltaExportService.DeltaResult.Success -> {
                            val service = ApplicationManager.getApplication().getService(ExportService::class.java)
                            service.syncToGraph(result.path, project.name, config)
                            LOG.info("Auto-sync complete: ${result.stats.upsertedClassCount} classes, ${result.stats.upsertedCallEdgeCount} edges")
                        }
                        is DeltaExportService.DeltaResult.NeedFullExport -> {
                            LOG.info("Auto-sync: full export needed, skipping (use manual Sync Graph)")
                        }
                        is DeltaExportService.DeltaResult.NoChanges -> {
                            LOG.info("Auto-sync: no changes detected")
                        }
                        is DeltaExportService.DeltaResult.Error -> {
                            LOG.warn("Auto-sync failed: ${result.message}")
                        }
                    }
                } finally {
                    syncing.set(false)
                }
            }
        })
    }

    override fun dispose() {
        alarm.cancelAllRequests()
    }
}
