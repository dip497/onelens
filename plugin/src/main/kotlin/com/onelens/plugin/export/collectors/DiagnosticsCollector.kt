package com.onelens.plugin.export.collectors

import com.intellij.openapi.project.Project
import com.onelens.plugin.export.DiagnosticEntry

/**
 * Collects unused/dead code diagnostics using IntelliJ's inspection APIs.
 * Runs UnusedDeclarationInspection headlessly.
 */
object DiagnosticsCollector {

    fun collect(project: Project): List<DiagnosticEntry> {
        // TODO: Phase 5 implementation
        return emptyList()
    }
}
