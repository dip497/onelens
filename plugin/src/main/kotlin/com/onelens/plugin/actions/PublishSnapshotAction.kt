package com.onelens.plugin.actions

import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.DumbAwareAction
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import com.onelens.plugin.snapshots.GitInfo
import com.onelens.plugin.snapshots.PublishSnapshotDialog
import com.onelens.plugin.snapshots.SnapshotManager

class PublishSnapshotAction : DumbAwareAction("Publish Snapshot…") {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        // Publishing copies `<graph>.rdb` + ~/.onelens/context/<graph>/ raw
        // off disk. If a live sync is writing to either, we produce a
        // half-baked bundle. Refuse up front — consistent with the
        // GraphCleanupService guard.
        if (com.onelens.plugin.export.SyncCoordinator.getInstance().isRunning()) {
            NotificationGroupManager.getInstance().getNotificationGroup("OneLens")
                .createNotification(
                    "OneLens: cannot publish while sync is running",
                    "Wait for the current sync to finish (or cancel it from Background Tasks) before publishing a snapshot — otherwise the bundle can be corrupt.",
                    NotificationType.WARNING,
                ).notify(project)
            return
        }
        val workspace = try { WorkspaceLoader.load(project) } catch (_: Exception) { return }

        // git tag listing shells out and must not run on EDT.
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "OneLens: Reading git tags", false) {
            override fun run(indicator: ProgressIndicator) {
                val suggestedTag = GitInfo.latestTag(project)
                val branch = GitInfo.currentBranch(project)
                val sha = GitInfo.headSha(project)
                ApplicationManager.getApplication().invokeLater({
                    openDialogAndPublish(project, workspace, suggestedTag, branch, sha)
                }, ModalityState.any())
            }
        })
    }

    private fun openDialogAndPublish(
        project: com.intellij.openapi.project.Project,
        workspace: com.onelens.plugin.framework.workspace.Workspace,
        suggestedTag: String?,
        branch: String?,
        headSha: String?,
    ) {
        val dlg = PublishSnapshotDialog(
            project = project,
            graph = workspace.graphId,
            suggestedTag = suggestedTag,
            branch = branch,
            headSha = headSha,
        )
        if (!dlg.showAndGet()) return
        val r = dlg.result()
        val mgr = SnapshotManager.getInstance(project)

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "OneLens: Publishing snapshot", true) {
            override fun run(indicator: ProgressIndicator) {
                val out = mgr.publish(
                    SnapshotManager.PublishArgs(
                        graph = workspace.graphId,
                        tag = r.tag,
                        includeEmbeddings = r.includeEmbeddings,
                    ),
                    indicator,
                )
                ApplicationManager.getApplication().invokeLater({
                    val group = NotificationGroupManager.getInstance()
                        .getNotificationGroup("OneLens")
                    if (out.exitCode == 0) {
                        group.createNotification(
                            "OneLens snapshot published",
                            "${workspace.graphId}@${r.tag} — ~/.onelens/bundles/",
                            NotificationType.INFORMATION,
                        ).notify(project)
                    } else {
                        group.createNotification(
                            "OneLens snapshot publish failed",
                            (out.stderr ?: out.stdout).take(400),
                            NotificationType.ERROR,
                        ).notify(project)
                    }
                }, ModalityState.any())
            }
        })
    }
}
