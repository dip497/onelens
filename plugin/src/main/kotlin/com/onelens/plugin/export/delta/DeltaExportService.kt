package com.onelens.plugin.export.delta

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.onelens.plugin.OneLensConstants
import com.onelens.plugin.export.*
import com.onelens.plugin.export.collectors.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.nio.file.Files
import java.nio.file.Path

/**
 * Produces delta JSON exports containing only changes since last export.
 *
 * For each changed file:
 *   - Collects classes, methods, fields, calls, inheritance for classes in that file
 *   - Marks deleted classes/methods from removed files
 *
 * For each deleted file:
 *   - Looks up what classes were in that file (from previous export state)
 *   - Adds their FQNs to the deleted list
 */
object DeltaExportService {

    private val LOG = logger<DeltaExportService>()

    private val json = Json {
        prettyPrint = true
        encodeDefaults = true
    }

    @Serializable
    data class DeltaDocument(
        val version: String,
        val exportType: String = "delta",
        val timestamp: String,
        val basedOnTimestamp: String,
        val changedFiles: List<String>,
        val deleted: DeletedSection,
        val upserted: UpsertedSection,
        val stats: DeltaStats
    )

    @Serializable
    data class DeletedSection(
        val classes: List<String> = emptyList(),
        val methods: List<String> = emptyList(),
        val fields: List<String> = emptyList(),
    )

    @Serializable
    data class UpsertedSection(
        val classes: List<ClassData> = emptyList(),
        val methods: List<MethodData> = emptyList(),
        val fields: List<FieldData> = emptyList(),
        val callGraph: List<CallEdge> = emptyList(),
        val inheritance: List<InheritanceEdge> = emptyList(),
        val methodOverrides: List<OverrideEdge> = emptyList(),
        val annotations: List<AnnotationUsage> = emptyList(),
    )

    @Serializable
    data class DeltaStats(
        val changedFileCount: Int = 0,
        val deletedClassCount: Int = 0,
        val upsertedClassCount: Int = 0,
        val upsertedMethodCount: Int = 0,
        val upsertedCallEdgeCount: Int = 0,
        val exportDurationMs: Long = 0
    )

    /**
     * Export only changes since last export.
     *
     * @return Path to delta JSON file, or null if no changes detected
     */
    fun exportDelta(project: Project, config: ExportConfig): DeltaResult {
        val startTime = System.currentTimeMillis()
        val basePath = project.basePath ?: return DeltaResult.Error("No project base path")
        val state = ExportState.getInstance(project)

        // 1. Detect changed files
        val changedFiles = DeltaTracker.getChangedFiles(project)

        if (changedFiles.isFullReexport) {
            return DeltaResult.NeedFullExport("No previous export state — full export needed")
        }

        if (!changedFiles.hasChanges) {
            return DeltaResult.NoChanges
        }

        LOG.info("Delta: ${changedFiles.modified.size} modified, ${changedFiles.deleted.size} deleted files")

        // 2. For deleted files: find what classes were in them (from file hashes map keys)
        val deletedClasses = mutableListOf<String>()
        val deletedMethods = mutableListOf<String>()
        val deletedFields = mutableListOf<String>()

        // We track file→classes mapping in state.fileHashes (key=filePath, value=comma-separated FQNs)
        for (deletedFile in changedFiles.deleted) {
            val classFqns = state.state.fileHashes[deletedFile]?.split(",") ?: continue
            deletedClasses.addAll(classFqns)
            // Methods and fields will be cascade-deleted when their class is deleted
        }

        // 3. For modified files: re-collect classes in those files
        val affectedClasses = ReadAction.compute<List<ClassData>, Throwable> {
            collectClassesFromFiles(project, changedFiles.modified, basePath)
        }

        // 4. Collect members, calls, inheritance for affected classes
        val members = MemberCollector.collect(project, affectedClasses)
        val callGraph = CallGraphCollector.collect(project, affectedClasses)
        val inheritance = InheritanceCollector.collect(project, affectedClasses)
        val annotations = AnnotationCollector.collect(project, affectedClasses)

        // Also add modified files' old classes to deleted (they'll be replaced by upserted)
        for (modifiedFile in changedFiles.modified) {
            val oldClassFqns = state.state.fileHashes[modifiedFile]?.split(",") ?: continue
            deletedClasses.addAll(oldClassFqns)
        }

        val durationMs = System.currentTimeMillis() - startTime

        // 5. Build delta document
        val delta = DeltaDocument(
            version = OneLensConstants.EXPORT_VERSION,
            timestamp = java.time.Instant.now().toString(),
            basedOnTimestamp = java.time.Instant.ofEpochMilli(state.state.lastExportTimestamp).toString(),
            changedFiles = changedFiles.modified + changedFiles.deleted,
            deleted = DeletedSection(
                classes = deletedClasses.distinct(),
                methods = deletedMethods,
                fields = deletedFields,
            ),
            upserted = UpsertedSection(
                classes = affectedClasses,
                methods = members.methods,
                fields = members.fields,
                callGraph = callGraph,
                inheritance = inheritance.edges,
                methodOverrides = inheritance.overrides,
                annotations = annotations,
            ),
            stats = DeltaStats(
                changedFileCount = changedFiles.totalChanges,
                deletedClassCount = deletedClasses.distinct().size,
                upsertedClassCount = affectedClasses.size,
                upsertedMethodCount = members.methods.size,
                upsertedCallEdgeCount = callGraph.size,
                exportDurationMs = durationMs
            )
        )

        // 6. Write delta JSON
        val outputDir = config.outputPath
        Files.createDirectories(outputDir)
        val fileName = "${project.name}-delta-${System.currentTimeMillis()}.json"
        val outputFile = outputDir.resolve(fileName)
        Files.writeString(outputFile, json.encodeToString(delta))

        // 7. Update state
        val newHash = DeltaTracker.getCurrentGitHash(basePath)
        state.state.lastExportTimestamp = System.currentTimeMillis()
        state.state.lastExportPath = outputFile.toString()
        if (newHash.isNotEmpty()) state.state.lastGitHash = newHash

        // Update file→classes mapping for affected files
        for (cls in affectedClasses) {
            val existing = state.state.fileHashes.getOrDefault(cls.filePath, "")
            val fqns = if (existing.isEmpty()) cls.fqn else "$existing,${cls.fqn}"
            state.state.fileHashes[cls.filePath] = fqns
        }
        for (deletedFile in changedFiles.deleted) {
            state.state.fileHashes.remove(deletedFile)
        }

        LOG.info("Delta export complete: $outputFile (${durationMs}ms)")
        return DeltaResult.Success(outputFile, delta.stats)
    }

    /**
     * Collect ClassData for classes found in specific files.
     */
    private fun collectClassesFromFiles(
        project: Project,
        filePaths: List<String>,
        basePath: String
    ): List<ClassData> {
        val result = mutableListOf<ClassData>()
        val psiManager = PsiManager.getInstance(project)
        val fs = com.intellij.openapi.vfs.LocalFileSystem.getInstance()

        for (relativePath in filePaths) {
            val absolutePath = "$basePath/$relativePath"
            val virtualFile = fs.findFileByPath(absolutePath) ?: continue
            val psiFile = psiManager.findFile(virtualFile) as? PsiJavaFile ?: continue

            for (psiClass in psiFile.classes) {
                val fqn = psiClass.qualifiedName ?: continue
                val filePath = relativePath

                result.add(ClassData(
                    fqn = fqn,
                    name = psiClass.name ?: "",
                    kind = getKind(psiClass),
                    modifiers = ClassCollector.extractModifiers(psiClass.modifierList),
                    genericParams = psiClass.typeParameters.map { it.name ?: "?" },
                    filePath = filePath,
                    lineStart = 0, // Skip line numbers for delta (saves time)
                    lineEnd = 0,
                    packageName = psiFile.packageName,
                    enclosingClass = psiClass.containingClass?.qualifiedName,
                    superClass = psiClass.superClass?.qualifiedName?.takeIf { it != "java.lang.Object" },
                    interfaces = psiClass.interfaces.mapNotNull { it.qualifiedName },
                    annotations = ClassCollector.extractAnnotations(psiClass.modifierList)
                ))

                // Also collect inner classes
                collectInnerClasses(psiClass, filePath, psiFile.packageName, result)
            }
        }

        return result
    }

    private fun collectInnerClasses(
        psiClass: PsiClass,
        filePath: String,
        packageName: String,
        result: MutableList<ClassData>
    ) {
        for (inner in psiClass.innerClasses) {
            val fqn = inner.qualifiedName ?: continue
            result.add(ClassData(
                fqn = fqn,
                name = inner.name ?: "",
                kind = getKind(inner),
                modifiers = ClassCollector.extractModifiers(inner.modifierList),
                filePath = filePath,
                lineStart = 0,
                packageName = packageName,
                enclosingClass = psiClass.qualifiedName,
                superClass = inner.superClass?.qualifiedName?.takeIf { it != "java.lang.Object" },
                interfaces = inner.interfaces.mapNotNull { it.qualifiedName },
                annotations = ClassCollector.extractAnnotations(inner.modifierList)
            ))
            collectInnerClasses(inner, filePath, packageName, result)
        }
    }

    private fun getKind(psiClass: PsiClass): String = when {
        psiClass.isInterface -> "INTERFACE"
        psiClass.isEnum -> "ENUM"
        psiClass.isAnnotationType -> "ANNOTATION_TYPE"
        psiClass.isRecord -> "RECORD"
        psiClass.hasModifierProperty("abstract") -> "ABSTRACT_CLASS"
        else -> "CLASS"
    }

    sealed class DeltaResult {
        data class Success(val path: Path, val stats: DeltaStats) : DeltaResult()
        data class Error(val message: String) : DeltaResult()
        data class NeedFullExport(val reason: String) : DeltaResult()
        data object NoChanges : DeltaResult()
    }
}
