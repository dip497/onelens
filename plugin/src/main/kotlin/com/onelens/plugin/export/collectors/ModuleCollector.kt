package com.onelens.plugin.export.collectors

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.module.ModuleManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ModuleRootManager
import com.onelens.plugin.export.ModuleCoordinates
import com.onelens.plugin.export.ModuleData
import com.onelens.plugin.export.ModuleDependency

/**
 * Collects Maven/Gradle module structure and inter-module dependencies.
 */
object ModuleCollector {

    private val LOG = logger<ModuleCollector>()

    fun collect(project: Project): List<ModuleData> {
        val basePath = project.basePath ?: ""
        val modules = ModuleManager.getInstance(project).modules

        val result = modules.map { module ->
            val rootManager = ModuleRootManager.getInstance(module)

            val sourceRoots = rootManager.sourceRoots
                .filter { !it.path.contains("/test/") }
                .map { it.path.removePrefix(basePath).removePrefix("/") }

            val testRoots = rootManager.sourceRoots
                .filter { it.path.contains("/test/") }
                .map { it.path.removePrefix(basePath).removePrefix("/") }

            val resourceRoots = rootManager.contentEntries
                .flatMap { it.sourceFolders.toList() }
                .filter { it.isTestSource.not() && it.rootType.toString().contains("resource", ignoreCase = true) }
                .mapNotNull { it.file?.path?.removePrefix(basePath)?.removePrefix("/") }

            val dependencies = rootManager.dependencies.map { dep ->
                ModuleDependency(moduleName = dep.name)
            }

            ModuleData(
                name = module.name,
                type = detectBuildSystem(module, basePath),
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

    private fun detectBuildSystem(module: com.intellij.openapi.module.Module, basePath: String): String {
        val modulePath = module.moduleFilePath
        return when {
            java.io.File("$basePath/build.gradle").exists() ||
                java.io.File("$basePath/build.gradle.kts").exists() -> "GRADLE"
            java.io.File("$basePath/pom.xml").exists() -> "MAVEN"
            else -> "UNKNOWN"
        }
    }
}
