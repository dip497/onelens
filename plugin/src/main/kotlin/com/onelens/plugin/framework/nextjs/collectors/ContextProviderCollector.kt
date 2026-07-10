package com.onelens.plugin.framework.nextjs.collectors

import com.intellij.lang.javascript.psi.JSCallExpression
import com.intellij.lang.javascript.psi.JSReferenceExpression
import com.intellij.lang.javascript.psi.JSVariable
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FileTypeIndex
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.ContextProviderData
import com.onelens.plugin.export.ProvidesContextEdge
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.jscommon.smartRead
import com.onelens.plugin.framework.nextjs.NextjsContext
import java.nio.file.Paths

/**
 * Emits a [ContextProviderData] for each top-level `const X = createContext(...)` (or
 * `React.createContext`) and a PROVIDES_CONTEXT edge from the enclosing ReactComponent
 * (if the site sits inside one) else the containing JsModule (its filePath).
 */
object ContextProviderCollector {
    private val LOG = logger<ContextProviderCollector>()

    private val EXTS = setOf("tsx", "jsx", "ts", "js")

    fun collect(project: Project, ctx: NextjsContext) {
        if (DumbService.isDumb(project)) {
            LOG.warn("Skipping context-provider collection — dumb mode")
            return
        }
        val componentFqns = ctx.components.mapTo(HashSet()) { it.fqn }
        val types = JsFileTypes.script()
        val scope = ctx.workspace.scope(project)
        val files = smartRead(project) {
            types.flatMap { FileTypeIndex.getFiles(it, scope) }.distinct()
                .filterNot { JsFileTypes.isVendorPath(it.path) }
                .filter { (it.extension?.lowercase() ?: "") in EXTS }
        }
        val psiManager = PsiManager.getInstance(project)
        for (vf in files) {
            ProgressManager.checkCanceled()
            val relative = ctx.relativize(Paths.get(vf.path))
            if (relative.isEmpty()) continue
            ReadAction.run<Throwable> {
                val psi = psiManager.findFile(vf) ?: return@run
                if (!psi.text.contains("createContext")) return@run // cheap gate
                val doc = PsiDocumentManager.getInstance(project).getDocument(psi)
                for (v in PsiTreeUtil.findChildrenOfType(psi, JSVariable::class.java)) {
                    val name = v.name ?: continue
                    if (!NextPsiUtil.isTopLevel(v)) continue
                    val init = v.initializerOrStub as? JSCallExpression ?: continue
                    if (!isCreateContext(init)) continue
                    val fqn = "$relative::$name"
                    ctx.contextProviders += ContextProviderData(
                        fqn = fqn, name = name, filePath = relative,
                        lineStart = NextPsiUtil.lineNumber(doc, v.textRange.startOffset),
                        lineEnd = NextPsiUtil.lineNumber(doc, v.textRange.endOffset),
                    )
                    val source = NextPsiUtil.enclosingSymbolFqn(v, relative, componentFqns) ?: relative
                    ctx.providesContext += ProvidesContextEdge(sourceFqn = source, contextFqn = fqn)
                }
            }
        }
        LOG.info("ContextProviderCollector: ${ctx.contextProviders.size} context providers")
    }

    private fun isCreateContext(call: JSCallExpression): Boolean {
        val callee = call.methodExpression as? JSReferenceExpression ?: return false
        if (callee.referenceName != "createContext") return false
        val qualifier = callee.qualifier?.text
        return qualifier == null || qualifier == "React"
    }
}
