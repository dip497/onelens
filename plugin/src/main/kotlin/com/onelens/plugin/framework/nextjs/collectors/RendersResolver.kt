package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.openapi.diagnostic.logger
import com.onelens.plugin.export.ImportsEdge
import com.onelens.plugin.export.RendersEdge
import com.onelens.plugin.framework.nextjs.NextjsContext

/**
 * Post-pass that turns the [com.onelens.plugin.framework.nextjs.RenderSite] rows
 * collected during the page / layout / component PSI passes into
 * (Page|Layout|ReactComponent) -[:RENDERS]-> ReactComponent edges.
 *
 * Resolution for each PascalCase JSX tag in a source file:
 *   1. the file's import binding whose local name matches the tag → its resolved
 *      `targetFqn` (or `<targetModule>::<tag>` / `<targetModule>::<importedName>`) when
 *      that fqn is a known component;
 *   2. otherwise a same-file component named after the tag.
 * Unresolved tags are dropped. Requires [com.onelens.plugin.framework.jscommon.JsModuleCollector]
 * to have populated `ctx.imports` and [ReactComponentCollector] the component set.
 */
object RendersResolver {
    private val LOG = logger<RendersResolver>()

    private val JS_EXT = Regex("""\.(tsx|ts|jsx|js|mjs)$""")

    /** `apps/web/foo/Bar.tsx::Baz` → `apps/web/foo/Bar::Baz`. Import specifiers are
     *  emitted extensionless, so component fqns must be matched on an extensionless key. */
    private fun stripExt(fqn: String): String {
        val sep = fqn.indexOf("::")
        if (sep < 0) return fqn
        return JS_EXT.replace(fqn.substring(0, sep), "") + fqn.substring(sep)
    }

    fun resolve(ctx: NextjsContext) {
        if (ctx.components.isEmpty()) return
        val componentFqns = ctx.components.mapTo(HashSet()) { it.fqn }
        // Second index keyed on the extensionless fqn, because `ImportsEdge.targetModule`
        // (and same-file specifiers) carry no file extension while `ReactComponentData.fqn`
        // does — a direct string match would never fire (verified: 0/64 on a real repo).
        val byExtless: Map<String, String> = ctx.components.associate { stripExt(it.fqn) to it.fqn }
        val importsBySource: Map<String, List<ImportsEdge>> = ctx.imports.groupBy { it.sourceModule }
        val seen = HashSet<Pair<String, String>>()
        for (site in ctx.renderSites) {
            val imports = importsBySource[site.filePath].orEmpty()
            for (tag in site.jsxTagNames) {
                val target = resolveTag(tag, site.filePath, imports, componentFqns, byExtless) ?: continue
                if (target == site.sourceFqn) continue
                if (seen.add(site.sourceFqn to target)) {
                    ctx.renders += RendersEdge(sourceFqn = site.sourceFqn, targetFqn = target)
                }
            }
        }
        LOG.info("RendersResolver: ${ctx.renders.size} RENDERS edges from ${ctx.renderSites.size} sites")
    }

    private fun resolveTag(
        tag: String,
        filePath: String,
        imports: List<ImportsEdge>,
        componentFqns: Set<String>,
        byExtless: Map<String, String>,
    ): String? {
        val edge = imports.firstOrNull { (it.localAlias ?: it.importedName) == tag }
        if (edge != null) {
            edge.targetFqn?.let {
                if (it in componentFqns) return it
                byExtless[stripExt(it)]?.let { fqn -> return fqn }
            }
            val mod = edge.targetModule
            byExtless["$mod::$tag"]?.let { return it }
            byExtless["$mod::${edge.importedName}"]?.let { return it }
        }
        // Same-file component (renders another export defined in the same module) —
        // both sides carry the file extension here, so a direct match is correct.
        if ("$filePath::$tag" in componentFqns) return "$filePath::$tag"
        return null
    }
}
