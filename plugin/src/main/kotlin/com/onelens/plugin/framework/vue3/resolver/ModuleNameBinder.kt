package com.onelens.plugin.framework.vue3.resolver

import com.intellij.lang.javascript.psi.JSLiteralExpression
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.util.Computable
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.ApiCallData
import com.onelens.plugin.framework.vue3.Vue3Context
import java.nio.file.Paths
import com.onelens.plugin.framework.vue3.smartRead

/**
 * Resolves the most common parametric-URL shape seen in the target repo:
 *
 *   const moduleName = 'request'
 *   api.post(`/${moduleName}/search/byqual`, ...)
 *
 * The [ApiCallCollector] emits these with `parametric=true, binding="moduleName"`.
 * This pass scans the file for a top-level `const moduleName = '<literal>'` and, if
 * found, inserts an additional non-parametric ApiCallData variant with the literal
 * substituted. The original parametric entry stays so the bridge matcher can still
 * use the template form if the substitution was imperfect.
 *
 * Limitations (intentional per decision 2):
 *   - Only resolves module-level `const X = 'literal'`.
 *   - Does not follow function-parameter bindings or route.params.X (those are
 *     deferred to Phase B2 / C).
 */
object ModuleNameBinder {
    private val LOG = logger<ModuleNameBinder>()

    fun bind(project: Project, ctx: Vue3Context) {
        if (DumbService.isDumb(project)) return
        val parametrics = ctx.apiCalls.filter { it.parametric && !it.binding.isNullOrBlank() }
        if (parametrics.isEmpty()) return

        val ftm = FileTypeManager.getInstance()
        val types = listOfNotNull(
            ftm.getFileTypeByExtension("vue").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("js").takeIf { it != UnknownFileType.INSTANCE },
            ftm.getFileTypeByExtension("ts").takeIf { it != UnknownFileType.INSTANCE }
        )
        val scope = ctx.workspace.scope(project)
        val psiManager = PsiManager.getInstance(project)

        // Pre-enumerate all candidate JS/TS/Vue files once inside a smart read
        // action. Per-file FileTypeIndex calls inside the parametrics loop
        // would re-pay the read-action penalty and trip WebStorm 2026.1's
        // strict "read access must be inside read action" guard.
        val allFiles = smartRead(project) { types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct() }

        // File → { varName → literal } cache, rebuilt lazily per file.
        val fileConstants = HashMap<String, Map<String, String>>()
        val newCalls = mutableListOf<ApiCallData>()
        val seenKey = HashSet<String>()

        for (api in parametrics) {
            val binding = api.binding ?: continue
            val filePath = api.filePath
            val consts = fileConstants.getOrPut(filePath) {
                val vf = allFiles.firstOrNull { ctx.relativize(Paths.get(it.path)) == filePath }
                    ?: return@getOrPut emptyMap()
                ReadAction.compute<Map<String, String>, Throwable> {
                    val psi = psiManager.findFile(vf) ?: return@compute emptyMap()
                    extractConstants(psi)
                }
            }
            val literal = consts[binding] ?: continue
            val resolvedPath = api.path.replace("\${${binding}}", literal)
            // Dedup: same file + method + resolved path should emit only once.
            val key = "${api.method}:$resolvedPath:${api.callerFqn}"
            if (!seenKey.add(key)) continue
            newCalls += api.copy(
                path = resolvedPath,
                parametric = false,
                binding = null
            )
        }
        if (newCalls.isNotEmpty()) {
            ctx.apiCalls += newCalls
            LOG.info("ModuleNameBinder: resolved ${newCalls.size} parametric URLs to literal bindings")
        }
    }

    private fun extractConstants(file: PsiFile): Map<String, String> {
        // Pick up top-level `const name = '<literal>'` / `let name = '<literal>'`.
        val vars = PsiTreeUtil.findChildrenOfType(file, JSVariable::class.java)
        val out = HashMap<String, String>()
        for (v in vars) {
            val name = v.name ?: continue
            val init = v.initializerOrStub as? JSLiteralExpression ?: continue
            if (!init.isStringLiteral) continue
            val raw = init.text.trim().trim('\'', '"', '`')
            if (raw.isNotBlank()) out[name] = raw
        }
        return out
    }
}
