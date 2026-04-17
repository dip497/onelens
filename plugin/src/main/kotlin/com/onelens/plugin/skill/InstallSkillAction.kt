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

        val skillBytes = loadBundledResource("/skills/onelens/SKILL.md")
        if (skillBytes == null) {
            notify(project,
                "OneLens skill is missing from the plugin bundle.\n" +
                    "This is a plugin packaging bug — please report.",
                NotificationType.ERROR)
            return
        }

        val home = System.getProperty("user.home")
        val skillRoot: Path = Paths.get(home, ".claude", "skills", "onelens")
        val dest: Path = skillRoot.resolve("SKILL.md")

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

        // Install stack-specific references. Each reference is loaded lazily by
        // the main SKILL.md via progressive disclosure, so missing ones are not
        // fatal — log and continue. The set of reference filenames is hard-coded
        // here because classpath-scanning directories inside a jar is awkward
        // across different IDE launch modes; when we add a new reference we also
        // add its filename here (one line per stack, obvious diff).
        val references = listOf("jvm.md", "vue3.md")
        val refDir = skillRoot.resolve("references")
        refDir.toFile().mkdirs()
        val missing = mutableListOf<String>()
        for (ref in references) {
            val bytes = loadBundledResource("/skills/onelens/references/$ref")
            if (bytes == null) {
                missing += ref
                continue
            }
            try {
                refDir.resolve(ref).toFile().writeBytes(bytes)
            } catch (ex: Exception) {
                log.warn("Failed to write reference $ref", ex)
                missing += ref
            }
        }

        val tail = if (missing.isEmpty()) {
            "References: ${references.joinToString(", ")}."
        } else {
            "References installed with gaps — missing: ${missing.joinToString(", ")}."
        }
        notify(project,
            "OneLens skill installed at $skillRoot\n$tail\n" +
                "Restart Claude Code once, then ask it anything about your codebase.",
            if (missing.isEmpty()) NotificationType.INFORMATION else NotificationType.WARNING)
    }

    /**
     * Load a resource packaged with the plugin by `processResources`. Returns
     * null if the resource is absent (e.g. a reference was renamed and this
     * action wasn't updated).
     */
    private fun loadBundledResource(path: String): ByteArray? {
        val stream = javaClass.getResourceAsStream(path) ?: return null
        return stream.use { it.readBytes() }
    }

    private fun notify(project: com.intellij.openapi.project.Project, msg: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("OneLens")
            ?.createNotification("OneLens Skill Install", msg, type)
            ?.notify(project)
    }
}
