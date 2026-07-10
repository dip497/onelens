package com.onelens.plugin.framework.jscommon

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSFunction
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.util.Computable
import com.intellij.openapi.diagnostic.logger
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
    private val CLIENT_NAMES = setOf(
        "api", "axios", "\$http", "http", "Api", "httpClient", "_client",
        "ky", "apiFetch", "request",
    )
    // Bare calls (no qualifier) that are themselves HTTP requests: `fetch(url, {method})`,
    // `ky(url)`, `apiFetch(url)`, `request(url)`. Method defaults to GET unless a second-arg
    // object literal carries `method: "X"`.
    private val BARE_FETCH_NAMES = setOf("fetch", "ky", "apiFetch", "request")
    private val METHOD_OPT_RE = Regex("""method\s*:\s*['"]([A-Za-z]+)['"]""")

    fun collect(project: Project, ctx: JsCommonSink) {
        if (DumbService.isDumb(project)) return

        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorFile(it, ctx) }
        }
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
                header.contains("from \"axios\"") ||
                header.contains("ky") || header.contains("fetch(") || header.contains("apiFetch")
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

    private fun extractCalls(file: PsiFile, ctx: JsCommonSink): List<ApiCallData> {
        val abs = Paths.get(file.virtualFile.path)
        val relative = ctx.relativize(abs)
        val out = mutableListOf<ApiCallData>()

        val allCalls = ctx.findAll<JSCallExpression>(file)
        for (call in allCalls) {
            val callee = call.methodExpression as? JSReferenceExpression ?: continue
            val refName = callee.referenceName ?: continue
            val qualifierNode = callee.qualifier

            val method: String = if (qualifierNode == null) {
                // Bare call — `fetch(url, {method})` / `ky(url)` / `apiFetch(url)`.
                if (refName !in BARE_FETCH_NAMES) continue
                val args = call.argumentList?.arguments ?: continue
                if (args.isEmpty()) continue
                args.getOrNull(1)?.let { METHOD_OPT_RE.find(it.text)?.groupValues?.get(1)?.uppercase() } ?: "GET"
            } else {
                // Qualified call — `client.verb(url)`.
                val verb = refName.lowercase()
                if (verb !in HTTP_METHODS) continue
                val qualifier = qualifierNode.text.substringAfterLast('.')
                if (qualifier !in CLIENT_NAMES && qualifier.lowercase() !in CLIENT_NAMES) continue
                verb.uppercase()
            }

            val args = call.argumentList?.arguments ?: continue
            if (args.isEmpty()) continue
            val urlText = args[0].text.trim()
            val (path, parametric, binding) = classifyUrl(urlText)

            val enclosing = enclosingFunctionFqn(call, relative)
            out += ApiCallData(
                method = method,
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
