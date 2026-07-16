package com.onelens.plugin.ui

import com.intellij.util.messages.Topic

/**
 * Application-level event bus for OneLens activity.
 *
 * Services (ExportService, AutoSyncService, PythonEnvManager, DeltaExportService)
 * publish events here; the Tool Window (`OneLensToolWindowFactory`) subscribes and
 * renders them into a live log + status strip. Decouples UI from services so we
 * can add panels without touching every publisher.
 *
 * Usage (publisher):
 *   ApplicationManager.getApplication().messageBus
 *       .syncPublisher(OneLensEventBus.TOPIC)
 *       .onEvent(OneLensEvent.Info("sync started"))
 */
interface OneLensEventListener {
    fun onEvent(event: OneLensEvent)
}

sealed class OneLensEvent(val timestampMs: Long = System.currentTimeMillis()) {
    /** Plain info line — dumped verbatim into the log console. */
    class Info(val message: String) : OneLensEvent()

    /** Warning — yellow in console. */
    class Warn(val message: String) : OneLensEvent()

    /** Error — red in console. */
    class Error(val message: String, val throwable: Throwable? = null) : OneLensEvent()

    /** Phase transition — rerender the status strip. */
    class StatusChange(val state: OneLensState) : OneLensEvent()

    /** Progress inside a long-running op (install, embedding pass). */
    class Progress(val label: String, val fraction: Double) : OneLensEvent()

    /**
     * A sync completed — the tool window refreshes graph stats. JVM counts
     * (`classes` / `methods` / `callEdges`) are zero for Vue-only projects;
     * `vueNodes` / `vueEdges` summarize the Vue3 adapter contribution so the
     * console log and status strip never display the misleading "0 classes ·
     * 0 methods" line on frontend-only syncs.
     */
    class SyncComplete(val graphName: String, val classes: Int, val methods: Int,
                       val callEdges: Int, val isDelta: Boolean, val durationMs: Long,
                       val vueNodes: Int = 0, val vueEdges: Int = 0,
                       val jsModules: Int = 0, val jsFunctions: Int = 0,
                       val activeAdapters: List<String> = emptyList()) : OneLensEvent()
}

enum class OneLensState { UNKNOWN, SETTING_UP, READY, SYNCING, ERROR }

object OneLensEventBus {
    val TOPIC: Topic<OneLensEventListener> =
        Topic.create("OneLens Events", OneLensEventListener::class.java)
}
