package com.onelens.plugin.autosync

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.onelens.plugin.settings.OneLensSettings

/**
 * Enables auto-sync on project open if the setting is enabled.
 */
class AutoSyncStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        if (OneLensSettings.getInstance().state.autoSyncEnabled) {
            val service = project.getService(AutoSyncService::class.java) ?: return
            service.enable()
        }
    }
}
