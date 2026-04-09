package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.editor.Document
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.onelens.plugin.export.*

data class MemberResult(
    val methods: List<MethodData>,
    val fields: List<FieldData>
)

/**
 * Collects all methods and fields from project classes.
 * Processes per-class in small ReadAction blocks to avoid UI freezes.
 */
object MemberCollector {

    private val LOG = logger<MemberCollector>()

    fun collect(project: Project, classes: List<ClassData>): MemberResult {
        val facade = JavaPsiFacade.getInstance(project)
        val scope = GlobalSearchScope.projectScope(project)

        val methods = mutableListOf<MethodData>()
        val fields = mutableListOf<FieldData>()

        for (classData in classes) {
            ProgressManager.checkCanceled()

            ReadAction.run<Throwable> {
                val psiClass = facade.findClass(classData.fqn, scope) ?: return@run

                for (method in psiClass.methods) {
                    if (method.containingClass != psiClass) continue
                    try {
                        methods.add(extractMethod(method, classData.fqn, classData.filePath, project))
                    } catch (e: Exception) {
                        LOG.debug("Failed to extract method ${method.name} from ${classData.fqn}: ${e.message}")
                    }
                }

                for (field in psiClass.fields) {
                    if (field.containingClass != psiClass) continue
                    try {
                        fields.add(extractField(field, classData.fqn, classData.filePath, project))
                    } catch (e: Exception) {
                        LOG.debug("Failed to extract field ${field.name} from ${classData.fqn}: ${e.message}")
                    }
                }
            }
        }

        LOG.info("Collected ${methods.size} methods, ${fields.size} fields")
        return MemberResult(methods, fields)
    }

    private fun extractMethod(
        method: PsiMethod,
        classFqn: String,
        filePath: String,
        project: Project
    ): MethodData {
        val paramSignature = method.parameterList.parameters.joinToString(",") { param ->
            try { param.type.canonicalText } catch (_: Exception) { "?" }
        }
        val fqn = "$classFqn#${method.name}($paramSignature)"

        val document = method.containingFile?.let {
            PsiDocumentManager.getInstance(project).getDocument(it)
        }

        val lineStart = safeGetLine(document, method.textOffset)
        val lineEnd = method.textRange?.let { safeGetLine(document, it.endOffset) } ?: 0

        val parameters = method.parameterList.parameters.map { param ->
            ParameterData(
                name = param.name ?: "",
                type = try { param.type.canonicalText } catch (_: Exception) { "?" },
                annotations = param.annotations.mapNotNull { it.qualifiedName }
            )
        }

        return MethodData(
            fqn = fqn,
            name = method.name,
            classFqn = classFqn,
            returnType = try { method.returnType?.canonicalText ?: "void" } catch (_: Exception) { "void" },
            parameters = parameters,
            modifiers = ClassCollector.extractModifiers(method.modifierList),
            isConstructor = method.isConstructor,
            isVarArgs = method.isVarArgs,
            throwsTypes = method.throwsList.referencedTypes.map {
                try { it.canonicalText } catch (_: Exception) { "?" }
            },
            annotations = ClassCollector.extractAnnotations(method.modifierList),
            filePath = filePath,
            lineStart = lineStart,
            lineEnd = lineEnd
        )
    }

    private fun extractField(
        field: PsiField,
        classFqn: String,
        filePath: String,
        project: Project
    ): FieldData {
        val fqn = "$classFqn#${field.name}"
        val document = field.containingFile?.let {
            PsiDocumentManager.getInstance(project).getDocument(it)
        }
        val lineStart = safeGetLine(document, field.textOffset)

        return FieldData(
            fqn = fqn,
            name = field.name,
            classFqn = classFqn,
            type = try { field.type.canonicalText } catch (_: Exception) { "?" },
            modifiers = ClassCollector.extractModifiers(field.modifierList),
            annotations = ClassCollector.extractAnnotations(field.modifierList),
            filePath = filePath,
            lineStart = lineStart
        )
    }

    private fun safeGetLine(document: Document?, offset: Int): Int {
        if (document == null) return 0
        if (offset < 0 || offset > document.textLength) return 0
        return document.getLineNumber(offset) + 1
    }
}
