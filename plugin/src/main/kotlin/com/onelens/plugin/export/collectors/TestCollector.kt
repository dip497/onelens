package com.onelens.plugin.export.collectors

import com.intellij.codeInsight.AnnotationUtil
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiAnnotation
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiClassObjectAccessExpression
import com.intellij.psi.PsiClassType
import com.intellij.psi.PsiLiteralExpression
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiModifierListOwner
import com.intellij.psi.search.searches.AnnotatedElementsSearch
import com.onelens.plugin.export.TestBeanBinding
import com.onelens.plugin.export.TestCaseData
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Detects test methods (JUnit 5 / JUnit 4 / TestNG / Cucumber) and classifies
 * them using `AnnotationUtil.CHECK_HIERARCHY` — the same resolution Spring
 * itself uses. Handles three inheritance shapes in one call:
 *
 *   - direct:           `@SpringBootTest class MyTest`
 *   - super-chain:      `class MyTest extends BaseTest` (BaseTest→CommonTest→@SpringBootTest)
 *   - meta-annotation:  `@MyIntegrationTest class MyTest` (composed from @SpringBootTest)
 *
 * Framework detection: walks each framework spec's test-annotation list via
 * `AnnotatedElementsSearch` (index-backed, no manual scan). A single method can
 * match multiple frameworks (rare); first match wins, preserving deterministic
 * output.
 *
 * Also picks up `@MockBean` / `@SpyBean` fields → bean bindings for
 * `:TESTS-[:MOCKS]->:SpringBean` and `:TESTS-[:SPIES]->:SpringBean` edges.
 */
object TestCollector {

    private val LOG = logger<TestCollector>()

    // --- Test framework specs (embedded; pluggable via workspace.yaml later) ---
    private data class FrameworkSpec(
        val id: String,
        val testAnnotations: List<String>,
        val defaultKind: String,   // overridden by Spring detection when applicable
    )

    private val FRAMEWORKS = listOf(
        FrameworkSpec(
            id = "junit5",
            testAnnotations = listOf(
                "org.junit.jupiter.api.Test",
                "org.junit.jupiter.params.ParameterizedTest",
                "org.junit.jupiter.api.RepeatedTest",
                "org.junit.jupiter.api.TestFactory",
                "org.junit.jupiter.api.TestTemplate",
            ),
            defaultKind = "unit",
        ),
        FrameworkSpec(
            id = "junit4",
            testAnnotations = listOf("org.junit.Test"),
            defaultKind = "unit",
        ),
        FrameworkSpec(
            id = "testng",
            testAnnotations = listOf("org.testng.annotations.Test"),
            defaultKind = "unit",
        ),
        FrameworkSpec(
            id = "cucumber",
            testAnnotations = listOf(
                "io.cucumber.java.en.Given",
                "io.cucumber.java.en.When",
                "io.cucumber.java.en.Then",
                "io.cucumber.java.en.And",
            ),
            defaultKind = "bdd",
        ),
    )

    // Spring annotations → kinds. Ordered: more specific (slices) first.
    private val SPRING_KIND_MAP = linkedMapOf(
        "org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest"       to "slice-jpa",
        "org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest"    to "slice-web",
        "org.springframework.boot.test.autoconfigure.json.JsonTest"             to "slice-json",
        "org.springframework.boot.test.autoconfigure.web.client.RestClientTest" to "slice-rest-client",
        "org.springframework.boot.test.context.SpringBootTest"                  to "integration",
    )

    private const val DISABLED_J5 = "org.junit.jupiter.api.Disabled"
    private const val DISABLED_J4 = "org.junit.Ignore"
    private const val TAG_ANNO = "org.junit.jupiter.api.Tag"
    private const val DISPLAY_NAME = "org.junit.jupiter.api.DisplayName"
    private const val EXTEND_WITH = "org.junit.jupiter.api.extension.ExtendWith"
    private const val MOCKITO_EXTENSION = "org.mockito.junit.jupiter.MockitoExtension"
    private const val TESTCONTAINERS_CLASS = "org.testcontainers.junit.jupiter.Testcontainers"
    private const val TESTCONTAINERS_FIELD = "org.testcontainers.junit.jupiter.Container"
    private const val ACTIVE_PROFILES = "org.springframework.test.context.ActiveProfiles"
    private const val CONTEXT_CONFIGURATION = "org.springframework.test.context.ContextConfiguration"
    private const val MOCK_BEAN = "org.springframework.boot.test.mock.mockito.MockBean"
    private const val SPY_BEAN = "org.springframework.boot.test.mock.mockito.SpyBean"

    /** Collector output. */
    data class Result(
        val tests: List<TestCaseData>,
        val mockBeans: List<TestBeanBinding>,
        val spyBeans: List<TestBeanBinding>,
    )

    fun collect(project: Project, workspace: Workspace): Result {
        if (ReadAction.compute<Boolean, Throwable> { DumbService.isDumb(project) }) {
            LOG.info("TestCollector skipped — dumb mode")
            return Result(emptyList(), emptyList(), emptyList())
        }

        val tests = LinkedHashMap<String, TestCaseData>()  // methodFqn → data (first framework wins)

        // Fragment the scan so each (framework, annotation) pair is its own
        // NonBlockingReadAction. Previously the whole sweep (including the
        // inner MockBean / SpyBean passes) was wrapped in a single
        // ReadAction.compute that held the read lock for the entire test
        // index walk — on a large repo (7k+ test methods resolved through
        // AnnotatedElementsSearch + stub index) this blocked EDT
        // write-intent requests and surfaced as a SuvorovProgress freeze.
        // Same fix shape as SpringModelCollector (see LESSONS-LEARNED #1).
        for (fw in FRAMEWORKS) {
            for (annoFqn in fw.testAnnotations) {
                ProgressManager.checkCanceled()
                val partial = try {
                    com.intellij.openapi.application.ReadAction
                        .nonBlocking<Map<String, TestCaseData>> {
                            val scope = workspace.scope(project)
                            val facade = JavaPsiFacade.getInstance(project)
                            val annoClass = facade.findClass(annoFqn, com.intellij.psi.search.GlobalSearchScope.allScope(project))
                                ?: return@nonBlocking emptyMap()
                            val local = LinkedHashMap<String, TestCaseData>()
                            AnnotatedElementsSearch.searchPsiMethods(annoClass, scope).forEach { method ->
                                ProgressManager.checkCanceled()
                                val methodFqn = fqnOf(method) ?: return@forEach
                                if (methodFqn in local) return@forEach
                                val data = buildTestCaseData(method, fw) ?: return@forEach
                                local[methodFqn] = data
                            }
                            local
                        }
                        .executeSynchronously()
                } catch (e: Throwable) {
                    LOG.debug("TestCollector[$annoFqn] failed: ${e.message}")
                    emptyMap()
                }
                // First-framework-wins: only add methodFqns not already seen.
                for ((fqn, data) in partial) tests.putIfAbsent(fqn, data)
            }
        }

        // @MockBean / @SpyBean passes — each gets its own non-blocking
        // read action so the test class set is captured once but the
        // field scan can yield to EDT if needed.
        val mocks = mutableListOf<TestBeanBinding>()
        val spies = mutableListOf<TestBeanBinding>()
        val testClassFqns = tests.values.map { it.testClass }.toSet()
        if (testClassFqns.isNotEmpty()) {
            try {
                com.intellij.openapi.application.ReadAction.nonBlocking<Unit> {
                    collectBeanBindings(project, workspace.scope(project), testClassFqns, MOCK_BEAN, mocks)
                }.executeSynchronously()
            } catch (e: Throwable) {
                LOG.debug("TestCollector[@MockBean] failed: ${e.message}")
            }
            try {
                com.intellij.openapi.application.ReadAction.nonBlocking<Unit> {
                    collectBeanBindings(project, workspace.scope(project), testClassFqns, SPY_BEAN, spies)
                }.executeSynchronously()
            } catch (e: Throwable) {
                LOG.debug("TestCollector[@SpyBean] failed: ${e.message}")
            }
        }

        LOG.info(
            "TestCollector: ${tests.size} tests, ${mocks.size} @MockBean, ${spies.size} @SpyBean"
        )
        return Result(tests.values.toList(), mocks, spies)
    }

    // --- per-method classification ------------------------------------------

    private fun buildTestCaseData(method: PsiMethod, fw: FrameworkSpec): TestCaseData? {
        val psiClass = method.containingClass ?: return null
        val methodFqn = fqnOf(method) ?: return null
        val classFqn = psiClass.qualifiedName ?: return null

        // Resolution preference: slice > integration > mocked-unit > framework default.
        val kind = when {
            fw.id == "cucumber" -> "bdd"
            else -> {
                val springKind = detectSpringKind(psiClass)
                when {
                    springKind != null -> springKind
                    isAnnotatedInChain(psiClass, EXTEND_WITH) && hasMockitoExtension(psiClass) -> "unit-mocked"
                    fw.defaultKind == "unit" -> "unit"
                    else -> fw.defaultKind
                }
            }
        }

        val tags = extractTags(method, psiClass)
        val disabled = isAnnotatedInChain(method, DISABLED_J5) ||
            isAnnotatedInChain(method, DISABLED_J4) ||
            isAnnotatedInChain(psiClass, DISABLED_J5) ||
            isAnnotatedInChain(psiClass, DISABLED_J4)
        val activeProfiles = extractActiveProfiles(psiClass)
        val springBootApp = extractSpringBootApp(psiClass)
        val usesMockito = hasMockitoExtension(psiClass)
        val usesTestcontainers = isAnnotatedInChain(psiClass, TESTCONTAINERS_CLASS) ||
            psiClass.fields.any { fld -> fld.annotations.any { it.qualifiedName == TESTCONTAINERS_FIELD } }
        val displayName = literalAttr(findAnnotation(method, DISPLAY_NAME), "value")
            ?: literalAttr(findAnnotation(psiClass, DISPLAY_NAME), "value")

        return TestCaseData(
            methodFqn = methodFqn,
            testClass = classFqn,
            testKind = kind,
            testFramework = fw.id,
            tags = tags,
            disabled = disabled,
            activeProfiles = activeProfiles,
            springBootApp = springBootApp,
            usesMockito = usesMockito,
            usesTestcontainers = usesTestcontainers,
            displayName = displayName,
        )
    }

    private fun detectSpringKind(psiClass: PsiClass): String? {
        for ((annoFqn, kind) in SPRING_KIND_MAP) {
            if (isAnnotatedInChain(psiClass, annoFqn)) return kind
        }
        // Any other @AutoConfigure* annotation → slice-other
        var cur: PsiClass? = psiClass
        val seen = HashSet<String>()
        while (cur != null && seen.add(cur.qualifiedName ?: return null)) {
            for (a in cur.annotations) {
                val q = a.qualifiedName ?: continue
                if (q.startsWith("org.springframework.boot.test.autoconfigure.") &&
                    !SPRING_KIND_MAP.containsKey(q)) {
                    return "slice-other"
                }
            }
            cur = cur.superClass
        }
        return null
    }

    // --- helpers ------------------------------------------------------------

    /**
     * Delegates to IntelliJ's `AnnotationUtil.CHECK_HIERARCHY` which mirrors
     * Spring's own resolution: walks class hierarchy + meta-annotations.
     * This is THE primitive for the whole collector — zero custom chain-walk.
     */
    private fun isAnnotatedInChain(element: PsiModifierListOwner, fqn: String): Boolean =
        AnnotationUtil.isAnnotated(element, fqn, AnnotationUtil.CHECK_HIERARCHY)

    /**
     * Find a single annotation anywhere in the hierarchy — used when we need
     * the annotation's attributes, not just a presence check.
     */
    private fun findAnnotation(element: PsiModifierListOwner, fqn: String): PsiAnnotation? =
        AnnotationUtil.findAnnotationInHierarchy(element, setOf(fqn))

    private fun hasMockitoExtension(psiClass: PsiClass): Boolean {
        // @ExtendWith(MockitoExtension.class) — need to look at the class literal.
        var cur: PsiClass? = psiClass
        val seen = HashSet<String>()
        while (cur != null && seen.add(cur.qualifiedName ?: return false)) {
            for (a in cur.annotations) {
                if (a.qualifiedName != EXTEND_WITH) continue
                val v = a.findAttributeValue("value") ?: continue
                val refs = when (v) {
                    is PsiClassObjectAccessExpression -> listOf(v)
                    is com.intellij.psi.PsiArrayInitializerMemberValue ->
                        v.initializers.filterIsInstance<PsiClassObjectAccessExpression>()
                    else -> emptyList()
                }
                for (ref in refs) {
                    val typeFqn = (ref.operand.type as? PsiClassType)?.resolve()?.qualifiedName
                    if (typeFqn == MOCKITO_EXTENSION) return true
                }
            }
            cur = cur.superClass
        }
        return false
    }

    private fun extractTags(method: PsiMethod, psiClass: PsiClass): List<String> {
        val out = LinkedHashSet<String>()
        for (target in listOf(method, psiClass)) {
            for (a in target.annotations) {
                if (a.qualifiedName != TAG_ANNO) continue
                literalAttr(a, "value")?.let { out += it }
            }
            // Inherited @Tag through hierarchy — use findAnnotationInHierarchy.
        }
        // Walk superclass hierarchy for class-level @Tag.
        var cur: PsiClass? = psiClass.superClass
        val seen = HashSet<String>()
        while (cur != null) {
            val qn = cur.qualifiedName
            if (qn == null || !seen.add(qn)) break
            for (a in cur.annotations) {
                if (a.qualifiedName == TAG_ANNO) literalAttr(a, "value")?.let { out += it }
            }
            cur = cur.superClass
        }
        return out.toList()
    }

    private fun extractActiveProfiles(psiClass: PsiClass): List<String> {
        val a = findAnnotation(psiClass, ACTIVE_PROFILES) ?: return emptyList()
        val v = a.findAttributeValue("value") ?: a.findAttributeValue("profiles") ?: return emptyList()
        return when (v) {
            is PsiLiteralExpression -> listOfNotNull(v.value?.toString())
            is com.intellij.psi.PsiArrayInitializerMemberValue -> v.initializers.mapNotNull {
                (it as? PsiLiteralExpression)?.value?.toString()
                    ?: it.text.removeSurrounding("\"").takeIf { s -> s.isNotBlank() }
            }
            else -> listOfNotNull(v.text.removeSurrounding("\"").takeIf { it.isNotBlank() })
        }
    }

    private fun extractSpringBootApp(psiClass: PsiClass): String? {
        val a = findAnnotation(psiClass, CONTEXT_CONFIGURATION) ?: return null
        val v = a.findAttributeValue("classes") ?: return null
        val refs = when (v) {
            is PsiClassObjectAccessExpression -> listOf(v)
            is com.intellij.psi.PsiArrayInitializerMemberValue ->
                v.initializers.filterIsInstance<PsiClassObjectAccessExpression>()
            else -> return null
        }
        for (ref in refs) {
            val fqn = (ref.operand.type as? PsiClassType)?.resolve()?.qualifiedName
            if (!fqn.isNullOrBlank()) return fqn
        }
        return null
    }

    private fun literalAttr(anno: PsiAnnotation?, attr: String): String? {
        val v = anno?.findAttributeValue(attr) ?: return null
        val lit = (v as? PsiLiteralExpression)?.value?.toString()
        if (lit != null) return lit
        return v.text?.removeSurrounding("\"")?.takeIf { it.isNotBlank() }
    }

    private fun fqnOf(method: PsiMethod): String? {
        val cls = method.containingClass?.qualifiedName ?: return null
        val params = method.parameterList.parameters.joinToString(",") {
            try { it.type.canonicalText } catch (_: Exception) { "?" }
        }
        return "$cls#${method.name}($params)"
    }

    private fun collectBeanBindings(
        project: Project,
        scope: com.intellij.psi.search.GlobalSearchScope,
        testClassFqns: Set<String>,
        annoFqn: String,
        out: MutableList<TestBeanBinding>,
    ) {
        val facade = JavaPsiFacade.getInstance(project)
        val annoClass = facade.findClass(annoFqn, com.intellij.psi.search.GlobalSearchScope.allScope(project))
            ?: return
        AnnotatedElementsSearch.searchPsiFields(annoClass, scope).forEach { field ->
            val cls = field.containingClass ?: return@forEach
            val classFqn = cls.qualifiedName ?: return@forEach
            if (classFqn !in testClassFqns) return@forEach
            val beanClassFqn = (field.type as? PsiClassType)?.resolve()?.qualifiedName ?: return@forEach
            out += TestBeanBinding(
                testClassFqn = classFqn,
                beanClassFqn = beanClassFqn,
                fieldName = field.name,
            )
        }
    }
}
