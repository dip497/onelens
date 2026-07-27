package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSAssignmentExpression
import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.lang.javascript.psi.JSReturnStatement
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.StoreData
import com.onelens.plugin.framework.jscommon.isTestFile
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Collects Vuex store modules — the Vue 2 counterpart to [PiniaStoreCollector].
 * Emits the same [StoreData] node so downstream queries do not care which state
 * library a repo uses.
 *
 * Two shapes:
 *
 *     // 1. Namespaced module file
 *     export default {
 *       namespaced: true,
 *       state: () => ({ items: [] }),
 *       getters:   { count: s => s.items.length },
 *       mutations: { SET_ITEMS(s, v) { s.items = v } },
 *       actions:   { async fetch({ commit }) {…} },
 *     }
 *
 *     // 2. Root store
 *     export default new Vuex.Store({ modules: { user, tickets } })
 *
 * Identity: `fqn = "<filePath>::<name>"`, same rule as Pinia. It matters MORE
 * here — Vuex module names are directory-derived, so `store/user/index.js` and
 * `store/admin/user.js` are both "user". Merging on the name would silently
 * collapse them.
 */
object VuexStoreCollector {
    private val LOG = logger<VuexStoreCollector>()
    private const val MAX_BODY_CHARS = 2000
    private const val DETECT_BYTES = 4096

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping Vuex collection — dumb mode")
            return
        }
        val ftm = FileTypeManager.getInstance()
        val jsTypes = listOf("js", "ts", "mjs").mapNotNull { ext ->
            ftm.getFileTypeByExtension(ext).takeIf { it != UnknownFileType.INSTANCE }
        }
        if (jsTypes.isEmpty()) {
            LOG.warn("No JS/TS file types registered")
            return
        }

        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) { jsTypes.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        val psiManager = PsiManager.getInstance(project)
        val seenFqns = ctx.stores.mapTo(HashSet()) { it.fqn }
        var emitted = 0
        var candidates = 0

        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))

            // Cheap pre-filter before the (100x more expensive) PSI parse.
            // Unlike Pinia's single `defineStore` marker, Vuex modules often
            // carry no distinguishing token at all — a plain `export default {
            // state, getters, actions }` is just an object. So accept EITHER a
            // Vuex keyword OR residence in a store directory, and let
            // extractStore() reject non-stores on shape.
            val inStoreDir = STORE_DIR_RE.containsMatchIn(relative)
            if (!inStoreDir && !hasVuexMarker(vf)) continue

            val stores = ReadAction.compute<List<StoreData>, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute emptyList()
                extractStores(psi, ctx, relative)
            }
            for (store in stores) {
                if (seenFqns.add(store.fqn)) {
                    ctx.stores += store
                    emitted++
                }
            }
            candidates++
        }
        // Same silent-empty guard as OptionsApiCollector: a Vuex shape this
        // collector does not recognise produces an empty store graph with a
        // successful exit, which is indistinguishable from "this repo has no
        // stores" unless it says so.
        if (candidates > 0 && emitted == 0) {
            LOG.warn(
                "Vuex collection examined $candidates candidate files but produced ZERO stores. " +
                    "Store-dependent queries will return nothing — check whether these modules use " +
                    "a shape other than `export default {…}` / `export const state = {…}` / " +
                    "`export const modules = { key: factory() }`."
            )
        }
        LOG.info("VuexStoreCollector: emitted $emitted stores from $candidates candidates")
    }

    private fun hasVuexMarker(vf: com.intellij.openapi.vfs.VirtualFile): Boolean = try {
        val head = vf.inputStream.use { it.readNBytes(DETECT_BYTES).decodeToString() }
        VUEX_MARKER_RE.containsMatchIn(head)
    } catch (_: Throwable) {
        false
    }

    private fun extractStores(file: PsiFile, ctx: Vue3Context, relative: String): List<StoreData> {
        // Two module shapes, both common — and a real 2100-SFC Vue 2 codebase used
        // ONLY the second, so handling just the first found zero stores:
        //
        //   1. single object: `export default { namespaced: true, state: {…}, … }`
        //   2. named exports: `export const state = {…}` / `export const getters = {…}`
        //
        // Named exports are checked FIRST and win. A file can contain both: the
        // module's own `export const state/getters/…` at top level, PLUS a nested
        // `const vuexModule = { namespaced: true, … }` inside a factory that builds
        // a SUB-module. Searching object literals first picked the sub-module and
        // dropped the real one — 10 of 44 modules in a real codebase.
        var storeObj: JSObjectLiteralExpression? = null
        var sections = namedExportSections(file)

        if (sections.size < 2) {
            val objects = PsiTreeUtil.findChildrenOfType(file, JSObjectLiteralExpression::class.java)
            // A store object declares at least two of the four Vuex sections, or is
            // explicitly `namespaced`. One section alone is too weak — `{ state: … }`
            // appears in plenty of non-store config.
            storeObj = objects.firstOrNull { obj ->
                obj.findProperty("namespaced") != null ||
                    SECTIONS.count { obj.findProperty(it) != null } >= 2
            }
            sections = storeObj
                ?.let { o -> SECTIONS.mapNotNull { s -> sectionObject(o.findProperty(s)?.value)?.let { s to it } }.toMap() }
                .orEmpty()
            // `export default {}` followed by `mod.state = {…}` assignments.
            if (sections.size < 2) {
                sections = sections + sectionsFromAssignments(file).filterKeys { it !in sections }
            }
        }
        val name = moduleName(relative)

        // Third shape: a sub-module REGISTRY. The file defines no module of its
        // own, only factories whose results are registered under static keys:
        //
        //   function getCategoryConfig() { … return vuexModule }
        //   export const modules = { categoryConfig: getCategoryConfig() }
        //
        // Vuex composes these into `<parent>/<key>` namespaces, which is exactly
        // what `createNamespacedHelpers('userGroup/technician')` binds against.
        // 8 of 44 modules in a real codebase used only this form.
        val subModules = registrySubModules(file, name, relative)
        if (sections.size < 2) return subModules

        val body = storeObj?.text ?: sections.values.joinToString("\n") { it.text }
        return subModules + listOf(
            StoreData(
                // Vuex has no `defineStore('id')` — the namespace IS the identity.
                // Populate both fields so importer code stays shape-agnostic
                // across Pinia and Vuex.
                id = name,
                name = name,
                filePath = relative,
                fqn = "$relative::$name",
                style = "vuex",
                state = keysIn(sections["state"]),
                getters = keysIn(sections["getters"]),
                actions = keysIn(sections["actions"]),
                mutations = keysIn(sections["mutations"]),
                body = body.take(MAX_BODY_CHARS),
                isTest = isTestFile(relative),
            )
        )
    }

    /**
     * Top-level `const state = {…}` / `const getters = {…}` declarations, which
     * an `export const state = …` module compiles down to in PSI. Matching on the
     * variable NAME rather than on the export keyword keeps this working whether
     * the section is exported inline or exported later in one `export {}` block.
     *
     * It also resolves the shorthand `export default { state, getters, mutations }`
     * form for free: the properties there are bare references the object-literal
     * path cannot unwrap, but the declarations they point at are exactly what this
     * finds.
     */
    private fun namedExportSections(file: PsiFile): Map<String, JSObjectLiteralExpression> =
        PsiTreeUtil.findChildrenOfType(file, JSVariable::class.java)
            .mapNotNull { v ->
                val n = v.name ?: return@mapNotNull null
                if (n !in SECTIONS) return@mapNotNull null
                // MUST be top-level. `findChildrenOfType` is a full-depth walk and
                // `toMap()` is last-wins, so a `const state` declared inside a
                // factory later in the file would silently replace the module's
                // real exported `state`.
                if (!isTopLevel(v)) return@mapNotNull null
                sectionObject(v.initializer)?.let { n to it }
            }
            .toMap()

    /** True when no function encloses [element] — i.e. it is a module-level declaration. */
    private fun isTopLevel(element: PsiElement): Boolean =
        PsiTreeUtil.getParentOfType(element, JSFunction::class.java, true) == null

    /** A section value: a plain object literal, or a `() => ({…})` state factory. */
    private fun sectionObject(value: com.intellij.psi.PsiElement?): JSObjectLiteralExpression? =
        when (value) {
            is JSObjectLiteralExpression -> value
            is JSFunction -> returnedObject(value)
            else -> null
        }

    private fun keysIn(obj: JSObjectLiteralExpression?): List<String> =
        obj?.properties?.mapNotNull { it.name }.orEmpty()

    /**
     * Sections attached by ASSIGNMENT rather than declared in the literal:
     *
     *     const vuexModule = { namespaced: true }
     *     vuexModule.state   = { categories: [] }
     *     vuexModule.actions = { … }
     *
     * A standard Vuex idiom for modules whose sections are built conditionally.
     * The object literal itself carries only `namespaced`, so a property lookup
     * finds nothing — every one of 95 sub-modules in the validation repo came out
     * with empty state/getters/mutations/actions before this.
     *
     * Matched on the assignment target's trailing `.<section>` rather than by
     * resolving the receiver: within a factory the receiver is unambiguous, and
     * this stays correct whether it is `vuexModule`, `mod`, or `this`.
     */
    private fun sectionsFromAssignments(scope: PsiElement): Map<String, JSObjectLiteralExpression> =
        PsiTreeUtil.findChildrenOfType(scope, JSAssignmentExpression::class.java)
            .mapNotNull { assign ->
                val lhs = assign.lOperand?.text ?: return@mapNotNull null
                val section = SECTIONS.firstOrNull { lhs.endsWith(".$it") } ?: return@mapNotNull null
                sectionObject(assign.rOperand)?.let { section to it }
            }
            .toMap()

    /**
     * Stores declared by a `const modules = { key: factory() }` registry.
     *
     * The KEYS are static even when the factory bodies are parameterised, and the
     * key is what determines the namespace — so the node can be emitted accurately
     * even where the sections cannot be resolved. Sections are recovered when the
     * value is a call to a function declared in the same file (the common case);
     * otherwise the store is emitted with empty sections, which still lets a
     * `createNamespacedHelpers('<parent>/<key>')` call resolve to a real node.
     */
    private fun registrySubModules(
        file: PsiFile,
        parentName: String,
        relative: String,
    ): List<StoreData> {
        val registry = PsiTreeUtil.findChildrenOfType(file, JSVariable::class.java)
            .firstOrNull { it.name == "modules" && isTopLevel(it) }
            ?.initializer as? JSObjectLiteralExpression ?: return emptyList()

        // EVERY value must be a factory CALL. This is what separates a registry of
        // generated sub-modules from the canonical Vuex root store, which
        // aggregates already-imported modules by reference:
        //
        //     const modules = { user, tickets }            // ← NOT a registry
        //     const modules = { cfg: getConfigModule() }   // ← a registry
        //
        // Without this check the root store emitted an empty duplicate Store per
        // module — same namespace, different fqn, so the importer MERGE kept both
        // — and `associateBy(namespaceKey)` in CallThroughResolver is last-wins,
        // so roughly half of all USES_STORE edges would point at the empty stub.
        if (registry.properties.isEmpty()) return emptyList()
        if (registry.properties.any { it.value !is JSCallExpression }) return emptyList()

        val functions = PsiTreeUtil.findChildrenOfType(file, JSFunction::class.java)
            .mapNotNull { fn -> fn.name?.let { it to fn } }
            .toMap()

        return registry.properties.mapNotNull { prop ->
            val key = prop.name ?: return@mapNotNull null
            // `key: getThing()` → resolve `getThing` in this file, else give up on
            // sections but still emit the node.
            val calleeName = ((prop.value as? JSCallExpression)?.methodExpression
                as? JSReferenceExpression)?.referenceName
            val factory = calleeName?.let { functions[it] }
            val moduleObj = factory?.let { fn ->
                PsiTreeUtil.findChildrenOfType(fn, JSObjectLiteralExpression::class.java)
                    .firstOrNull { o ->
                        o.findProperty("namespaced") != null ||
                            SECTIONS.count { o.findProperty(it) != null } >= 2
                    }
            }
            // Literal properties first, then assignment-attached sections. The
            // second is what these factories actually use; without it the node is
            // an empty shell that only serves namespace resolution.
            val secs = buildMap {
                moduleObj?.let { o ->
                    SECTIONS.forEach { s -> sectionObject(o.findProperty(s)?.value)?.let { put(s, it) } }
                }
                factory?.let { putAll(sectionsFromAssignments(it)) }
            }
            val ns = if (parentName == "root") key else "$parentName/$key"
            StoreData(
                id = ns,
                name = ns,
                filePath = relative,
                fqn = "$relative::$ns",
                style = "vuex",
                state = keysIn(secs["state"]),
                getters = keysIn(secs["getters"]),
                actions = keysIn(secs["actions"]),
                mutations = keysIn(secs["mutations"]),
                body = (factory?.text ?: moduleObj?.text)?.take(MAX_BODY_CHARS),
                isTest = isTestFile(relative),
            )
        }
    }

    /**
     * The object literal returned by `() => ({…})` or `function () { return {…} }`.
     *
     * The explicit `return` is checked FIRST. Taking the first descendant object
     * instead is wrong for any function that builds a local object before
     * returning — `state() { const defaults = {…}; return { items: [], filters:
     * defaults } }` would yield `defaults`' keys. The descendant search remains
     * only as the fallback for a concise arrow body, which has no return statement.
     */
    private fun returnedObject(fn: JSFunction): JSObjectLiteralExpression? =
        PsiTreeUtil.findChildrenOfType(fn, JSReturnStatement::class.java)
            .firstNotNullOfOrNull { it.expression as? JSObjectLiteralExpression }
            ?: PsiTreeUtil.findChildrenOfType(fn, JSObjectLiteralExpression::class.java).firstOrNull()

    /**
     * Namespace for a module file. Vuex namespaces mirror the directory layout
     * beneath a store-root marker, and a generic filename (`index`, `module`,
     * `store`) names itself after its parent folder:
     *
     *     store/user/index.js                 → "user"
     *     store/admin/roles.js                → "admin/roles"
     *     state/modules/user-group/module.js  → "user-group"
     *     state/modules/user-group/technician/module.js → "user-group/technician"
     *     store/index.js                      → "root"
     *
     * The LAST marker wins so `src/state/modules/…` anchors on `modules/`, not
     * on `state/`. Dropping the generic filename matters more than it looks: a
     * real codebase with 44 modules named `module.js` would otherwise collapse
     * every namespace to the literal string "module".
     */
    internal fun moduleName(relative: String): String {
        // Segment-based rather than regex: a regex marker consumes the separator,
        // so `src/state/modules/…` could only ever match `state/` and never the
        // adjacent `modules/`, yielding "modules/location" instead of "location".
        val all = relative.replace(EXT_RE, "").split('/').filter { it.isNotBlank() }
        val lastMarker = all.indexOfLast { it in STORE_DIR_NAMES }
        val segments = if (lastMarker >= 0) all.drop(lastMarker + 1) else listOfNotNull(all.lastOrNull())
        val trimmed = if (segments.lastOrNull() in GENERIC_FILENAMES) segments.dropLast(1) else segments
        return if (trimmed.isEmpty()) "root" else trimmed.joinToString("/")
    }

    /**
     * Lookup key that survives naming-convention drift between the directory and
     * the registered namespace. Codebases routinely register the camelCase form
     * of a kebab-case directory (`user-group/` → `userGroup`), so comparing the
     * raw strings misses every such store. Normalising both sides is cheaper and
     * safer than guessing one convention and camelCasing the name itself.
     */
    fun namespaceKey(raw: String): String =
        raw.lowercase().filter { it.isLetterOrDigit() || it == '/' }

    private val SECTIONS = listOf("state", "getters", "actions", "mutations")
    private val GENERIC_FILENAMES = setOf("index", "module", "store")
    private val STORE_DIR_NAMES = setOf("store", "stores", "state", "modules")
    private val STORE_DIR_RE = Regex("""(^|/)(stores?|state|modules)/""")
    private val EXT_RE = Regex("""\.(js|ts|mjs)$""")
    private val VUEX_MARKER_RE = Regex("""Vuex|namespaced|\bmutations\b""")
}
