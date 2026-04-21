package com.onelens.plugin.framework.vue3

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.project.Project
import java.util.concurrent.Callable

/**
 * Cooperative smart-mode read action. Replaces the deprecated
 * `DumbService.getInstance(project).runReadActionInSmartMode { ... }` per
 * JetBrains 2024.1+ guidance. Key difference: the underlying
 * `ReadAction.nonBlocking` yields to pending writes, so long Vue collector
 * passes don't block user keystrokes — eliminates the visible IDE lag
 * during full-sync.
 *
 * Call from a background thread (Task.Backgroundable). Synchronous from
 * the caller's POV — the work runs on the caller's executor, not a pooled
 * background task. If the project leaves smart mode mid-execution, the
 * underlying read-action retries automatically when indexes are ready.
 */
inline fun <T> smartRead(project: Project, crossinline block: () -> T): T =
    ReadAction.nonBlocking<T>(Callable { block() })
        .inSmartMode(project)
        .executeSynchronously()
