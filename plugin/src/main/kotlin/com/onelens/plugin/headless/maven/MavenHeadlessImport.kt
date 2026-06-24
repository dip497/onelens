package com.onelens.plugin.headless.maven

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import org.jetbrains.idea.maven.project.MavenImportListener
import org.jetbrains.idea.maven.project.MavenProjectsManager
import java.util.concurrent.CountDownLatch

/**
 * Typed adapter for Maven import synchronization in headless mode.
 *
 * Replaces the earlier fully-reflective implementation. With `org.jetbrains
 * .idea.maven` declared as an optional `<depends>` (maven-headless.xml) AND
 * on the compile classpath (gradle.properties platformBundledPlugins), every
 * Maven API reference below is a typed symbol — a rename in a future platform
 * version breaks the build instead of silently stopping the import event.
 *
 * Why this exists: headless `idea.sh onelens-export` of a Maven project can
 * hit two failure modes — (1) Maven's auto-import is unreliable without a UI
 * consumer, and (2) on warm-cache runs `MavenProjectsManager.hasProjects()`
 * can be false because Maven's lazy startup hasn't re-registered the pom.
 * This adapter forces pom discovery + import, then signals completion via a
 * [CountDownLatch] released on `MavenImportListener.importFinished`.
 *
 * The adapter is loaded by the OneLens classloader but reaches the Maven
 * classes through the optional-dependency classloader edge. Callers should
 * still guard with [isAvailable] (cheap class-existence probe) so the JAR
 * loads on IDEs without Maven installed.
 */
object MavenHeadlessImport {

    private val log = logger<MavenHeadlessImport>()

    /**
     * Directory patterns whose poms should be ignored by Maven import. These
     * are tool-managed worktree copies (Claude Code, git worktree) that would
     * otherwise be imported as full Maven modules — doubling+ the indexed
     * file count with duplicate source. Matched relative to the project root
     * and one level down (multi-module layouts).
     */
    private val WORKTREE_PATTERNS = listOf(
        ".claude/worktrees",
    )

    /**
     * `true` if the Maven bundled plugin is on the classpath. Cheap — single
     * `Class.forName`. Callers use this to decide whether to invoke
     * [awaitImport] or fall through to the Gradle/external-system path.
     */
    fun isAvailable(): Boolean = try {
        Class.forName("org.jetbrains.idea.maven.project.MavenProjectsManager")
        true
    } catch (_: ClassNotFoundException) {
        false
    }

    /**
     * Subscribe to `MavenImportListener.importFinished` for [project],
     * force-discover the pom, kick the import, and return a latch that counts
     * down when the import completes.
     *
     * Contract mirrors the Gradle path in
     * `OneLensExportStarter.waitForExternalSystemResolve`: caller registers
     * BEFORE waiting on the rest of the index gate, then bounded-awaits the
     * returned latch so the post-import reindex settles before exporting.
     *
     * No-op (returns an already-counted-down latch) if [project] has no pom
     * registered and discovery finds nothing.
     */
    fun awaitImport(project: Project): CountDownLatch {
        val latch = CountDownLatch(1)
        val mgr = MavenProjectsManager.getInstance(project)

        // Subscribe FIRST so we don't miss an import that completes quickly
        // after we kick it below.
        project.messageBus.connect().subscribe(MavenImportListener.TOPIC, object : MavenImportListener {
            override fun importFinished(
                importedProjects: Collection<org.jetbrains.idea.maven.project.MavenProject>,
                importedModules: List<com.intellij.openapi.module.Module>
            ) {
                log.info("onelens-export: Maven importFinished fired (${importedProjects.size} projects)")
                latch.countDown()
            }
        })

        // Force pom discovery + registration. On warm cache, hasProjects()
        // can be false because Maven's lazy startup hasn't re-registered the
        // pom; forceUpdateAllProjectsOrFindAllAvailablePomFiles discovers it.
        // NOTE: discovery is ASYNC — hasProjects() immediately afterward may
        // still be false even though the pom will be registered a moment
        // later. So we kick scheduleImportAndResolve() unconditionally (it's
        // a no-op if nothing's registered, and once discovery registers the
        // pom the import queue picks it up), and rely SOLELY on
        // importFinished for the completion signal. Do NOT count down the
        // latch synchronously on hasProjects()==false — that releases the
        // caller before the real import fires (observed regression: 17→13
        // classes because the re-gate ran before Maven attached source roots).

        // PRE-IMPORT EXCLUSION: ignore poms under known excluded paths
        // (worktrees, build output) so Maven doesn't import them as modules.
        // Without this, e.g. `.claude/worktrees/*/pom.xml` would each be
        // imported as a full Maven module — doubling+ the indexed file count
        // with duplicate source. setIgnoredFilesPaths is additive with the
        // manager's existing ignored list.
        val basePath = project.basePath
        if (basePath != null) {
            val base = basePath.replace('\\', '/')
            val toIgnore = mutableListOf<String>().apply {
                for (pat in WORKTREE_PATTERNS) {
                    val pomPath = "$base/$pat/pom.xml"
                    if (java.io.File(pomPath).isFile) add(pomPath)
                }
                // Also check one level down for multi-module layouts.
                val subDirs = java.io.File(base).listFiles { f -> f.isDirectory } ?: emptyArray()
                for (sub in subDirs) {
                    for (pat in WORKTREE_PATTERNS) {
                        val pomPath = "${sub.absolutePath.replace('\\', '/')}/$pat/pom.xml"
                        if (java.io.File(pomPath).isFile) add(pomPath)
                    }
                }
            }
            if (toIgnore.isNotEmpty()) {
                log.info("onelens-export: ignoring ${toIgnore.size} worktree/excluded poms: $toIgnore")
                try {
                    val existing = mgr.ignoredFilesPaths
                    mgr.setIgnoredFilesPaths((existing + toIgnore).distinct())
                } catch (e: Throwable) {
                    log.warn("onelens-export: Maven ignore-paths failed (continuing): ${e.message}")
                }
            }
        }

        // --- Import sibling workspace roots as Maven projects ---
        //
        // The primary Maven import (below) discovers poms under the project's
        // base path. But workspace YAML roots like `../motadata_plugins` are
        // OUTSIDE the project base — Maven never sees them. In the GUI, the
        // user right-clicks and "Add as Maven Project". Headlessly, we must
        // explicitly add their pom.xml files as managed projects.
        //
        // This is the fix for multi-project workspaces: sibling repos declared
        // as workspace roots get their poms linked, so their classes appear in
        // the IntelliJ stub index and ClassCollector finds them.
        //
        // IMPORTANT: addManagedFiles is called BEFORE the primary import kick
        // (scheduleImportAndResolve below) so that BOTH the primary and sibling
        // poms are imported in a SINGLE pass. A separate latch is used for the
        // sibling import to avoid the primary import's importFinished consuming
        // the latch before the sibling import completes.
        val workspace = com.onelens.plugin.framework.workspace.WorkspaceLoader.load(project)
        val siblingPoms = findSiblingPomFiles(project, workspace)
        val hasSiblings = siblingPoms.isNotEmpty()

        // Kick the import. Use forceUpdateAllProjectsOrFindAllAvailablePomFiles
        // to discover the PRIMARY pom if it's not yet registered (cold start).
        //
        // CRITICAL: when sibling poms are added via addManagedFiles below,
        // mgr.hasProjects() returns true (siblings registered) BEFORE the
        // primary pom is discovered. So we must check hasProjects() and do
        // discovery BEFORE adding siblings, not after.
        log.info("onelens-export: forcing Maven pom discovery + import")
        if (!mgr.hasProjects()) {
            try {
                mgr.forceUpdateAllProjectsOrFindAllAvailablePomFiles()
            } catch (e: Throwable) {
                log.warn("onelens-export: Maven pom discovery threw (continuing): ${e.message}")
            }
        } else {
            log.info("onelens-export: ${mgr.projects.size} Maven projects already registered; skipping discovery")
        }

        // NOW add sibling poms (after primary discovery, so hasProjects()
        // doesn't short-circuit the primary pom discovery above).
        if (hasSiblings) {
            log.info("onelens-export: adding ${siblingPoms.size} sibling-workspace pom(s) as Maven projects")
            siblingPoms.forEach { log.info("  → ${it.path}") }
            mgr.addManagedFiles(siblingPoms)
        }
        mgr.scheduleImportAndResolve()

        // Fallback for genuinely-non-Maven projects: discovery is async, so
        // poll briefly (max 5s) for the pom to register. If after 5s the
        // manager still has no projects AND importFinished hasn't fired, this
        // is a plain-Java/Gradle project that will never fire the Maven
        // callback — count down so the caller doesn't wait the full
        // EXT_RESOLVE_TIMEOUT. If the pom DOES register during the window,
        // scheduleImportAndResolve will trigger importFinished (already
        // subscribed above) and that path wins.
        Thread {
            val deadline = System.currentTimeMillis() + 5_000L
            while (System.currentTimeMillis() < deadline) {
                if (mgr.hasProjects()) return@Thread // import will fire
                Thread.sleep(200)
            }
            log.info("onelens-export: no Maven projects registered after 5s; releasing Maven latch")
            latch.countDown()
        }.apply { isDaemon = true; name = "onelens-maven-noproj-fallback"; start() }

        return latch
    }

    /**
     * Find pom.xml files in workspace roots OTHER than the project's base path.
     *
     * The primary Maven import discovers poms under `project.basePath`. Sibling
     * workspace roots (e.g. `../motadata_plugins`) are outside that path and
     * need explicit linking. This method:
     *
     * 1. Loads the workspace YAML.
     * 2. For each root whose path differs from the project base path:
     *    - If the root has `include` patterns, find pom.xml files matching them.
     *    - If no patterns, look for a `pom.xml` at the root itself (the common case).
     * 3. Returns the discovered [VirtualFile]s, excluding any already-managed poms.
     */
    private fun findSiblingPomFiles(
        project: com.intellij.openapi.project.Project,
        workspace: com.onelens.plugin.framework.workspace.Workspace,
    ): List<com.intellij.openapi.vfs.VirtualFile> {
        val vfs = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
        val basePath = project.basePath ?: return emptyList()
        val basePathNorm = basePath.replace('\\', '/').trimEnd('/')

        val mgr = MavenProjectsManager.getInstance(project)
        val alreadyManaged = mgr.projects.mapNotNull { it.file?.path }.toSet()

        val result = mutableListOf<com.intellij.openapi.vfs.VirtualFile>()
        for (root in workspace.roots) {
            val rootPath = root.path.toString().replace('\\', '/').trimEnd('/')
            // Skip the primary root — it's already discovered by the main import.
            if (rootPath == basePathNorm || rootPath.startsWith("$basePathNorm/")) continue

            if (root.include.isNotEmpty()) {
                // Use the include patterns to find pom.xml files.
                for (pattern in root.include) {
                    val cleanPattern = pattern.removePrefix("./").removePrefix("/")
                    val candidate = java.nio.file.Paths.get(rootPath, cleanPattern).let {
                        if (it.toString().endsWith("pom.xml") || it.toString().endsWith("pom")) it
                        else java.nio.file.Paths.get(rootPath, cleanPattern, "pom.xml")
                    }
                    val vf = vfs.findFileByPath(candidate.toString())
                    if (vf != null && vf.path !in alreadyManaged) {
                        result.add(vf)
                    }
                }
            } else {
                // No include patterns — look for pom.xml at the root itself.
                val pomPath = java.nio.file.Paths.get(rootPath, "pom.xml").toString()
                val vf = vfs.findFileByPath(pomPath)
                if (vf != null && vf.path !in alreadyManaged) {
                    result.add(vf)
                }
            }
        }
        return result
    }
}
