package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.onelens.plugin.export.AnnotationUsage
import com.onelens.plugin.export.ClassData
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Collects all annotation usages across classes, methods, and fields.
 * Processes per-class in small ReadAction blocks.
 *
 * Each usage carries two attribute views:
 * - `params` — legacy map of raw attribute text, kept so the pre-1.1 Python
 *   importer keeps working unchanged.
 * - `attributes` — JSON-encoded map of resolved values via [ExpressionResolver].
 *   Arrays, class literals (as FQN), enum refs (as name), and nested annotations
 *   are preserved structurally. Unresolvable values serialize as `<dynamic>`.
 */
object AnnotationCollector {

    private val LOG = logger<AnnotationCollector>()

    private val JSON: Json = Json { encodeDefaults = true }

    fun collect(project: Project, classes: List<ClassData>): List<AnnotationUsage> {
        val facade = JavaPsiFacade.getInstance(project)
        val scope = GlobalSearchScope.projectScope(project)
        val result = mutableListOf<AnnotationUsage>()

        for (classData in classes) {
            ProgressManager.checkCanceled()

            ReadAction.run<Throwable> {
                val psiClass = facade.findClass(classData.fqn, scope) ?: return@run

                extractAnnotationUsages(psiClass.modifierList, classData.fqn, "CLASS", result)

                for (method in psiClass.methods) {
                    if (method.containingClass != psiClass) continue
                    val methodFqn = buildMethodFqn(method, classData.fqn)
                    extractAnnotationUsages(method.modifierList, methodFqn, "METHOD", result)
                }

                for (field in psiClass.fields) {
                    if (field.containingClass != psiClass) continue
                    val fieldFqn = "${classData.fqn}#${field.name}"
                    extractAnnotationUsages(field.modifierList, fieldFqn, "FIELD", result)
                }
            }
        }

        LOG.info("Collected ${result.size} annotation usages")
        return result
    }

    private fun extractAnnotationUsages(
        modifierList: PsiModifierList?, targetFqn: String,
        targetKind: String, result: MutableList<AnnotationUsage>
    ) {
        if (modifierList == null) return
        for (annotation in modifierList.annotations) {
            val annotationFqn = annotation.qualifiedName ?: continue

            val params = mutableMapOf<String, String>()
            val resolved = mutableMapOf<String, JsonElement>()
            for (attr in annotation.parameterList.attributes) {
                val name = attr.name ?: "value"
                params[name] = attr.value?.text ?: ""
                resolved[name] = ExpressionResolver.resolveAnnotationValue(attr.value)
            }
            val attributes = try {
                JSON.encodeToString(JsonObject.serializer(), JsonObject(resolved))
            } catch (_: Throwable) { "{}" }

            result.add(AnnotationUsage(targetFqn, targetKind, annotationFqn, params, attributes))
        }
    }

    private fun buildMethodFqn(method: PsiMethod, classFqn: String): String {
        val params = method.parameterList.parameters.joinToString(",") {
            try { it.type.canonicalText } catch (_: Exception) { "?" }
        }
        return "$classFqn#${method.name}($params)"
    }
}
