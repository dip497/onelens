package com.onelens.plugin.framework.springboot

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.AnnotationUsage
import com.onelens.plugin.export.CallEdge
import com.onelens.plugin.export.ClassData
import com.onelens.plugin.export.DiagnosticEntry
import com.onelens.plugin.export.FieldData
import com.onelens.plugin.export.InheritanceEdge
import com.onelens.plugin.export.MethodData
import com.onelens.plugin.export.ModuleData
import com.onelens.plugin.export.OverrideEdge
import com.onelens.plugin.export.SpringData
import com.onelens.plugin.export.collectors.AnnotationCollector
import com.onelens.plugin.export.collectors.CallGraphCollector
import com.onelens.plugin.export.collectors.ClassCollector
import com.onelens.plugin.export.collectors.DiagnosticsCollector
import com.onelens.plugin.export.collectors.InheritanceCollector
import com.onelens.plugin.export.collectors.MemberCollector
import com.onelens.plugin.export.collectors.ModuleCollector
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
    val diagnostics: List<DiagnosticEntry>
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

        indicator?.text = "Java: collecting classes…"
        indicator?.fraction = base
        val classes = ClassCollector.collect(project)
        LOG.info("Collected ${classes.size} classes")

        indicator?.text = "Java: methods & fields (${classes.size} classes)…"
        indicator?.fraction = base + 0.02
        val members = MemberCollector.collect(project, classes)
        LOG.info("Collected ${members.methods.size} methods, ${members.fields.size} fields")

        indicator?.text = "Java: resolving call graph…"
        indicator?.fraction = base + 0.05
        val callGraph = CallGraphCollector.collect(project, classes)
        LOG.info("Collected ${callGraph.size} call edges")

        indicator?.text = "Java: inheritance & overrides…"
        indicator?.fraction = base + 0.25
        val inheritance = InheritanceCollector.collect(project, classes)
        LOG.info("Collected ${inheritance.edges.size} inheritance edges, ${inheritance.overrides.size} overrides")

        indicator?.text = "Java: modules…"
        indicator?.fraction = base + 0.35
        val modules = ModuleCollector.collect(project)
        LOG.info("Collected ${modules.size} modules")

        indicator?.text = "Java: annotation usages…"
        indicator?.fraction = base + 0.38
        val annotations = AnnotationCollector.collect(project, classes)
        LOG.info("Collected ${annotations.size} annotation usages")

        indicator?.text = "Java: Spring beans & endpoints…"
        indicator?.fraction = base + 0.42
        val spring = SpringCollector.collect(project)

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
            diagnostics = diagnostics
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
            put("diagnosticCount", diagnostics.size)
            if (spring != null) {
                put("spring", json.encodeToJsonElement(SpringData.serializer(), spring))
            }
        }

        val edgeCount = callGraph.size + inheritance.edges.size + inheritance.overrides.size +
            (spring?.injections?.size ?: 0)
        val nodeCount = classes.size + members.methods.size + members.fields.size +
            modules.size + (spring?.beans?.size ?: 0) + (spring?.endpoints?.size ?: 0)

        return CollectorOutput(data = subdoc, nodeCount = nodeCount, edgeCount = edgeCount)
    }

    companion object {
        private val LOG = logger<SpringBootCollector>()
    }
}
