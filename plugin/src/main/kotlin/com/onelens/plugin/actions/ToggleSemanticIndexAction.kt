package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.ToggleAction
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.onelens.plugin.export.PythonEnvManager
import com.onelens.plugin.mcp.OneLensMcpService
import com.onelens.plugin.settings.OneLensSettings
import com.onelens.plugin.ui.OneLensEvent
import com.onelens.plugin.ui.OneLensEvents

/**
 * Tools → OneLens → Build Semantic Index. Identical behavior to the
 * toolbar's Semantic toggle — kept for muscle-memory and discoverability
 * via the Tools menu. Both code paths install the backend-appropriate
 * stack and start/stop [OneLensMcpService] so the user's VRAM state
 * matches whichever control they used.
 *
 * ON: installs chromadb + onnxruntime-gpu (local) or chromadb + httpx
 *   (openai), starts the MCP HTTP server, warms embed + rerank TRT
 *   engines so the first sync lands on hot providers.
 * OFF: stops MCP, frees VRAM. Next sync runs graph-only.
 */
class ToggleSemanticIndexAction : ToggleAction() {

    override fun isSelected(e: AnActionEvent): Boolean =
        OneLensSettings.getInstance().state.buildSemanticIndex

    override fun setSelected(e: AnActionEvent, state: Boolean) {
        val settings = OneLensSettings.getInstance().state
        val project = e.project
        val mcp = OneLensMcpService.getInstance()
        settings.buildSemanticIndex = state
        if (state && project != null) {
            ProgressManager.getInstance().run(object : Task.Backgroundable(
                project, "OneLens: Enabling semantic index", true,
            ) {
                override fun run(indicator: ProgressIndicator) {
                    PythonEnvManager.installSemanticStack()
                    val port = mcp.start()
                    if (port > 0) {
                        OneLensEvents.publish(OneLensEvent.Info("Semantic enabled · MCP on port $port (warming up)"))
                    }
                }
            })
        } else {
            mcp.stop()
            OneLensEvents.publish(OneLensEvent.Info("Semantic disabled — MCP stopped, VRAM freed"))
        }
    }

    override fun update(e: AnActionEvent) {
        super.update(e)
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
