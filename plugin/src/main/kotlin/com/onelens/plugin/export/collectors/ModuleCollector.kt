package com.onelens.plugin.export.collectors

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.module.ModuleManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ModuleRootManager
import com.onelens.plugin.export.ModuleCoordinates
import com.onelens.plugin.export.ModuleData
import com.onelens.plugin.export.ModuleDependency
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Collects Maven/Gradle module structure and inter-module dependencies.
 */
object ModuleCollector {

    private val LOG = logger<ModuleCollector>()

    fun collect(project: Project, workspace: Workspace): List<ModuleData> {
        // Workspace-relative paths — single source of truth. First-root-hit wins
        // so sibling-repo modules render against their own root, not the primary.
        fun rel(path: String): String = workspace.relativePath(path)

        val modules = ModuleManager.getInstance(project).modules

        val result = modules.map { module ->
            val rootManager = ModuleRootManager.getInstance(module)

            val sourceRoots = rootManager.sourceRoots
                .filter { !it.path.contains("/test/") }
                .map { rel(it.path) }

            val testRoots = rootManager.sourceRoots
                .filter { it.path.contains("/test/") }
                .map { rel(it.path) }

            val resourceRoots = rootManager.contentEntries
                .flatMap { it.sourceFolders.toList() }
                .filter { it.isTestSource.not() && it.rootType.toString().contains("resource", ignoreCase = true) }
                .mapNotNull { it.file?.path?.let { p -> rel(p) } }

            val dependencies = rootManager.dependencies.map { dep ->
                ModuleDependency(moduleName = dep.name)
            }

            ModuleData(
                name = module.name,
                type = detectBuildSystem(module, workspace),
                sourceRoots = sourceRoots,
                resourceRoots = resourceRoots,
                testSourceRoots = testRoots,
                dependencies = dependencies,
                coordinates = null // TODO: extract Maven coordinates from pom.xml if present
            )
        }

        LOG.info("Collected ${result.size} modules")
        return result
    }

    private fun detectBuildSystem(module: com.intellij.openapi.module.Module, workspace: Workspace): String {
        // Probe the module's own directory first — then every workspace root in
        // order. Multi-root workspaces (sibling Gradle + Maven repos) resolve
        // correctly instead of silently collapsing to whichever signal the
        // primary root has.
        val moduleDir = module.moduleFile?.parent?.path
        val candidates = buildList {
            if (moduleDir != null) add(moduleDir)
            workspace.roots.forEach { add(it.path.toString()) }
        }
        for (dir in candidates) {
            when {
                java.io.File("$dir/build.gradle").exists() ||
                    java.io.File("$dir/build.gradle.kts").exists() -> return "GRADLE"
                java.io.File("$dir/pom.xml").exists() -> return "MAVEN"
            }
        }
        return "UNKNOWN"
    }
}
