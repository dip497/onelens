package com.onelens.plugin.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.*

/**
 * Application-level settings for OneLens plugin.
 */
@Service(Service.Level.APP)
@State(name = "OneLensSettings", storages = [Storage("onelens-settings.xml")])
class OneLensSettings : PersistentStateComponent<OneLensSettings.State> {

    data class State(
        var exportDirectory: String = "",
        var includeSpring: Boolean = true,
        var includeDiagnostics: Boolean = false,
        var excludeTestSources: Boolean = false,
        // Auto-sync ON by default — users expect "install plugin → always fresh graph"
        // without digging through Tools menu. Toggle off via Tools → OneLens.
        var autoSyncEnabled: Boolean = true,
        var autoSyncDebounceMs: Int = 5000,
        // First-run flag — the startup activity checks this and shows a
        // one-time onboarding balloon on the first project open with the
        // plugin installed. Reset only by deleting onelens-settings.xml.
        var firstRunComplete: Boolean = false,
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        this.state = state
    }

    companion object {
        fun getInstance(): OneLensSettings =
            ApplicationManager.getApplication().getService(OneLensSettings::class.java)
    }
}
