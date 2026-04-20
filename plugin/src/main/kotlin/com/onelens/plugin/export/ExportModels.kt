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
    val vue3: Vue3Data? = null,
    /** JPA / Spring Data payload (Phase C3c). Null when no @Entity types found. */
    val jpa: JpaData? = null,
    /**
     * Tests payload (Phase Q.code). List of test methods with classification
     * (unit / integration / slice-*). Empty when no JUnit/TestNG annotations
     * present. Test data gets dual-labelled on the Method node (:Method:TestCase)
     * loader-side to avoid a parallel node hierarchy.
     */
    val tests: List<TestCaseData> = emptyList(),
    /** `(:TestCase)-[:MOCKS]->(:SpringBean)` pairs from @MockBean fields. */
    val mockBeans: List<TestBeanBinding> = emptyList(),
    /** `(:TestCase)-[:SPIES]->(:SpringBean)` pairs from @SpyBean fields. */
    val spyBeans: List<TestBeanBinding> = emptyList(),
    /**
     * Phase C2 — adapter-agnostic App + Package primitives. Apps group classes /
     * components into logical deployables (one per `@SpringBootApplication` for
     * Spring Boot, one per Vue root for Vue3). Packages mirror the Java package
     * hierarchy and, for Vue3, the top-level `src/` directories.
     */
    val apps: List<AppData> = emptyList(),
    val packages: List<PackageData> = emptyList(),
    /**
     * Workspace header (Phase C). Absent on pre-workspace exports — Python side
     * must treat null as "implicit single-root workspace derived from project".
     */
    val workspace: WorkspaceInfo? = null
)

/**
 * Workspace metadata for multi-root / multi-repo exports. Python loader uses
 * [graphId] as the target graph name, [roots] for log output, and
 * [duplicateFqnPolicy] to decide between MERGE (default), warn-on-duplicate,
 * or fail-fast CREATE semantics.
 */
/**
 * App = one deployable / bounded context. Springboot adapter emits one per
 * `@SpringBootApplication` class with its resolved `scanBasePackages`. Vue3
 * adapter emits one per detected Vue root (typically one per workspace root
 * with `package.json` + a `vue` dep).
 *
 * `id` is the Cypher-side primary key. Loader uses it for `CONTAINS` / `PART_OF`
 * edges. Format: `app:<type>:<stable-suffix>` — suffix is the root class FQN
 * for Spring, the root path for Vue3.
 */
@Serializable
data class AppData(
    val id: String,
    val name: String,
    /** `spring-boot` | `vue3`. */
    val type: String,
    /** Spring: fully-qualified class name of the `@SpringBootApplication`. Blank for Vue3. */
    val rootFqn: String = "",
    /** Vue3: absolute or workspace-relative path of the Vue project root. Blank for Spring. */
    val rootPath: String = "",
    /** Scan packages (Spring) or `src/` subdir names (Vue3) used to bind members. */
    val scanPackages: List<String> = emptyList(),
    /** Modules this app spans — informational only; loader uses scanPackages. */
    val moduleNames: List<String> = emptyList(),
)

/**
 * Package = Java package (Spring) or `src/<segment>` folder (Vue3). The hierarchy
 * is encoded via `parentId` — the loader materialises `PARENT_OF` edges from that.
 * `id` == fully-qualified package name for Spring (`com.acme.service`), and
 * `vue:<root>:<segment>` for Vue3 so the two namespaces never collide.
 */
@Serializable
data class PackageData(
    val id: String,
    val name: String,
    val parentId: String? = null,
    /** Owning app id — blank when a package spans multiple apps (rare; last writer wins). */
    val appId: String = "",
)

/**
 * A single test method. Dual-labelled `:Method:TestCase` loader-side —
 * [methodFqn] IS the Method node's primary key.
 *
 * `testKind` vocabulary is fixed (10 values) — keeps Cypher portable across
 * projects. PSI resolution uses `AnnotationUtil.CHECK_HIERARCHY`, which honours
 * both inheritance (e.g. a reference project `CommonTest`→`MockHelper`→`BaseTest`) AND
 * meta-annotations (e.g. `@MyIntegrationTest` composed from `@SpringBootTest`).
 */
@Serializable
data class TestCaseData(
    val methodFqn: String,
    val testClass: String,
    /**
     * unit | unit-mocked | integration | slice-jpa | slice-web | slice-json |
     * slice-rest-client | slice-other | bdd | unknown
     */
    val testKind: String,
    /** "junit5" | "junit4" | "testng" | "cucumber" | "unknown" */
    val testFramework: String,
    /** @Tag values (JUnit 5). Empty for other frameworks. */
    val tags: List<String> = emptyList(),
    /** @Disabled / @Ignore — anywhere in the chain. */
    val disabled: Boolean = false,
    /** @ActiveProfiles — resolved via chain walk. */
    val activeProfiles: List<String> = emptyList(),
    /** @ContextConfiguration(classes = Foo.class) — first root found. */
    val springBootApp: String? = null,
    /** Any @ExtendWith(MockitoExtension) in chain. */
    val usesMockito: Boolean = false,
    /** @Testcontainers at class level, or any @Container field. */
    val usesTestcontainers: Boolean = false,
    /** @DisplayName, if present. */
    val displayName: String? = null,
)

/**
 * `@MockBean` / `@SpyBean` field binding on a test class.
 * Becomes a `:MOCKS` / `:SPIES` edge in the graph.
 */
@Serializable
data class TestBeanBinding(
    val testClassFqn: String,     // source of the edge
    val beanClassFqn: String,     // target: the mocked/spied class
    val fieldName: String,
)

@Serializable
data class WorkspaceInfo(
    val name: String,
    val graphId: String,
    val roots: List<String> = emptyList(),
    val duplicateFqnPolicy: String = "merge",
    val configFile: String? = null
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
    val callsApi: List<CallsApiEdge> = emptyList(),
    // Phase B2 — business-logic layer. Closes the gap where plain JS helpers
    // (`src/data/*.js`, `*-api.js`, module-local `helpers/*.js`) were invisible.
    val modules: List<JsModuleData> = emptyList(),
    val functions: List<JsFunctionData> = emptyList(),
    val imports: List<ImportsEdge> = emptyList()
)

/**
 * Every `.js` / `.ts` / `.vue` source file that participates in the import
 * graph. Present for files already modelled as Component / Composable / Store
 * too, so the import target resolves to a single node kind. Pure container —
 * the interesting stuff (Functions, imports) hangs off this.
 */
@Serializable
data class JsModuleData(
    val filePath: String,              // project-relative, canonicalized
    val isBarrel: Boolean = false,     // heuristic: all statements are re-exports
    val fileKind: String = "js"        // "js" | "ts" | "vue"
)

/**
 * Top-level function / const-arrow / const-function declaration in a JS module.
 * Mirrors tree-sitter's `@definition.function` set: named function declarations,
 * `const x = () => …`, `export default function`, `export default () => …`.
 * Methods inside classes are NOT emitted here — classes are framework-specific.
 */
@Serializable
data class JsFunctionData(
    val fqn: String,                   // "<filePath>::<name>" — matches callerFqn elsewhere
    val name: String,
    val filePath: String,
    val exported: Boolean = false,
    val isDefault: Boolean = false,    // `export default function …`
    val isAsync: Boolean = false,
    val lineStart: Int = 0,
    val lineEnd: Int = 0,
    val body: String? = null
)

/**
 * ES6 `import … from '…'` resolved via IntelliJ JS PSI. One edge per imported
 * binding. For aliased imports (`import { X as Y }`) the target node is the
 * original, not the alias specifier (2-hop resolve inside the collector).
 *
 * `sourceModule` points at the importer's module filePath; `targetModule` is
 * the absolute resolved file path of the source. `targetFqn` points at a
 * specific `JsFunctionData.fqn` when the binding resolves to a named export;
 * null when the resolve fell short (barrel edge-case, external, or missed).
 */
@Serializable
data class ImportsEdge(
    val sourceModule: String,          // filePath of the importing module
    val targetModule: String,          // filePath of the imported module
    val importedName: String,          // "default" / "*" / named binding
    val localAlias: String? = null,    // non-null when `{ X as Y }`
    val isDefault: Boolean = false,
    val isNamespace: Boolean = false,  // `import * as ns from …`
    val targetFqn: String? = null,     // `<targetModule>::<resolved-name>` when resolved
    val unresolved: Boolean = false,
    val lineStart: Int = 0
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
    val injections: List<SpringInjection> = emptyList(),
    /**
     * Auto-configuration chains discovered via META-INF/spring.factories and
     * META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
     * resource scans. One entry per declared class. Phase C3b.
     */
    val autoConfigs: List<SpringAutoConfig> = emptyList(),
)

@Serializable
data class SpringAutoConfig(
    val classFqn: String,
    /** "spring.factories" | "autoconfig.imports" */
    val source: String,
    /** Path of the originating resource file (library jar entries stay absolute). */
    val sourceFile: String = "",
)

@Serializable
data class SpringBean(
    val name: String,
    val classFqn: String,
    val scope: String = "singleton",
    val profile: String? = null,
    val dependencies: List<String> = emptyList(),
    val type: String = "",
    // C3a additions — populated by SpringModelCollector when com.intellij.spring is present.
    // Older annotation-only path leaves these at defaults so JSON stays stable.
    val primary: Boolean = false,
    val source: String = "annotation",           // annotation | java-config | xml | jam
    val factoryMethodFqn: String? = null,        // set when bean is defined via @Bean method
    val activeProfiles: List<String> = emptyList(),
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
    val injectionType: String,  // CONSTRUCTOR, FIELD, SETTER
    /** @Qualifier("…") value when present on the target field / parameter. Phase C3b. */
    val qualifier: String? = null,
)

/**
 * JPA / Spring Data payload. PSI-native — does not require the IntelliJ JPA plugin.
 * Detects @Entity / @Table / @Id / @Column via annotations and repositories via
 * `extends JpaRepository / CrudRepository / PagingAndSortingRepository` inheritance.
 *
 * Phase C3c. Maps straight onto FalkorDB `JpaEntity` + `JpaRepository` nodes with
 * `HAS_COLUMN`, `QUERIES`, and `REPOSITORY_FOR` edges.
 */
@Serializable
data class JpaData(
    val entities: List<JpaEntity> = emptyList(),
    val repositories: List<JpaRepository> = emptyList(),
)

@Serializable
data class JpaEntity(
    val classFqn: String,
    val tableName: String,
    val schema: String = "",
    val idFieldFqns: List<String> = emptyList(),
    val columns: List<JpaColumn> = emptyList(),
)

@Serializable
data class JpaColumn(
    val fieldFqn: String,
    val columnName: String,
    val nullable: Boolean = true,
    val unique: Boolean = false,
    val relation: String? = null,  // OneToOne | OneToMany | ManyToOne | ManyToMany | null
    val targetEntityFqn: String? = null,
)

@Serializable
data class JpaRepository(
    val classFqn: String,
    /** The entity type the repository parametrises — i.e. `User` in `JpaRepository<User,Long>`. */
    val entityFqn: String,
    /** Derived-query method names (`findByEmail`, `countByStatus`, ...). */
    val derivedQueries: List<JpaRepositoryQuery> = emptyList(),
)

@Serializable
data class JpaRepositoryQuery(
    val methodFqn: String,
    val methodName: String,
    /** "derived" | "named" | "jpql" — derived-only for C3c; @Query support later. */
    val kind: String = "derived",
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
