package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.ToggleAction
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.onelens.plugin.export.PythonEnvManager
import com.onelens.plugin.settings.OneLensSettings

/**
 * Menu toggle for the ChromaDB semantic index. Checkmark = ON.
 *
 * ON: pass `--context` to `onelens import_graph` → graph + Qwen3 embeddings +
 * mxbai rerank. Enables `onelens retrieve` and natural-language queries. First
 * full sync takes ~20 min on a 10K-class project; deltas are seconds.
 *
 * OFF: graph-only import. ~30 s full sync. Only structural queries
 * (`impact`, `trace`, Cypher, `search`) work; NL retrieval is disabled.
 *
 * Tools → OneLens → Build Semantic Index.
 */
class ToggleSemanticIndexAction : ToggleAction() {

    override fun isSelected(e: AnActionEvent): Boolean =
        OneLensSettings.getInstance().state.buildSemanticIndex

    override fun setSelected(e: AnActionEvent, state: Boolean) {
        OneLensSettings.getInstance().state.buildSemanticIndex = state
        val project = e.project
        if (state && project != null) {
            // User just enabled semantic — fetch the heavy stack (~80 MB,
            // ~5 min on a fresh venv) off-EDT. Idempotent if already present.
            ProgressManager.getInstance().run(object : Task.Backgroundable(
                project, "OneLens: Installing semantic stack", true,
            ) {
                override fun run(indicator: ProgressIndicator) {
                    PythonEnvManager.installSemanticStack()
                }
            })
        }
    }

    override fun update(e: AnActionEvent) {
        super.update(e)
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
