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
        // Auto-sync OFF by default. On fresh installs, auto-sync can fire
        // during IntelliJ's dumb-mode indexing pass (IndexNotReadyException)
        // and overlap with the user's first manual Sync, producing empty or
        // duplicate graphs with unexpected names. Opt-in: toggle on via Tools
        // → OneLens → Enable Auto-Sync after the first manual sync succeeds.
        var autoSyncEnabled: Boolean = false,
        var autoSyncDebounceMs: Int = 5000,
        // First-run flag — the startup activity checks this and shows a
        // one-time onboarding balloon on the first project open with the
        // plugin installed. Reset only by deleting onelens-settings.xml.
        var firstRunComplete: Boolean = false,
        // Vue 3 adapter override. null = auto-detect (default); true/false force on/off.
        // Stored as String so kotlinx-serialization-style nulls survive round-trip
        // through IntelliJ's XmlSerializer, which treats Boolean? fields inconsistently.
        var vueAdapterOverride: String = "auto",
        // Build ChromaDB semantic index alongside the graph. OFF by default —
        // graph-only is ~30 s full sync and covers structural queries (impact /
        // trace / Cypher / search). Flip ON to spend ~20 min on Qwen3 embeddings
        // and unlock natural-language retrieval (`onelens retrieve`).
        var buildSemanticIndex: Boolean = false,
        // Graph backend: "falkordblite" (embedded, no Docker) or "falkordb" (Docker on :17532).
        // Default flipped to lite in v0.2 for zero-setup UX. Windows users must pick "falkordb".
        var graphBackend: String = "falkordblite",
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
