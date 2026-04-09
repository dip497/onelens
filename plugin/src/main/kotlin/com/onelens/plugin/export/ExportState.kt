package com.onelens.plugin.export

import com.intellij.openapi.components.*
import com.intellij.openapi.project.Project

/**
 * Persisted per-project state for tracking exports.
 * Stores last export timestamp and per-file content hashes for delta detection.
 */
@Service(Service.Level.PROJECT)
@State(name = "OneLensExportState", storages = [Storage("onelens-export.xml")])
class ExportState : PersistentStateComponent<ExportState.State> {

    data class State(
        var lastExportTimestamp: Long = 0,
        var lastExportPath: String = "",
        var lastGitHash: String = "",
        var lastGraphName: String = "",
        var fileHashes: MutableMap<String, String> = mutableMapOf()
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        this.state = state
    }

    companion object {
        fun getInstance(project: Project): ExportState =
            project.getService(ExportState::class.java)
    }
}
