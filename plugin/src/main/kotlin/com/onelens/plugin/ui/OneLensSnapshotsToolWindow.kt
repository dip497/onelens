package com.onelens.plugin.ui

import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.ui.ScrollPaneFactory
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBPanel
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import com.onelens.plugin.snapshots.LocalSnapshot
import com.onelens.plugin.snapshots.PublishedBundle
import com.onelens.plugin.snapshots.SnapshotManager
import java.awt.BorderLayout
import java.awt.Component
import java.awt.Dimension
import java.awt.FlowLayout
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import javax.swing.BorderFactory
import javax.swing.BoxLayout
import javax.swing.DefaultListModel
import javax.swing.JComponent
import javax.swing.JList
import javax.swing.JPanel
import javax.swing.ListCellRenderer
import javax.swing.SwingConstants

/** Unified model for both remote and local rows. */
private sealed class Row {
    abstract val display: String

    data class Published(val bundle: PublishedBundle, val installed: Boolean) : Row() {
        override val display: String get() = buildString {
            append(bundle.tag).append("  ·  ").append(humanBytes(bundle.tgzBytes)).append("  ·  tgz")
            if (installed) append("  ·  ✓ installed")
        }
    }

    data class Local(val snap: LocalSnapshot) : Row() {
        override val display: String get() =
            "${snap.tag}  ·  ${humanBytes(snap.rdbBytes)}  ·  rdb"
    }

    data class Header(val text: String) : Row() {
        override val display: String get() = text
    }
}

class OneLensSnapshotsPanel(private val project: Project) : JBPanel<OneLensSnapshotsPanel>(BorderLayout()) {

    private val model = DefaultListModel<Row>()
    private val list = JBList(model).apply {
        cellRenderer = RowRenderer()
        selectionMode = javax.swing.ListSelectionModel.SINGLE_SELECTION
    }
    private val graphLabel = JBLabel(" ")

    init {
        border = BorderFactory.createEmptyBorder(6, 8, 6, 8)
        add(header(), BorderLayout.NORTH)
        add(ScrollPaneFactory.createScrollPane(list), BorderLayout.CENTER)
        list.addMouseListener(object : MouseAdapter() {
            override fun mousePressed(e: MouseEvent) { maybePopup(e) }
            override fun mouseReleased(e: MouseEvent) { maybePopup(e) }
            override fun mouseClicked(e: MouseEvent) {
                if (e.clickCount == 2 && !e.isPopupTrigger) {
                    val row = list.selectedValue ?: return
                    onRowActivate(row)
                }
            }
            private fun maybePopup(e: MouseEvent) {
                if (!e.isPopupTrigger) return
                val idx = list.locationToIndex(e.point).takeIf { it >= 0 } ?: return
                list.selectedIndex = idx
                val row = model.getElementAt(idx)
                when (row) {
                    is Row.Local -> showLocalContextMenu(row.snap, e)
                    is Row.Published -> showPublishedContextMenu(row.bundle, row.installed, e)
                    is Row.Header -> Unit
                }
            }
        })
        refresh()
    }

    private fun header(): JComponent {
        val bar = JPanel(FlowLayout(FlowLayout.LEFT, 4, 4))
        val group = DefaultActionGroup().apply {
            add(object : AnAction("Refresh", null, AllIcons.Actions.Refresh) {
                override fun actionPerformed(e: AnActionEvent) = refresh()
            })
            add(ActionManager.getInstance().getAction("onelens.PublishSnapshot")
                ?: object : AnAction("Publish…", null, AllIcons.Actions.Upload) {
                    override fun actionPerformed(e: AnActionEvent) {
                        ActionManager.getInstance().getAction("onelens.PublishSnapshot")
                            ?.actionPerformed(e)
                    }
                })
        }
        val toolbar = ActionManager.getInstance().createActionToolbar(
            ActionPlaces.TOOLWINDOW_CONTENT, group, true
        )
        toolbar.targetComponent = this
        bar.add(toolbar.component)
        val labels = JPanel().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            graphLabel.alignmentX = Component.LEFT_ALIGNMENT
            add(graphLabel)
        }
        val wrap = JPanel(BorderLayout())
        wrap.add(bar, BorderLayout.NORTH)
        wrap.add(labels, BorderLayout.CENTER)
        return wrap
    }

    fun refresh() {
        val workspace = try { WorkspaceLoader.load(project) } catch (_: Exception) { return }
        val graph = workspace.graphId
        graphLabel.text = "Graph: $graph"
        val mgr = SnapshotManager.getInstance(project)
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Loading snapshots", false) {
            override fun run(indicator: ProgressIndicator) {
                val published = mgr.listPublished(graph)
                val local = mgr.listLocal(graph)
                val installedTags = local.map { it.tag }.toSet()
                ApplicationManager.getApplication().invokeLater({
                    model.clear()
                    model.addElement(Row.Header("⇡ Published (${published.size})"))
                    published.forEach {
                        model.addElement(Row.Published(it, it.tag in installedTags))
                    }
                    model.addElement(Row.Header("⌂ Installed (${local.size})"))
                    local.forEach { model.addElement(Row.Local(it)) }
                }, ModalityState.any())
            }
        })
    }

    private fun onRowActivate(row: Row) {
        when (row) {
            is Row.Published -> installBundle(row.bundle)
            is Row.Local -> try {
                com.intellij.ide.actions.RevealFileAction.openDirectory(
                    java.io.File(row.snap.rdbPath).parentFile,
                )
            } catch (_: Throwable) {}
            is Row.Header -> Unit
        }
    }

    private fun installBundle(bundle: PublishedBundle) {
        val mgr = SnapshotManager.getInstance(project)
        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project, "OneLens: Installing ${bundle.graph}@${bundle.tag}", true,
        ) {
            override fun run(indicator: ProgressIndicator) {
                val out = mgr.install(bundle, indicator)
                ApplicationManager.getApplication().invokeLater({
                    val group = com.intellij.notification.NotificationGroupManager.getInstance()
                        .getNotificationGroup("OneLens")
                    if (out.exitCode == 0) {
                        group.createNotification(
                            "OneLens snapshot installed",
                            "${bundle.graph}@${bundle.tag} — query via --graph ${bundle.graph}@${bundle.tag}",
                            com.intellij.notification.NotificationType.INFORMATION,
                        ).notify(project)
                    } else {
                        group.createNotification(
                            "OneLens snapshot install failed",
                            (out.stderr ?: out.stdout).take(400),
                            com.intellij.notification.NotificationType.ERROR,
                        ).notify(project)
                    }
                    refresh()
                }, ModalityState.any())
            }
        })
    }

    private fun showPublishedContextMenu(bundle: PublishedBundle, installed: Boolean, e: MouseEvent) {
        val menu = javax.swing.JPopupMenu()
        menu.add(javax.swing.JMenuItem("Start working from this snapshot").apply {
            addActionListener {
                com.onelens.plugin.actions.StartFromSnapshotAction.run(
                    project, bundle.graph, bundle.tag, alreadyInstalled = installed,
                )
            }
        })
        menu.add(javax.swing.JMenuItem(if (installed) "Re-install (overwrite)" else "Install").apply {
            addActionListener { installBundle(bundle) }
        })
        menu.add(javax.swing.JMenuItem("Open bundles folder").apply {
            addActionListener {
                try {
                    com.intellij.ide.actions.RevealFileAction.openDirectory(
                        java.io.File(bundle.tgzPath).parentFile,
                    )
                } catch (_: Throwable) {}
            }
        })
        menu.addSeparator()
        menu.add(javax.swing.JMenuItem("Delete tgz…").apply {
            addActionListener {
                val ok = com.intellij.openapi.ui.Messages.showYesNoDialog(
                    project,
                    "Delete published bundle ${bundle.graph}@${bundle.tag}?\n\n" +
                        "File: ${bundle.tgzPath}\n" +
                        "Size: ${humanBytes(bundle.tgzBytes)}\n\n" +
                        "Installed copy (if any) is not affected.",
                    "Delete Bundle",
                    com.intellij.openapi.ui.Messages.getWarningIcon(),
                ) == com.intellij.openapi.ui.Messages.YES
                if (ok) {
                    java.io.File(bundle.tgzPath).delete()
                    java.io.File("${bundle.tgzPath}.sha256").delete()
                    refresh()
                }
            }
        })
        menu.show(list, e.x, e.y)
    }

    private fun showLocalContextMenu(snap: LocalSnapshot, e: MouseEvent?) {
        val menu = javax.swing.JPopupMenu()
        menu.add(javax.swing.JMenuItem("Start working from this snapshot").apply {
            addActionListener {
                com.onelens.plugin.actions.StartFromSnapshotAction.run(
                    project, snap.graph, snap.tag, alreadyInstalled = true,
                )
            }
        })
        menu.addSeparator()
        menu.add(javax.swing.JMenuItem("Copy --graph ${snap.graphName}").apply {
            addActionListener {
                val sel = java.awt.datatransfer.StringSelection("--graph ${snap.graphName}")
                java.awt.Toolkit.getDefaultToolkit().systemClipboard.setContents(sel, null)
            }
        })
        menu.add(javax.swing.JMenuItem("Open folder").apply {
            addActionListener {
                try {
                    val dir = java.io.File(snap.rdbPath).parentFile
                    com.intellij.ide.actions.RevealFileAction.openDirectory(dir)
                } catch (_: Throwable) {}
            }
        })
        menu.addSeparator()
        menu.add(javax.swing.JMenuItem("Delete…").apply {
            addActionListener {
                val ok = com.intellij.openapi.ui.Messages.showYesNoDialog(
                    project,
                    "Delete local snapshot ${snap.graphName}?\n\n" +
                        "Folder: ${java.io.File(snap.rdbPath).parent}\n" +
                        "Size: ${humanBytes(snap.rdbBytes)}",
                    "Delete Snapshot",
                    com.intellij.openapi.ui.Messages.getWarningIcon(),
                ) == com.intellij.openapi.ui.Messages.YES
                if (ok) {
                    val graphDir = java.io.File(snap.rdbPath).parentFile
                    graphDir.deleteRecursively()
                    val contextDir = java.io.File(
                        System.getProperty("user.home"),
                        ".onelens/context/${snap.graphName}",
                    )
                    if (contextDir.exists()) contextDir.deleteRecursively()
                    refresh()
                }
            }
        })
        if (e != null) menu.show(list, e.x, e.y) else menu.show(list, 20, 20)
    }

    private class RowRenderer : ListCellRenderer<Row> {
        private val label = JBLabel()
        private val panel = JPanel(BorderLayout()).apply {
            add(label, BorderLayout.CENTER)
            border = BorderFactory.createEmptyBorder(2, 6, 2, 6)
            preferredSize = Dimension(-1, 22)
        }

        override fun getListCellRendererComponent(
            list: JList<out Row>, value: Row, index: Int,
            isSelected: Boolean, cellHasFocus: Boolean,
        ): Component {
            label.text = value.display
            label.horizontalAlignment = SwingConstants.LEFT
            when (value) {
                is Row.Header -> {
                    label.icon = null
                    label.font = label.font.deriveFont(java.awt.Font.BOLD)
                }
                is Row.Published -> {
                    label.icon = if (value.installed) AllIcons.General.InspectionsOK
                                 else AllIcons.Actions.Download
                    label.font = label.font.deriveFont(java.awt.Font.PLAIN)
                }
                is Row.Local -> {
                    label.icon = AllIcons.Nodes.Folder
                    label.font = label.font.deriveFont(java.awt.Font.PLAIN)
                }
            }
            panel.background = if (isSelected) list.selectionBackground else list.background
            label.foreground = if (isSelected) list.selectionForeground else list.foreground
            return panel
        }
    }
}

private fun humanBytes(b: Long): String = when {
    b < 1024 -> "$b B"
    b < 1024 * 1024 -> "${b / 1024} KB"
    b < 1024L * 1024 * 1024 -> "${b / (1024 * 1024)} MB"
    else -> "%.1f GB".format(b / (1024.0 * 1024 * 1024))
}
