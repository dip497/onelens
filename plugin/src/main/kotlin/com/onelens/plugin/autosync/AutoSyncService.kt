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
import com.onelens.plugin.ui.OneLensEvents
import com.onelens.plugin.ui.OneLensState
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
    private val pendingDeletedFiles = mutableSetOf<String>()
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
            pendingDeletedFiles.clear()
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
            // If a file is deleted and recreated inside one debounce window,
            // prefer the modified path (new content wins).
            pendingDeletedFiles.remove(relativePath)
        }

        scheduleDebounced()
    }

    /**
     * Called by AutoSyncFileListener when a .java file is deleted or moved away.
     * Delta exporter needs to know the old path so it can drop its classes
     * from the graph + embeddings — otherwise orphan nodes accumulate.
     */
    fun onJavaFileDeleted(relativePath: String) {
        if (!enabled || syncing.get()) return

        synchronized(pendingDeletedFiles) {
            pendingDeletedFiles.add(relativePath)
            // Deletion supersedes a modification in the same window.
            pendingChangedFiles.remove(relativePath)
        }

        scheduleDebounced()
    }

    private fun scheduleDebounced() {
        val debounceMs = OneLensSettings.getInstance().state.autoSyncDebounceMs.toLong()
        alarm.cancelAllRequests()
        alarm.addRequest(::triggerSync, debounceMs)
    }

    // Git branch-change listener was deferred — the Platform's
    // BranchChangeListener topic classpath varies by IDE bundle and the
    // reliable path is to let the VFS file listener pick up the file
    // modifications that branch switches / pulls produce. Revisit once
    // we have a stable reference to the correct topic for the target
    // IDE flavors.

    private fun triggerSync() {
        if (!syncing.compareAndSet(false, true)) return

        // Don't sync while IDE is indexing — PSI data isn't ready.
        // Retry after smart mode by firing triggerSync directly; adding an
        // empty path to pendingChangedFiles (the previous approach) would
        // inject `""` into the file list and confuse the exporter.
        if (DumbService.isDumb(project)) {
            syncing.set(false)
            DumbService.getInstance(project).runWhenSmart {
                val debounceMs = OneLensSettings.getInstance().state.autoSyncDebounceMs.toLong()
                alarm.cancelAllRequests()
                alarm.addRequest(::triggerSync, debounceMs)
            }
            return
        }

        val filesToSync: List<String>
        val filesDeleted: List<String>
        synchronized(pendingChangedFiles) {
            if (pendingChangedFiles.isEmpty() && pendingDeletedFiles.isEmpty()) {
                syncing.set(false)
                return
            }
            filesToSync = pendingChangedFiles.toList()
            filesDeleted = pendingDeletedFiles.toList()
            pendingChangedFiles.clear()
            pendingDeletedFiles.clear()
        }

        LOG.info("Auto-sync triggered: ${filesToSync.size} modified, ${filesDeleted.size} deleted")
        OneLensEvents.status(OneLensState.SYNCING)
        OneLensEvents.info("Auto-sync triggered: ${filesToSync.size} modified, ${filesDeleted.size} deleted")

        val coordinator = com.onelens.plugin.export.SyncCoordinator.getInstance()
        if (!coordinator.tryAcquire()) {
            LOG.info("Auto-sync skipped — another sync is already running")
            OneLensEvents.info("Auto-sync skipped — a sync is already running")
            syncing.set(false)
            return
        }
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "OneLens: Auto-syncing", true) {
            override fun run(indicator: ProgressIndicator) {
                val start = System.currentTimeMillis()
                try {
                    indicator.text = "Auto-syncing ${filesToSync.size} modified, ${filesDeleted.size} deleted..."
                    val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
                    val config = ExportConfig(
                        buildSemanticIndex = settings.buildSemanticIndex,
                        graphBackend = settings.graphBackend,
                    )
                    val result = DeltaExportService.exportDeltaForFiles(project, config, filesToSync, filesDeleted)

                    when (result) {
                        is DeltaExportService.DeltaResult.Success -> {
                            val service = ApplicationManager.getApplication().getService(ExportService::class.java)
                            val graphId = try {
                                com.onelens.plugin.framework.workspace.WorkspaceLoader.load(project).graphId
                            } catch (_: Exception) { project.name }
                            service.syncToGraph(result.path, graphId, config, isFull = false, projectBasePath = project.basePath)
                            val dur = System.currentTimeMillis() - start
                            LOG.info("Auto-sync complete: ${result.stats.upsertedClassCount} classes, ${result.stats.upsertedCallEdgeCount} edges")
                            OneLensEvents.syncComplete(
                                graphName = graphId,
                                classes = result.stats.upsertedClassCount,
                                methods = result.stats.upsertedMethodCount,
                                callEdges = result.stats.upsertedCallEdgeCount,
                                isDelta = true,
                                durationMs = dur,
                            )
                        }
                        is DeltaExportService.DeltaResult.NeedFullExport -> {
                            LOG.info("Auto-sync: full export needed, skipping (use manual Sync Graph)")
                            OneLensEvents.warn("Auto-sync skipped: full export needed. Click Sync Graph.")
                        }
                        is DeltaExportService.DeltaResult.NoChanges -> {
                            LOG.info("Auto-sync: no changes detected")
                            OneLensEvents.info("Auto-sync: no changes detected")
                        }
                        is DeltaExportService.DeltaResult.Error -> {
                            LOG.warn("Auto-sync failed: ${result.message}")
                            OneLensEvents.error("Auto-sync failed: ${result.message}")
                        }
                    }
                } catch (t: Throwable) {
                    OneLensEvents.error("Auto-sync crashed: ${t.message}", t)
                } finally {
                    OneLensEvents.status(OneLensState.READY)
                    syncing.set(false)
                }
            }
            override fun onFinished() {
                coordinator.release()
            }
            override fun onCancel() {
                coordinator.killActive()
                OneLensEvents.warn("Auto-sync cancelled by user")
            }
        })
    }

    override fun dispose() {
        alarm.cancelAllRequests()
    }
}
