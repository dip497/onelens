package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.editor.Document
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.onelens.plugin.export.*
import com.onelens.plugin.framework.workspace.Workspace
import kotlinx.serialization.json.Json

data class MemberResult(
    val methods: List<MethodData>,
    val fields: List<FieldData>,
    val enumConstants: List<EnumConstantData> = emptyList()
)

/**
 * Collects all methods and fields from project classes.
 * Processes per-class in small ReadAction blocks to avoid UI freezes.
 */
object MemberCollector {

    private val LOG = logger<MemberCollector>()

    /** Shared JSON codec for serializing EnumConstant.args / Annotation.attributes. */
    private val JSON: Json = Json { encodeDefaults = true }

    fun collect(project: Project, classes: List<ClassData>, workspace: Workspace): MemberResult {
        val facade = JavaPsiFacade.getInstance(project)
        val scope = workspace.scope(project)

        val methods = mutableListOf<MethodData>()
        val fields = mutableListOf<FieldData>()
        val enumConstants = mutableListOf<EnumConstantData>()

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

                var enumOrdinal = 0
                for (field in psiClass.fields) {
                    if (field.containingClass != psiClass) continue
                    try {
                        // EnumConstant is a PsiField subtype — still emit the FieldData row so
                        // existing HAS_FIELD edges / fqn lookups keep working, then additionally
                        // emit EnumConstantData with resolved constructor args.
                        fields.add(extractField(field, classData.fqn, classData.filePath, project))
                        if (field is PsiEnumConstant) {
                            enumConstants.add(
                                extractEnumConstant(field, classData.fqn, classData.filePath, enumOrdinal, project)
                            )
                            enumOrdinal++
                        }
                    } catch (e: Exception) {
                        LOG.debug("Failed to extract field ${field.name} from ${classData.fqn}: ${e.message}")
                    }
                }
            }
        }

        LOG.info("Collected ${methods.size} methods, ${fields.size} fields, ${enumConstants.size} enum constants")
        return MemberResult(methods, fields, enumConstants)
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

        // Body + javadoc: capped to keep JSON export lean and within embedder context.
        // Null for interfaces/abstracts (no body) or methods too large for a useful embedding.
        val body = try {
            method.body?.text?.takeIf { it.length <= MAX_BODY_CHARS }
        } catch (_: Exception) { null }
        val javadoc = try {
            method.docComment?.text?.take(MAX_JAVADOC_CHARS)
        } catch (_: Exception) { null }

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
            lineEnd = lineEnd,
            body = body,
            javadoc = javadoc
        )
    }

    private const val MAX_BODY_CHARS = 20_000
    private const val MAX_JAVADOC_CHARS = 2_000

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

    private fun extractEnumConstant(
        constant: PsiEnumConstant,
        classFqn: String,
        filePath: String,
        ordinal: Int,
        project: Project
    ): EnumConstantData {
        val document = constant.containingFile?.let {
            PsiDocumentManager.getInstance(project).getDocument(it)
        }
        val lineStart = safeGetLine(document, constant.textOffset)

        val argExprs = constant.argumentList?.expressions?.toList() ?: emptyList()
        val argsJson = argExprs.map { ExpressionResolver.resolve(it) }
        val flat = argsJson.flatMap { ExpressionResolver.flatten(it) }
        val types = argExprs.map { ExpressionResolver.typeOf(it) }

        val argsString = try {
            JSON.encodeToString(
                kotlinx.serialization.json.JsonArray.serializer(),
                kotlinx.serialization.json.JsonArray(argsJson)
            )
        } catch (_: Throwable) { "[]" }

        return EnumConstantData(
            fqn = "$classFqn#${constant.name}",
            name = constant.name,
            ordinal = ordinal,
            enumFqn = classFqn,
            args = argsString,
            argList = flat,
            argTypes = types,
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
