package com.onelens.plugin.export.collectors

import com.intellij.openapi.diagnostic.logger
import com.onelens.plugin.export.AppData
import com.onelens.plugin.export.ClassData
import com.onelens.plugin.export.PackageData

/**
 * Derives [PackageData] nodes from the set of project classes and links each to
 * the owning [AppData] via a longest-prefix match against [AppData.scanPackages].
 *
 * The hierarchy is materialised by walking every dotted segment — a class in
 * `com.acme.order.service` produces `com.acme`, `com.acme.order`, and
 * `com.acme.order.service`, each pointing at its parent. Loader side turns the
 * `parentId` pointer into a `PARENT_OF` edge.
 *
 * A package is assigned to ONE app (winner = longest prefix). In the rare case
 * where two Spring apps declare overlapping scan trees, the more specific app
 * wins; if scans are identical the first app emitted wins (stable, but
 * non-deterministic across projects — we document this as a known limitation).
 */
object PackageCollector {

    private val LOG = logger<PackageCollector>()

    fun collect(classes: List<ClassData>, apps: List<AppData>): List<PackageData> {
        if (classes.isEmpty()) return emptyList()

        val packageNames = HashSet<String>()
        for (c in classes) {
            val pkg = c.packageName
            if (pkg.isBlank()) continue
            var current = pkg
            while (current.isNotBlank()) {
                packageNames += current
                val dot = current.lastIndexOf('.')
                if (dot <= 0) break
                current = current.substring(0, dot)
            }
        }
        if (packageNames.isEmpty()) return emptyList()

        val out = ArrayList<PackageData>(packageNames.size)
        for (name in packageNames) {
            val parentName = name.substringBeforeLast('.', "")
            val parentId = parentName.takeIf { it.isNotBlank() && it in packageNames }
            val appId = matchApp(name, apps)
            out += PackageData(id = name, name = name, parentId = parentId, appId = appId)
        }
        LOG.info("PackageCollector: ${out.size} package nodes")
        return out
    }

    private fun matchApp(pkg: String, apps: List<AppData>): String {
        var best: AppData? = null
        var bestLen = -1
        for (app in apps) {
            for (scan in app.scanPackages) {
                val matches = pkg == scan || pkg.startsWith("$scan.")
                if (matches && scan.length > bestLen) {
                    best = app
                    bestLen = scan.length
                }
            }
        }
        return best?.id.orEmpty()
    }
}
