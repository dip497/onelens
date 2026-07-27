package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.ecmascript6.psi.ES6ExportDefaultAssignment
import com.intellij.lang.javascript.psi.JSArrayLiteralExpression
import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSLiteralExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReferenceExpression
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
import com.onelens.plugin.export.ComponentData
import com.onelens.plugin.framework.jscommon.isTestFile
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Collects Vue 2 Options-API components — the `.vue` SFCs that
 * [SfcScriptSetupCollector] deliberately skips.
 *
 *     export default {
 *       name: 'UserCard',
 *       props: { title: String, active: { type: Boolean, required: true } },
 *       mixins: [formMixin],
 *       components: { ChildCard },
 *       methods: { save() {…} },
 *     }
 *
 * Extracted: props (via the shared [VuePropParser]), `mixins` identifiers,
 * locally registered `components`, and `this.$emit('x')` literals as `emits`
 * (Vue 2.6 has no `emits` option — the call sites are the only declaration).
 *
 * NOT extracted: `methods` / `computed` / `watch` / `data` key lists. They stay
 * inside the captured `body` text where the Python miner embeds them. Promoting
 * them to node fields would answer no query anyone has asked for.
 *
 * Runs only when `ctx.vueMajor == 2`. Vue 2.7 files that DO use `<script setup>`
 * are handled by [SfcScriptSetupCollector], which also runs on Vue 2 — the two
 * are mutually exclusive per file (see [alreadyCollected]).
 */
object OptionsApiCollector {
    private val LOG = logger<OptionsApiCollector>()
    private const val MAX_BODY_CHARS = 2000

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping Options-API collection — project is in dumb mode")
            return
        }
        val vueType = FileTypeManager.getInstance().getFileTypeByExtension("vue")
        if (vueType == UnknownFileType.INSTANCE) {
            LOG.warn("Vue file type not registered — is the Vue plugin installed?")
            return
        }

        val scope = ctx.workspace.scope(project)
        val vueFiles = smartRead(project) { FileTypeIndex.getFiles(vueType, scope).toList() }
        val psiManager = PsiManager.getInstance(project)

        // Files already emitted by SfcScriptSetupCollector (Vue 2.7 `<script setup>`).
        // Keyed by FILE, not fqn: the two collectors derive `name` differently —
        // Sfc uses the filename, this one prefers the `name:` option — so the same
        // SFC can yield two different fqns and an fqn-keyed set would let both
        // through as separate Component nodes. One SFC is one component.
        val alreadyCollected = ctx.components.mapTo(HashSet()) { it.filePath }

        var emitted = 0
        for (vf in vueFiles) {
            ProgressManager.checkCanceled()
            val component = ReadAction.compute<ComponentData?, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute null
                extractComponent(psi, ctx)
            } ?: continue
            if (!alreadyCollected.add(component.filePath)) continue
            ctx.components += component
            emitted++
        }

        // Silent-empty guard. A Vue 2 export where every SFC parsed to nothing is
        // indistinguishable from a successful run at the CLI: exit 0, no error,
        // an empty component graph. Same failure shape as the isVendorPath
        // absolute-path bug. Warn loudly rather than let it look like success.
        // Tests THIS collector's own output, not `ctx.components` — that list is
        // shared with SfcScriptSetupCollector, so on a Vue 2.7 hybrid a single
        // `<script setup>` file was enough to suppress the warning while all 2000
        // Options-API files silently failed to parse.
        if (vueFiles.isNotEmpty() && emitted == 0) {
            LOG.warn(
                "Options-API collection found ${vueFiles.size} .vue files but produced ZERO " +
                    "components (vueMajor=${ctx.vueMajor}). The component graph will be empty — " +
                    "check that these SFCs use `export default {…}` and that the Vue plugin parsed them."
            )
        }
        LOG.info("OptionsApiCollector: $emitted components from ${vueFiles.size} .vue files")
    }

    private fun extractComponent(file: PsiFile, ctx: Vue3Context): ComponentData? {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val fileName = abs.fileName.toString().removeSuffix(".vue")

        // `<script setup>` files belong to SfcScriptSetupCollector. Bail before
        // doing any PSI work so a Vue 2.7 hybrid repo doesn't double-parse.
        if (file.text.contains("<script setup")) return null

        val options = findDefaultExportObject(file) ?: return null

        // A `name:` option wins over the filename — Vue 2 codebases rely on it for
        // recursive components and devtools, and it is what `components: {}` maps
        // register under. Falls back to the filename, matching Vue 3's convention.
        val declaredName = (options.findProperty("name")?.value as? JSLiteralExpression)
            ?.takeIf { it.isQuotedLiteral }
            ?.stringValue
        val name = declaredName?.takeIf { it.isNotBlank() } ?: fileName

        return ComponentData(
            name = name,
            filePath = relative,
            fqn = "$relative::$name",
            scriptSetup = false,
            props = VuePropParser.parse(options.findProperty("props")?.value),
            emits = extractEmits(file),
            exposes = emptyList(), // Vue 2 has no defineExpose equivalent.
            mixins = extractIdentifierArray(options, "mixins"),
            body = extractScriptText(file)?.take(MAX_BODY_CHARS),
            isTest = isTestFile(relative),
        )
    }

    /**
     * Finds the object literal of `export default { … }`.
     *
     * Also unwraps the two wrapper calls Vue 2 codebases use — `Vue.extend({…})`
     * and `defineComponent({…})` — since the options object inside is identical.
     * Anything else (a default-exported identifier, a factory call) yields null:
     * a component we cannot parse is reported as absent, not as an empty one.
     */
    private fun findDefaultExportObject(file: PsiFile): JSObjectLiteralExpression? {
        // PRIMARY: resolve the actual default-export node. This is exact — it
        // cannot pick up an unrelated local constant, and it accepts a legitimate
        // options object with no recognisable option key (`export default { name:
        // 'Background' }`, a template-only presentational component — 31 of them
        // in the validation repo).
        //
        // Two earlier attempts were both wrong: a text-offset scan plus "first
        // object literal with a known option key" DROPPED those 31, and adding a
        // blind `?: firstOrNull()` fallback made it pick an unrelated object when
        // the default export is an identifier.
        PsiTreeUtil.findChildrenOfType(file, ES6ExportDefaultAssignment::class.java)
            .firstNotNullOfOrNull { unwrapOptions(it.expression) }
            ?.let { return it }

        // FALLBACK: shape heuristic, for Vue-plugin versions that wrap SFC script
        // content such that the export assignment is not in this tree. Still
        // requires a real option key — never a blind first-object grab.
        val offset = EXPORT_DEFAULT_RE.find(file.text)?.range?.last ?: return null
        return PsiTreeUtil.findChildrenOfType(file, JSObjectLiteralExpression::class.java)
            .filter { it.textOffset >= offset }
            .sortedBy { it.textOffset }
            .firstOrNull { obj -> OPTION_KEYS.any { key -> obj.findProperty(key) != null } }
    }

    /**
     * The options object of a default export: the literal itself, or the first
     * argument of a `Vue.extend(…)` / `defineComponent(…)` wrapper. A
     * default-exported identifier yields null — absent, not guessed.
     */
    private fun unwrapOptions(expr: PsiElement?): JSObjectLiteralExpression? = when (expr) {
        is JSObjectLiteralExpression -> expr
        is JSCallExpression -> expr.argumentList?.arguments?.firstOrNull() as? JSObjectLiteralExpression
        else -> null
    }

    /**
     * Vue 2.6 has no `emits` option, so the emitted event names are only visible
     * at the call sites: `this.$emit('save', payload)`. Collect the literal first
     * arguments and dedupe. Dynamic emits (`this.$emit(someVar)`) are skipped.
     */
    private fun extractEmits(file: PsiFile): List<String> =
        PsiTreeUtil.findChildrenOfType(file, JSCallExpression::class.java)
            .filter { it.methodExpression?.text?.endsWith("\$emit") == true }
            .mapNotNull { call ->
                (call.argumentList?.arguments?.firstOrNull() as? JSLiteralExpression)
                    ?.takeIf { it.isQuotedLiteral }
                    ?.stringValue
            }
            .distinct()

    /** `mixins: [formMixin, tableMixin]` → the identifier names, in order. */
    private fun extractIdentifierArray(options: JSObjectLiteralExpression, key: String): List<String> {
        val array = options.findProperty(key)?.value as? JSArrayLiteralExpression ?: return emptyList()
        return array.expressions.mapNotNull { (it as? JSReferenceExpression)?.referenceName }
    }

    /**
     * Text of the SFC's `<script>` block, for the embedding miner. Mirrors
     * [SfcScriptSetupCollector]'s raw-text approach: the embedded-content PSI API
     * varies by Vue plugin version and only the literal source is needed here.
     */
    private fun extractScriptText(file: PsiFile): String? =
        SCRIPT_RE.find(file.text)?.groupValues?.get(1)

    private val EXPORT_DEFAULT_RE = Regex("""export\s+default""")

    /**
     * Shape probe for a component options object. `name` alone is too weak (any
     * config object has one), so the list is restricted to keys that only a Vue
     * component declares.
     */
    private val OPTION_KEYS = listOf(
        "props", "data", "computed", "methods", "watch", "components",
        "mixins", "created", "mounted", "template", "render", "setup",
    )

    private val SCRIPT_RE = Regex(
        """<script(?![^>]*\ssetup)[^>]*>([\s\S]*?)</script>""",
        RegexOption.IGNORE_CASE,
    )
}
