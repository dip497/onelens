package com.onelens.plugin.headless

import com.onelens.plugin.export.ExportState
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Cross-JVM export-state bridge for headless delta exports.
 *
 * ## The problem this solves
 *
 * [ExportState] persists to IntelliJ's project config dir, which lives under
 * `idea.system.path`. The headless task isolates `idea.system.path` to
 * `build/onelens-system/` per run (see `build.gradle.kts`), so a headless JVM
 * always sees an **empty** ExportState — `lastExportTimestamp == 0` → every
 * delta degrades to a full re-export. This makes a naive `--delta` flag
 * useless.
 *
 * ## The fix
 *
 * Write a JSON marker at `~/.onelens/graphs/<graphId>/.onelens-lastexport`
 * (outside any system dir, shared across JVM invocations). The headless
 * starter loads this into ExportState before running the delta, and writes it
 * back after any successful export (full or delta). This mirrors the
 * `.onelens-baseline` snapshot-seed mechanism already used by DeltaTracker
 * (`DeltaTracker.consumeBaselineMarker`).
 *
 * The graphId is derived from the project directory name (same logic as
 * `WorkspaceLoader`), so it's stable across runs without the caller having to
 * pass it.
 */
object HeadlessExportState {

    private const val SCHEMA_VERSION = 1
    private const val FILE_NAME = ".onelens-lastexport"

    /**
     * Locate the marker file for a given graphId. Always under
     * `~/.onelens/graphs/<graphId>/` — created on demand.
     */
    fun markerPath(graphId: String): Path {
        val dir = Paths.get(System.getProperty("user.home"), ".onelens", "graphs", graphId)
        return dir.resolve(FILE_NAME)
    }

    /**
     * Load the persisted state into the given [ExportState] so DeltaTracker /
     * DeltaExportService see the previous export's git hash and file→classes
     * mapping. No-op (returns false) if no marker exists — the caller should
     * treat this as "first export, full re-export needed."
     *
     * @return true if a valid marker was loaded, false if absent or stale
     */
    fun loadInto(graphId: String, exportState: ExportState): Boolean {
        val marker = markerPath(graphId)
        if (!Files.isRegularFile(marker)) return false

        return try {
            val text = Files.readString(marker)
            val commit = parseField(text, "lastGitHash")
            val timestamp = parseField(text, "lastExportTimestamp")?.toLongOrNull() ?: 0L
            val schema = parseField(text, "schemaVersion")?.toIntOrNull() ?: 0

            if (schema != SCHEMA_VERSION) return false

            exportState.state.lastGitHash = commit ?: ""
            exportState.state.lastExportTimestamp = timestamp
            val fileHashes = parseFileHashes(text)
            if (fileHashes.isNotEmpty()) {
                exportState.state.fileHashes.clear()
                exportState.state.fileHashes.putAll(fileHashes)
            }

            commit != null && commit.isNotEmpty()
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Persist the current [ExportState] to the marker file so the next headless
     * run can diff from this export's commit. Called after a successful export
     * (full or delta).
     */
    fun saveFrom(graphId: String, exportState: ExportState) {
        val marker = markerPath(graphId)
        try {
            Files.createDirectories(marker.parent)

            // Build a compact JSON. Using manual construction (not kotlinx.serialization)
            // to avoid a circular dependency on the export models — this file is a
            // transport format, not a domain model.
            val sb = StringBuilder()
            sb.append("{\n")
            sb.append("  \"schemaVersion\": $SCHEMA_VERSION,\n")
            sb.append("  \"lastGitHash\": \"${escapeJson(exportState.state.lastGitHash)}\",\n")
            sb.append("  \"lastExportTimestamp\": ${exportState.state.lastExportTimestamp},\n")
            sb.append("  \"fileHashes\": {")
            val entries = exportState.state.fileHashes.entries
            if (entries.isNotEmpty()) {
                sb.append("\n")
                entries.joinTo(sb, ",\n") { (k, v) ->
                    "    \"${escapeJson(k)}\": \"${escapeJson(v)}\""
                }
                sb.append("\n  ")
            }
            sb.append("}\n")
            sb.append("}\n")

            Files.writeString(marker, sb.toString())
        } catch (e: Exception) {
            // Non-fatal — the export already succeeded; we just can't do a
            // delta next time. Log loudly so it's visible.
            System.err.println("[onelens] WARNING: failed to write export state marker to $marker: ${e.message}")
        }
    }

    // --- Simple JSON field extraction (no parser dependency) ---

    private fun parseField(json: String, field: String): String? {
        // Match both quoted string values ("field": "value") and unquoted
        // numeric values ("field": 123). The `\"?` makes the quote optional
        // on both sides of the captured value.
        val re = Regex("\"$field\"\\s*:\\s*\"?([^\"\\s,}]+)\"?")
        return re.find(json)?.groupValues?.getOrNull(1)
    }

    private fun parseFileHashes(json: String): Map<String, String> {
        val result = mutableMapOf<String, String>()
        // Match the "fileHashes" object and extract key-value pairs.
        val blockRe = Regex("\"fileHashes\"\\s*:\\s*\\{([^}]*)\\}", RegexOption.DOT_MATCHES_ALL)
        val block = blockRe.find(json)?.groupValues?.getOrNull(1) ?: return result
        val pairRe = Regex("\"([^\"]+)\"\\s*:\\s*\"([^\"]*)\"")
        for (m in pairRe.findAll(block)) {
            result[m.groupValues[1]] = m.groupValues[2]
        }
        return result
    }

    private fun escapeJson(s: String): String =
        s.replace("\\", "\\\\").replace("\"", "\\\"")
}
