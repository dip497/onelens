package com.onelens.plugin.export

import java.nio.file.Path
import java.nio.file.Paths

/**
 * Configuration for an export operation.
 *
 * All data lives under ~/.onelens/:
 *   exports/    ← JSON export files
 *   venv/       ← auto-managed Python environment
 *
 * Graph DB: FalkorDB (Docker) with browser at localhost:3000
 */
data class ExportConfig(
    val outputPath: Path = Paths.get(System.getProperty("user.home"), ".onelens", "exports"),
    val includeSpring: Boolean = true,
    val includeDiagnostics: Boolean = false,
    val excludeTestSources: Boolean = false,
    val excludeLibraryClasses: Boolean = true,
    val autoImport: Boolean = true,
    val onelensSourcePath: String = "",
    val graphBackend: String = "falkordb",       // falkordb (default, Docker) or falkordblite (embedded)
    val falkordbHost: String = "localhost",
    val falkordbPort: Int = 17532,
)
