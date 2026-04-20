package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.onelens.plugin.export.ClassData
import com.onelens.plugin.export.InheritanceEdge
import com.onelens.plugin.export.OverrideEdge
import com.onelens.plugin.framework.workspace.Workspace

data class InheritanceResult(
    val edges: List<InheritanceEdge>,
    val overrides: List<OverrideEdge>
)

/**
 * Collects inheritance relationships and method overrides.
 * Processes per-class in small ReadAction blocks to avoid UI freezes.
 */
object InheritanceCollector {

    private val LOG = logger<InheritanceCollector>()

    fun collect(project: Project, classes: List<ClassData>, workspace: Workspace): InheritanceResult {
        val facade = JavaPsiFacade.getInstance(project)
        val scope = workspace.scope(project)

        val inheritanceEdges = mutableListOf<InheritanceEdge>()
        val overrideEdges = mutableListOf<OverrideEdge>()
        val seenOverrides = mutableSetOf<String>()

        for (classData in classes) {
            ProgressManager.checkCanceled()

            ReadAction.run<Throwable> {
                val psiClass = facade.findClass(classData.fqn, scope) ?: return@run

                // EXTENDS
                val superClass = psiClass.superClass
                if (superClass != null) {
                    val superFqn = superClass.qualifiedName
                    if (superFqn != null && superFqn != "java.lang.Object") {
                        inheritanceEdges.add(InheritanceEdge(classData.fqn, superFqn, "EXTENDS"))
                    }
                }

                // IMPLEMENTS (directly declared only)
                for (ref in psiClass.implementsListTypes) {
                    val resolved = ref.resolve()
                    if (resolved is PsiClass) {
                        val ifaceFqn = resolved.qualifiedName ?: return@run
                        inheritanceEdges.add(InheritanceEdge(classData.fqn, ifaceFqn, "IMPLEMENTS"))
                    }
                }

                // Interface extends interface
                for (ref in psiClass.extendsListTypes) {
                    val resolved = ref.resolve()
                    if (resolved is PsiClass && resolved.qualifiedName != "java.lang.Object") {
                        val parentFqn = resolved.qualifiedName ?: return@run
                        if (parentFqn != superClass?.qualifiedName) {
                            inheritanceEdges.add(InheritanceEdge(
                                classData.fqn, parentFqn,
                                if (psiClass.isInterface) "EXTENDS" else "IMPLEMENTS"
                            ))
                        }
                    }
                }

                // Method overrides (immediate parents via findSuperMethods)
                for (method in psiClass.methods) {
                    if (method.containingClass != psiClass) continue
                    val superMethods = method.findSuperMethods(false)
                    if (superMethods.isNotEmpty()) {
                        val childFqn = buildMethodFqn(method, classData.fqn)
                        for (superMethod in superMethods) {
                            val superClassFqn = superMethod.containingClass?.qualifiedName ?: continue
                            val parentFqn = buildMethodFqn(superMethod, superClassFqn)
                            val key = "$childFqn→$parentFqn"
                            if (seenOverrides.add(key)) {
                                overrideEdges.add(OverrideEdge(childFqn, parentFqn))
                            }
                        }
                    }
                }
            }
        }

        LOG.info("Collected ${inheritanceEdges.size} inheritance edges, ${overrideEdges.size} overrides")
        return InheritanceResult(inheritanceEdges, overrideEdges)
    }

    private fun buildMethodFqn(method: PsiMethod, classFqn: String): String {
        val params = method.parameterList.parameters.joinToString(",") {
            try { it.type.canonicalText } catch (_: Exception) { "?" }
        }
        return "$classFqn#${method.name}($params)"
    }
}
