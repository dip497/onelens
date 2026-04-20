package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FilenameIndex
import com.intellij.psi.search.GlobalSearchScope
import com.onelens.plugin.export.SpringAutoConfig
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Walks the Spring Boot auto-configuration resource files and returns one
 * [SpringAutoConfig] per declared class. Two formats:
 *   - `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`
 *     (Boot 2.7+): one FQN per non-blank line. Comment prefix `#`.
 *   - `META-INF/spring.factories` (legacy): `key=Value1,Value2,\` continuation style.
 *     We only lift the keys ending in `EnableAutoConfiguration` which drive
 *     auto-config registration; other keys (e.g. ContextInitializer) stay out.
 *
 * Scanned scope is `allScope(project)` because starter JARs contribute most
 * auto-config entries and those live outside workspace roots. Individual
 * entries' [SpringAutoConfig.sourceFile] preserves the absolute path so the
 * Python side can decide whether to filter to project-only.
 */
object AutoConfigCollector {

    private val LOG = logger<AutoConfigCollector>()

    private const val IMPORTS_FILE =
        "AutoConfiguration.imports" // actual lookup target is the basename
    private const val FACTORIES_FILE = "spring.factories"

    fun collect(project: Project, workspace: Workspace): List<SpringAutoConfig> {
        return ReadAction.compute<List<SpringAutoConfig>, Throwable> {
            // Key by classFqn — same class can appear in BOTH spring.factories (legacy)
            // and AutoConfiguration.imports (Boot 2.7+) during a migration. We prefer
            // autoconfig.imports when both exist (it's the current format) and keep
            // the first seen source file so Cypher queries show a deterministic path.
            val byClass = LinkedHashMap<String, SpringAutoConfig>()
            val scope = GlobalSearchScope.allScope(project)
            val psiManager = PsiManager.getInstance(project)

            for (vFile in FilenameIndex.getVirtualFilesByName(IMPORTS_FILE, scope)) {
                // IntelliJ JarFileSystem paths look like `jar:///path/starter.jar!/META-INF/spring/…`.
                // Accept both filesystem form and JAR-internal form.
                if (!vFile.path.contains("META-INF/spring/")) continue
                val content = readText(psiManager, vFile) ?: continue
                for (fqn in parseImports(content)) {
                    byClass[fqn] = SpringAutoConfig(
                        classFqn = fqn,
                        source = "autoconfig.imports",
                        sourceFile = vFile.path,
                    )
                }
            }

            for (vFile in FilenameIndex.getVirtualFilesByName(FACTORIES_FILE, scope)) {
                if (!vFile.path.contains("META-INF/")) continue
                val content = readText(psiManager, vFile) ?: continue
                for (fqn in parseFactories(content)) {
                    // Skip if already captured from autoconfig.imports.
                    if (byClass.containsKey(fqn)) continue
                    byClass[fqn] = SpringAutoConfig(
                        classFqn = fqn,
                        source = "spring.factories",
                        sourceFile = vFile.path,
                    )
                }
            }

            LOG.info("AutoConfigCollector: ${byClass.size} auto-configuration class entries")
            byClass.values.toList()
        }
    }

    private fun readText(psiManager: PsiManager, file: VirtualFile): String? =
        try { String(file.contentsToByteArray(), Charsets.UTF_8) }
        catch (e: Throwable) { LOG.debug("readText failed for ${file.path}: ${e.message}"); null }

    private fun parseImports(content: String): List<String> =
        content.lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() && !it.startsWith("#") }
            .distinct()
            .toList()

    private fun parseFactories(content: String): List<String> {
        // Join line-continuation (`\` at EOL) into single logical lines.
        val logical = content.replace("\\\n", "").replace("\\\r\n", "")
        val out = ArrayList<String>()
        for (rawLine in logical.lines()) {
            val line = rawLine.trim()
            if (line.isEmpty() || line.startsWith("#")) continue
            val eq = line.indexOf('=')
            if (eq <= 0) continue
            val key = line.substring(0, eq).trim()
            // Only auto-config entries — other keys (ApplicationContextInitializer,
            // etc.) aren't the bean-chain input we need.
            if (!key.endsWith("EnableAutoConfiguration")) continue
            val values = line.substring(eq + 1).trim()
            values.split(',').map { it.trim() }.filter { it.isNotEmpty() }.forEach { out += it }
        }
        return out
    }
}
