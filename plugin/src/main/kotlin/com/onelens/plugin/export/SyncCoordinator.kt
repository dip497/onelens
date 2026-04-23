package com.onelens.plugin.export

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.logger
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/**
 * Tracks whether a graph sync is currently running and keeps a handle to
 * the active Python child process so Cancel can actually kill it.
 *
 * Single source of truth across entry points — the toolbar Sync action,
 * the Tools menu `ExportFullAction`, and `AutoSyncService` all register
 * here. Clean-up operations (`GraphCleanupService`) consult this before
 * deleting files a live sync might be reading.
 *
 * Why an app service: one project can have one sync at a time, but we
 * also want to refuse *cross-project* overlap (two IDE windows, same
 * ~/.onelens/). App scope covers both.
 */
@Service(Service.Level.APP)
class SyncCoordinator {

    private val running = AtomicBoolean(false)
    private val activeProcess = AtomicReference<Process?>(null)

    fun isRunning(): Boolean = running.get()

    /** Returns true if the caller acquired the sync slot, false if another sync is in flight. */
    fun tryAcquire(): Boolean = running.compareAndSet(false, true)

    /** Release the slot. Idempotent. */
    fun release() {
        activeProcess.set(null)
        running.set(false)
    }

    /** Register the running child so Cancel can kill it. */
    fun setActiveProcess(proc: Process?) {
        activeProcess.set(proc)
    }

    /**
     * Kill whatever Python child is currently registered. Returns true if
     * a process was alive and has been signalled. Called from cancel
     * hooks in [ExportService.syncToGraph].
     */
    fun killActive(): Boolean {
        val p = activeProcess.get() ?: return false
        return try {
            if (p.isAlive) {
                p.descendants().forEach { it.destroyForcibly() }
                p.destroyForcibly()
                LOG.info("SyncCoordinator killed active child pid=${p.pid()}")
                true
            } else false
        } catch (e: Exception) {
            LOG.warn("Failed to kill active process: ${e.message}")
            false
        }
    }

    companion object {
        private val LOG = logger<SyncCoordinator>()
        fun getInstance(): SyncCoordinator = ApplicationManager.getApplication().service()
    }
}
