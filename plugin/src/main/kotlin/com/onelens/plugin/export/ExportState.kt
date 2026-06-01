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
        // Set ONLY after the import is confirmed in the graph (not just the
        // export written). Drives the "graph fresh vs stale" UI indicator and
        // lets us tell a successful sync from one whose import silently failed.
        var lastSuccessfulImportTimestamp: Long = 0,
        var fileHashes: MutableMap<String, String> = mutableMapOf()
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        this.state = state
    }

    /**
     * Snapshot of the delta diff-base — captured before an export so a failed
     * import can roll the baseline back. Without this, `exportDeltaForFiles`
     * advances `lastGitHash` / `fileHashes` to current HEAD even when the
     * import never lands; the next delta then diffs from the new base and the
     * failed window's changes are lost forever (silent permanent staleness).
     */
    data class Baseline(
        val lastExportTimestamp: Long,
        val lastExportPath: String,
        val lastGitHash: String,
        val fileHashes: Map<String, String>,
    )

    fun snapshotBaseline(): Baseline = Baseline(
        lastExportTimestamp = state.lastExportTimestamp,
        lastExportPath = state.lastExportPath,
        lastGitHash = state.lastGitHash,
        // Deep copy — fileHashes is mutated in place by exportDeltaForFiles.
        fileHashes = HashMap(state.fileHashes),
    )

    fun restoreBaseline(b: Baseline) {
        state.lastExportTimestamp = b.lastExportTimestamp
        state.lastExportPath = b.lastExportPath
        state.lastGitHash = b.lastGitHash
        state.fileHashes = HashMap(b.fileHashes)
    }

    companion object {
        fun getInstance(project: Project): ExportState =
            project.getService(ExportState::class.java)

        /** True iff a `syncToGraph` result string indicates the import
         * actually landed. The method returns success and failure both as
         * non-null strings (and null on Python/IO failure), so the only safe
         * discriminator is the "Import successful" prefix it writes on the
         * two success paths (MCP + CLI exit 0). */
        fun isImportSuccess(result: String?): Boolean =
            result != null && result.startsWith("Import successful")
    }
}
