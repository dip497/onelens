package com.onelens.plugin.skill

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.diagnostic.logger
import java.io.File
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Installs the OneLens skill (SKILL.md) for Claude Code.
 *
 * This is the **minimal install path for Claude Code users** — no daemon,
 * no port, no MCP configs. Claude Code reads the skill, uses its Bash tool
 * to invoke `onelens <command>` directly, and gets everything the MCP path
 * would provide without the subprocess daemon overhead.
 *
 * MCP install (`Install MCP for AI Tools`) is for editors that can't shell
 * out freely — Cursor, Codex, Windsurf. If you only use Claude Code, this
 * skill install is all you need.
 *
 * Skill source is bundled with the plugin (`/skills/onelens/SKILL.md` under
 * plugin resources). Destination is `~/.claude/skills/onelens/SKILL.md`.
 * Overwrites without prompt (skill evolves with plugin updates — keeping a
 * stale local copy is worse than the overwrite).
 */
class InstallSkillAction : AnAction("Install OneLens Skill for Claude Code") {

    private val log = logger<InstallSkillAction>()

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        val skillBytes = loadBundledSkill()
        if (skillBytes == null) {
            notify(project,
                "OneLens skill is missing from the plugin bundle.\n" +
                    "This is a plugin packaging bug — please report.",
                NotificationType.ERROR)
            return
        }

        val home = System.getProperty("user.home")
        val dest: Path = Paths.get(home, ".claude", "skills", "onelens", "SKILL.md")

        try {
            dest.parent.toFile().mkdirs()
            dest.toFile().writeBytes(skillBytes)
        } catch (ex: Exception) {
            log.warn("Failed to write skill to $dest", ex)
            notify(project,
                "Failed to write skill to $dest: ${ex.message}",
                NotificationType.ERROR)
            return
        }

        notify(project,
            "OneLens skill installed at $dest\n" +
                "Restart Claude Code once, then ask it anything about your codebase.",
            NotificationType.INFORMATION)
    }

    /**
     * Load SKILL.md from the plugin's classpath. The skill is packaged under
     * `/skills/onelens/SKILL.md` by the Gradle `processResources` task (see
     * `plugin/build.gradle.kts` — the skill copy is the intended pattern).
     * If the skill isn't bundled, this returns null and the action surfaces
     * a packaging error.
     */
    private fun loadBundledSkill(): ByteArray? {
        val stream = javaClass.getResourceAsStream("/skills/onelens/SKILL.md")
            ?: return null
        return stream.use { it.readBytes() }
    }

    private fun notify(project: com.intellij.openapi.project.Project, msg: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("OneLens")
            ?.createNotification("OneLens Skill Install", msg, type)
            ?.notify(project)
    }
}
