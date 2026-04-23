package com.onelens.plugin.settings

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.ProjectManager
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.onelens.plugin.export.PythonEnvManager
import javax.swing.ButtonGroup
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JRadioButton

/**
 * Settings panel at **Preferences → Tools → OneLens Semantic**.
 *
 * Two backend choices:
 *   - **Local** (default): on-device embed + rerank via onnxruntime-gpu.
 *     One-click "Install TensorRT acceleration" button for 3-4× fp16 speedup
 *     after base install.
 *   - **OpenAI-compat cloud**: BYOK URL + API key + model + dim.
 *
 * Modal is *not* exposed here on purpose — it's a dev-time backend, set
 * via env var if needed (ONELENS_EMBED_BACKEND=modal).
 *
 * Secrets hygiene: the API key travels through [OpenAiSecrets] so it lands
 * in IntelliJ's encrypted PasswordSafe, not the plaintext XML under
 * `~/.config/JetBrains/.../options/`.
 */
class SemanticSettingsConfigurable : Configurable {

    private val settings = OneLensSettings.getInstance()

    private val localRadio = JRadioButton("Local (on-device, air-gapped)")
    private val openaiRadio = JRadioButton("OpenAI-compat cloud (BYOK)")
    private val providerLabel = JBLabel("Provider: detecting…")
    private val installTrtBtn = JButton("Install TensorRT fp16 acceleration (+1 GB, ~3× faster)")

    private val openaiBaseUrl = JBTextField()
    private val openaiApiKey = JBPasswordField()
    private val openaiModel = JBTextField()
    private val openaiDim = JBTextField()

    private var root: JPanel? = null

    override fun getDisplayName(): String = "OneLens Semantic"

    override fun createComponent(): JComponent {
        ButtonGroup().apply {
            add(localRadio); add(openaiRadio)
        }

        val localBlock = FormBuilder.createFormBuilder()
            .addComponent(providerLabel)
            .addComponent(installTrtBtn)
            .panel

        val openaiBlock = FormBuilder.createFormBuilder()
            .addLabeledComponent("Base URL", openaiBaseUrl)
            .addLabeledComponent("API key", openaiApiKey)
            .addLabeledComponent("Embed model", openaiModel)
            .addLabeledComponent("Dimension", openaiDim)
            .panel

        val panel = FormBuilder.createFormBuilder()
            .addComponent(localRadio)
            .addComponent(localBlock)
            .addSeparator()
            .addComponent(openaiRadio)
            .addComponent(openaiBlock)
            .addComponentFillVertically(JPanel(), 0)
            .panel

        installTrtBtn.addActionListener {
            installTrtBtn.isEnabled = false
            installTrtBtn.text = "Installing TensorRT…"
            val project = ProjectManager.getInstance().openProjects.firstOrNull()
                ?: ProjectManager.getInstance().defaultProject
            ProgressManager.getInstance().run(object : Task.Backgroundable(
                project, "OneLens: Installing TensorRT fp16 acceleration", true,
            ) {
                override fun run(indicator: ProgressIndicator) {
                    val ok = PythonEnvManager.installTensorrt()
                    settings.state.localEmbedderUseTRT = ok
                    javax.swing.SwingUtilities.invokeLater {
                        refreshLocalBlock()
                    }
                }
            })
        }

        localRadio.addActionListener { refreshEnabled() }
        openaiRadio.addActionListener { refreshEnabled() }

        reset()
        root = panel
        return panel
    }

    private fun refreshEnabled() {
        val local = localRadio.isSelected
        providerLabel.isEnabled = local
        installTrtBtn.isEnabled = local && !settings.state.localEmbedderUseTRT
        openaiBaseUrl.isEnabled = !local
        openaiApiKey.isEnabled = !local
        openaiModel.isEnabled = !local
        openaiDim.isEnabled = !local
    }

    private fun refreshLocalBlock() {
        val provider = PythonEnvManager.detectLocalProvider()
        providerLabel.text = "Provider: $provider"
        // Ground-truth TRT state is the venv, not the settings flag. The
        // flag can lag behind reality if the user installed tensorrt-cu12
        // manually (via `uv pip install` or a prior version of the plugin
        // before this button shipped). Detect and self-heal.
        val installedInVenv = PythonEnvManager.isTensorrtInstalled()
        if (installedInVenv && !settings.state.localEmbedderUseTRT) {
            settings.state.localEmbedderUseTRT = true
        }
        if (installedInVenv || settings.state.localEmbedderUseTRT) {
            installTrtBtn.text = "✓ TensorRT fp16 installed"
            installTrtBtn.isEnabled = false
        } else {
            installTrtBtn.text = "Install TensorRT fp16 acceleration (+1 GB, ~3× faster)"
            installTrtBtn.isEnabled = localRadio.isSelected
        }
    }

    override fun isModified(): Boolean {
        val s = settings.state
        val currentBackend = if (localRadio.isSelected) "local" else "openai"
        return currentBackend != s.embedderBackend ||
            openaiBaseUrl.text != s.openaiBaseUrl ||
            openaiModel.text != s.openaiEmbedModel ||
            openaiDim.text != s.openaiEmbedDim.toString() ||
            String(openaiApiKey.password) != (OpenAiSecrets.get() ?: "")
    }

    override fun apply() {
        val s = settings.state
        s.embedderBackend = if (localRadio.isSelected) "local" else "openai"
        s.openaiBaseUrl = openaiBaseUrl.text.trim().ifEmpty { "https://api.openai.com/v1" }
        s.openaiEmbedModel = openaiModel.text.trim().ifEmpty { "text-embedding-3-small" }
        s.openaiEmbedDim = openaiDim.text.trim().toIntOrNull() ?: 1536
        OpenAiSecrets.set(String(openaiApiKey.password))
    }

    override fun reset() {
        val s = settings.state
        val local = s.embedderBackend.equals("local", ignoreCase = true)
        localRadio.isSelected = local
        openaiRadio.isSelected = !local
        openaiBaseUrl.text = s.openaiBaseUrl
        openaiModel.text = s.openaiEmbedModel
        openaiDim.text = s.openaiEmbedDim.toString()
        openaiApiKey.text = OpenAiSecrets.get() ?: ""
        refreshLocalBlock()
        refreshEnabled()
    }
}
