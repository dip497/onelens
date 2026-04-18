package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.ecmascript6.psi.ES6ImportDeclaration
import com.intellij.lang.ecmascript6.psi.ES6ImportSpecifier
import com.intellij.lang.ecmascript6.psi.ES6ImportSpecifierAlias
import com.intellij.lang.ecmascript6.psi.impl.ES6ImportPsiUtil
import com.intellij.lang.javascript.psi.resolve.JSResolveUtil
import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSFunctionExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Computable
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.ImportsEdge
import com.onelens.plugin.export.JsFunctionData
import com.onelens.plugin.export.JsModuleData
import com.onelens.plugin.framework.vue3.Vue3Context
import com.onelens.plugin.framework.vue3.VuePsiScope
import java.nio.file.Paths

/**
 * Closes the "business-logic layer is invisible" gap: plain JS helper
 * modules under `src/data/`, `src/utils/`, module-local helper dirs,
 * and api-wrapper files that aren't Components / Composables / Stores
 * produced zero graph nodes in Phase B. A real-world dogfood of a
 * 1500+ file Vue 3 repo confirmed 1000+ LOC business-logic files were
 * invisible to the graph even when 4+ components imported them.
 *
 * Emits, for every JS / TS / Vue source under the project:
 *   - one [JsModuleData] per file (always)
 *   - one [JsFunctionData] per top-level exported function / arrow-const /
 *     default export. Mirrors tree-sitter's @definition.function set.
 *   - one [ImportsEdge] per ES6 import specifier, target resolved via
 *     IntelliJ JS PSI resolve() with a 2-hop for aliased imports
 *     (`import { X as Y }` — first resolve stops at the alias node; we
 *     call resolve again to reach the original declaration. Verified in
 *     ImportResolveTest.)
 *
 * Non-goals (Phase B2 follow-ups):
 *   - Capturing every local function (only exports today — mirrors the
 *     publishing surface that matters for cross-module edges).
 *   - Re-export edges (`export { X } from …`) — Phase B2 follow-up.
 *   - `Channel` / `EMITS` / `LISTENS` — separate collector.
 *   - `Constant` nodes for exported object / array literals — follow-up.
 *   - JS `CALLS` edges — follow-up; the raw data is here via JSCallExpression
 *     but emitting is a separate pass.
 */
object JsModuleCollector {
    private val LOG = logger<JsModuleCollector>()
    private const val MAX_BODY_CHARS = 2000

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping JS module collection — dumb mode")
            return
        }
        val ftm = FileTypeManager.getInstance()
        val types = listOfNotNull(
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("mjs").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("vue").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = GlobalSearchScope.projectScope(project)
        val allFiles = DumbService.getInstance(project).runReadActionInSmartMode(
            Computable { types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        )
        val psiManager = PsiManager.getInstance(project)

        for (vf in allFiles) {
            ProgressManager.checkCanceled()
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                val relative = ctx.relativize(Paths.get(vf.path))
                val ext = vf.extension?.lowercase() ?: "js"

                // Module node — always. Even barrel / empty files land here so
                // ImportsEdge has a valid `targetModule` anchor.
                val module = JsModuleData(
                    filePath = relative,
                    fileKind = ext,
                    isBarrel = looksLikeBarrel(psi)
                )
                ctx.modules += module

                // Function nodes — only exported top-level functions / arrows.
                collectExportedFunctions(psi, relative).forEach { ctx.functions += it }

                // Import edges.
                collectImports(psi, relative, ctx).forEach { ctx.imports += it }
            }
        }
        LOG.info(
            "JsModuleCollector: modules=${ctx.modules.size}, functions=${ctx.functions.size}, imports=${ctx.imports.size}"
        )
    }

    /**
     * Heuristic: a barrel file is one whose entire top-level body is re-exports
     * (`export { foo } from './foo'`). Cheap textual probe — no PSI cost beyond
     * the source read we already did.
     */
    private fun looksLikeBarrel(file: PsiFile): Boolean {
        val txt = file.text.trim()
        if (txt.isEmpty()) return false
        // Any non-trivial line that isn't a re-export / import / blank / comment
        // disqualifies the file.
        val lineCommentStart = "//"
        val blockCommentStart = "/" + "*"
        val blockCommentEnd = "*" + "/"
        val lines = txt.lines().map { it.trim() }.filter {
            it.isNotEmpty() && !it.startsWith(lineCommentStart) &&
                !it.startsWith(blockCommentStart) && it != blockCommentEnd
        }
        if (lines.isEmpty()) return false
        return lines.all { line ->
            line.startsWith("export") && (line.contains("from '") || line.contains("from \"")) ||
                line.startsWith("export *") ||
                line.startsWith("import ")
        }
    }

    /**
     * Top-level export sites we care about:
     *   - `export function foo() {}`
     *   - `export async function foo() {}`
     *   - `export const foo = () => {}` / `= function () {}`
     *   - `export default function foo() {}` / `export default () => {}`
     * Functions nested inside classes / other functions are skipped.
     */
    private fun collectExportedFunctions(file: PsiFile, relative: String): List<JsFunctionData> {
        val out = mutableListOf<JsFunctionData>()
        // Walk every JSFunction; we filter to module-top-level by checking the
        // parent chain stops at the file / an export statement.
        val fns = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSFunction>(file)
        for (fn in fns) {
            val name = fn.name ?: continue
            if (!isTopLevel(fn)) continue
            val exported = isExported(fn)
            if (!exported) continue
            out += JsFunctionData(
                fqn = "$relative::$name",
                name = name,
                filePath = relative,
                exported = true,
                isDefault = isDefaultExport(fn),
                isAsync = fn.text.substringBefore("(").contains("async"),
                body = fn.text.take(MAX_BODY_CHARS)
            )
        }
        // `export const foo = () => {}` / `= function () {}` — RHS is a function
        // expression, variable is the named binding.
        val vars = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSVariable>(file)
        for (v in vars) {
            val name = v.name ?: continue
            if (!isTopLevel(v)) continue
            if (!isExported(v)) continue
            val init = v.initializerOrStub ?: continue
            val isFunctional = init is JSFunction ||
                init is JSFunctionExpression ||
                (init is PsiElement && init.text.let { it.contains("=>") || it.trimStart().startsWith("function") })
            if (!isFunctional) continue
            // Skip duplicates — if the JSFunction sweep already captured it,
            // don't double-emit.
            if (out.any { it.name == name }) continue
            out += JsFunctionData(
                fqn = "$relative::$name",
                name = name,
                filePath = relative,
                exported = true,
                isDefault = false,
                isAsync = init.text.substringBefore("(").contains("async"),
                body = v.text.take(MAX_BODY_CHARS)
            )
        }
        return out
    }

    private fun isTopLevel(element: PsiElement): Boolean {
        // A function is top-level if its nearest enclosing function-like
        // ancestor IS the file itself. Walking the parent chain to a JSFunction
        // and returning false when the function is an ancestor covers it.
        var parent: PsiElement? = element.parent
        while (parent != null && parent !is PsiFile) {
            if (parent is JSFunction && parent !== element) return false
            parent = parent.parent
        }
        return true
    }

    /**
     * An element is "exported" when any ancestor is an ES6 `export` statement
     * OR the element is itself a function with `export` in its leading tokens.
     * The JS PSI has no single `ExportStatement` interface shared across
     * versions, so we fall back to a textual probe on the leading chars of the
     * enclosing statement — stable enough for the shapes tree-sitter's
     * `tags.scm` also targets.
     */
    private fun isExported(element: PsiElement): Boolean {
        var cursor: PsiElement? = element
        while (cursor != null && cursor !is PsiFile) {
            // Check textual prefix of the enclosing statement.
            val txt = cursor.text.orEmpty().trimStart()
            if (txt.startsWith("export ") || txt.startsWith("export\n") ||
                txt.startsWith("export{") || txt.startsWith("export*") ||
                txt.startsWith("export default ")
            ) return true
            cursor = cursor.parent
        }
        return false
    }

    private fun isDefaultExport(element: PsiElement): Boolean {
        var cursor: PsiElement? = element
        while (cursor != null && cursor !is PsiFile) {
            if (cursor.text.orEmpty().trimStart().startsWith("export default")) return true
            cursor = cursor.parent
        }
        return false
    }

    /**
     * Walk every `ES6ImportDeclaration` in the file and emit one [ImportsEdge]
     * per imported binding.
     */
    private fun collectImports(file: PsiFile, sourceModule: String, ctx: Vue3Context): List<ImportsEdge> {
        val out = mutableListOf<ImportsEdge>()
        val decls = findImportDeclarations(file)
        val sourceDir = file.virtualFile?.parent?.path
        for (decl in decls) {
            val rawModule = decl.importModuleText?.trim()?.trim('\'', '"', '`') ?: continue
            val moduleText = normalizeModuleSpecifier(rawModule, sourceDir, ctx)
            val lineStart = 0 // line numbers require Document — cheap future addition

            // Each binding in the declaration produces one edge.
            for (binding in decl.importedBindings) {
                val resolvedFqn = resolveWithAliasHop(binding, ctx)
                val targetModule = targetModuleFromFqn(resolvedFqn) ?: moduleText
                out += ImportsEdge(
                    sourceModule = sourceModule,
                    targetModule = targetModule,
                    importedName = binding.name ?: "default",
                    localAlias = null,
                    isDefault = true, // default binding is the bare `import Foo from '…'` form
                    isNamespace = false,
                    targetFqn = resolvedFqn,
                    unresolved = resolvedFqn == null,
                    lineStart = lineStart
                )
            }
            for (spec in decl.importSpecifiers) {
                val (resolvedFqn, targetModule) = resolveSpecifier(spec, moduleText, ctx)
                val external = spec.referenceName
                val local = spec.declaredName
                val importedName = external ?: local ?: "?"
                // localAlias is non-null only when external and local differ
                // (i.e. `import { X as Y }`). When both are the same or one is
                // null, there is no alias to record.
                val aliasValue = if (external != null && local != null && external != local) local else null
                out += ImportsEdge(
                    sourceModule = sourceModule,
                    targetModule = targetModule,
                    importedName = importedName,
                    localAlias = aliasValue,
                    isDefault = false,
                    isNamespace = false,
                    targetFqn = resolvedFqn,
                    unresolved = resolvedFqn == null,
                    lineStart = lineStart
                )
            }
            // Namespace imports: `import * as ns from '…'`. The PSI `namedImports`
            // accessor exposes the specifier list; the namespace case is a
            // distinct node we pull via text probe on the declaration.
            val hasNamespace = decl.text.contains("import *") ||
                decl.text.contains("import * as")
            if (hasNamespace) {
                out += ImportsEdge(
                    sourceModule = sourceModule,
                    targetModule = moduleText,
                    importedName = "*",
                    isDefault = false,
                    isNamespace = true,
                    targetFqn = null,
                    unresolved = true,
                    lineStart = lineStart
                )
            }
        }
        // Fallback: if the PSI walk yielded no edges for this file but the
        // text shows `import `, run the regex scanner. Triggered both when
        // `decls` is empty AND when decls exist but their specifier /
        // binding arrays came back empty (stub-only trees — common on
        // stub-backed lazy files in large real-world projects). The regex
        // emits one edge per specifier with `unresolved=true`.
        if (out.isEmpty() && file.text.contains("import ")) {
            return extractImportsTextual(file, sourceModule, ctx)
        }
        return out
    }

    /**
     * Resolve a specifier, handling the aliased-import 2-hop case
     * (`import { alpha as renamed } from './a'`). The first `.resolve()` on
     * the reference element stops at `ES6ImportSpecifierAlias`; we call
     * resolve again on the alias's own reference to reach the original
     * declaration. Verified in ImportResolveTest.testCaseF.
     */
    private fun resolveSpecifier(spec: ES6ImportSpecifier, moduleText: String, ctx: Vue3Context): Pair<String?, String> {
        // `spec.declaredName` is the binding visible in this file. When there's
        // an alias, this is the alias; otherwise it matches the external name.
        val ref = spec.reference ?: return null to moduleText
        var target: PsiElement? = try { ref.resolve() } catch (_: Throwable) { null }
        if (target is ES6ImportSpecifierAlias) {
            val inner = target.reference
            target = try { inner?.resolve() } catch (_: Throwable) { null }
        }
        if (target == null) return null to moduleText
        val fqn = fqnFor(target, ctx)
        val module = fqn?.substringBefore("::") ?: moduleText
        return fqn to module
    }

    /**
     * Regex fallback for files where the ES6 PSI walk returned zero
     * declarations. Emits one edge per named binding and one per default
     * binding, with `unresolved=true` across the board (no `.resolve()` is
     * available without PSI). Target module is the raw specifier text —
     * the importer can still traverse source → target at file granularity.
     *
     * Handles:
     *   import defaultName from '…'
     *   import { a, b, c as renamed } from '…'
     *   import defaultName, { a, b } from '…'
     *   import * as ns from '…'
     *   import '…'                       (side-effect only, emits a * edge)
     */
    private fun extractImportsTextual(file: PsiFile, sourceModule: String, ctx: Vue3Context): List<ImportsEdge> {
        val out = mutableListOf<ImportsEdge>()
        val src = file.text
        val sourceDir = file.virtualFile?.parent?.path
        IMPORT_STMT_RE.findAll(src).forEach { m ->
            var clause = m.groupValues[1].trim()
            val module = normalizeModuleSpecifier(m.groupValues[2], sourceDir, ctx)
            // TypeScript `import type { X }` — the regex captures "type { X }"
            // as the clause. Strip the `type ` prefix so downstream parsing
            // doesn't emit a phantom default binding named "type". Skip pure
            // `import type X` (no brace) entirely: type-only default imports
            // aren't runtime edges.
            val isTypeOnly = clause == "type" || clause.startsWith("type ")
            if (isTypeOnly) {
                clause = clause.removePrefix("type").trim()
                // Pure `import type Foo from '…'` produces nothing but a
                // type-level reference; skip it to keep the graph runtime-
                // accurate.
                if (clause.isEmpty() || !clause.contains('{') && !clause.contains('*')) {
                    return@forEach
                }
            }
            when {
                clause.isBlank() -> {
                    // side-effect import: `import '…'`
                    out += ImportsEdge(
                        sourceModule = sourceModule,
                        targetModule = module,
                        importedName = "*",
                        isDefault = false,
                        isNamespace = true,
                        targetFqn = null,
                        unresolved = true
                    )
                }
                clause.contains("* as ") -> {
                    val ns = NAMESPACE_RE.find(clause)?.groupValues?.get(1) ?: "*"
                    out += ImportsEdge(
                        sourceModule = sourceModule,
                        targetModule = module,
                        importedName = "*",
                        localAlias = ns,
                        isDefault = false,
                        isNamespace = true,
                        targetFqn = null,
                        unresolved = true
                    )
                }
                else -> {
                    // Default binding (before the opening `{` or the whole
                    // clause when there's no brace block).
                    val braceIdx = clause.indexOf('{')
                    val defaultChunk = if (braceIdx >= 0) clause.substring(0, braceIdx) else clause
                    val defaultName = defaultChunk.trim().trimEnd(',').trim()
                    if (defaultName.isNotEmpty()) {
                        out += ImportsEdge(
                            sourceModule = sourceModule,
                            targetModule = module,
                            importedName = defaultName,
                            isDefault = true,
                            isNamespace = false,
                            targetFqn = null,
                            unresolved = true
                        )
                    }
                    // Named specifiers inside `{ … }`.
                    if (braceIdx >= 0) {
                        val close = clause.indexOf('}', braceIdx)
                        if (close > braceIdx) {
                            val inner = clause.substring(braceIdx + 1, close)
                            inner.split(',').forEach { raw ->
                                val piece = raw.trim()
                                if (piece.isEmpty()) return@forEach
                                val (extName, alias) = if (" as " in piece) {
                                    val parts = piece.split(" as ")
                                    parts[0].trim() to parts.getOrNull(1)?.trim()
                                } else piece to null
                                out += ImportsEdge(
                                    sourceModule = sourceModule,
                                    targetModule = module,
                                    importedName = extName,
                                    localAlias = alias,
                                    isDefault = false,
                                    isNamespace = false,
                                    targetFqn = null,
                                    unresolved = true
                                )
                            }
                        }
                    }
                }
            }
        }
        return out
    }

    /**
     * Stub-aware import-declaration enumeration.
     *
     * `.vue` files embed `<script>` / `<script setup>` as
     * `JSEmbeddedContent` nodes. A plain `PsiTreeUtil.findChildrenOfType`
     * walk often misses declarations hiding behind stubs on large real
     * projects — which is why every `.vue` file in the dogfood repo
     * produced zero imports before this fix. The Vue plugin exposes
     * `findModule(file, setup)` → `JSExecutionScope` and pairs it with
     * `JSResolveUtil.getStubbedChildren(scope, ES6_IMPORT_DECLARATION)`
     * — the exact pattern `VueExtractComponentDataBuilder` uses internally.
     *
     * For plain `.js` / `.ts`, stub-children on the file itself returns
     * the same set as the tree walk (verified via bytecode: both code
     * paths surface `ES6ImportDeclaration`).
     */
    private fun findImportDeclarations(file: PsiFile): List<ES6ImportDeclaration> {
        // For .vue files, prefer the stub-aware getStubbedChildren path on the
        // embedded script module — some real-world files expose imports only
        // through the stub children API and hide them from the PSI tree walk.
        // For .js / .ts, VuePsiScope.findAll delegates to PsiTreeUtil (same as
        // before). Both layers fall back gracefully on any exception.
        return try {
            if (file.javaClass.name == "org.jetbrains.vuejs.lang.html.VueFile") {
                val scopes = VuePsiScope.scriptRoots(file)
                scopes.asSequence()
                    .flatMap {
                        JSResolveUtil.getStubbedChildren(it, ES6ImportPsiUtil.ES6_IMPORT_DECLARATION)
                            .asSequence()
                    }
                    .filterIsInstance<ES6ImportDeclaration>()
                    .toList()
            } else {
                PsiTreeUtil.findChildrenOfType(file, ES6ImportDeclaration::class.java).toList()
            }
        } catch (_: Throwable) {
            PsiTreeUtil.findChildrenOfType(file, ES6ImportDeclaration::class.java).toList()
        }
    }

    // Import matcher used only by the textual fallback (see extractImportsTextual).
    // Clause group uses `[\s\S]*?` instead of `[^\n]` so Prettier-formatted
    // multi-line named imports are captured — the majority of named imports in
    // a real Vue 3 codebase. The lazy quantifier stops at the first
    // `from '…'` anchor, so adjacent imports remain separated.
    // Module specifier excludes only the quote characters — NOT `\n` — because
    // the full statement is allowed to span lines. Detection of the terminating
    // quote pair on its own line is sufficient.
    /**
     * Normalize a raw import specifier to a project-relative form so it can
     * be joined directly to `JsModule.filePath` / `Component.filePath`.
     *
     *   `@/views/Foo.vue`  → `src/views/Foo.vue`                (alias resolve)
     *   `./bar`            → `<dir-of-source>/bar`              (relative)
     *   `some-package`     → unchanged — npm / external stub
     *
     * For alias targets, `ctx.aliases` stores absolute paths; we resolve and
     * relativize through `ctx`. Without this, `@/` imports never matched any
     * JsModule row and every alias-form IMPORTS edge silently dropped during
     * the Python join.
     */
    private fun normalizeModuleSpecifier(spec: String, sourceDir: String?, ctx: Vue3Context): String {
        // Alias hit — exact or prefix match, longest alias first to avoid a
        // shorter alias shadowing a longer one.
        val sorted = ctx.aliases.entries.sortedByDescending { it.key.length }
        for ((alias, absBase) in sorted) {
            val prefix = if (alias.endsWith("/")) alias else "$alias/"
            val resolved = when {
                spec == alias -> absBase
                spec.startsWith(prefix) -> absBase.resolve(spec.substring(prefix.length))
                else -> null
            }
            if (resolved != null) {
                return ctx.relativize(resolved)
            }
        }
        // Relative — resolve against the source file's directory.
        if ((spec.startsWith("./") || spec.startsWith("../")) && sourceDir != null) {
            return try {
                ctx.relativize(Paths.get(sourceDir).resolve(spec).normalize())
            } catch (_: Throwable) { spec }
        }
        // Bare specifier (npm package) — leave as-is.
        return spec
    }

    private val IMPORT_STMT_RE = Regex(
        """import\s+(?:([\s\S]*?)\s+from\s+)?['"`]([^'"`]+)['"`]""",
        RegexOption.MULTILINE
    )
    private val NAMESPACE_RE = Regex("""\*\s+as\s+(\w+)""")

    /**
     * Same two-hop resolve for default-binding references, if they ever land
     * on an alias node.
     */
    private fun resolveWithAliasHop(binding: PsiElement, ctx: Vue3Context): String? {
        val ref = binding.references.firstOrNull() ?: return null
        var target: PsiElement? = try { ref.resolve() } catch (_: Throwable) { null }
        if (target is ES6ImportSpecifierAlias) {
            val inner = target.reference
            target = try { inner?.resolve() } catch (_: Throwable) { null }
        }
        return target?.let { fqnFor(it, ctx) }
    }

    /**
     * Compute a `<filePath>::<name>` fqn for a resolved PSI element.
     * Falls back to null when the element doesn't belong to a nameable
     * declaration (built-ins, external libs, etc).
     */
    private fun fqnFor(element: PsiElement, ctx: Vue3Context): String? {
        val vf = element.containingFile?.virtualFile ?: return null
        val name = when (element) {
            is JSFunction -> element.name
            is JSVariable -> element.name
            is ES6ImportSpecifier -> element.declaredName
            else -> element.text.takeIf { it.length < 120 }?.substringBefore('(')?.trim()
        } ?: return null
        // Match JsFunctionData.fqn shape — `<project-relative-path>::<name>`.
        // Returning absolute paths here broke the IMPORTS join silently: target
        // side stored relative fqns while resolved edges stored absolute fqns,
        // so no resolved edge ever matched a JsFunction row.
        val relative = try { ctx.relativize(Paths.get(vf.path)) } catch (_: Throwable) { vf.path }
        return "$relative::$name"
    }

    /**
     * Extract the target module path from a resolved fqn (`path::name` → `path`).
     * Returns null when the fqn shape is unexpected.
     */
    private fun targetModuleFromFqn(fqn: String?): String? {
        if (fqn.isNullOrBlank()) return null
        val idx = fqn.lastIndexOf("::")
        return if (idx > 0) fqn.substring(0, idx) else null
    }
}
