package com.onelens.plugin.snapshots

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.ValidationInfo
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets
import javax.swing.JComponent
import javax.swing.JPanel

class PublishSnapshotDialog(
    private val project: Project,
    private val graph: String,
    private val suggestedTag: String?,
    private val branch: String? = null,
    private val headSha: String? = null,
) : DialogWrapper(project, true) {

    private val tagField = JBTextField(suggestedTag ?: "v0.1.0", 20)
    private val includeEmbeddings = JBCheckBox("Include semantic embeddings (doubles bundle size)")

    data class Result(
        val tag: String,
        val includeEmbeddings: Boolean,
    )

    init {
        title = "Publish OneLens Snapshot — $graph"
        init()
    }

    override fun createCenterPanel(): JComponent {
        val p = JPanel(GridBagLayout())
        val c = GridBagConstraints().apply {
            anchor = GridBagConstraints.WEST
            insets = Insets(4, 4, 4, 8)
        }
        var row = 0
        if (branch != null || headSha != null) {
            val info = buildString {
                if (branch != null) append("Branch: ").append(branch)
                if (headSha != null) {
                    if (isNotEmpty()) append("  ·  ")
                    append("HEAD: ").append(headSha.take(7))
                }
            }
            c.gridx = 0; c.gridy = row; c.gridwidth = 2; c.fill = GridBagConstraints.HORIZONTAL
            p.add(JBLabel(info).apply { foreground = foreground.darker() }, c)
            c.gridwidth = 1
            row++
        }
        fun addRow(label: String, field: JComponent) {
            c.gridx = 0; c.gridy = row; c.weightx = 0.0; c.fill = GridBagConstraints.NONE
            p.add(JBLabel(label), c)
            c.gridx = 1; c.weightx = 1.0; c.fill = GridBagConstraints.HORIZONTAL
            p.add(field, c)
            row++
        }
        addRow("Git tag:", tagField)
        c.gridx = 1; c.gridy = row; c.fill = GridBagConstraints.HORIZONTAL
        p.add(includeEmbeddings, c); row++
        c.gridx = 1; c.gridy = row
        p.add(JBLabel("Publishes to ~/.onelens/bundles/ (local file).").apply {
            foreground = foreground.darker()
        }, c); row++
        return p
    }

    override fun doValidate(): ValidationInfo? {
        if (tagField.text.isNullOrBlank()) {
            return ValidationInfo("Tag is required", tagField)
        }
        return null
    }

    fun result(): Result = Result(
        tag = tagField.text.trim(),
        includeEmbeddings = includeEmbeddings.isSelected,
    )
}
