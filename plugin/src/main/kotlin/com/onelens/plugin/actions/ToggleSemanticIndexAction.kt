package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.ToggleAction
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
    }

    override fun update(e: AnActionEvent) {
        super.update(e)
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
