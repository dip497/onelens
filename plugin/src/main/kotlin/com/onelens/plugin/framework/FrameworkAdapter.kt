package com.onelens.plugin.framework

import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.project.Project
import kotlinx.serialization.json.JsonElement

/**
 * Framework adapter SPI. Each language/framework lives in its own module and contributes:
 *   - activation logic (detect project type from build files)
 *   - an ordered list of collectors
 *   - a JSON key under which its nodes/edges are merged into the root ExportDocument
 *
 * The core orchestrator (ExportService) iterates registered adapters, filters by [detect],
 * runs their collectors, and merges outputs. Adapters must not share state or mutate
 * data owned by another adapter.
 *
 * Register via the `com.onelens.plugin.frameworkAdapter` extension point in plugin.xml.
 */
interface FrameworkAdapter {
    /** Stable identifier: `spring-boot`, `vue3`, `fastapi`, ... */
    val id: String

    /** JSON key under which this adapter's section appears in the export document. */
    val jsonKey: String

    /** Return true if this adapter applies to [project]. Cheap file-system probe; no PSI. */
    fun detect(project: Project): Boolean

    /** Ordered list of collectors. Each is invoked with a fresh [CollectContext]. */
    fun collectors(): List<Collector>

    companion object {
        val EP_NAME: ExtensionPointName<FrameworkAdapter> =
            ExtensionPointName.create("com.onelens.plugin.frameworkAdapter")
    }
}

/**
 * A single collection pass over the project. Collectors must:
 *   - Hold [com.intellij.openapi.application.ReadAction] per-file (never project-wide).
 *   - Call [com.intellij.openapi.progress.ProgressManager.checkCanceled] in tight loops.
 *   - Respect [com.intellij.openapi.project.DumbService] — bail if index unavailable.
 */
interface Collector {
    /** Stable id used for progress reporting and logs. */
    val id: String

    /** Human-readable label shown in progress UI. */
    val label: String

    fun collect(ctx: CollectContext): CollectorOutput
}

data class CollectContext(
    val project: Project,
    val indicator: ProgressIndicator?,
    /** Fraction of overall export allocated to this collector; used to report progress. */
    val progressFraction: Double = 0.0
)

/**
 * Opaque per-adapter output. The adapter is responsible for the shape of [data]
 * — it is merged into the root export JSON under the adapter's [FrameworkAdapter.jsonKey].
 *
 * `nodes` / `edges` counts are exposed for stats only; individual node/edge
 * schemas remain adapter-specific so we can tune per framework.
 */
data class CollectorOutput(
    val data: JsonElement,
    val nodeCount: Int = 0,
    val edgeCount: Int = 0
)
