package com.onelens.plugin.actions

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.CapturingProcessHandler
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.onelens.plugin.export.PythonEnvManager
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import com.onelens.plugin.snapshots.SnapshotManager
import java.io.File

/**
 * Stage 1d — "Start working from this snapshot". Installs (if needed) +
 * promotes a snapshot into the live graph slot so the next Sync Graph
 * deltas only the branch diff since the tag's commit.
 *
 * Programmatic only — invoked from Snapshots tab right-click menu with
 * the user's chosen tag, not a plugin.xml action.
 */
object StartFromSnapshotAction {

    fun run(project: Project, graph: String, tag: String, alreadyInstalled: Boolean) {
        // Promotion renames graph keys in the rdb + swaps the live graph
        // folder. A live sync writing the rdb at the same time ends up
        // half-copied. Gate identically to the Publish path.
        if (com.onelens.plugin.export.SyncCoordinator.getInstance().isRunning()) {
            com.intellij.notification.NotificationGroupManager.getInstance().getNotificationGroup("OneLens")
                .createNotification(
                    "OneLens: cannot start from snapshot while sync is running",
                    "Wait for the current sync to finish (or cancel it from Background Tasks) before promoting a snapshot.",
                    com.intellij.notification.NotificationType.WARNING,
                ).notify(project)
            return
        }
        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project, "OneLens: Preparing seed from $graph@$tag", true,
        ) {
            override fun run(indicator: ProgressIndicator) {
                val basePath = try {
                    WorkspaceLoader.load(project).primaryRoot.toString()
                } catch (_: Exception) {
                    project.basePath ?: System.getProperty("user.home")
                }
                // Guard 3: ancestor check (warn, don't block).
                indicator.text = "Checking branch ancestry"
                val ancestor = runGit(basePath, "merge-base", "--is-ancestor", tag, "HEAD")
                val branchDescendsFromTag = ancestor.exitCode == 0

                // Guard 1: live graph exists?
                val liveRdb = File(
                    System.getProperty("user.home"),
                    ".onelens/graphs/$graph/$graph.rdb",
                )
                val liveExists = liveRdb.isFile && liveRdb.length() > 10_000

                val confirm = buildConfirmMessage(tag, graph, liveExists, branchDescendsFromTag)

                ApplicationManager.getApplication().invokeLater({
                    val choice = Messages.showYesNoDialog(
                        project, confirm,
                        "Start Working From Snapshot",
                        "Continue", "Cancel",
                        Messages.getQuestionIcon(),
                    )
                    if (choice == Messages.YES) {
                        runPromote(project, graph, tag, alreadyInstalled)
                    }
                }, ModalityState.any())
            }
        })
    }

    private fun buildConfirmMessage(
        tag: String, graph: String, liveExists: Boolean, branchDescendsFromTag: Boolean,
    ): String = buildString {
        append("Seed live graph `$graph` from snapshot @$tag?\n\n")
        append("• Next Sync Graph will delta from @$tag's commit → HEAD (fast).\n")
        if (liveExists) {
            append("• Your current live graph will be overwritten.\n")
        }
        if (!branchDescendsFromTag) {
            append("\n⚠ Your branch doesn't descend from @$tag. ")
            append("Delta may include many files (still faster than full sync).\n")
        }
    }

    private fun runPromote(project: Project, graph: String, tag: String, alreadyInstalled: Boolean) {
        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project, "OneLens: Seeding live graph from $graph@$tag", true,
        ) {
            override fun run(indicator: ProgressIndicator) {
                if (!alreadyInstalled) {
                    indicator.text = "Installing $graph@$tag"
                    val mgr = SnapshotManager.getInstance(project)
                    val published = mgr.listPublished(graph).firstOrNull { it.tag == tag }
                    if (published == null) {
                        notify(project, "Published bundle for @$tag not found", error = true)
                        return
                    }
                    val installOut = mgr.install(published, indicator)
                    if (installOut.exitCode != 0) {
                        notify(
                            project,
                            "Install failed: ${(installOut.stderr ?: installOut.stdout).take(300)}",
                            error = true,
                        )
                        return
                    }
                }

                indicator.text = "Promoting $graph@$tag to live graph"
                val cli = PythonEnvManager.getOneLensCli() ?: run {
                    notify(project, "onelens CLI not installed", error = true)
                    return
                }
                val basePath = try {
                    WorkspaceLoader.load(project).primaryRoot.toString()
                } catch (_: Exception) {
                    project.basePath ?: System.getProperty("user.home")
                }
                val cmd = GeneralCommandLine(
                    cli, "call-tool", "onelens_snapshot_promote",
                    "--graph", graph,
                    "--tag", tag,
                ).apply {
                    workDirectory = File(basePath)
                    charset = Charsets.UTF_8
                }
                val out = CapturingProcessHandler(cmd).runProcess(10 * 60 * 1000, true)

                ApplicationManager.getApplication().invokeLater({
                    if (out.exitCode == 0) {
                        notify(
                            project,
                            "Live graph seeded from @$tag. Next Sync will delta from this point.",
                        )
                    } else {
                        notify(
                            project,
                            "Promote failed: ${(out.stderr ?: out.stdout).take(300)}",
                            error = true,
                        )
                    }
                }, ModalityState.any())
            }
        })
    }

    private data class ProcOut(val exitCode: Int, val stdout: String)

    private fun runGit(cwd: String, vararg args: String): ProcOut = try {
        val cmd = GeneralCommandLine("git", *args).apply {
            workDirectory = File(cwd)
            charset = Charsets.UTF_8
        }
        val out = CapturingProcessHandler(cmd).runProcess(10_000, true)
        ProcOut(out.exitCode, out.stdout)
    } catch (_: Throwable) {
        ProcOut(1, "")
    }

    private fun notify(project: Project, msg: String, error: Boolean = false) {
        val group = NotificationGroupManager.getInstance().getNotificationGroup("OneLens")
        val title = if (error) "OneLens seed failed" else "OneLens snapshot seed"
        group.createNotification(
            title, msg,
            if (error) NotificationType.ERROR else NotificationType.INFORMATION,
        ).notify(project)
    }
}
