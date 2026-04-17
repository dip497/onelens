package com.onelens.plugin.autosync

import com.intellij.notification.Notification
import com.intellij.notification.NotificationAction
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.onelens.plugin.actions.ExportFullAction
import com.onelens.plugin.settings.OneLensSettings

/**
 * Enables auto-sync on project open and, on the very first project open with
 * this plugin installed, shows an onboarding balloon offering to sync the
 * current project into the graph. One-time — re-opens are silent.
 */
class AutoSyncStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        val settings = OneLensSettings.getInstance()
        val state = settings.state

        if (state.autoSyncEnabled) {
            val service = project.getService(AutoSyncService::class.java) ?: return
            service.enable()
        }

        // No MCP daemon auto-start here. Most users run Claude Code /
        // OpenCode which invoke `onelens` via their own bash tool — the
        // daemon's sole purpose is to keep Qwen3+mxbai warm across MCP
        // HTTP calls, irrelevant for shell-spawned CLI usage. The daemon
        // starts on-demand when the user runs "Install MCP for AI Tools"
        // (for Cursor/Codex/Windsurf) or manually via `onelens daemon start`.

        if (!state.firstRunComplete) {
            state.firstRunComplete = true
            showOnboarding(project)
        }
    }

    private fun showOnboarding(project: Project) {
        val group = NotificationGroupManager.getInstance()
            .getNotificationGroup("OneLens")
            ?: return

        val notification: Notification = group.createNotification(
            "OneLens is ready",
            "Two things to set up:\n" +
                "1. Sync Graph — builds the knowledge graph (~30s) + semantic embeddings (~20 min in background).\n" +
                "2. Install Skill — drops SKILL.md into ~/.claude/skills/ so Claude Code knows how to use " +
                "`onelens` via its bash tool. No MCP needed for Claude Code.\n\n" +
                "After both, every file save delta-syncs in seconds.",
            NotificationType.INFORMATION
        )

        notification.addAction(object : NotificationAction("Sync now") {
            override fun actionPerformed(e: AnActionEvent, n: Notification) {
                n.expire()
                ExportFullAction().actionPerformed(e)
            }
        })
        notification.addAction(object : NotificationAction("Install Skill") {
            override fun actionPerformed(e: AnActionEvent, n: Notification) {
                n.expire()
                com.onelens.plugin.skill.InstallSkillAction().actionPerformed(e)
            }
        })
        notification.addAction(object : NotificationAction("Later") {
            override fun actionPerformed(e: AnActionEvent, n: Notification) {
                n.expire()
            }
        })
        notification.notify(project)
    }
}
