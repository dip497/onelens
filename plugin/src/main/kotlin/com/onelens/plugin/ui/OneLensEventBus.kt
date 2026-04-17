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

    /** A sync completed — the tool window refreshes graph stats. */
    class SyncComplete(val graphName: String, val classes: Int, val methods: Int,
                       val callEdges: Int, val isDelta: Boolean, val durationMs: Long) : OneLensEvent()
}

enum class OneLensState { UNKNOWN, SETTING_UP, READY, SYNCING, ERROR }

object OneLensEventBus {
    val TOPIC: Topic<OneLensEventListener> =
        Topic.create("OneLens Events", OneLensEventListener::class.java)
}
