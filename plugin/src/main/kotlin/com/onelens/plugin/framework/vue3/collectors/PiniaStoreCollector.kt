package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSFunctionExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.intellij.lang.javascript.psi.JSReturnStatement
import com.intellij.lang.javascript.psi.JSVarStatement
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
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.StoreData
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Collects Pinia store definitions. Recognizes both supported shapes:
 *
 *   Options style:
 *     export const useX = defineStore('x', {
 *       state: () => ({...}),
 *       getters: {...},
 *       actions: {...}
 *     })
 *
 *   Setup style:
 *     export const useX = defineStore('x', () => {
 *       const name = ref('')
 *       const load = async () => {}
 *       return { name, load }
 *     })
 *
 * We extract: id, export name (`useX`), style, and string lists for state / getters /
 * actions. Full expression resolution (e.g. typed state shape) is out of scope — the
 * graph only needs the names. Raw function body is stored for embedding.
 */
object PiniaStoreCollector {
    private val LOG = logger<PiniaStoreCollector>()
    private const val MAX_BODY_CHARS = 2000

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping Pinia collection — dumb mode")
            return
        }
        val fileTypeManager = FileTypeManager.getInstance()
        val jsTypes = listOfNotNull(
            fileTypeManager.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            fileTypeManager.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE },
            fileTypeManager.getFileTypeByExtension("mjs").takeIf { it != UnknownFileType.INSTANCE }
        )
        if (jsTypes.isEmpty()) {
            LOG.warn("No JS/TS file types registered")
            return
        }
        val scope = ctx.workspace.scope(project)
        // FileTypeIndex.getFiles() needs a smart read action; WebStorm 2026.1+
        // throws "Read access is allowed from inside read-action only" otherwise.
        val files = DumbService.getInstance(project).runReadActionInSmartMode(
            Computable { jsTypes.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        )
        val psiManager = PsiManager.getInstance(project)
        var scanned = 0

        for (vf in files) {
            ProgressManager.checkCanceled()
            // Cheap pre-filter: skip files that don't even mention `defineStore`.
            // PSI parse is 100× more expensive than a text probe, so shrink the
            // candidate set before entering ReadAction.
            val contentPrefix = try {
                vf.inputStream.use { it.readNBytes(DETECT_BYTES).decodeToString() }
            } catch (_: Throwable) { "" }
            val maybeHas = contentPrefix.contains("defineStore") ||
                // Some files import defineStore further down — if the first 4 KB
                // didn't contain it, also probe the full text for small files.
                (vf.length < FULL_SCAN_THRESHOLD && vf.inputStream.use { it.readAllBytes() }
                    .decodeToString().contains("defineStore"))
            if (!maybeHas) continue

            val stores = ReadAction.compute<List<StoreData>, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute emptyList()
                extractStoresFromFile(psi, ctx)
            }
            scanned++
            ctx.stores += stores
        }
        LOG.info("PiniaStoreCollector: ${ctx.stores.size} stores from $scanned candidate files")
    }

    private fun extractStoresFromFile(file: PsiFile, ctx: Vue3Context): List<StoreData> {
        val calls = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSCallExpression>(file)
            .filter { it.methodExpression?.text?.endsWith("defineStore") == true }

        if (calls.isEmpty()) return emptyList()

        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val result = mutableListOf<StoreData>()

        for (call in calls) {
            val args = call.argumentList?.arguments ?: continue
            if (args.isEmpty()) continue
            val id = stripQuotes(args[0].text) ?: continue

            // Export name: walk up to the enclosing `const useX = defineStore(...)`.
            val varStmt = PsiTreeUtil.getParentOfType(call, JSVarStatement::class.java)
            val exportName = varStmt?.variables?.firstOrNull()?.name ?: "use${id.replaceFirstChar { it.uppercase() }}Store"

            val secondArg = args.getOrNull(1)
            val (style, state, getters, actions, body) = when {
                secondArg is JSObjectLiteralExpression -> parseOptionsStyle(secondArg)
                secondArg is JSFunction || secondArg is JSFunctionExpression -> parseSetupStyle(secondArg)
                secondArg != null && secondArg.text.let { it.startsWith("(") || it.startsWith("function") } ->
                    parseSetupStyle(secondArg)
                else -> PiniaShape("unknown", emptyList(), emptyList(), emptyList(), null)
            }

            result += StoreData(
                id = id,
                name = exportName,
                filePath = relative,
                style = style,
                state = state,
                getters = getters,
                actions = actions,
                lineStart = 0,
                body = body?.take(MAX_BODY_CHARS)
            )
        }
        return result
    }

    /** Options-style: `{ state: () => ({...}), getters: {...}, actions: {...} }`. */
    private fun parseOptionsStyle(obj: JSObjectLiteralExpression): PiniaShape {
        val stateProp = obj.properties.firstOrNull { it.name == "state" }
        val gettersProp = obj.properties.firstOrNull { it.name == "getters" }
        val actionsProp = obj.properties.firstOrNull { it.name == "actions" }

        val state = extractReturnObjectKeys(stateProp?.value)
        val getters = extractObjectKeys(gettersProp?.value)
        val actions = extractObjectKeys(actionsProp?.value)

        return PiniaShape(
            style = "options",
            state = state,
            getters = getters,
            actions = actions,
            body = obj.text
        )
    }

    /** Setup-style: a function whose returned object lists the public store surface. */
    private fun parseSetupStyle(fn: com.intellij.psi.PsiElement): PiniaShape {
        val returns = PsiTreeUtil.findChildrenOfType(fn, JSReturnStatement::class.java)
        val exposed = returns.mapNotNull { it.expression as? JSObjectLiteralExpression }
            .flatMap { obj -> obj.properties.mapNotNull { it.name } }
            .distinct()
        return PiniaShape(
            style = "setup",
            state = emptyList(),
            getters = emptyList(),
            actions = exposed, // setup-style merges state+getters+actions behind names
            body = fn.text
        )
    }

    private fun extractReturnObjectKeys(value: com.intellij.psi.PsiElement?): List<String> {
        if (value == null) return emptyList()
        // state: () => ({ a: 1, b: 2 }) — first object literal found inside the
        // state function body is the state shape.
        val obj = PsiTreeUtil.findChildrenOfType(value, JSObjectLiteralExpression::class.java)
            .firstOrNull()
        return obj?.properties?.mapNotNull { it.name }.orEmpty()
    }

    private fun extractObjectKeys(value: com.intellij.psi.PsiElement?): List<String> {
        val obj = value as? JSObjectLiteralExpression ?: return emptyList()
        return obj.properties.mapNotNull { it.name }
    }

    private fun stripQuotes(raw: String): String? {
        val trimmed = raw.trim()
        if (trimmed.length < 2) return null
        val first = trimmed.first()
        if (first != '\'' && first != '"' && first != '`') return null
        return trimmed.substring(1, trimmed.length - 1)
    }

    private data class PiniaShape(
        val style: String,
        val state: List<String>,
        val getters: List<String>,
        val actions: List<String>,
        val body: String?
    )

    private const val DETECT_BYTES = 4096
    private const val FULL_SCAN_THRESHOLD = 32_768L
}
