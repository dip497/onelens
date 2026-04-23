package com.onelens.plugin.ui

import com.intellij.execution.filters.TextConsoleBuilderFactory
import com.intellij.execution.ui.ConsoleView
import com.intellij.execution.ui.ConsoleViewContentType
import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.util.ui.JBUI
import com.onelens.plugin.export.ExportConfig
import com.onelens.plugin.export.PythonEnvManager
import com.onelens.plugin.skill.InstallSkillAction
import java.awt.BorderLayout
import java.awt.Color
import java.awt.FlowLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets
import java.text.SimpleDateFormat
import java.util.Date
import javax.swing.BorderFactory
import javax.swing.BoxLayout
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.SwingConstants

/**
 * OneLens tool window — right sidebar panel showing live status, resource usage,
 * quick actions, and a streaming event log. Subscribes to `OneLensEventBus` so
 * anything services publish lands here.
 */
class OneLensToolWindowFactory : ToolWindowFactory, DumbAware {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val cm = toolWindow.contentManager
        val status = cm.factory.createContent(OneLensMainPanel(project), "Status", false)
        val snapshots = cm.factory.createContent(OneLensSnapshotsPanel(project), "Snapshots", false)
        cm.addContent(status)
        cm.addContent(snapshots)
        cm.setSelectedContent(status)
    }
}

private class OneLensMainPanel(private val project: Project) : JBPanel<OneLensMainPanel>(BorderLayout()) {

    private val statusLabel = JBLabel("OneLens: initializing…")
    private val falkordbLabel = JBLabel(" ")
    private val semanticLabel = JBLabel(" ")
    private val branchLabel = JBLabel(" ")
    private val seedLabel = JBLabel(" ")
    private val checklistPanel = JPanel()
    private val prereqSummary = JBLabel(" ")
    private var checklistForceVisible = false
    private val statsLabel = JBLabel(" ")
    private val resourcesLabel = JBLabel(" ")
    private val lastSyncLabel = JBLabel(" ")
    @Volatile private var lastSyncTs: Long? = null
    private val console: ConsoleView = TextConsoleBuilderFactory.getInstance()
        .createBuilder(project)
        .console

    // Cached last status snapshot so StatusChange events don't wipe the
    // FalkorDB / semantic line (we only have state, not a full snapshot).
    @Volatile private var lastSnapshot: OneLensStatus? = null
    // Cached last SyncComplete so the stats row survives across refreshes.
    @Volatile private var lastSyncInfo: String = ""
    private val syncRunning = java.util.concurrent.atomic.AtomicBoolean(false)
    private val setupRunning = java.util.concurrent.atomic.AtomicBoolean(false)

    init {
        border = JBUI.Borders.empty(8)

        val header = buildHeader()
        val toolbar = buildToolbar()
        val body = buildBody()

        val top = JPanel(BorderLayout())
        top.add(header, BorderLayout.NORTH)
        top.add(toolbar, BorderLayout.CENTER)
        top.add(body, BorderLayout.SOUTH)

        add(top, BorderLayout.NORTH)
        add(console.component, BorderLayout.CENTER)
        console.component.isVisible = false // show after first event

        subscribe()
        refreshAsync()

        // Tick the "Last sync: … ago" label every 30 s so it doesn't stay
        // stale at "18h ago" for a day. Only re-formats the cached timestamp —
        // no status poll, no git shell-out.
        javax.swing.Timer(30_000) {
            val ts = lastSyncTs ?: return@Timer
            lastSyncLabel.text = if (lastSyncInfo.isNotEmpty())
                "$lastSyncInfo   (file ${fmtAgo(ts)})"
            else
                "Last sync: ${fmtAgo(ts)}"
        }.apply { isRepeats = true; start() }

        // Semantic line refresh: every 5 s read MCP state + shell `nvidia-smi`
        // (if available) to show live VRAM. Coalesces when MCP is down so the
        // poller does no work on structural-only projects.
        javax.swing.Timer(5_000) {
            updateSemanticLine()
        }.apply { isRepeats = true; start() }
        updateSemanticLine()
    }

    private fun updateSemanticLine() {
        val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
        if (!settings.buildSemanticIndex) {
            semanticLabel.text = "Semantic: off (click Enable Semantic in the toolbar)"
            semanticLabel.foreground = semanticLabel.foreground.darker()
            return
        }
        val mcp = com.onelens.plugin.mcp.OneLensMcpService.getInstance()
        if (!mcp.isRunning) {
            semanticLabel.text = "Semantic: on · MCP server not running (will start on next sync)"
            return
        }
        val provider = SystemMonitor.localProvider()
        val pid = mcp.pid()
        val vramBytes = SystemMonitor.gpuMemoryBytesForPid(pid)
        val vramPart = if (vramBytes > 0) " · VRAM ${fmtBytes(vramBytes)}" else ""
        semanticLabel.text = "Semantic: on · $provider · MCP pid=$pid$vramPart"
    }

    private fun buildHeader(): JComponent {
        val stack = JPanel().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            border = JBUI.Borders.emptyBottom(6)
        }
        statusLabel.horizontalAlignment = SwingConstants.LEFT
        statusLabel.font = statusLabel.font.deriveFont(statusLabel.font.size2D + 1f).deriveFont(java.awt.Font.BOLD)
        statusLabel.alignmentX = java.awt.Component.LEFT_ALIGNMENT
        falkordbLabel.horizontalAlignment = SwingConstants.LEFT
        falkordbLabel.alignmentX = java.awt.Component.LEFT_ALIGNMENT
        branchLabel.horizontalAlignment = SwingConstants.LEFT
        branchLabel.alignmentX = java.awt.Component.LEFT_ALIGNMENT
        branchLabel.foreground = branchLabel.foreground.darker()
        seedLabel.horizontalAlignment = SwingConstants.LEFT
        seedLabel.alignmentX = java.awt.Component.LEFT_ALIGNMENT
        seedLabel.foreground = java.awt.Color(0xC7, 0x8F, 0x00)
        seedLabel.isVisible = false
        semanticLabel.horizontalAlignment = SwingConstants.LEFT
        semanticLabel.alignmentX = java.awt.Component.LEFT_ALIGNMENT
        stack.add(statusLabel)
        stack.add(falkordbLabel)
        stack.add(semanticLabel)
        stack.add(branchLabel)
        stack.add(seedLabel)
        return stack
    }

    private fun buildToolbar(): JComponent {
        val group = DefaultActionGroup().apply {
            add(SyncAction())
            add(SetupAction())
            add(ToggleSemanticToolbarAction())
            add(RebuildSemanticAction())
            add(ToggleAutoSyncToolbarAction())
            add(InstallSkillToolbarAction())
            ActionManager.getInstance().getAction("onelens.PublishSnapshot")?.let { add(it) }
            addSeparator()
            add(RefreshAction())
            add(OpenFalkorUIAction())
            add(DangerZoneAction())
            add(ClearLogAction())
        }
        val tb = ActionManager.getInstance()
            .createActionToolbar("OneLensToolWindow", group, true)
        tb.targetComponent = this
        return tb.component
    }

    private fun buildBody(): JComponent {
        val panel = JPanel().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            border = JBUI.Borders.emptyTop(4)
        }
        checklistPanel.layout = GridBagLayout()
        checklistPanel.border = BorderFactory.createTitledBorder("Prerequisites")
        prereqSummary.apply {
            foreground = java.awt.Color(0x3A, 0x9B, 0x3A)
            cursor = java.awt.Cursor.getPredefinedCursor(java.awt.Cursor.HAND_CURSOR)
            addMouseListener(object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    checklistForceVisible = !checklistForceVisible
                    checklistPanel.isVisible = checklistForceVisible
                    prereqSummary.text = if (checklistForceVisible)
                        "✓ Prerequisites OK (click to collapse)"
                    else
                        "✓ Prerequisites OK (click to expand)"
                    revalidate(); repaint()
                }
            })
        }
        panel.add(prereqSummary)
        panel.add(checklistPanel)

        val stats = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        stats.border = JBUI.Borders.emptyTop(6)
        stats.add(statsLabel)
        panel.add(stats)

        val res = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        resourcesLabel.font = resourcesLabel.font.deriveFont(resourcesLabel.font.size2D - 1f)
        resourcesLabel.foreground = resourcesLabel.foreground.darker()
        res.add(resourcesLabel)
        panel.add(res)

        val last = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        last.add(lastSyncLabel)
        panel.add(last)

        return panel
    }

    private fun subscribe() {
        val conn = ApplicationManager.getApplication().messageBus.connect(console)
        conn.subscribe(OneLensEventBus.TOPIC, object : OneLensEventListener {
            override fun onEvent(event: OneLensEvent) {
                when (event) {
                    is OneLensEvent.Info -> logLine(event.message, ConsoleViewContentType.LOG_INFO_OUTPUT)
                    is OneLensEvent.Warn -> logLine(event.message, ConsoleViewContentType.LOG_WARNING_OUTPUT)
                    is OneLensEvent.Error -> {
                        logLine(event.message, ConsoleViewContentType.LOG_ERROR_OUTPUT)
                        event.throwable?.let { logLine(it.stackTraceToString(), ConsoleViewContentType.LOG_ERROR_OUTPUT) }
                    }
                    is OneLensEvent.StatusChange -> {
                        // Release the sync button guard when a backend signals
                        // READY / ERROR (we never release on SYNCING).
                        if (event.state == OneLensState.READY || event.state == OneLensState.ERROR) {
                            syncRunning.set(false)
                        }
                        ApplicationManager.getApplication().invokeLater({
                            renderStatus(event.state, lastSnapshot)
                        }, ModalityState.any())
                    }
                    is OneLensEvent.Progress -> logLine("[${(event.fraction * 100).toInt()}%] ${event.label}", ConsoleViewContentType.LOG_INFO_OUTPUT)
                    is OneLensEvent.SyncComplete -> {
                        // Release the sync-running guard — the StatusChange →
                        // READY event that was supposed to do this doesn't
                        // always fire, so SyncComplete is the reliable signal.
                        syncRunning.set(false)
                        // Render counts per active adapter. On Java-only projects
                        // we show the classes/methods/edges line; Vue-only projects
                        // showed "0 classes · 0 methods" before, which looked like
                        // a silent failure. Composite projects show both.
                        val summary = buildSyncSummary(event)
                        logLine(
                            "Sync complete (${if (event.isDelta) "delta" else "full"}) · $summary · ${event.durationMs}ms",
                            ConsoleViewContentType.LOG_INFO_OUTPUT,
                        )
                        lastSyncInfo = "Last sync: ${if (event.isDelta) "delta" else "full"} — " +
                            "$summary · ${event.durationMs}ms"
                        // refreshAsync re-reads the .onelens-baseline marker so the
                        // "⚑ Seeded from @<tag>" banner disappears once DeltaTracker
                        // has consumed it (marker file is gone → banner hides).
                        refreshAsync()
                    }
                }
            }
        })
    }

    /**
     * Build a per-adapter "X classes · Y methods" summary from a SyncComplete
     * event. Shows JVM counts only on Java-only projects, Vue counts only on
     * Vue-only projects, both on composite projects. Stops showing the
     * "0 classes · 0 methods" line on frontend-only syncs that used to look
     * like a silent failure.
     */
    private fun buildSyncSummary(e: OneLensEvent.SyncComplete): String {
        val parts = mutableListOf<String>()
        val adapters = e.activeAdapters
        val hasJvm = adapters.contains("spring-boot") || e.classes > 0 || e.methods > 0 || e.callEdges > 0
        val hasVue = adapters.contains("vue3") || e.vueNodes > 0 || e.jsModules > 0
        if (hasJvm) {
            parts += "${e.classes} classes · ${e.methods} methods · ${e.callEdges} edges"
        }
        if (hasVue) {
            parts += "${e.vueNodes} Vue nodes · ${e.vueEdges} Vue edges" +
                if (e.jsModules > 0) " · ${e.jsModules} modules · ${e.jsFunctions} fns" else ""
        }
        if (parts.isEmpty()) {
            parts += "${e.classes} classes · ${e.methods} methods · ${e.callEdges} edges"
        }
        return parts.joinToString(" · ")
    }

    private fun logLine(text: String, type: ConsoleViewContentType) {
        ApplicationManager.getApplication().invokeLater({
            val ts = SimpleDateFormat("HH:mm:ss").format(Date())
            console.print("[$ts] $text\n", type)
            if (!console.component.isVisible) {
                console.component.isVisible = true
                revalidate(); repaint()
            }
        }, ModalityState.any())
    }

    private fun refreshAsync() {
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "OneLens: refreshing status", true) {
            override fun run(indicator: ProgressIndicator) {
                val snap = OneLensStatusService.getInstance(project).snapshot()
                val branch = com.onelens.plugin.snapshots.GitInfo.currentBranch(project)
                val sha = com.onelens.plugin.snapshots.GitInfo.headSha(project)
                val seedTag = readSeedTag(snap.graphName)
                ApplicationManager.getApplication().invokeLater({
                    render(snap)
                    branchLabel.text = when {
                        branch != null && sha != null -> "Branch: $branch  ·  HEAD: ${sha.take(7)}"
                        branch != null -> "Branch: $branch"
                        else -> " "
                    }
                    if (seedTag != null) {
                        seedLabel.text = "⚑ Seeded from @$seedTag — next Sync will delta from this point"
                        seedLabel.isVisible = true
                    } else {
                        seedLabel.isVisible = false
                    }
                }, ModalityState.any())
            }
        })
    }

    private fun render(s: OneLensStatus) {
        lastSnapshot = s
        val state = when {
            !s.falkordbReachable -> OneLensState.ERROR
            s.cliPath == null -> OneLensState.SETTING_UP
            else -> OneLensState.READY
        }
        renderStatus(state, s)
        renderChecklist(s)
        statsLabel.text = "Graph: ${s.graphName ?: "—"}   Exports: ${s.exportCount}   ChromaDB: ${fmtBytes(s.chromaSizeBytes)}"
        resourcesLabel.text = "Venv: ${fmtBytes(s.venvSizeBytes)}   Exports on disk: ${fmtBytes(s.exportsSizeBytes)}"
        lastSyncTs = s.lastExportTimestamp
        val ts = s.lastExportTimestamp?.let { fmtAgo(it) } ?: "never"
        lastSyncLabel.text = if (lastSyncInfo.isNotEmpty()) "$lastSyncInfo   (file $ts)" else "Last sync: $ts"
        revalidate(); repaint()
    }

    private fun renderStatus(state: OneLensState, s: OneLensStatus?) {
        val (text, color) = when (state) {
            OneLensState.READY -> "OneLens: Ready" to Color(0x3A, 0x9B, 0x3A)
            OneLensState.SETTING_UP -> "OneLens: Setting up…" to Color(0xC7, 0x8F, 0x00)
            OneLensState.SYNCING -> "OneLens: Syncing…" to Color(0x1E, 0x8E, 0xD5)
            OneLensState.ERROR -> (if (s?.backend == "falkordblite")
                "OneLens: Graph not yet indexed" else "OneLens: Error — FalkorDB unreachable"
                ) to Color(0xC0, 0x38, 0x38)
            OneLensState.UNKNOWN -> "OneLens: Unknown" to Color(0x99, 0x99, 0x99)
        }
        statusLabel.text = text
        statusLabel.foreground = color
        s?.let {
            val reach = if (it.falkordbReachable) "✓" else "✗"
            val backendLine = when (it.backend) {
                "falkordblite" -> "FalkorDB Lite: embedded $reach"
                else -> "FalkorDB: ${it.falkordbHost}:${it.falkordbPort} $reach"
            }
            // Drop the legacy "Semantic: …" suffix from this line — the
            // dedicated semanticLabel below carries the live status + VRAM
            // + MCP PID. The old suffix hard-coded "modal SDK not installed"
            // which was wrong for users on the new local / openai backends.
            falkordbLabel.text = backendLine
        }
    }

    private fun renderChecklist(s: OneLensStatus) {
        checklistPanel.removeAll()
        val failures = listOfNotNull(
            if (!s.falkordbReachable && s.backend != "falkordblite") "backend" else null,
            if (s.uvPath == null) "uv" else null,
            if (!s.venvExists) "venv" else null,
            if (s.cliPath == null) "cli" else null,
        )
        val allOk = failures.isEmpty()
        if (allOk) {
            prereqSummary.isVisible = true
            prereqSummary.text = "✓ Prerequisites OK (click to expand)"
            checklistPanel.isVisible = checklistForceVisible
        } else {
            prereqSummary.isVisible = false
            checklistPanel.isVisible = true
        }
        val backendCheck = when (s.backend) {
            "falkordblite" -> checkItem(
                s.falkordbReachable, "FalkorDB Lite",
                if (s.falkordbReachable) "embedded rdb at ${s.liteRdbPath} (${fmtBytes(s.liteRdbSizeBytes)})"
                else "no graph indexed yet",
                "run Sync Graph to build the embedded rdb",
            )
            else -> checkItem(
                s.falkordbReachable, "FalkorDB",
                "running at ${s.falkordbHost}:${s.falkordbPort}",
                "start: docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest",
            )
        }
        val semanticItems = if (s.semanticEnabled) listOf(
            checkItem(s.modalAvailable != false, "modal SDK",
                if (s.modalAvailable == true) "installed (remote backend ready)"
                else "missing — semantic search disabled",
                "re-run setup"),
            checkItem(true, "Embeddings backend",
                "configured via ONELENS_EMBED_BACKEND (modal | openai); weights live on the remote.",
                null),
        ) else emptyList()
        val items = listOf(
            backendCheck,
            checkItem(s.uvPath != null, "uv", "found at ${s.uvPath ?: "—"}",
                "install: curl -LsSf https://astral.sh/uv/install.sh | sh"),
            checkItem(s.venvExists, "Python venv", "~/.onelens/venv",
                "run 'Setup / Reinstall' below"),
            checkItem(s.cliPath != null, "onelens CLI", s.cliPath ?: "not installed",
                "run 'Setup / Reinstall' below"),
        ) + semanticItems
        val c = GridBagConstraints().apply {
            gridx = 0; anchor = GridBagConstraints.NORTHWEST
            fill = GridBagConstraints.HORIZONTAL; weightx = 1.0
            insets = Insets(2, 4, 2, 4)
        }
        var row = 0
        for (item in items) {
            c.gridy = row++
            checklistPanel.add(item, c)
        }
    }

    private fun checkItem(ok: Boolean, name: String, detail: String, fix: String?): JComponent {
        val icon = if (ok) AllIcons.General.InspectionsOK else AllIcons.General.BalloonError
        // Render fix hint inline (not just as tooltip) so broken prerequisites
        // are actionable at a glance.
        val html = buildString {
            append("<html><b>").append(name).append("</b>  ")
            append("<span style='color:#888'>").append(detail).append("</span>")
            if (!ok && fix != null) {
                append("<br/><span style='color:#B04040;font-size:smaller'>Fix: ").append(fix).append("</span>")
            }
            append("</html>")
        }
        return JBLabel(html, icon, SwingConstants.LEFT)
    }

    private fun fmtBytes(b: Long): String = when {
        b <= 0 -> "0 B"
        b < 1024 -> "$b B"
        b < 1024L * 1024 -> "%.1f KB".format(b / 1024.0)
        b < 1024L * 1024 * 1024 -> "%.1f MB".format(b / (1024.0 * 1024))
        else -> "%.2f GB".format(b / (1024.0 * 1024 * 1024))
    }

    private fun fmtAgo(ts: Long): String {
        val diff = System.currentTimeMillis() - ts
        return when {
            diff < 60_000 -> "${diff / 1000}s ago"
            diff < 3600_000 -> "${diff / 60_000}m ago"
            diff < 86_400_000 -> "${diff / 3600_000}h ago"
            else -> SimpleDateFormat("yyyy-MM-dd HH:mm").format(Date(ts))
        }
    }

    // ─── Toolbar Actions ───────────────────────────────────────────────────

    private inner class SyncAction : AnAction("Sync Graph",
        "Smart sync — delta when possible, falls back to full",
        AllIcons.Actions.Refresh) {
        override fun actionPerformed(e: AnActionEvent) {
            if (!syncRunning.compareAndSet(false, true)) {
                publish(OneLensEvent.Warn("Sync already running — ignoring double-click"))
                return
            }
            publish(OneLensEvent.Info("Sync Graph requested"))
            // Dispatch through the registered action so we get the same smart
            // full/delta detection + ProgressManager task that Tools → OneLens
            // → Sync Graph uses. The guard is released by the StatusChange
            // listener when the backend publishes READY / ERROR. If the
            // backend never does, Refresh clears the UI and the user can
            // click Sync again (idempotent).
            val action = ActionManager.getInstance().getAction("OneLens.SyncGraph")
            if (action != null) {
                action.actionPerformed(e)
            } else {
                publish(OneLensEvent.Error("OneLens.SyncGraph action not registered"))
                syncRunning.set(false)
            }
        }

        override fun update(e: AnActionEvent) {
            val dumb = com.intellij.openapi.project.DumbService.isDumb(project)
            e.presentation.isEnabled = !syncRunning.get() && !dumb
            e.presentation.description = when {
                dumb -> "Waiting for IntelliJ to finish indexing — " +
                    "PSI APIs throw IndexNotReadyException during dumb mode, " +
                    "which produces an empty graph."
                syncRunning.get() -> "Sync already running"
                else -> "Smart sync — delta when possible, falls back to full"
            }
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT
    }

    private inner class SetupAction : AnAction("Setup / Reinstall",
        "Recreate the OneLens venv and reinstall the CLI",
        AllIcons.Actions.Install) {
        override fun actionPerformed(e: AnActionEvent) {
            if (!setupRunning.compareAndSet(false, true)) {
                publish(OneLensEvent.Warn("Setup already running"))
                return
            }
            publish(OneLensEvent.Info("Running Setup / Reinstall…"))
            ApplicationManager.getApplication().executeOnPooledThread {
                try {
                    val venv = java.io.File(System.getProperty("user.home") + "/.onelens/venv")
                    if (venv.exists()) {
                        venv.deleteRecursively()
                        publish(OneLensEvent.Info("Removed stale venv"))
                    }
                    val cli = PythonEnvManager.getOneLensCli(ExportConfig().onelensSourcePath)
                    if (cli != null) publish(OneLensEvent.Info("Setup complete: $cli"))
                    else publish(OneLensEvent.Error("Setup failed — see idea.log"))
                } finally {
                    setupRunning.set(false)
                    refreshAsync()
                }
            }
        }

        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = !setupRunning.get()
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT
    }

    private inner class ToggleAutoSyncToolbarAction : AnAction() {
        override fun actionPerformed(e: AnActionEvent) {
            val svc = project.getService(com.onelens.plugin.autosync.AutoSyncService::class.java) ?: return
            val settings = com.onelens.plugin.settings.OneLensSettings.getInstance()
            if (svc.isEnabled()) {
                svc.disable(); settings.state.autoSyncEnabled = false
                publish(OneLensEvent.Info("Auto-sync disabled"))
            } else {
                svc.enable(); settings.state.autoSyncEnabled = true
                publish(OneLensEvent.Info("Auto-sync enabled — .java saves trigger delta imports"))
            }
        }

        override fun update(e: AnActionEvent) {
            val svc = project.getService(com.onelens.plugin.autosync.AutoSyncService::class.java)
            val enabled = svc?.isEnabled() == true
            e.presentation.text = if (enabled) "Disable Auto-Sync" else "Enable Auto-Sync"
            e.presentation.description = if (enabled)
                "Stop reacting to .java file saves" else "React to .java saves with a debounced delta import"
            e.presentation.icon = if (enabled) AllIcons.Actions.Suspend else AllIcons.Actions.Execute
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT
    }

    private inner class ToggleSemanticToolbarAction : AnAction() {
        override fun actionPerformed(e: AnActionEvent) {
            val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
            val mcp = com.onelens.plugin.mcp.OneLensMcpService.getInstance()
            if (settings.buildSemanticIndex) {
                settings.buildSemanticIndex = false
                mcp.stop()
                publish(OneLensEvent.Info("Semantic index disabled — MCP server stopped, VRAM freed"))
            } else {
                settings.buildSemanticIndex = true
                // Install backend-appropriate deps if missing (chromadb +
                // onnxruntime-gpu / httpx). Runs off-EDT via Task.Backgroundable
                // so the toolbar click stays responsive.
                ProgressManager.getInstance().run(object : Task.Backgroundable(
                    project, "OneLens: Enabling semantic index", true,
                ) {
                    override fun run(indicator: ProgressIndicator) {
                        PythonEnvManager.installSemanticStack()
                        // Start MCP now — server warms embed + rerank TRT
                        // engines via ONELENS_WARM_ON_START, so first sync
                        // lands on hot providers.
                        val port = mcp.start()
                        if (port > 0) {
                            publish(OneLensEvent.Info("Semantic index enabled · MCP on port $port (warming up)"))
                        } else {
                            publish(OneLensEvent.Warn("Semantic enabled but MCP server failed to start — check idea.log"))
                        }
                    }
                })
            }
            updateSemanticLine()
        }

        override fun update(e: AnActionEvent) {
            val on = com.onelens.plugin.settings.OneLensSettings.getInstance().state.buildSemanticIndex
            e.presentation.text = if (on) "Disable Semantic Index" else "Enable Semantic Index"
            e.presentation.description = if (on)
                "Stop embedding index, free VRAM" else "Build ChromaDB embeddings alongside the graph (~7 min first sync with GPU)"
            e.presentation.icon = if (on) AllIcons.Diff.MagicResolve else AllIcons.Diff.MagicResolveToolbar
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT
    }

    private inner class RebuildSemanticAction : AnAction(
        "Rebuild Semantic Only",
        "Re-embed the existing graph (skip graph import). ~2-3 min on GPU, ~30 min on CPU.",
        AllIcons.Actions.Rerun,
    ) {
        override fun update(e: AnActionEvent) {
            val graph = lastSnapshot?.graphName
            val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
            e.presentation.isEnabled = !graph.isNullOrBlank() && settings.buildSemanticIndex
            e.presentation.description = when {
                graph.isNullOrBlank() -> "Waiting for status refresh — graph name not yet known"
                !settings.buildSemanticIndex -> "Enable Semantic Index first"
                else -> "Re-embed '$graph' from the latest export. Skips graph import."
            }
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT

        override fun actionPerformed(e: AnActionEvent) {
            val graph = lastSnapshot?.graphName?.takeIf { it.isNotBlank() } ?: return
            val cliPath = PythonEnvManager.getOneLensCli() ?: run {
                publish(OneLensEvent.Error("onelens CLI not found — run Sync once first to install venv"))
                return
            }
            ProgressManager.getInstance().run(object : Task.Backgroundable(
                project, "OneLens: Rebuilding semantic index for '$graph'", true,
            ) {
                override fun run(indicator: ProgressIndicator) {
                    val cmd = listOf(cliPath, "call-tool", "onelens_reindex_semantic",
                        "--graph", graph)
                    publish(OneLensEvent.Info("$ ${cmd.joinToString(" ")}"))
                    val pb = ProcessBuilder(cmd).redirectErrorStream(true)
                    // Pass the same backend env the regular sync uses so the
                    // CLI subprocess picks up local embedder + local rerank.
                    val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
                    val env = pb.environment()
                    // Same ONELENS_PROJECT_ROOT reason as ExportService —
                    // CodeMiner + retrieval both resolve project-relative
                    // file_paths against this root.
                    project.basePath?.let { env["ONELENS_PROJECT_ROOT"] = it }
                    when (settings.embedderBackend.lowercase()) {
                        "local" -> {
                            env["ONELENS_EMBED_BACKEND"] = "local"
                            env["ONELENS_RERANK_BACKEND"] = "local"
                        }
                        "openai" -> {
                            env["ONELENS_EMBED_BACKEND"] = "openai"
                            env["ONELENS_RERANK_BACKEND"] = "none"
                            env["ONELENS_EMBED_BASE_URL"] = settings.openaiBaseUrl
                            env["ONELENS_EMBED_MODEL"] = settings.openaiEmbedModel
                            env["ONELENS_EMBED_DIM"] = settings.openaiEmbedDim.toString()
                            com.onelens.plugin.settings.OpenAiSecrets.get()?.let {
                                env["ONELENS_EMBED_API_KEY"] = it
                            }
                        }
                    }
                    val proc = pb.start()
                    proc.inputStream.bufferedReader().use { r ->
                        while (true) {
                            val line = r.readLine() ?: break
                            publish(OneLensEvent.Info(line))
                        }
                    }
                    val code = proc.waitFor()
                    if (code == 0) publish(OneLensEvent.Info("Semantic rebuild complete"))
                    else publish(OneLensEvent.Error("Semantic rebuild failed (exit $code)"))
                    refreshAsync()
                }
            })
        }
    }

    private inner class DangerZoneAction : AnAction(
        "Clean Up…",
        "Delete graph, exports, or semantic index for a fresh start",
        AllIcons.Actions.GC,
    ) {
        override fun update(e: AnActionEvent) {
            // Disable until we know the graph name — destructive ops on a
            // fallback "current" name would no-op or wipe the wrong target.
            val haveGraph = !lastSnapshot?.graphName.isNullOrBlank()
            e.presentation.isEnabled = haveGraph
            e.presentation.description = if (haveGraph)
                "Delete graph, exports, or semantic index for a fresh start"
            else
                "Waiting for status refresh — graph name not yet known"
        }

        override fun getActionUpdateThread() = com.intellij.openapi.actionSystem.ActionUpdateThread.BGT

        override fun actionPerformed(e: AnActionEvent) {
            val graph = lastSnapshot?.graphName?.takeIf { it.isNotBlank() } ?: return
            val choice = com.intellij.openapi.ui.Messages.showDialog(
                project,
                "Pick a cleanup target — all operations are irreversible:\n\n" +
                    "• Clear exports: deletes ~/.onelens/exports/$graph-*.json\n" +
                    "• Reset semantic: wipes ChromaDB + TRT cache (forces re-embed)\n" +
                    "• Delete graph: wipes the rdb (graph goes to 0 nodes)",
                "OneLens Clean Up",
                arrayOf("Clear exports", "Reset semantic", "Delete graph", "Cancel"),
                3,
                AllIcons.General.WarningDialog,
            )
            val svc = GraphCleanupService.getInstance()
            when (choice) {
                0 -> {
                    val r = svc.clearExports(graph)
                    publish(OneLensEvent.Info("Cleared ${r.description} — freed ${fmtBytes(r.bytesFreed)}"))
                    refreshAsync()
                }
                1 -> {
                    val r = svc.resetSemantic(graph)
                    publish(OneLensEvent.Info("Reset ${r.description} — freed ${fmtBytes(r.bytesFreed)}. Re-sync to rebuild embeddings."))
                    updateSemanticLine()
                }
                2 -> {
                    if (com.intellij.openapi.ui.Messages.showYesNoDialog(
                            project,
                            "Delete graph '$graph' (rdb ${fmtBytes(lastSnapshot?.liteRdbSizeBytes ?: 0L)})? Re-sync required.",
                            "Delete graph",
                            AllIcons.General.WarningDialog,
                        ) == com.intellij.openapi.ui.Messages.YES) {
                        val r = svc.deleteGraph(graph)
                        publish(OneLensEvent.Warn("Deleted ${r.description} — freed ${fmtBytes(r.bytesFreed)}. Click Sync to rebuild."))
                        refreshAsync()
                    }
                }
            }
        }
    }

    private inner class InstallSkillToolbarAction : AnAction("Install Claude Skill",
        "Drop SKILL.md into ~/.claude/skills/onelens/",
        AllIcons.Actions.Download) {
        override fun actionPerformed(e: AnActionEvent) {
            InstallSkillAction().actionPerformed(e)
            publish(OneLensEvent.Info("Skill install requested"))
        }
    }

    private inner class RefreshAction : AnAction("Refresh", "Recompute status", AllIcons.Actions.Refresh) {
        override fun actionPerformed(e: AnActionEvent) = refreshAsync()
    }

    private inner class OpenFalkorUIAction : AnAction("Open FalkorDB Browser",
        "Launch http://localhost:3001 in your browser",
        AllIcons.General.Web) {
        override fun actionPerformed(e: AnActionEvent) {
            try {
                com.intellij.ide.BrowserUtil.browse("http://localhost:3001")
            } catch (t: Throwable) {
                publish(OneLensEvent.Warn("Could not open browser: ${t.message}"))
            }
        }
    }

    private inner class ClearLogAction : AnAction("Clear / Hide Log", "Clear the event log + hide it until next event", AllIcons.Actions.GC) {
        override fun actionPerformed(e: AnActionEvent) {
            console.clear()
            console.component.isVisible = false
            revalidate(); repaint()
        }
    }

    private fun readSeedTag(graphId: String?): String? {
        if (graphId.isNullOrBlank()) return null
        val marker = java.io.File(
            System.getProperty("user.home"),
            ".onelens/graphs/$graphId/.onelens-baseline",
        )
        if (!marker.isFile) return null
        return try {
            Regex("\"tag\"\\s*:\\s*\"([^\"]+)\"")
                .find(marker.readText())?.groupValues?.get(1)
        } catch (_: Throwable) { null }
    }

    private fun publish(event: OneLensEvent) {
        ApplicationManager.getApplication().messageBus
            .syncPublisher(OneLensEventBus.TOPIC)
            .onEvent(event)
    }
}
