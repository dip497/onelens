package com.onelens.plugin.framework.vue3.resolver

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Resolves path aliases defined in `vite.config.{js,ts}`. For this repo's real config
 * aliases like `@`, `@ui`, `@utils`, `@modules`, `@state`
 * show up as an `resolve.alias` object literal. Parsing full JS/TS in this Kotlin pass
 * is out of scope — instead we pattern-match that block with a tight regex. Anything
 * dynamic (conditional, computed, imported from another module) is reported as
 * unresolved so callers can degrade gracefully.
 *
 * Strategy (per plan B2, resolver-reuse first):
 *   1. Try tsconfig/jsconfig `compilerOptions.paths` first — it's JSON, cheap, and
 *      the IntelliJ JS plugin already understands it for navigation. When present it
 *      wins, since it's the canonical source of aliases in modern Vite projects.
 *   2. Fall back to scanning `vite.config.{js,ts}` for a static `resolve.alias` block.
 *   3. Return an empty map if neither yields anything; collectors treat `@/x` imports
 *      as unresolved and log a warning.
 */
object ViteAliasResolver {
    private val LOG = logger<ViteAliasResolver>()

    /** Alias prefix → absolute path. Keys are normalized without trailing slash. */
    fun resolve(project: Project): Map<String, Path> {
        val base = project.basePath ?: return emptyMap()
        return resolveFromBase(Paths.get(base))
    }

    /** Test-friendly overload that takes a raw base path; same algorithm as [resolve]. */
    fun resolveFromBase(baseDir: Path): Map<String, Path> {
        // Merge strategy: take the union of tsconfig/jsconfig `paths` and vite.config
        // `resolve.alias`. vite.config wins on conflicts because it's the runtime
        // source of truth — tsconfig exists mostly for IDE navigation and is often
        // a narrow subset (a real-world Vue 3 repo we tested has 1 entry in jsconfig vs 27 in
        // vite.config). Without merging, we'd miss the 26 vite-only aliases.
        val tsConfig = readTsConfigPaths(baseDir)
        val viteConfig = readViteConfig(baseDir)
        val merged = LinkedHashMap<String, Path>().apply {
            putAll(tsConfig)
            putAll(viteConfig) // vite wins on overlap
        }
        if (merged.isEmpty()) {
            LOG.warn("No Vite aliases resolved; @-prefixed imports will be marked unresolved")
        } else {
            LOG.info("Vite alias map: ${merged.size} entries (tsconfig=${tsConfig.size}, vite=${viteConfig.size})")
        }
        return merged
    }

    /**
     * Parse `compilerOptions.paths` out of `jsconfig.json` or `tsconfig.json`.
     * The JSON is fine to parse by regex because we only care about string literals
     * on the right-hand side; fancier edge cases (paths inheriting `extends`) fall
     * through and reveal themselves in the log as unresolved imports.
     */
    private fun readTsConfigPaths(baseDir: Path): Map<String, Path> {
        val candidates = listOf("jsconfig.json", "tsconfig.json")
        for (name in candidates) {
            val file = baseDir.resolve(name).toFile()
            if (!file.exists()) continue
            try {
                val text = file.readText()
                val paths = PATHS_PATTERN.find(text)?.value ?: continue
                val map = mutableMapOf<String, Path>()
                ENTRY_PATTERN.findAll(paths).forEach { match ->
                    val alias = match.groupValues[1].trimEnd('/').removeSuffix("/*")
                    val target = match.groupValues[2].removeSuffix("/*").trim('"', ' ')
                    if (alias.isBlank() || target.isBlank()) return@forEach
                    val resolved = baseDir.resolve(target).normalize()
                    map[alias] = resolved
                }
                if (map.isNotEmpty()) return map
            } catch (e: Throwable) {
                LOG.warn("Failed to parse $name: ${e.message}")
            }
        }
        return emptyMap()
    }

    /**
     * Best-effort scan of `vite.config.{js,ts}` for a static `resolve.alias` block.
     * Matches entries of the form `'@x': path.resolve(__dirname, 'src/x')` and plain
     * `'@x': 'src/x'`. Anything involving function calls or variables is skipped.
     */
    private fun readViteConfig(baseDir: Path): Map<String, Path> {
        val candidates = listOf("vite.config.ts", "vite.config.js", "vite.config.mjs")
        for (name in candidates) {
            val file = baseDir.resolve(name).toFile()
            if (!file.exists()) continue
            try {
                val text = file.readText()
                val block = ALIAS_BLOCK_PATTERN.find(text)?.value ?: continue
                val map = mutableMapOf<String, Path>()
                VITE_ENTRY_LITERAL.findAll(block).forEach { m ->
                    val alias = m.groupValues[1]
                    val target = m.groupValues[2]
                    if (alias.isBlank() || target.isBlank()) return@forEach
                    map[alias] = baseDir.resolve(target).normalize()
                }
                VITE_ENTRY_PATH_RESOLVE.findAll(block).forEach { m ->
                    val alias = m.groupValues[1]
                    val target = m.groupValues[2]
                    if (alias.isBlank() || target.isBlank()) return@forEach
                    map[alias] = baseDir.resolve(target).normalize()
                }
                if (map.isNotEmpty()) return map
            } catch (e: Throwable) {
                LOG.warn("Failed to parse $name: ${e.message}")
            }
        }
        return emptyMap()
    }

    /**
     * Given an import spec like `@ui/components/Button`, return the absolute file path
     * using the longest matching alias prefix. Caller appends the file extension.
     */
    fun resolveImport(aliases: Map<String, Path>, importSpec: String): Path? {
        if (importSpec.isBlank()) return null
        val match = aliases.keys
            .filter { importSpec == it || importSpec.startsWith("$it/") }
            .maxByOrNull { it.length } ?: return null
        val tail = importSpec.removePrefix(match).removePrefix("/")
        val base = aliases.getValue(match)
        return if (tail.isBlank()) base else base.resolve(tail)
    }

    private val PATHS_PATTERN = Regex(""""paths"\s*:\s*\{[^\}]*\}""", RegexOption.DOT_MATCHES_ALL)
    private val ENTRY_PATTERN = Regex(""""([^"]+)"\s*:\s*\[\s*"([^"]+)"\s*\]""")
    private val ALIAS_BLOCK_PATTERN = Regex(
        """alias\s*:\s*\{[^}]*\}""",
        RegexOption.DOT_MATCHES_ALL
    )
    private val VITE_ENTRY_LITERAL = Regex("""['"]([^'"]+)['"]\s*:\s*['"]([^'"]+)['"]""")
    private val VITE_ENTRY_PATH_RESOLVE = Regex(
        """['"]([^'"]+)['"]\s*:\s*(?:path\.)?resolve\s*\([^,]+,\s*['"]([^'"]+)['"]\s*\)"""
    )
}
