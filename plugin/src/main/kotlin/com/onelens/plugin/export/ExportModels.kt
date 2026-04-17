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
    val enumConstants: List<EnumConstantData> = emptyList(),
    val diagnostics: List<DiagnosticEntry> = emptyList(),
    val stats: ExportStats = ExportStats(),
    /**
     * Adapters that contributed to this document. Default ["spring-boot"] for
     * back-compat with pre-adapter exports. Python importer inspects this to
     * decide which top-level sub-documents to process.
     */
    val adapters: List<String> = listOf("spring-boot"),
    /** Vue 3 adapter output. Present only if Vue3Adapter was active. */
    val vue3: Vue3Data? = null
)

/**
 * Vue 3 adapter payload. Mirrors the per-label split used on the FalkorDB side.
 * Empty lists (rather than nulls) so Python `data.get("vue3", {}).get("components", [])`
 * stays clean.
 */
@Serializable
data class Vue3Data(
    val components: List<ComponentData> = emptyList(),
    val composables: List<ComposableData> = emptyList(),
    val stores: List<StoreData> = emptyList(),
    val routes: List<RouteData> = emptyList(),
    val apiCalls: List<ApiCallData> = emptyList(),
    val usesStore: List<UsesStoreEdge> = emptyList(),
    val usesComposable: List<UsesComposableEdge> = emptyList(),
    val dispatches: List<DispatchesEdge> = emptyList(),
    val callsApi: List<CallsApiEdge> = emptyList()
)

@Serializable
data class ComponentData(
    val name: String,
    val filePath: String,         // canonical (symlink-resolved) relative path
    val scriptSetup: Boolean = true,
    val props: List<PropData> = emptyList(),
    val emits: List<String> = emptyList(),
    val exposes: List<String> = emptyList(),
    val lineStart: Int = 0,
    val lineEnd: Int = 0,
    val body: String? = null       // <script setup> content, truncated by Python miner
)

@Serializable
data class PropData(
    val name: String,
    val type: String = "",
    val required: Boolean = false,
    val defaultValue: String? = null
)

@Serializable
data class ComposableData(
    val name: String,
    val fqn: String,              // module-path::functionName
    val filePath: String,
    val lineStart: Int = 0,
    val lineEnd: Int = 0,
    val body: String? = null
)

@Serializable
data class StoreData(
    val id: String,               // first arg of defineStore(...)
    val name: String,             // `useXStore` export name
    val filePath: String,
    val style: String = "options", // "options" | "setup"
    val state: List<String> = emptyList(),
    val getters: List<String> = emptyList(),
    val actions: List<String> = emptyList(),
    val lineStart: Int = 0,
    val body: String? = null
)

@Serializable
data class RouteData(
    val name: String,             // resolved route name literal
    val path: String,             // route pattern with placeholders
    val componentRef: String? = null, // lazy import target (relative path)
    val meta: Map<String, String> = emptyMap(),
    val parentName: String? = null,
    val filePath: String,
    val lineStart: Int = 0
)

@Serializable
data class ApiCallData(
    val method: String,           // GET/POST/PATCH/DELETE
    val path: String,             // literal or template
    val parametric: Boolean = false,
    val binding: String? = null,  // source of parametric binding if known
    val callerFqn: String,        // fqn of enclosing function/component
    val filePath: String,
    val lineStart: Int = 0
)

@Serializable
data class UsesStoreEdge(
    val callerFqn: String,        // component or composable fqn
    val storeId: String,
    val indirect: Boolean = false,
    val via: String? = null       // wrapper function name when indirect
)

@Serializable
data class UsesComposableEdge(
    val callerFqn: String,
    val composableFqn: String
)

@Serializable
data class DispatchesEdge(
    val routeName: String,
    val componentRef: String      // relative path of component
)

@Serializable
data class CallsApiEdge(
    val callerFqn: String,
    val apiCallFqn: String        // deterministic: "<method>:<path>:<callerFqn>"
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

/**
 * A single enum constant with its constructor arguments resolved to serializable
 * shapes. `args` is a JSON array (stringified) preserving order + nesting for
 * human inspection; `argList` is a flat list of string tokens suitable for
 * FalkorDB array predicates (`WHERE 'REQUEST' IN ec.argList`). Unresolvable
 * fragments render as `<dynamic>`.
 */
@Serializable
data class EnumConstantData(
    val fqn: String,              // com.example.MyEnum#STATUS
    val name: String,             // STATUS
    val ordinal: Int,             // declaration index among enum constants
    val enumFqn: String,          // owning enum class FQN
    val args: String = "[]",      // JSON-serialized resolved args
    val argList: List<String> = emptyList(), // flattened string tokens
    val argTypes: List<String> = emptyList(),
    val filePath: String = "",
    val lineStart: Int = 0
)

/**
 * Annotation usage with resolved attribute values.
 *
 * `params` (legacy) = raw text of each attribute, kept for back-compat with the
 * pre-1.1 importer. `attributes` = JSON-serialized resolved values via
 * [com.onelens.plugin.export.collectors.ExpressionResolver] — nested arrays,
 * class literals (as FQN), enum refs (as name). New queries should read
 * `attributes`; callers that haven't migrated fall through to `params`.
 */
@Serializable
data class AnnotationUsage(
    val targetFqn: String,
    val targetKind: String,
    val annotationFqn: String,
    val params: Map<String, String> = emptyMap(),
    val attributes: String = "{}"
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
    val enumConstantCount: Int = 0,
    val diagnosticCount: Int = 0,
    val exportDurationMs: Long = 0
)
