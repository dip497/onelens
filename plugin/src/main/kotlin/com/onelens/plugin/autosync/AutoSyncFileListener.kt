package com.onelens.plugin.autosync

import com.intellij.openapi.project.ProjectLocator
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileCreateEvent
import com.intellij.openapi.vfs.newvfs.events.VFileDeleteEvent
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.openapi.vfs.newvfs.events.VFileMoveEvent
import com.intellij.openapi.vfs.newvfs.events.VFilePropertyChangeEvent

/**
 * Listens for VFS changes and notifies AutoSyncService when .java files change.
 * Registered as an application-level listener in plugin.xml.
 *
 * Distinguishes modifications from deletions/moves so AutoSyncService can
 * pass the correct lists to DeltaExportService — otherwise a deleted or
 * renamed file leaves orphan nodes in the graph silently.
 */
class AutoSyncFileListener : BulkFileListener {

    // Skip changes in build output / generated directories
    private val EXCLUDED_DIRS = setOf("/build/", "/target/", "/out/", "/.gradle/", "/.idea/")

    override fun after(events: MutableList<out VFileEvent>) {
        for (event in events) {
            when (event) {
                is VFileDeleteEvent -> handleDelete(event.file)
                is VFileMoveEvent -> {
                    // Old path is gone, new path is effectively a create.
                    handleDelete(event.file, oldPath = event.oldPath)
                    handleModify(event.file)
                }
                is VFilePropertyChangeEvent -> {
                    // PSI-relevant rename: propertyName == VirtualFile.PROP_NAME.
                    if (event.propertyName == VirtualFile.PROP_NAME) {
                        val oldName = event.oldValue as? String ?: continue
                        val parentPath = event.file.parent?.path ?: continue
                        handleDelete(event.file, oldPath = "$parentPath/$oldName")
                        handleModify(event.file)
                    } else {
                        handleModify(event.file)
                    }
                }
                is VFileCreateEvent -> handleModify(event.file ?: continue)
                else -> {
                    // VFileContentChangeEvent + everything else = modification
                    handleModify(event.file ?: continue)
                }
            }
        }
    }

    private fun handleModify(file: VirtualFile) {
        if (!file.name.endsWith(".java")) return
        if (EXCLUDED_DIRS.any { file.path.contains(it) }) return
        val project = ProjectLocator.getInstance().guessProjectForFile(file) ?: return
        val service = project.getService(AutoSyncService::class.java) ?: return
        if (!service.isEnabled()) return
        val basePath = project.basePath ?: return
        val relativePath = file.path.removePrefix(basePath).removePrefix("/")
        service.onJavaFileChanged(relativePath)
    }

    private fun handleDelete(file: VirtualFile?, oldPath: String? = null) {
        val path = oldPath ?: file?.path ?: return
        if (!path.endsWith(".java")) return
        if (EXCLUDED_DIRS.any { path.contains(it) }) return
        // Deleted file: no VirtualFile remaining → resolve project via parent.
        val project = file?.let { ProjectLocator.getInstance().guessProjectForFile(it) }
            ?: run {
                // Fall back: any open project whose basePath is a prefix.
                com.intellij.openapi.project.ProjectManager.getInstance().openProjects
                    .firstOrNull { proj -> proj.basePath?.let { path.startsWith(it) } == true }
            }
            ?: return
        val service = project.getService(AutoSyncService::class.java) ?: return
        if (!service.isEnabled()) return
        val basePath = project.basePath ?: return
        val relativePath = path.removePrefix(basePath).removePrefix("/")
        service.onJavaFileDeleted(relativePath)
    }
}
