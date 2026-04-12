package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.ToggleAction
import com.onelens.plugin.autosync.AutoSyncService
import com.onelens.plugin.settings.OneLensSettings

/**
 * Menu toggle for auto-sync. Shows checkmark when enabled.
 * Tools → OneLens → Toggle Auto-Sync
 */
class ToggleAutoSyncAction : ToggleAction() {

    override fun isSelected(e: AnActionEvent): Boolean {
        return OneLensSettings.getInstance().state.autoSyncEnabled
    }

    override fun setSelected(e: AnActionEvent, state: Boolean) {
        OneLensSettings.getInstance().state.autoSyncEnabled = state

        val project = e.project ?: return
        val service = project.getService(AutoSyncService::class.java) ?: return
        if (state) {
            service.enable()
        } else {
            service.disable()
        }
    }

    override fun update(e: AnActionEvent) {
        super.update(e)
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
