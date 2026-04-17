package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSLiteralExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
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
import com.onelens.plugin.export.ComponentData
import com.onelens.plugin.export.PropData
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Walks every `.vue` file under the project and emits a [ComponentData] per SFC.
 *   - Finds `defineProps`, `defineEmits`, `defineExpose` inside the `<script setup>` block.
 *   - Extracts prop names and (when the arg is a plain object literal) per-prop type/required.
 *   - Stores raw script body truncated to 2000 chars for the Python embedding miner
 *     (matches the plan's B10 embedding-body rule).
 *
 * Non-goals for this collector:
 *   - Options-API components (98.7% of the target repo uses `<script setup>`; Options API
 *     is P1-deferred per the plan's Decision 5).
 *   - Template rendering edges (`RENDERS`) — deferred to P1.
 *   - Type resolution via Vue plugin APIs — textual extraction is enough for name graphs.
 */
object SfcScriptSetupCollector {
    private val LOG = logger<SfcScriptSetupCollector>()
    private const val MAX_BODY_CHARS = 2000

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping SFC collection — project is in dumb mode")
            return
        }

        val vueType = FileTypeManager.getInstance().getFileTypeByExtension("vue")
        if (vueType == UnknownFileType.INSTANCE) {
            LOG.warn("Vue file type not registered — is the Vue plugin installed?")
            return
        }

        val scope = GlobalSearchScope.projectScope(project)
        // FileTypeIndex.getFiles() is index-backed and must run inside a read
        // action AND with the indexes ready. WebStorm 2026.1+ throws
        // `Read access is allowed from inside read-action only` if we call it
        // from a background thread directly (older IDEs are more lenient).
        // runReadActionInSmartMode handles both constraints in one call.
        val vueFiles = DumbService.getInstance(project)
            .runReadActionInSmartMode(Computable { FileTypeIndex.getFiles(vueType, scope).toList() })
        LOG.info("SfcScriptSetupCollector: ${vueFiles.size} .vue files to scan")
        val psiManager = PsiManager.getInstance(project)

        for (vf in vueFiles) {
            ProgressManager.checkCanceled()
            val component = ReadAction.compute<ComponentData?, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute null
                extractComponent(psi, ctx)
            } ?: continue
            ctx.components += component
        }
    }

    private fun extractComponent(file: PsiFile, ctx: Vue3Context): ComponentData? {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val name = abs.fileName.toString().removeSuffix(".vue")

        // All JS calls within the file (Vue plugin makes the embedded <script setup>
        // part of the VueFile's PSI tree — a plain PsiTreeUtil walk sees them).
        val calls = PsiTreeUtil.findChildrenOfType(file, JSCallExpression::class.java)

        val defineProps = calls.firstOrNull { callee(it) == "defineProps" }
        val defineEmits = calls.firstOrNull { callee(it) == "defineEmits" }
        val defineExpose = calls.firstOrNull { callee(it) == "defineExpose" }

        // Heuristic: a file is "script-setup" if any of the compiler macros are present.
        // Files without any macro (dumb render-only templates, legacy Options API) skip.
        if (defineProps == null && defineEmits == null && defineExpose == null &&
            !file.text.contains("<script setup")) {
            return null
        }

        val props = defineProps?.let(::extractProps).orEmpty()
        val emits = defineEmits?.let(::extractStringList).orEmpty()
        val exposes = defineExpose?.let(::extractObjectKeys).orEmpty()

        val scriptSetupBody = extractScriptSetupText(file)

        return ComponentData(
            name = name,
            filePath = relative,
            scriptSetup = true,
            props = props,
            emits = emits,
            exposes = exposes,
            body = scriptSetupBody?.take(MAX_BODY_CHARS)
        )
    }

    /**
     * Parses the first argument of `defineProps({...})`. Supports:
     *   - `defineProps({ title: String })` → `PropData("title", "String")`
     *   - `defineProps({ count: { type: Number, default: 0 } })` →
     *       `PropData("count", "Number", default="0")`
     *   - `defineProps({ active: { type: Boolean, required: true } })` → `required=true`
     *   - `defineProps(['title', 'id'])` → names only, no types.
     */
    private fun extractProps(call: JSCallExpression): List<PropData> {
        val arg = call.argumentList?.arguments?.firstOrNull() ?: return emptyList()
        if (arg is JSObjectLiteralExpression) {
            return arg.properties.mapNotNull { prop ->
                val key = prop.name ?: return@mapNotNull null
                when (val v = prop.value) {
                    is JSObjectLiteralExpression -> {
                        val typeText = v.findProperty("type")?.value?.text.orEmpty()
                        val required = v.findProperty("required")?.value?.text == "true"
                        val default = v.findProperty("default")?.value?.text
                        PropData(name = key, type = typeText, required = required, defaultValue = default)
                    }
                    else -> PropData(name = key, type = v?.text.orEmpty())
                }
            }
        }
        // Array form: defineProps(['a', 'b'])
        val arrayNames = STRING_LITERAL_RE.findAll(arg.text)
            .map { it.groupValues[1] }
            .toList()
        return arrayNames.map { PropData(name = it) }
    }

    private fun extractStringList(call: JSCallExpression): List<String> {
        val arg = call.argumentList?.arguments?.firstOrNull() ?: return emptyList()
        return STRING_LITERAL_RE.findAll(arg.text).map { it.groupValues[1] }.toList()
    }

    private fun extractObjectKeys(call: JSCallExpression): List<String> {
        val arg = call.argumentList?.arguments?.firstOrNull() as? JSObjectLiteralExpression
            ?: return emptyList()
        return arg.properties.mapNotNull { it.name }
    }

    /**
     * Extract the text between `<script setup ...>` and `</script>`. We use raw text
     * rather than descending into the PSI embedded-content node because the embedding
     * API varies by Vue plugin version and we only need the literal source for
     * downstream embedding. Returns null if there is no `<script setup>` block.
     */
    private fun extractScriptSetupText(file: PsiFile): String? {
        val src = file.text
        val match = SCRIPT_SETUP_RE.find(src) ?: return null
        return match.groupValues[1]
    }

    private fun callee(call: JSCallExpression): String =
        call.methodExpression?.text.orEmpty()

    private val STRING_LITERAL_RE = Regex("""['"]([^'"]+)['"]""")
    private val SCRIPT_SETUP_RE = Regex(
        """<script\s+setup[^>]*>([\s\S]*?)</script>""",
        RegexOption.IGNORE_CASE
    )
}
