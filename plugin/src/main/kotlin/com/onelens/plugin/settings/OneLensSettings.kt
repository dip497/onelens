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
        // Vue 3 adapter override. null = auto-detect (default); true/false force on/off.
        // Stored as String so kotlinx-serialization-style nulls survive round-trip
        // through IntelliJ's XmlSerializer, which treats Boolean? fields inconsistently.
        var vueAdapterOverride: String = "auto",
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        this.state = state
    }

    /**
     * Vue 3 adapter override as a Boolean (null = auto-detect). Thin accessor over
     * [State.vueAdapterOverride] so callers don't have to parse the stored string.
     */
    val vueAdapterEnabled: Boolean?
        get() = when (state.vueAdapterOverride.lowercase()) {
            "on", "true", "yes" -> true
            "off", "false", "no" -> false
            else -> null
        }

    companion object {
        fun getInstance(): OneLensSettings =
            ApplicationManager.getApplication().getService(OneLensSettings::class.java)
    }
}
