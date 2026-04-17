package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSArrayLiteralExpression
import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSProperty
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.util.Computable
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.DispatchesEdge
import com.onelens.plugin.export.RouteData
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Parses `*-routes.js` / `*-routes.ts` files and emits [RouteData] + `DISPATCHES`
 * edges to the lazy-imported component.
 *
 * Target shape (verified against a large real-world Vue 3 repo):
 *   ```
 *   import config from './config'
 *   const routePrefix = config.routePrefix          // string literal on config.js
 *   const routeNamePrefix = config.routeNamePrefix
 *   export default [
 *     {
 *       path: `/${routePrefix}/:ticketType`,
 *       component: () => import('./views/main.vue'),
 *       meta: { moduleName },
 *       children: [
 *         { path: '', name: `${routeNamePrefix}`, component: () => import('./views/list-view.vue') },
 *         ...
 *       ]
 *     }
 *   ]
 *   ```
 *
 * We resolve `routePrefix` / `routeNamePrefix` etc. from a sibling `config.js` when it
 * exists, swapping the placeholders before emitting. Unresolved interpolations fall
 * through as-is — the route is still indexable by the literal segment, just with a
 * placeholder substring.
 */
object LazyRouteCollector {
    private val LOG = logger<LazyRouteCollector>()

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping route collection — dumb mode")
            return
        }
        val ftm = FileTypeManager.getInstance()
        val jsTypes = listOfNotNull(
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("mjs").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = GlobalSearchScope.projectScope(project)
        val routeFiles = DumbService.getInstance(project).runReadActionInSmartMode(
            Computable {
                jsTypes.flatMap { FileTypeIndex.getFiles(it, scope) }
                    .filter { it.name.endsWith("-routes.js") || it.name.endsWith("-routes.ts") }
                    .distinct()
            }
        )

        val psiManager = PsiManager.getInstance(project)
        for (vf in routeFiles) {
            ProgressManager.checkCanceled()
            val routes = ReadAction.compute<List<RouteData>, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute emptyList()
                // Resolve config.js next to the routes file (same directory) for
                // placeholder substitution. If missing, use empty map — interpolations
                // pass through literally.
                val configPath = vf.parent?.findChild("config.js")
                    ?: vf.parent?.findChild("config.ts")
                val configConstants = configPath?.let {
                    val cfgPsi = psiManager.findFile(it) ?: return@let emptyMap()
                    readConfigConstants(cfgPsi)
                } ?: emptyMap()
                extractRoutes(psi, ctx, configConstants)
            }
            ctx.routes += routes
            // Emit dispatch edges from Route -> Component for each lazy-imported
            // component. Avoids a second pass later.
            for (r in routes) {
                val comp = r.componentRef ?: continue
                ctx.dispatches += DispatchesEdge(routeName = r.name, componentRef = comp)
            }
        }
        LOG.info("LazyRouteCollector: ${ctx.routes.size} routes from ${routeFiles.size} route files")
    }

    /** Reads string-literal / number-literal / boolean top-level const keys from a config file. */
    private fun readConfigConstants(file: PsiFile): Map<String, String> {
        // Grab a `default export {}` or `module.exports = {}` object literal's properties.
        val obj = PsiTreeUtil.findChildrenOfType(file, JSObjectLiteralExpression::class.java)
            .firstOrNull() ?: return emptyMap()
        return obj.properties.mapNotNull { prop ->
            val k = prop.name ?: return@mapNotNull null
            val v = prop.value?.text?.trim('\'', '"', ' ', '`')
            if (v.isNullOrBlank()) null else k to v
        }.toMap()
    }

    private fun extractRoutes(
        file: PsiFile,
        ctx: Vue3Context,
        constants: Map<String, String>
    ): List<RouteData> {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)

        // The default export is a JSArrayLiteralExpression of route objects.
        val arr = PsiTreeUtil.findChildrenOfType(file, JSArrayLiteralExpression::class.java)
            .firstOrNull() ?: return emptyList()

        val out = mutableListOf<RouteData>()
        arr.expressions.forEach { expr ->
            if (expr is JSObjectLiteralExpression) {
                walkRouteObject(expr, relative, constants, null, out)
            }
        }
        return out
    }

    private fun walkRouteObject(
        obj: JSObjectLiteralExpression,
        filePath: String,
        constants: Map<String, String>,
        parentName: String?,
        out: MutableList<RouteData>
    ) {
        val path = extractStringProp(obj, "path", constants).orEmpty()
        val name = extractStringProp(obj, "name", constants).orEmpty()
        val componentRef = extractLazyImport(obj.findProperty("component"))
        val meta = extractMetaKeys(obj.findProperty("meta"))

        // Emit every node — even ones without an explicit name get a synthesized key so
        // cross-references work.
        val resolvedName = name.ifBlank { "${filePath}::${path.ifBlank { "(unnamed)" }}" }
        out += RouteData(
            name = resolvedName,
            path = path,
            componentRef = componentRef,
            meta = meta,
            parentName = parentName,
            filePath = filePath
        )

        // Recurse into children.
        val children = obj.findProperty("children")?.value as? JSArrayLiteralExpression ?: return
        children.expressions.forEach { child ->
            if (child is JSObjectLiteralExpression) {
                walkRouteObject(child, filePath, constants, resolvedName, out)
            }
        }
    }

    /** Substitute `${foo}` interpolations with known [constants] values. */
    private fun interpolate(raw: String, constants: Map<String, String>): String {
        if (raw.isBlank()) return raw
        val r = StringBuilder(raw)
        INTERPOLATION_RE.findAll(raw).forEach { m ->
            val key = m.groupValues[1]
            val value = constants[key] ?: return@forEach
            val idx = r.indexOf(m.value)
            if (idx >= 0) r.replace(idx, idx + m.value.length, value)
        }
        return r.toString()
    }

    private fun extractStringProp(
        obj: JSObjectLiteralExpression,
        name: String,
        constants: Map<String, String>
    ): String? {
        val prop = obj.findProperty(name)?.value ?: return null
        val raw = prop.text.trim().trim('\'', '"', '`')
        return interpolate(raw, constants)
    }

    /**
     * `() => import('./views/main.vue')` → `./views/main.vue`.
     *
     * `import(...)` is a keyword in JS, not a plain reference — the call node has a
     * `JSImportCallExpression` shape where [JSCallExpression.methodExpression] can be
     * null or a keyword token. So we match by textual shape (`import(...)`) instead of
     * by the methodExpression type, which is more robust across JS plugin versions.
     */
    private fun extractLazyImport(prop: JSProperty?): String? {
        val value = prop?.value ?: return null
        // PSI probe: any call expression under `value` whose text starts with `import`.
        val importCall = PsiTreeUtil.findChildrenOfType(value, JSCallExpression::class.java)
            .firstOrNull { it.text.trimStart().startsWith("import") }
        if (importCall != null) {
            val arg = importCall.argumentList?.arguments?.firstOrNull()
            if (arg != null) return arg.text.trim().trim('\'', '"', '`')
        }
        // Text fallback: dynamic `import(...)` can appear without a JSCallExpression
        // wrapper depending on JS plugin version. Pull the first string literal inside
        // a top-level `import(...)` occurrence.
        val match = IMPORT_LITERAL_RE.find(value.text) ?: return null
        return match.groupValues[1]
    }

    private val IMPORT_LITERAL_RE = Regex("""import\s*\(\s*['"`]([^'"`]+)['"`]\s*\)""")

    private fun extractMetaKeys(prop: JSProperty?): Map<String, String> {
        val obj = prop?.value as? JSObjectLiteralExpression ?: return emptyMap()
        return obj.properties.mapNotNull { p ->
            val k = p.name ?: return@mapNotNull null
            val v = p.value?.text?.trim('\'', '"', ' ') ?: return@mapNotNull null
            k to v
        }.toMap()
    }

    private val INTERPOLATION_RE = Regex("""\$\{([A-Za-z_$][\w$]*)\}""")
}
