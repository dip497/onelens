package com.onelens.plugin.export

import kotlinx.serialization.Serializable

@Serializable
data class ExportDocument(
    val version: String,
    val exportType: String,
    val timestamp: String,
    val project: ProjectInfo,
    val classes: List<ClassData> = emptyList(),
    val methods: List<MethodData> = emptyList(),
    val fields: List<FieldData> = emptyList(),
    val callGraph: List<CallEdge> = emptyList(),
    val inheritance: List<InheritanceEdge> = emptyList(),
    val methodOverrides: List<OverrideEdge> = emptyList(),
    val spring: SpringData? = null,
    val modules: List<ModuleData> = emptyList(),
    val annotations: List<AnnotationUsage> = emptyList(),
    val diagnostics: List<DiagnosticEntry> = emptyList(),
    val stats: ExportStats = ExportStats()
)

@Serializable
data class ProjectInfo(
    val name: String,
    val basePath: String,
    val jdkVersion: String = ""
)

@Serializable
data class ClassData(
    val fqn: String,
    val name: String,
    val kind: String,
    val modifiers: List<String> = emptyList(),
    val genericParams: List<String> = emptyList(),
    val filePath: String,
    val lineStart: Int,
    val lineEnd: Int = 0,
    val packageName: String = "",
    val enclosingClass: String? = null,
    val superClass: String? = null,
    val interfaces: List<String> = emptyList(),
    val annotations: List<AnnotationData> = emptyList()
)

@Serializable
data class MethodData(
    val fqn: String,
    val name: String,
    val classFqn: String,
    val returnType: String = "",
    val parameters: List<ParameterData> = emptyList(),
    val modifiers: List<String> = emptyList(),
    val isConstructor: Boolean = false,
    val isVarArgs: Boolean = false,
    val throwsTypes: List<String> = emptyList(),
    val annotations: List<AnnotationData> = emptyList(),
    val filePath: String = "",
    val lineStart: Int = 0,
    val lineEnd: Int = 0,
    val body: String? = null,
    val javadoc: String? = null
)

@Serializable
data class ParameterData(
    val name: String,
    val type: String,
    val annotations: List<String> = emptyList()
)

@Serializable
data class FieldData(
    val fqn: String,
    val name: String,
    val classFqn: String,
    val type: String,
    val modifiers: List<String> = emptyList(),
    val annotations: List<AnnotationData> = emptyList(),
    val filePath: String = "",
    val lineStart: Int = 0
)

@Serializable
data class AnnotationData(
    val fqn: String,
    val params: Map<String, String> = emptyMap()
)

@Serializable
data class CallEdge(
    val callerFqn: String,
    val calleeFqn: String,
    val line: Int = 0,
    val filePath: String = "",
    val receiverType: String? = null  // Declared type of the object being called on (e.g., "Child" even if method resolves to "Parent")
)

@Serializable
data class InheritanceEdge(
    val childFqn: String,
    val parentFqn: String,
    val relationType: String  // EXTENDS or IMPLEMENTS
)

@Serializable
data class OverrideEdge(
    val methodFqn: String,
    val overridesFqn: String
)

@Serializable
data class SpringData(
    val beans: List<SpringBean> = emptyList(),
    val endpoints: List<SpringEndpoint> = emptyList(),
    val injections: List<SpringInjection> = emptyList()
)

@Serializable
data class SpringBean(
    val name: String,
    val classFqn: String,
    val scope: String = "singleton",
    val profile: String? = null,
    val dependencies: List<String> = emptyList(),
    val type: String = ""
)

@Serializable
data class SpringEndpoint(
    val path: String,
    val httpMethod: String,
    val controllerFqn: String,
    val handlerMethodFqn: String,
    val produces: List<String> = emptyList(),
    val consumes: List<String> = emptyList()
)

@Serializable
data class SpringInjection(
    val targetClassFqn: String,
    val targetFieldOrParam: String,
    val injectedBeanName: String = "",
    val injectedClassFqn: String,
    val injectionType: String  // CONSTRUCTOR, FIELD, SETTER
)

@Serializable
data class ModuleData(
    val name: String,
    val type: String = "MAVEN",
    val sourceRoots: List<String> = emptyList(),
    val resourceRoots: List<String> = emptyList(),
    val testSourceRoots: List<String> = emptyList(),
    val dependencies: List<ModuleDependency> = emptyList(),
    val coordinates: ModuleCoordinates? = null
)

@Serializable
data class ModuleDependency(
    val moduleName: String,
    val scope: String = "COMPILE"
)

@Serializable
data class ModuleCoordinates(
    val groupId: String = "",
    val artifactId: String = "",
    val version: String = ""
)

@Serializable
data class AnnotationUsage(
    val targetFqn: String,
    val targetKind: String,
    val annotationFqn: String,
    val params: Map<String, String> = emptyMap()
)

@Serializable
data class DiagnosticEntry(
    val elementFqn: String,
    val elementKind: String,
    val type: String,
    val message: String
)

@Serializable
data class ExportStats(
    val classCount: Int = 0,
    val methodCount: Int = 0,
    val fieldCount: Int = 0,
    val callEdgeCount: Int = 0,
    val inheritanceEdgeCount: Int = 0,
    val overrideCount: Int = 0,
    val springBeanCount: Int = 0,
    val endpointCount: Int = 0,
    val moduleCount: Int = 0,
    val annotationUsageCount: Int = 0,
    val diagnosticCount: Int = 0,
    val exportDurationMs: Long = 0
)
