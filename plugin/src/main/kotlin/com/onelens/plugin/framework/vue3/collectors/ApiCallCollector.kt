package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.util.Computable
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
import com.onelens.plugin.export.ApiCallData
import com.onelens.plugin.export.CallsApiEdge
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths

/**
 * Emits [ApiCallData] for HTTP calls through common client wrappers:
 *   - `api.get|post|patch|put|delete(url, ...)`
 *   - `axios.get|post|patch|put|delete(url, ...)`
 *   - `$http.get|...` (Nuxt-style) — best-effort
 *
 * Path extraction: if the first argument is a string literal, emit
 * `parametric=false`. If it's a template string (`` `…${x}…` ``), emit as-is with
 * `parametric=true` and record the interpolated identifier in `binding` so the
 * later `ModuleNameBinder` pass can narrow it to a literal when possible.
 *
 * Caller fqn: enclosing `JSFunction` (or "top-level" if none). Used for the
 * `CALLS_API` edge.
 */
object ApiCallCollector {
    private val LOG = logger<ApiCallCollector>()
    private val HTTP_METHODS = setOf("get", "post", "put", "patch", "delete")
    private val CLIENT_NAMES = setOf("api", "axios", "\$http", "http", "Api", "httpClient", "_client")

    fun collect(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) return

        val ftm = FileTypeManager.getInstance()
        val types = listOfNotNull(
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("mjs").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("vue").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = ctx.workspace.scope(project)
        val files = DumbService.getInstance(project).runReadActionInSmartMode(
            Computable { types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }
        )
        val psiManager = PsiManager.getInstance(project)

        var scanned = 0
        for (vf in files) {
            ProgressManager.checkCanceled()
            // Cheap text probe: only parse files whose name or header suggests HTTP use.
            // Full PSI walk across 2000+ .vue / .js is otherwise the slowest stage.
            val header = try {
                vf.inputStream.use { it.readNBytes(PROBE_BYTES).decodeToString() }
            } catch (_: Throwable) { "" }
            val maybeHttp = CLIENT_NAMES.any { header.contains("$it.") } ||
                header.contains("axios(") || header.contains("from 'axios'") ||
                header.contains("from \"axios\"")
            if (!maybeHttp) continue

            val calls = ReadAction.compute<List<ApiCallData>, Throwable> {
                val psi = psiManager.findFile(vf) ?: return@compute emptyList()
                extractCalls(psi, ctx)
            }
            scanned++
            ctx.apiCalls += calls
            calls.forEach { api ->
                ctx.callsApi += CallsApiEdge(
                    callerFqn = api.callerFqn,
                    apiCallFqn = "${api.method}:${api.path}:${api.callerFqn}"
                )
            }
        }
        LOG.info("ApiCallCollector: ${ctx.apiCalls.size} api calls from $scanned files")
    }

    private fun extractCalls(file: PsiFile, ctx: Vue3Context): List<ApiCallData> {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val out = mutableListOf<ApiCallData>()

        val allCalls = com.onelens.plugin.framework.vue3.VuePsiScope.findAll<JSCallExpression>(file)
        for (call in allCalls) {
            val callee = call.methodExpression as? JSReferenceExpression ?: continue
            val methodName = callee.referenceName?.lowercase() ?: continue
            if (methodName !in HTTP_METHODS) continue

            // Qualifier must look like a known HTTP client.
            val qualifier = callee.qualifier?.text?.substringAfterLast('.') ?: continue
            if (qualifier !in CLIENT_NAMES && qualifier.lowercase() !in CLIENT_NAMES) continue

            val args = call.argumentList?.arguments ?: continue
            if (args.isEmpty()) continue
            val firstArg = args[0]
            val urlText = firstArg.text.trim()
            val (path, parametric, binding) = classifyUrl(urlText)

            val enclosing = enclosingFunctionFqn(call, relative)
            out += ApiCallData(
                method = methodName.uppercase(),
                path = path,
                parametric = parametric,
                binding = binding,
                callerFqn = enclosing,
                filePath = relative
            )
        }
        return out
    }

    /**
     * Classify a URL argument:
     *   - `'/users/123'` or `"..."` → literal, non-parametric.
     *   - `` `/users/${id}` `` → parametric template, binding = "id".
     *   - anything else (variable ref, call expression) → parametric, binding = raw text.
     */
    private fun classifyUrl(raw: String): Triple<String, Boolean, String?> {
        if (raw.length < 2) return Triple(raw, true, "unresolved")
        val first = raw.first()
        return when (first) {
            '\'', '"' -> {
                val inner = raw.trim().trim('\'', '"')
                Triple(inner, false, null)
            }
            '`' -> {
                val inner = raw.trim().trim('`')
                val match = INTERP_RE.find(inner)
                val binding = match?.groupValues?.get(1)
                Triple(inner, true, binding ?: "template")
            }
            else -> Triple(raw, true, raw)
        }
    }

    private fun enclosingFunctionFqn(element: PsiElement, relative: String): String {
        val fn = PsiTreeUtil.getParentOfType(element, JSFunction::class.java, true)
        val name = fn?.name ?: return "$relative::<module>"
        return "$relative::$name"
    }

    private val INTERP_RE = Regex("""\$\{([^}]+)\}""")
    private const val PROBE_BYTES = 4096
}
