package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.psi.util.PsiUtil
import com.onelens.plugin.export.ClassData
import com.onelens.plugin.export.DataFlowData
import com.onelens.plugin.export.FieldAccessEdge
import com.onelens.plugin.export.InstantiationEdge
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Tier-1 data-flow collector — field read/write access + instantiation edges.
 *
 * Walks each method body once (parallel per-class chunks, same ReadAction
 * pattern as [CallGraphCollector] to avoid EDT freezes — see LESSONS-LEARNED).
 * Kept separate from CallGraphCollector so the hot CALLS path stays untouched;
 * the marginal cost is one extra body walk per class.
 *
 * 100% PSI-accurate: `resolve()` distinguishes `this.x` from a shadowing local,
 * resolves inherited fields to their declaring class, and skips locals/params
 * (only `PsiField` resolutions become edges). This is exactly what tree-sitter
 * tools cannot do.
 */
object DataFlowCollector {

    private val LOG = logger<DataFlowCollector>()

    fun collect(
        project: Project,
        classes: List<ClassData>,
        workspace: Workspace,
    ): DataFlowData {
        val threads = maxOf(1, Runtime.getRuntime().availableProcessors())
        val executor = java.util.concurrent.Executors.newFixedThreadPool(threads)
        val fieldAccesses = java.util.concurrent.ConcurrentLinkedQueue<FieldAccessEdge>()
        val instantiations = java.util.concurrent.ConcurrentLinkedQueue<InstantiationEdge>()

        try {
            val futures = classes.chunked(maxOf(1, classes.size / threads)).map { chunk ->
                executor.submit<Unit> {
                    for (classData in chunk) {
                        ProgressManager.checkCanceled()
                        try {
                            ReadAction.run<Throwable> {
                                val facade = JavaPsiFacade.getInstance(project)
                                val scope = workspace.scope(project)
                                val psiClass = facade.findClass(classData.fqn, scope) ?: return@run
                                for (method in psiClass.methods) {
                                    if (method.containingClass != psiClass) continue
                                    val body = method.body ?: continue
                                    val accessorFqn = buildMethodFqn(method, classData.fqn)
                                    collectFieldAccess(body, accessorFqn, project, fieldAccesses)
                                    collectInstantiations(body, accessorFqn, project, instantiations)
                                }
                            }
                        } catch (e: Exception) {
                            LOG.warn("Data-flow collect failed for ${classData.fqn}: ${e.message}")
                        }
                    }
                }
            }
            futures.forEach { it.get() }
        } finally {
            executor.shutdown()
        }

        val fa = fieldAccesses.toList()
        val inst = instantiations.toList()
        LOG.info("Collected ${fa.size} field accesses, ${inst.size} instantiations")
        return DataFlowData(fieldAccesses = fa, instantiations = inst)
    }

    private fun collectFieldAccess(
        body: PsiCodeBlock, accessorFqn: String, project: Project,
        out: MutableCollection<FieldAccessEdge>,
    ) {
        for (ref in PsiTreeUtil.findChildrenOfType(body, PsiReferenceExpression::class.java)) {
            // Skip the method-name half of a call expression (handled by CALLS).
            if (ref.parent is PsiMethodCallExpression &&
                (ref.parent as PsiMethodCallExpression).methodExpression === ref) continue
            val resolved = try { ref.resolve() } catch (_: Exception) { null }
            if (resolved !is PsiField) continue
            val declaringClass = resolved.containingClass?.qualifiedName ?: continue
            val fieldFqn = "$declaringClass#${resolved.name}"
            val mode = if (PsiUtil.isAccessedForWriting(ref)) "write" else "read"
            out.add(FieldAccessEdge(
                accessorFqn = accessorFqn,
                fieldFqn = fieldFqn,
                mode = mode,
                line = safeGetLine(ref, project),
            ))
        }
    }

    private fun collectInstantiations(
        body: PsiCodeBlock, accessorFqn: String, project: Project,
        out: MutableCollection<InstantiationEdge>,
    ) {
        for (newExpr in PsiTreeUtil.findChildrenOfType(body, PsiNewExpression::class.java)) {
            // Resolve via the type ref so anonymous classes resolve to their
            // named base, and array `new`s (no class type) are skipped.
            val classRef = newExpr.classOrAnonymousClassReference
            val resolved = try { classRef?.resolve() } catch (_: Exception) { null }
            val classFqn = (resolved as? PsiClass)?.qualifiedName ?: continue
            out.add(InstantiationEdge(
                methodFqn = accessorFqn,
                classFqn = classFqn,
                line = safeGetLine(newExpr, project),
            ))
        }
    }

    private fun buildMethodFqn(method: PsiMethod, classFqn: String): String {
        val params = method.parameterList.parameters.joinToString(",") {
            try { it.type.canonicalText } catch (_: Exception) { "?" }
        }
        return "$classFqn#${method.name}($params)"
    }

    private fun safeGetLine(element: PsiElement, project: Project): Int {
        val doc = element.containingFile?.let { PsiDocumentManager.getInstance(project).getDocument(it) } ?: return 0
        val offset = element.textOffset
        if (offset < 0 || offset > doc.textLength) return 0
        return doc.getLineNumber(offset) + 1
    }
}
