package com.onelens.plugin.framework.jscommon

import com.intellij.openapi.diagnostic.logger
import java.io.File
import java.nio.file.Path

/**
 * Builds a monorepo package-alias map: workspace package `name` → its directory (as a
 * base-relative POSIX path). Sources, in order: `pnpm-workspace.yaml` `packages:` globs,
 * else root `package.json` `"workspaces"` (array or `{ packages: [...] }`). Each matched
 * dir's `package.json` `"name"` becomes the key.
 *
 * Lets [RendersResolver][com.onelens.plugin.framework.nextjs.collectors.RendersResolver]
 * turn a cross-package import specifier `@scope/pkg[/sub]` into an extensionless module
 * path so `<Badge/>` imported from another workspace package resolves.
 *
 * ponytail: only literal one-level ("dir/star") and recursive ("dir/star-star") globs
 * are expanded (both treated as one level) — full glob semantics aren't needed for the
 * pnpm/npm conventions in the wild.
 */
object WorkspaceAliasResolver {
    private val LOG = logger<WorkspaceAliasResolver>()

    private val NAME_RE = Regex(""""name"\s*:\s*"([^"]+)"""")
    private val PNPM_PKG_LINE = Regex("""^\s*-\s*['"]?([^'"#\s]+)['"]?""")

    /** package name → base-relative dir. Empty when the repo isn't a workspace. */
    fun buildAliasMap(base: Path): Map<String, String> {
        val baseDir = base.toFile()
        val globs = readPnpmGlobs(baseDir).ifEmpty { readPackageJsonWorkspaces(baseDir) }
        if (globs.isEmpty()) return emptyMap()
        val out = LinkedHashMap<String, String>()
        for (glob in globs) {
            for (dir in expandGlob(baseDir, glob)) {
                val pkgJson = File(dir, "package.json")
                if (!pkgJson.isFile) continue
                val name = try { NAME_RE.find(pkgJson.readText())?.groupValues?.get(1) } catch (_: Throwable) { null }
                    ?: continue
                val rel = baseDir.toPath().relativize(dir.toPath()).toString().replace('\\', '/')
                out.putIfAbsent(name, rel)
            }
        }
        if (out.isNotEmpty()) LOG.info("WorkspaceAliasResolver: ${out.size} workspace packages")
        return out
    }

    private fun readPnpmGlobs(baseDir: File): List<String> {
        val f = File(baseDir, "pnpm-workspace.yaml").takeIf { it.isFile }
            ?: File(baseDir, "pnpm-workspace.yml").takeIf { it.isFile }
            ?: return emptyList()
        return try {
            val lines = f.readLines()
            val out = mutableListOf<String>()
            var inPackages = false
            for (raw in lines) {
                val line = raw.substringBefore('#')
                if (Regex("""^\s*packages\s*:""").containsMatchIn(line)) { inPackages = true; continue }
                if (inPackages) {
                    val m = PNPM_PKG_LINE.find(line)
                    if (m != null) out += m.groupValues[1]
                    else if (line.isNotBlank() && !line.first().isWhitespace()) break // next top-level key
                }
            }
            out
        } catch (_: Throwable) { emptyList() }
    }

    private fun readPackageJsonWorkspaces(baseDir: File): List<String> {
        val pkg = File(baseDir, "package.json").takeIf { it.isFile } ?: return emptyList()
        return try {
            val txt = pkg.readText()
            // "workspaces": [ ... ]  OR  "workspaces": { "packages": [ ... ] }
            val block = Regex(""""workspaces"\s*:\s*(\{[^}]*\}|\[[^\]]*\])""").find(txt)?.groupValues?.get(1)
                ?: return emptyList()
            Regex("""['"]([^'"]+)['"]""").findAll(block)
                .map { it.groupValues[1] }
                .filter { it != "packages" }
                .toList()
        } catch (_: Throwable) { emptyList() }
    }

    private fun expandGlob(baseDir: File, glob: String): List<File> {
        val g = glob.trim().removeSuffix("/")
        return when {
            g.endsWith("/*") || g.endsWith("/**") -> {
                val parent = File(baseDir, g.removeSuffix("/**").removeSuffix("/*"))
                parent.listFiles()?.filter { it.isDirectory && !it.name.startsWith(".") }.orEmpty()
            }
            else -> {
                val d = File(baseDir, g)
                if (d.isDirectory) listOf(d) else emptyList()
            }
        }
    }
}
