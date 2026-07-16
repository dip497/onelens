package com.onelens.plugin.ui

import com.intellij.openapi.application.ApplicationManager

/**
 * Thin helper so service code can publish one-line events without
 * boilerplate. All publications are best-effort: if the message bus isn't
 * available (plugin disposed, test harness), we swallow rather than leak
 * the exception into unrelated code paths.
 */
object OneLensEvents {

    fun info(message: String) = publish(OneLensEvent.Info(message))
    fun warn(message: String) = publish(OneLensEvent.Warn(message))
    fun error(message: String, throwable: Throwable? = null) =
        publish(OneLensEvent.Error(message, throwable))
    fun status(state: OneLensState) = publish(OneLensEvent.StatusChange(state))
    fun progress(label: String, fraction: Double) =
        publish(OneLensEvent.Progress(label, fraction))
    fun syncComplete(
        graphName: String, classes: Int, methods: Int, callEdges: Int,
        isDelta: Boolean, durationMs: Long,
    ) = publish(OneLensEvent.SyncComplete(graphName, classes, methods, callEdges, isDelta, durationMs))

    fun publish(event: OneLensEvent) {
        try {
            ApplicationManager.getApplication().messageBus
                .syncPublisher(OneLensEventBus.TOPIC).onEvent(event)
        } catch (_: Throwable) {
            // No subscribers / bus disposed — safe to drop.
        }
    }
}
