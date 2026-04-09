package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent

/**
 * Menu action for delta (incremental) export.
 * TODO: Implement in Phase 6.
 */
class ExportDeltaAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        // TODO: Implement delta export
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
