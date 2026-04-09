package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.PsiShortNamesCache
import com.onelens.plugin.export.AnnotationData
import com.onelens.plugin.export.ClassData

/**
 * Collects all classes, interfaces, enums, records, and annotation types from the project.
 *
 * Uses small ReadAction blocks per class name to avoid freezing the IDE.
 */
object ClassCollector {

    private val LOG = logger<ClassCollector>()

    fun collect(project: Project): List<ClassData> {
        // Step 1: get all class names (quick ReadAction)
        val allNames = ReadAction.compute<Array<String>, Throwable> {
            PsiShortNamesCache.getInstance(project).allClassNames
        }
        LOG.info("Found ${allNames.size} unique class names")

        val scope = GlobalSearchScope.projectScope(project)
        val result = mutableListOf<ClassData>()
        val seen = mutableSetOf<String>()
        val basePath = project.basePath ?: ""

        // Step 2: process each name in a small ReadAction (UI stays responsive)
        for (name in allNames) {
            ProgressManager.checkCanceled()

            val classes = ReadAction.compute<List<ClassData>, Throwable> {
                val batch = mutableListOf<ClassData>()
                val psiClasses = PsiShortNamesCache.getInstance(project).getClassesByName(name, scope)

                for (psiClass in psiClasses) {
                    val fqn = psiClass.qualifiedName ?: continue
                    if (psiClass.name == null) continue
                    if (!seen.add(fqn)) continue

                    val file = psiClass.containingFile?.virtualFile ?: continue
                    val filePath = file.path.removePrefix(basePath).removePrefix("/")

                    batch.add(extractClassData(psiClass, fqn, filePath, project))
                }
                batch
            }
            result.addAll(classes)
        }

        LOG.info("Collected ${result.size} classes/interfaces/enums")
        return result
    }

    private fun extractClassData(
        psiClass: PsiClass,
        fqn: String,
        filePath: String,
        project: Project
    ): ClassData {
        val document = PsiDocumentManager.getInstance(project)
            .getDocument(psiClass.containingFile)

        val lineStart = safeGetLine(document, psiClass.textOffset)
        val lineEnd = psiClass.textRange?.let { safeGetLine(document, it.endOffset) } ?: 0

        return ClassData(
            fqn = fqn,
            name = psiClass.name ?: "",
            kind = getKind(psiClass),
            modifiers = extractModifiers(psiClass.modifierList),
            genericParams = psiClass.typeParameters.map { it.name ?: "?" },
            filePath = filePath,
            lineStart = lineStart,
            lineEnd = lineEnd,
            packageName = (psiClass.containingFile as? PsiJavaFile)?.packageName ?: "",
            enclosingClass = psiClass.containingClass?.qualifiedName,
            superClass = psiClass.superClass?.qualifiedName?.takeIf { it != "java.lang.Object" },
            interfaces = psiClass.interfaces.mapNotNull { it.qualifiedName },
            annotations = extractAnnotations(psiClass.modifierList)
        )
    }

    private fun getKind(psiClass: PsiClass): String = when {
        psiClass.isInterface -> "INTERFACE"
        psiClass.isEnum -> "ENUM"
        psiClass.isAnnotationType -> "ANNOTATION_TYPE"
        psiClass.isRecord -> "RECORD"
        psiClass.hasModifierProperty("abstract") -> "ABSTRACT_CLASS"
        else -> "CLASS"
    }

    internal fun extractModifiers(modifierList: PsiModifierList?): List<String> {
        if (modifierList == null) return emptyList()
        val modifiers = mutableListOf<String>()

        if (modifierList.hasExplicitModifier("public")) modifiers.add("public")
        else if (modifierList.hasExplicitModifier("private")) modifiers.add("private")
        else if (modifierList.hasExplicitModifier("protected")) modifiers.add("protected")

        if (modifierList.hasExplicitModifier("static")) modifiers.add("static")
        if (modifierList.hasExplicitModifier("final")) modifiers.add("final")
        if (modifierList.hasExplicitModifier("abstract")) modifiers.add("abstract")
        if (modifierList.hasExplicitModifier("synchronized")) modifiers.add("synchronized")
        if (modifierList.hasExplicitModifier("native")) modifiers.add("native")
        if (modifierList.hasModifierProperty("default")) modifiers.add("default")

        return modifiers
    }

    internal fun extractAnnotations(modifierList: PsiModifierList?): List<AnnotationData> {
        if (modifierList == null) return emptyList()
        return modifierList.annotations.mapNotNull { annotation ->
            val fqn = annotation.qualifiedName ?: return@mapNotNull null
            val params = mutableMapOf<String, String>()
            for (attr in annotation.parameterList.attributes) {
                val name = attr.name ?: "value"
                val value = attr.value?.text ?: ""
                params[name] = value
            }
            AnnotationData(fqn = fqn, params = params)
        }
    }

    private fun safeGetLine(document: com.intellij.openapi.editor.Document?, offset: Int): Int {
        if (document == null) return 0
        if (offset < 0 || offset > document.textLength) return 0
        return document.getLineNumber(offset) + 1
    }
}
