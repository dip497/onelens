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
    // Default flipped to falkordblite in v0.2: zero-Docker setup, bundled Redis
    // ships inside the Python venv. Users who already have Docker running on
    // :17532 can override to "falkordb" in settings; preflight will pick it up.
    // Windows users must use "falkordb" (no bundled binaries for Windows).
    val graphBackend: String = "falkordblite",
    val falkordbHost: String = "localhost",
    val falkordbPort: Int = 17532,
    // Mirror of [OneLensSettings.State.buildSemanticIndex]. OFF by default to
    // keep first-sync fast (~30 s). Flip ON to pass `--context` to
    // `onelens import_graph` and build the ChromaDB layer.
    val buildSemanticIndex: Boolean = false,
)
