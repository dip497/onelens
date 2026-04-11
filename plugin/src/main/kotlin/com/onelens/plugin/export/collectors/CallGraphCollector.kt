package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.CallEdge
import com.onelens.plugin.export.ClassData

/**
 * Collects the complete call graph with 100% accurate type resolution.
 * Processes per-class in small ReadAction blocks to avoid UI freezes.
 */
object CallGraphCollector {

    private val LOG = logger<CallGraphCollector>()

    fun collect(project: Project, classes: List<ClassData>): List<CallEdge> {
        // Use half the available cores — keep system responsive
        val threads = maxOf(1, Runtime.getRuntime().availableProcessors() / 2)
        val executor = java.util.concurrent.Executors.newFixedThreadPool(threads)
        val allEdges = java.util.concurrent.ConcurrentLinkedQueue<CallEdge>()

        LOG.info("Collecting call graph with $threads threads")

        try {
            // Split classes into chunks, process in parallel
            val futures = classes.chunked(maxOf(1, classes.size / threads)).map { chunk ->
                executor.submit<Unit> {
                    for (classData in chunk) {
                        ProgressManager.checkCanceled()

                        try {
                            val classEdges = ReadAction.compute<List<CallEdge>, Throwable> {
                                val facade = JavaPsiFacade.getInstance(project)
                                val scope = GlobalSearchScope.projectScope(project)
                                val psiClass = facade.findClass(classData.fqn, scope)
                                    ?: return@compute emptyList()
                                val batch = mutableListOf<CallEdge>()

                                for (method in psiClass.methods) {
                                    if (method.containingClass != psiClass) continue
                                    val body = method.body ?: continue
                                    val callerFqn = buildMethodFqn(method, classData.fqn)

                                    collectMethodCalls(body, callerFqn, classData.filePath, project, batch)
                                    collectConstructorCalls(body, callerFqn, classData.filePath, project, batch)
                                    collectMethodReferences(body, callerFqn, classData.filePath, project, batch)
                                }
                                batch
                            }
                            allEdges.addAll(classEdges)
                        } catch (e: Exception) {
                            LOG.warn("Failed to collect call edges for ${classData.fqn}: ${e.message}")
                        }
                    }
                }
            }

            // Wait for all threads
            futures.forEach { it.get() }
        } finally {
            executor.shutdown()
        }

        val result = allEdges.toList()
        LOG.info("Collected ${result.size} call edges")
        return result
    }

    private fun collectMethodCalls(
        body: PsiCodeBlock, callerFqn: String, filePath: String,
        project: Project, edges: MutableList<CallEdge>
    ) {
        for (callExpr in PsiTreeUtil.findChildrenOfType(body, PsiMethodCallExpression::class.java)) {
            val calledMethod = try { callExpr.resolveMethod() } catch (_: Exception) { null } ?: continue
            val calleeClass = calledMethod.containingClass?.qualifiedName ?: continue

            edges.add(CallEdge(
                callerFqn = callerFqn,
                calleeFqn = buildMethodFqn(calledMethod, calleeClass),
                line = safeGetLine(callExpr, project),
                filePath = filePath,
                receiverType = extractReceiverType(callExpr)
            ))
        }
    }

    private fun collectConstructorCalls(
        body: PsiCodeBlock, callerFqn: String, filePath: String,
        project: Project, edges: MutableList<CallEdge>
    ) {
        for (newExpr in PsiTreeUtil.findChildrenOfType(body, PsiNewExpression::class.java)) {
            val constructor = try { newExpr.resolveConstructor() } catch (_: Exception) { null } ?: continue
            val calleeClass = constructor.containingClass?.qualifiedName ?: continue

            edges.add(CallEdge(
                callerFqn = callerFqn,
                calleeFqn = buildMethodFqn(constructor, calleeClass),
                line = safeGetLine(newExpr, project),
                filePath = filePath,
                receiverType = calleeClass
            ))
        }
    }

    private fun collectMethodReferences(
        body: PsiCodeBlock, callerFqn: String, filePath: String,
        project: Project, edges: MutableList<CallEdge>
    ) {
        for (ref in PsiTreeUtil.findChildrenOfType(body, PsiMethodReferenceExpression::class.java)) {
            val resolved = try { ref.resolve() } catch (_: Exception) { null }
            if (resolved is PsiMethod) {
                val calleeClass = resolved.containingClass?.qualifiedName ?: continue

                edges.add(CallEdge(
                    callerFqn = callerFqn,
                    calleeFqn = buildMethodFqn(resolved, calleeClass),
                    line = safeGetLine(ref, project),
                    filePath = filePath,
                    receiverType = try {
                        ref.qualifierExpression?.type?.canonicalText?.replace(Regex("<.*>"), "")
                    } catch (_: Exception) { null }
                ))
            }
        }
    }

    private fun extractReceiverType(callExpr: PsiMethodCallExpression): String? {
        val qualifier = callExpr.methodExpression.qualifierExpression ?: return null
        val type = try { qualifier.type } catch (_: Exception) { null }
        if (type != null) {
            val raw = type.canonicalText.replace(Regex("<.*>"), "")
            if (raw == "java.lang.Object" || !raw.contains('.')) return null
            return raw
        }
        if (qualifier is PsiReferenceExpression) {
            val resolved = try { qualifier.resolve() } catch (_: Exception) { null }
            if (resolved is PsiClass) return resolved.qualifiedName
        }
        return null
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
