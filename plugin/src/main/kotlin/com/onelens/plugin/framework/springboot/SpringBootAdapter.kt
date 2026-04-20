package com.onelens.plugin.framework.springboot

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.AnnotationUsage
import com.onelens.plugin.export.CallEdge
import com.onelens.plugin.export.ClassData
import com.onelens.plugin.export.DiagnosticEntry
import com.onelens.plugin.export.EnumConstantData
import com.onelens.plugin.export.FieldData
import com.onelens.plugin.export.InheritanceEdge
import com.onelens.plugin.export.MethodData
import com.onelens.plugin.export.ModuleData
import com.onelens.plugin.export.OverrideEdge
import com.onelens.plugin.export.SpringData
import com.onelens.plugin.export.AppData
import com.onelens.plugin.export.JpaData
import com.onelens.plugin.export.PackageData
import com.onelens.plugin.export.TestBeanBinding
import com.onelens.plugin.export.TestCaseData
import com.onelens.plugin.export.collectors.AnnotationCollector
import com.onelens.plugin.export.collectors.AppCollector
import com.onelens.plugin.export.collectors.AutoConfigCollector
import com.onelens.plugin.export.collectors.TestCollector
import com.onelens.plugin.export.collectors.CallGraphCollector
import com.onelens.plugin.export.collectors.ClassCollector
import com.onelens.plugin.export.collectors.DiagnosticsCollector
import com.onelens.plugin.export.collectors.InheritanceCollector
import com.onelens.plugin.export.collectors.JpaCollector
import com.onelens.plugin.export.collectors.MemberCollector
import com.onelens.plugin.export.collectors.ModuleCollector
import com.onelens.plugin.export.collectors.PackageCollector
import com.onelens.plugin.export.collectors.SpringCollector
import com.onelens.plugin.framework.Collector
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.CollectorOutput
import com.onelens.plugin.framework.FrameworkAdapter
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.put

/**
 * Adapter for Java / Spring Boot projects. Active when a pom.xml or build.gradle[.kts]
 * is present at the project root or any module root. Encapsulates the existing seven
 * collectors (Class, Member, CallGraph, Inheritance, Module, Annotation, Spring) as a
 * single composite pass — inter-collector dependencies (MemberCollector needs classes,
 * CallGraphCollector needs classes) are preserved by running them sequentially in one
 * [SpringBootCollector].
 *
 * This file does not move the existing collector classes; it wraps them so ExportService
 * can iterate adapters without a full collector-file migration. A later cleanup can
 * physically relocate `export/collectors/` under `framework/springboot/collectors/`.
 */
class SpringBootAdapter : FrameworkAdapter {
    override val id: String = "spring-boot"
    override val jsonKey: String = "springBoot"

    override fun detect(project: Project): Boolean {
        val base = project.basePath ?: return false
        val baseDir = java.io.File(base)
        // Cheap file-system probe — no PSI. A real Java project will have one of these
        // at the root or one level down. Avoid walking the entire tree.
        val topLevelSignals = listOf("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
        if (topLevelSignals.any { java.io.File(baseDir, it).exists() }) return true
        // Multi-module projects may have no root pom/build file — peek one level down.
        val children = baseDir.listFiles()?.filter { it.isDirectory } ?: return false
        return children.any { child ->
            topLevelSignals.any { sig -> java.io.File(child, sig).exists() }
        }
    }

    override fun collectors(): List<Collector> = listOf(SpringBootCollector())
}

/**
 * Result of the composite Spring Boot collection pass. Exposes the individual
 * lists so ExportService can merge them into the existing top-level JSON keys
 * for back-compat with the Python importer.
 */
data class SpringBootCollectionResult(
    val classes: List<ClassData>,
    val methods: List<MethodData>,
    val fields: List<FieldData>,
    val callGraph: List<CallEdge>,
    val inheritance: List<InheritanceEdge>,
    val methodOverrides: List<OverrideEdge>,
    val modules: List<ModuleData>,
    val annotations: List<AnnotationUsage>,
    val spring: SpringData?,
    val diagnostics: List<DiagnosticEntry>,
    val enumConstants: List<EnumConstantData> = emptyList(),
    val jpa: JpaData? = null,
    val apps: List<AppData> = emptyList(),
    val packages: List<PackageData> = emptyList(),
    val tests: List<TestCaseData> = emptyList(),
    val mockBeans: List<TestBeanBinding> = emptyList(),
    val spyBeans: List<TestBeanBinding> = emptyList(),
)

/**
 * Runs the seven existing Java/Spring collectors in dependency order. Produces a
 * JSON subdoc for the adapter's `springBoot` section AND a structured side-channel
 * (available via [lastResult]) that ExportService uses to populate the legacy
 * top-level keys (`classes`, `methods`, etc.) until the Python importer migrates
 * to reading only adapter sub-documents.
 */
class SpringBootCollector : Collector {
    override val id: String = "spring-boot.all"
    override val label: String = "Java / Spring Boot"

    /** Most recent structured result. ExportService reads this after [collect]. */
    var lastResult: SpringBootCollectionResult? = null
        private set

    override fun collect(ctx: CollectContext): CollectorOutput {
        val project = ctx.project
        val indicator = ctx.indicator
        val base = ctx.progressFraction
        val workspace = ctx.workspace

        indicator?.text = "Java: collecting classes…"
        indicator?.fraction = base
        val classes = ClassCollector.collect(project, workspace)
        LOG.info("Collected ${classes.size} classes")

        indicator?.text = "Java: methods & fields (${classes.size} classes)…"
        indicator?.fraction = base + 0.02
        val members = MemberCollector.collect(project, classes, workspace)
        LOG.info("Collected ${members.methods.size} methods, ${members.fields.size} fields")

        indicator?.text = "Java: resolving call graph…"
        indicator?.fraction = base + 0.05
        val callGraph = CallGraphCollector.collect(project, classes, workspace)
        LOG.info("Collected ${callGraph.size} call edges")

        indicator?.text = "Java: inheritance & overrides…"
        indicator?.fraction = base + 0.25
        val inheritance = InheritanceCollector.collect(project, classes, workspace)
        LOG.info("Collected ${inheritance.edges.size} inheritance edges, ${inheritance.overrides.size} overrides")

        indicator?.text = "Java: modules…"
        indicator?.fraction = base + 0.35
        val modules = ModuleCollector.collect(project, workspace)
        LOG.info("Collected ${modules.size} modules")

        indicator?.text = "Java: annotation usages…"
        indicator?.fraction = base + 0.38
        val annotations = AnnotationCollector.collect(project, classes, workspace)
        LOG.info("Collected ${annotations.size} annotation usages")

        indicator?.text = "Java: Spring beans & endpoints…"
        indicator?.fraction = base + 0.42
        val annotationSpring = SpringCollector.collect(project, workspace)

        // Augment with IntelliJ Spring-plugin model when available. The plugin
        // resolves @Bean factories, XML beans, JAM beans, @Primary, scope — things
        // annotation scraping misses. Guard is runtime so the JAR still loads on
        // IC / WebStorm where com.intellij.spring is absent; the SpringModelCollector
        // class (which statically references SpringManager) is only touched on the
        // true branch, so the JVM never tries to verify it otherwise.
        val springModelBeans = if (isSpringPluginAvailable()) {
            try { SpringModelCollector.collect(project, workspace) }
            catch (t: Throwable) {
                LOG.warn("SpringModelCollector failed — falling back to annotation beans", t)
                emptyList()
            }
        } else emptyList()
        val mergedSpring = mergeSpring(annotationSpring, springModelBeans)

        indicator?.text = "Spring: auto-configuration chains…"
        indicator?.fraction = base + 0.43
        val autoConfigs = try { AutoConfigCollector.collect(project, workspace) }
            catch (t: Throwable) { LOG.warn("AutoConfigCollector failed", t); emptyList() }
        val spring = if (mergedSpring != null || autoConfigs.isNotEmpty()) {
            (mergedSpring ?: SpringData()).copy(autoConfigs = autoConfigs)
        } else null

        indicator?.text = "JPA: entities & repositories…"
        indicator?.fraction = base + 0.44
        val jpa = try { JpaCollector.collect(project, workspace) }
            catch (t: Throwable) { LOG.warn("JpaCollector failed", t); null }

        indicator?.text = "Apps & packages…"
        indicator?.fraction = base + 0.445
        val apps = try { AppCollector.collect(project, workspace) }
            catch (t: Throwable) { LOG.warn("AppCollector failed", t); emptyList() }
        val packages = try { PackageCollector.collect(classes, apps) }
            catch (t: Throwable) { LOG.warn("PackageCollector failed", t); emptyList() }

        indicator?.text = "Tests…"
        indicator?.fraction = base + 0.448
        val testResult = try { TestCollector.collect(project, workspace) }
            catch (t: Throwable) {
                LOG.warn("TestCollector failed", t)
                TestCollector.Result(emptyList(), emptyList(), emptyList())
            }

        indicator?.text = "Java: diagnostics…"
        indicator?.fraction = base + 0.45
        val diagnostics = DiagnosticsCollector.collect(project)

        val result = SpringBootCollectionResult(
            classes = classes,
            methods = members.methods,
            fields = members.fields,
            callGraph = callGraph,
            inheritance = inheritance.edges,
            methodOverrides = inheritance.overrides,
            modules = modules,
            annotations = annotations,
            spring = spring,
            diagnostics = diagnostics,
            enumConstants = members.enumConstants,
            jpa = jpa,
            apps = apps,
            packages = packages,
            tests = testResult.tests,
            mockBeans = testResult.mockBeans,
            spyBeans = testResult.spyBeans,
        )
        lastResult = result

        // Adapter-owned JSON subdoc. For now this is a thin summary; the
        // legacy top-level keys carry the canonical data until the Python
        // importer reads adapters-first.
        val json = Json { encodeDefaults = true }
        val subdoc = buildJsonObject {
            put("classCount", classes.size)
            put("methodCount", members.methods.size)
            put("fieldCount", members.fields.size)
            put("callEdgeCount", callGraph.size)
            put("inheritanceEdgeCount", inheritance.edges.size)
            put("overrideCount", inheritance.overrides.size)
            put("moduleCount", modules.size)
            put("annotationUsageCount", annotations.size)
            put("springBeanCount", spring?.beans?.size ?: 0)
            put("endpointCount", spring?.endpoints?.size ?: 0)
            put("autoConfigCount", spring?.autoConfigs?.size ?: 0)
            put("jpaEntityCount", jpa?.entities?.size ?: 0)
            put("jpaRepositoryCount", jpa?.repositories?.size ?: 0)
            put("appCount", apps.size)
            put("packageCount", packages.size)
            put("testCount", testResult.tests.size)
            put("mockBeanCount", testResult.mockBeans.size)
            put("spyBeanCount", testResult.spyBeans.size)
            put("enumConstantCount", members.enumConstants.size)
            put("diagnosticCount", diagnostics.size)
            if (spring != null) {
                put("spring", json.encodeToJsonElement(SpringData.serializer(), spring))
            }
            if (jpa != null) {
                put("jpa", json.encodeToJsonElement(JpaData.serializer(), jpa))
            }
        }

        val edgeCount = callGraph.size + inheritance.edges.size + inheritance.overrides.size +
            (spring?.injections?.size ?: 0)
        val nodeCount = classes.size + members.methods.size + members.fields.size +
            modules.size + (spring?.beans?.size ?: 0) + (spring?.endpoints?.size ?: 0)

        return CollectorOutput(data = subdoc, nodeCount = nodeCount, edgeCount = edgeCount)
    }

    private fun isSpringPluginAvailable(): Boolean = try {
        val pid = com.intellij.openapi.extensions.PluginId.getId("com.intellij.spring")
        com.intellij.ide.plugins.PluginManagerCore.getPlugin(pid)?.isEnabled == true
    } catch (_: Throwable) {
        false
    }

    /**
     * Merge annotation-scraped beans with Spring-plugin-resolved beans. Dedupe key
     * is classFqn + name + factoryMethodFqn so XML-only or @Bean-only definitions
     * don't collapse into the stereotype bean for the same class. Annotation beans
     * keep their dependencies/endpoints fields (which the model path leaves empty);
     * model beans contribute the @Primary / scope / source / factoryMethod fields
     * that annotation scraping can't resolve.
     */
    private fun mergeSpring(
        annotation: SpringData?,
        modelBeans: List<com.onelens.plugin.export.SpringBean>
    ): SpringData? {
        if (annotation == null && modelBeans.isEmpty()) return null
        val existing = annotation?.beans ?: emptyList()
        val byKey = existing.associateBy { "${it.classFqn}|${it.name}|" } // empty factoryMethodFqn for annotation beans
        val merged = existing.toMutableList()
        for (mb in modelBeans) {
            val key = "${mb.classFqn}|${mb.name}|${mb.factoryMethodFqn ?: ""}"
            val prior = byKey[key]
            if (prior != null) {
                // Prefer annotation bean's dependencies; upgrade with model-resolved flags.
                val idx = merged.indexOf(prior)
                merged[idx] = prior.copy(
                    primary = prior.primary || mb.primary,
                    scope = if (prior.scope == "singleton" && mb.scope != "singleton") mb.scope else prior.scope,
                    source = if (mb.source != "annotation") mb.source else prior.source,
                    factoryMethodFqn = prior.factoryMethodFqn ?: mb.factoryMethodFqn,
                    activeProfiles = mb.activeProfiles.ifEmpty { prior.activeProfiles },
                )
            } else {
                merged += mb
            }
        }
        return (annotation ?: SpringData()).copy(beans = merged)
    }

    companion object {
        private val LOG = logger<SpringBootCollector>()
    }
}
