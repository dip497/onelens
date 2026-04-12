package com.onelens.plugin.autosync

import com.intellij.openapi.project.ProjectLocator
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent

/**
 * Listens for VFS changes and notifies AutoSyncService when .java files change.
 * Registered as an application-level listener in plugin.xml.
 */
class AutoSyncFileListener : BulkFileListener {

    // Skip changes in build output / generated directories
    private val EXCLUDED_DIRS = setOf("/build/", "/target/", "/out/", "/.gradle/", "/.idea/")

    override fun after(events: MutableList<out VFileEvent>) {
        for (event in events) {
            val file = event.file ?: continue
            if (!file.name.endsWith(".java")) continue
            if (EXCLUDED_DIRS.any { file.path.contains(it) }) continue

            val project = ProjectLocator.getInstance().guessProjectForFile(file) ?: continue
            val service = project.getService(AutoSyncService::class.java) ?: continue
            if (!service.isEnabled()) continue

            val basePath = project.basePath ?: continue
            val relativePath = file.path.removePrefix(basePath).removePrefix("/")
            service.onJavaFileChanged(relativePath)
        }
    }
}
