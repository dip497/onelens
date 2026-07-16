package com.onelens.plugin.headless

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ApplicationStarter
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.ProjectManager
import com.onelens.plugin.export.ExportConfig
import com.onelens.plugin.export.ExportService
import com.onelens.plugin.export.ExportState
import com.onelens.plugin.export.delta.DeltaExportService
import com.onelens.plugin.export.delta.DeltaExportService.DeltaResult
import com.onelens.plugin.framework.workspace.WorkspaceLoader
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Headless export entry point.
 *
 * Boots the IntelliJ Platform without a GUI (same runtime Qodana uses) and
 * drives the exact same PSI collectors the in-IDE Tools → OneLens → Sync Graph
 * action drives — [ExportService.exportFull] is GUI-decoupled (zero AWT/Swing
 * references; verified by grep across the export package). The starter just
 * supplies a [Project] and an [ExportConfig] instead of an AnActionEvent +
 * ProgressIndicator.
 *
 * Invoked by the platform when the IDE is launched with `onelens-export` as
 * the first command-line arg, e.g.:
 *
 *   idea.sh onelens-export --project /path/to/spring/app --output-dir /out
 *
 * Deliberately JSON-only: writes
 * `~/.onelens/exports/<graph>-full-<ts>.json` and exits. The downstream
 * `onelens call-tool onelens_import --export-path … --graph …` is a separate
 * step (mirrors how the plugin splits export from import). No FalkorDB
 * preflight, no CLI shell-out, no embeddings — those are the Python side's
 * job. `autoImport = false` and `buildSemanticIndex = false` enforce this.
 *
 * Licensing note: PSI + the bundled Spring/JPA model classes resolve inside a
 * Community-platform JVM, but the Spring plugin's model (the `@Bean`/autowire
 * candidates the collectors rely on) ships only with IntelliJ Ultimate. So a
 * headless run against a Spring Boot project needs an Ultimate-licensed
 * platform — typically `jetbrains/qodana-jvm` (see `docker/Dockerfile`).
 *
 * ApplicationStarter is a Kotlin interface whose `getCommandName()` /
 * `isHeadless()` / `getRequiredModality()` are exposed as Kotlin properties
 * (`commandName`, `isHeadless`, `requiredModality`) due to the `get`/`is`
 * prefix convention; `main(args)` and `premain(args)` are plain functions.
 */
class OneLensExportStarter : ApplicationStarter {

    private val log = logger<OneLensExportStarter>()

    // commandName is intentionally NOT overridden: the modern platform reads
    // the command name from the `id` attribute on `<appStarter>` in plugin.xml
    // (getCommandName() is @Deprecated with that exact message). Keeping the
    // XML as the source of truth also means renaming the command is a one-line
    // XML edit, not a recompile. See plugin.xml: <appStarter id="onelens-export" .../>.

    // Headless: no Swing UI. A headless app still pumps an EDT (it's not
    // "no EDT"), so invokeLater works; we use it only to dispatch, then move
    // the blocking waitForSmartMode/exportFull onto a pooled thread to avoid
    // self-deadlock (see main()).
    override val isHeadless: Boolean = true

    @Suppress("overriding_deprecated") // main(List<String>) is the entry contract; no non-deprecated alternative exists.
    override fun main(args: List<String>) {
        // ENTRY LOG — without this, dispatch success is unfalsifiable from
        // idea.log (the bootstrap logger logs argv for every launch, including
        // unknown commands, so "args: onelens-export …" alone proves nothing).
        log.info("onelens-export: main entered with ${args.size} arg(s): ${args.drop(1)}")
        println("onelens-export: dispatch confirmed, starting…")

        val opts = parse(args) ?: run {
            // parse() already printed usage to stderr.
            log.warn("onelens-export: argument parse failed; exiting")
            ApplicationManager.getApplication().exit()
            return
        }
        log.info("onelens-export: parsed project=${opts.projectPath} output=${opts.outputDir}")

        // Hop to EDT only to dispatch, then run the blocking sequence on a
        // pooled thread. Calling waitForSmartMode() on the EDT risks
        // self-deadlock: Gradle-import / scanning publishes dumb-mode
        // transitions via EDT callbacks, and blocking the EDT in
        // waitForSmartMode can stall the very machinery that ends dumb mode
        // (observed symptom: run hangs on heavy-Gradle projects until kill).
        // exportFull's collectors are PSI readers wrapped in ReadAction; they
        // don't require the EDT.
        ApplicationManager.getApplication().invokeLater({
            ApplicationManager.getApplication().executeOnPooledThread {
                runExport(opts)
            }
        }, ModalityState.nonModal())
    }

    private fun runExport(opts: Options) {
        val project = try {
            log.info("onelens-export: loadAndOpenProject(${opts.projectPath})")
            // loadAndOpenProject works headless — it's the same API Qodana
            // uses. Returns Project?; throws on bad path / unreadable .idea.
            ProjectManager.getInstance().loadAndOpenProject(opts.projectPath.toString())
        } catch (e: Exception) {
            log.error("onelens-export: loadAndOpenProject threw: ${e.message}", e)
            System.err.println("onelens-export: failed to open project '${opts.projectPath}': ${e.message}")
            ApplicationManager.getApplication().exit()
            return
        }

        if (project == null) {
            log.error("onelens-export: loadAndOpenProject returned null for ${opts.projectPath}")
            System.err.println("onelens-export: loadAndOpenProject returned null for '${opts.projectPath}'")
            ApplicationManager.getApplication().exit()
            return
        }
        log.info("onelens-export: project opened: ${project.name}")

        // External-system (Maven/Gradle) resolve — wait for the model to be applied.
        val resolveDone = waitForExternalSystemResolve(project)
        try { resolveDone.await(EXT_RESOLVE_TIMEOUT_SEC.toLong(), java.util.concurrent.TimeUnit.SECONDS) }
        catch (_: InterruptedException) { Thread.currentThread().interrupt() }

        // CRITICAL indexing gate. The index must be FULLY built (all roots)
        // before any collector runs. If even one file isn't indexed, those
        // classes silently disappear from the graph.
        log.info("onelens-export: waiting for index populated…")
        waitForVfsRootVisible(project)
        waitForStubIndexPopulated(project)

        // After the external-system resolve completes, the post-import reindex
        // may have invalidated the stub index. Re-wait for smart mode + re-gate
        // so collectors see the final, consistent index state.
        log.info("onelens-export: external-system resolve done; re-gating index…")
        DumbService.getInstance(project).waitForSmartMode()
        waitForStubIndexPopulated(project)

        // ── Sibling workspace roots: force index coverage ──
        //
        // Maven registered sibling modules (106+ with source roots), but
        // IntelliJ's stub index hasn't scanned their files yet. We request
        // reindex on each sibling source root, then re-gate. This must happen
        // AFTER the primary index is stable.
        indexSiblingModuleRoots(project)
        DumbService.getInstance(project).waitForSmartMode()
        waitForStubIndexPopulated(project)

        // If an external-system resolve was in flight, block until it
        // completes, then re-gate: the resolve invalidates + rebuilds the
        // stub index, so the gate above may have read a stale pre-resolve
        // state. This is the load-bearing close for the warm-cache race.
        if (resolveDone.await(EXT_RESOLVE_TIMEOUT_SEC.toLong(), java.util.concurrent.TimeUnit.SECONDS)) {
            log.info("onelens-export: external-system RESOLVE_PROJECT completed; re-gating index")
            DumbService.getInstance(project).waitForSmartMode()
            waitForStubIndexPopulated(project)
        } else {
            log.info("onelens-export: no external-system resolve observed (non-Maven/Gradle project); proceeding")
        }
        // One more smart-mode pass — belt-and-suspenders against late
        // dumb-mode transitions before the collector runs.
        DumbService.getInstance(project).waitForSmartMode()
        log.info("onelens-export: index ready")

        val config = ExportConfig(
            outputPath = opts.outputDir,
            // JSON-only path: do not shell out to onelens CLI or probe
            // FalkorDB. The export file is the deliverable; import is a
            // separate `onelens call-tool onelens_import` step.
            autoImport = false,
            // Embeddings are the Python side's job (onelens_import --context).
            buildSemanticIndex = false,
        )

        // --- Branch: full export vs delta export ---
        //
        // Delta mode: load the previous export's commit from the cross-JVM
        // state file (~/.onelens/graphs/<graphId>/.onelens-lastexport) into
        // ExportState so DeltaTracker can git-diff against it. If no previous
        // state exists (first export), fall back to full export.
        //
        // Full mode: export everything, then persist the state file so the
        // next --delta run can diff from here.
        val graphId = WorkspaceLoader.load(project).graphId
        val exportState = ExportState.getInstance(project)

        val exitCode: Int = if (opts.delta) {
            runDeltaExport(project, config, graphId, exportState)
        } else {
            runFullExport(project, config, graphId, exportState)
        }

        // The exit code is already determined by the export branch above.
        log.info("onelens-export: requesting graceful Application.exit()")

        // closeAndDispose can throw if an external-system import (Maven/Gradle)
        // is still mid-flight — non-fatal since the export already wrote.
        try {
            ProjectManager.getInstance().closeAndDispose(project)
        } catch (e: Exception) {
            log.warn("onelens-export: closeAndDispose threw (non-fatal, export already complete): ${e.message}")
        }

        // Shutdown contract:
        //   PRIMARY  = Application.exit() — graceful lifecycle shutdown that
        //              flushes index/VFS/state. Should terminate the JVM under
        //              normal conditions.
        //   WATCHDOG = exitProcess after SHUTDOWN_WATCHDOG_SEC, ONLY if the
        //              primary path didn't exit. Catches the Gradle-JavaExec
        //              case where non-daemon threads keep the JVM alive.
        Thread({
            try {
                Thread.sleep(SHUTDOWN_WATCHDOG_SEC * 1000L)
                log.warn(
                    "onelens-export: WATCHDOG — JVM did not exit within ${SHUTDOWN_WATCHDOG_SEC}s of " +
                        "Application.exit(); forcing exitProcess($exitCode). This indicates a non-daemon " +
                        "thread kept the JVM alive (likely a Gradle-JavaExec worker); report if it fires " +
                        "outside Gradle."
                )
                kotlin.system.exitProcess(exitCode)
            } catch (_: InterruptedException) {
                // Graceful exit terminated this thread — expected, nothing to do.
            }
        }, "onelens-exit-watchdog").apply { isDaemon = true; start() }
        ApplicationManager.getApplication().exit()
    }

    /**
     * Run a full export. After success, persist the export state (git commit +
     * file→classes map) to `~/.onelens/graphs/<graphId>/.onelens-lastexport`
     * so the next `--delta` run can diff from here.
     *
     * @return exit code (0 = success, 1 = error)
     */
    private fun runFullExport(
        project: Project,
        config: ExportConfig,
        graphId: String,
        exportState: ExportState,
    ): Int {
        val service = ApplicationManager.getApplication().getService(ExportService::class.java)
        log.info("onelens-export: calling ExportService.exportFull …")
        val started = System.currentTimeMillis()
        val result = service.exportFull(project, config, indicator = null)
        val elapsed = (System.currentTimeMillis() - started) / 1000.0

        return when (result) {
            is ExportService.ExportResult.Success -> {
                val s = result.stats
                log.info(
                    "onelens-export: exportFull OK in ${elapsed}s — " +
                        "${s.classCount} classes, ${s.methodCount} methods, " +
                        "${s.callEdgeCount} calls, ${s.endpointCount} endpoints → ${result.path}"
                )
                println(
                    "onelens-export: wrote ${result.path} " +
                        "(${s.classCount} classes, ${s.methodCount} methods, " +
                        "${s.callEdgeCount} calls, ${s.endpointCount} endpoints) in ${elapsed}s"
                )
                // Persist state for the next --delta run.
                HeadlessExportState.saveFrom(graphId, exportState)
                0
            }
            is ExportService.ExportResult.Error -> {
                log.error("onelens-export: exportFull error: ${result.message}")
                System.err.println("onelens-export: ${result.message}")
                1
            }
        }
    }

    /**
     * Run a delta export — only changes since the last export.
     *
     * Loads the previous export state from `~/.onelens/graphs/<graphId>/.onelens-lastexport`
     * into ExportState, then calls DeltaExportService.exportDelta(). If no
     * previous state exists, falls back to a full export.
     *
     * @return exit code (0 = success, 1 = error)
     */
    private fun runDeltaExport(
        project: Project,
        config: ExportConfig,
        graphId: String,
        exportState: ExportState,
    ): Int {
        log.info("onelens-export: --delta mode, loading previous export state…")

        val hasPrevious = HeadlessExportState.loadInto(graphId, exportState)
        if (!hasPrevious) {
            log.info("onelens-export: no previous export state — falling back to full export")
            println("onelens-export: no previous export found, running full export instead")
            return runFullExport(project, config, graphId, exportState)
        }

        log.info(
            "onelens-export: previous export loaded (commit=${exportState.state.lastGitHash.take(7)}, " +
                "fileHashes=${exportState.state.fileHashes.size} entries)"
        )

        val started = System.currentTimeMillis()
        val result = DeltaExportService.exportDelta(project, config)
        val elapsed = (System.currentTimeMillis() - started) / 1000.0

        return when (result) {
            is DeltaResult.Success -> {
                val s = result.stats
                log.info(
                    "onelens-export: delta OK in ${elapsed}s — " +
                        "${s.changedFileCount} changed files, ${s.upsertedClassCount} upserted classes, " +
                        "${s.deletedClassCount} deleted classes, ${s.upsertedCallEdgeCount} call edges → ${result.path}"
                )
                println(
                    "onelens-export: wrote ${result.path} " +
                        "(${s.changedFileCount} changed, ${s.upsertedClassCount} upserted, " +
                        "${s.deletedClassCount} deleted, ${s.upsertedCallEdgeCount} calls) in ${elapsed}s"
                )
                HeadlessExportState.saveFrom(graphId, exportState)
                0
            }
            is DeltaResult.NoChanges -> {
                log.info("onelens-export: no changes detected since last export")
                println("onelens-export: no changes since last export — nothing to write")
                0
            }
            is DeltaResult.NeedFullExport -> {
                log.info("onelens-export: delta needs full export: ${result.reason}")
                println("onelens-export: full export needed (${result.reason}), running…")
                runFullExport(project, config, graphId, exportState)
            }
            is DeltaResult.Error -> {
                log.error("onelens-export: delta error: ${result.message}")
                System.err.println("onelens-export: delta error: ${result.message}")
                1
            }
        }
    }

    /** Parsed command-line options. */
    private data class Options(
        val projectPath: Path,
        val outputDir: Path,
        val delta: Boolean = false,
    )

    private fun parse(args: List<String>): Options? {
        // args[0] is the command name ("onelens-export"); flags follow.
        var projectPath: Path? = null
        var outputDir: Path? = null
        var delta = false
        val i = args.listIterator(1)
        while (i.hasNext()) {
            when (val flag = i.next()) {
                "--project" -> projectPath = i.nextString("--project")?.let { Paths.get(it) }
                "--output-dir" -> outputDir = i.nextString("--output-dir")?.let { Paths.get(it) }
                "--delta" -> delta = true
                "-h", "--help" -> { printUsage(); return null }
                else -> {
                    System.err.println("onelens-export: unknown flag '$flag'")
                    printUsage()
                    return null
                }
            }
        }
        val project = projectPath
        if (project == null || !java.nio.file.Files.isDirectory(project)) {
            System.err.println("onelens-export: --project <dir> is required and must exist")
            printUsage()
            return null
        }
        val output: Path = outputDir
            ?: Paths.get(System.getProperty("user.home"), ".onelens", "exports")
        return Options(projectPath = project, outputDir = output, delta = delta)
    }

    /**
     * Force re-index of sibling workspace source roots.
     *
     * When [MavenHeadlessImport] adds sibling repo poms via `addManagedFiles`,
     * IntelliJ creates modules for them but the stub index doesn't immediately
     * scan their source roots. This method finds all module source roots that
     * are OUTSIDE the project base path (i.e. sibling repos) and requests a
     * re-index via `FileBasedIndex.requestReindex()`. The subsequent
     * `waitForSmartMode` + `waitForStubIndexPopulated` gates then ensure the
     * index is populated before collectors run.
     */
    /**
     * Request reindex of sibling modules' source roots.
     *
     * After Maven registers sibling workspace modules (via addManagedFiles),
     * the modules exist with source roots, but IntelliJ's stub index hasn't
     * scanned those files yet. `requestReindex` marks them dirty so the next
     * dumb-mode pass indexes them. Called AFTER the primary index is stable
     * to avoid invalidating primary entries.
     */
    private fun indexSiblingModuleRoots(project: Project) {
        val basePath = project.basePath?.replace('\\', '/')?.trimEnd('/') ?: return
        val fileBasedIndex = com.intellij.util.indexing.FileBasedIndex.getInstance()
        var count = 0

        ReadAction.run<Throwable> {
            for (module in com.intellij.openapi.module.ModuleManager.getInstance(project).modules) {
                val rootManager = com.intellij.openapi.roots.ModuleRootManager.getInstance(module)
                for (srcRoot in rootManager.sourceRoots) {
                    val rootPath = srcRoot.path.replace('\\', '/')
                    // Only re-index roots OUTSIDE the project base (siblings).
                    if (!rootPath.startsWith("$basePath/")) {
                        try {
                            fileBasedIndex.requestReindex(srcRoot)
                            count++
                        } catch (e: Exception) {
                            log.warn("onelens-export: reindex failed for $rootPath: ${e.message}")
                        }
                    }
                }
            }
        }
        if (count > 0) {
            log.info("onelens-export: requested reindex of $count sibling module source root(s)")
        }
    }

    private fun ListIterator<String>.nextString(flagName: String): String? {
        if (!hasNext()) {
            System.err.println("onelens-export: $flagName requires a value")
            return null
        }
        return next()
    }

    private fun printUsage() {
        System.err.println(
            """
            usage: idea.sh onelens-export --project <path> [--output-dir <path>] [--delta]

              --project      Path to the IntelliJ/Spring project to export (required)
              --output-dir   Where to write the export JSON (default: ~/.onelens/exports)
              --delta        Export only changes since the last export (git-diff based).
                             Falls back to full export if no previous export state exists.
                             The last-export commit is persisted to
                             ~/.onelens/graphs/<graphId>/.onelens-lastexport so successive
                             headless runs can diff.

            Without --delta: writes <graphId>-full-<timestamp>.json
            With --delta:    writes <graphId>-delta-<timestamp>.json

            Import separately via:
              onelens call-tool onelens_import --export-path <json> --graph <name>
            """.trimIndent()
        )
    }

    /**
     * Dump modules, content roots, source roots, and SDK to the log so the
     * "0 classes" failure mode is debuggable. If source roots are empty, no
     * amount of waiting will populate the stub index — the module must
     * declare source roots for ClassCollector to find anything.
     */
    private fun dumpProjectStructure(project: com.intellij.openapi.project.Project) {
        try {
            val moduleManager = com.intellij.openapi.module.ModuleManager.getInstance(project)
            val sb = StringBuilder("onelens-export: project structure dump —\n")
            for (module in moduleManager.modules) {
                sb.append("  module '${module.name}' type=${module.moduleTypeName ?: "<null>"}\n")
                val roots = com.intellij.openapi.roots.ModuleRootManager.getInstance(module)
                sb.append("    sdk=${roots.sdk?.name ?: "<none>"}\n")
                sb.append("    content roots:\n")
                for (root in roots.contentRoots) {
                    sb.append("      ${root.path}\n")
                }
                sb.append("    source roots:\n")
                for (entry in roots.sourceRoots) {
                    sb.append("      ${entry.path}\n")
                }
                val order = roots.orderEntries
                sb.append("    order entries: ${order.size}\n")
            }
            sb.append("  project.basePath = ${project.basePath}\n")
            // Probe the workspace scope that ClassCollector relies on — this
            // is the #1 cause of "Found N names, Collected 0" (the scope is
            // EMPTY_SCOPE because LocalFileSystem didn't cache the root).
            try {
                val ws = com.onelens.plugin.framework.workspace.WorkspaceLoader.load(project)
                sb.append("  workspace.roots = ${ws.roots.map { it.path }}\n")
                val scope = ws.scope(project)
                sb.append("  workspace.scope = $scope (isEmpty=${scope === com.intellij.psi.search.GlobalSearchScope.EMPTY_SCOPE})\n")
            } catch (e: Exception) {
                sb.append("  workspace probe failed: ${e.message}\n")
            }
            log.info(sb.toString())
        } catch (e: Exception) {
            log.warn("onelens-export: structure dump failed: ${e.message}")
        }
    }

    /**
     * Block until the project's source classes are resolvable via the stub
     * index AND the resolution is STABLE across a smart-mode cycle.
     *
     * Why "stable" matters: a single successful `findClass` is NOT enough.
     * Maven/Gradle external-system import fires asynchronously and, when it
     * applies the imported module model, can invalidate the stub index for
     * source files (the source-root-to-index association changes). Observed
     * on a warm-cache Spring Boot run: sentinel resolved at T, Maven import
     * finished at T+2s, export ran at T+4s → `Collected 0` because the
     * source files' stubs were invalidated by the import and not yet rebuilt.
     *
     * Fix: resolve sentinel → waitForSmartMode → resolve sentinel AGAIN. Only
     * exit if both probes succeed AND the workspace scope is non-empty. The
     * second probe catches any invalidation the smart-mode cycle introduced.
     *
     * Also: PSI index reads throw [IndexNotReadyException] during dumb mode
     * rather than returning empty — caught here and treated as "not ready".
     */
    private fun waitForStubIndexPopulated(project: com.intellij.openapi.project.Project) {
        // DIAGNOSTIC: dump what the platform actually sees so the "0 classes"
        // failure mode is debuggable. Opt-in via ONELENS_DEBUG=1 — off by
        // default so it doesn't run (and log) on every CI export.
        if (debugEnabled()) dumpProjectStructure(project)

        val sentinelFqn = firstJavaClassFqn(project)
        if (sentinelFqn == null) {
            log.info("onelens-export: no .java sentinel found; relying on smart-mode gate only")
            return
        }
        log.info("onelens-export: waiting for stub index to stably resolve '$sentinelFqn'…")
        val deadline = System.currentTimeMillis() + TIMEOUT_SEC * 1000L
        val scope = com.intellij.psi.search.GlobalSearchScope.allScope(project)
        val facade = com.intellij.psi.JavaPsiFacade.getInstance(project)
        val namesCache = com.intellij.psi.search.PsiShortNamesCache.getInstance(project)
        var stable = false
        var stableChecks = 0
        while (System.currentTimeMillis() < deadline) {
            var resolved: com.intellij.psi.PsiClass? = null
            var namesCount = 0
            try {
                resolved = com.intellij.openapi.application.ReadAction.compute<com.intellij.psi.PsiClass?, Throwable> {
                    facade.findClass(sentinelFqn, scope)
                }
                namesCount = com.intellij.openapi.application.ReadAction.compute<Int, Throwable> {
                    namesCache.allClassNames.size
                }
            } catch (e: com.intellij.openapi.project.IndexNotReadyException) {
                // Expected during dumb mode.
            }
            if (resolved != null && namesCount > 0) {
                DumbService.getInstance(project).waitForSmartMode()
                try {
                    val reResolved = com.intellij.openapi.application.ReadAction.compute<com.intellij.psi.PsiClass?, Throwable> {
                        facade.findClass(sentinelFqn, scope)
                    }
                    if (reResolved != null) {
                        stableChecks++
                        if (stableChecks >= 2) {
                            log.info("onelens-export: stub index stable ('$sentinelFqn' resolves, $namesCount names, $stableChecks stable checks)")
                            stable = true
                            break
                        }
                        Thread.sleep(500)
                        continue
                    }
                } catch (e: com.intellij.openapi.project.IndexNotReadyException) {
                    stableChecks = 0
                }
            }
            DumbService.getInstance(project).waitForSmartMode()
            Thread.sleep(300)
        }
        if (!stable) {
            // SEVERE (not warn): a CI feature whose value prop is determinism
            // should surface gate timeouts loudly. The export still proceeds
            // (better partial than nothing), but this log line + the stderr
            // line below are greppable from CI to detect flaky runs that
            // would otherwise silently degrade to "0 classes".
            log.error(
                "onelens-export: GATE TIMEOUT after ${TIMEOUT_SEC}s waiting for '$sentinelFqn' " +
                    "to stably resolve. Proceeding, but export is likely incomplete (check class count)."
            )
            System.err.println(
                "onelens-export: WARNING — gate timeout (${TIMEOUT_SEC}s); " +
                    "export may be incomplete."
            )
        }
    }

    /**
     * Subscribe to external-system resolve notifications and return a
     * [java.util.concurrent.CountDownLatch] that counts down when the
     * external-system import+resolve completes.
     *
     * Covers BOTH build systems via their respective completion events:
     *   - **Gradle** → unified `ExternalSystemProgressNotificationManager`,
     *     `onEnd` with `ExternalSystemTaskType.RESOLVE_PROJECT`.
     *   - **Maven** → Maven's OWN message-bus topic `MavenImportListener.TOPIC`
     *     with `importFinished` (Maven does NOT publish through the unified
     *     external-system bus — it predates that framework — so the unified
     *     listener alone never fires for Maven projects; this was the bug in
     *     the first attempt). Resolved reflectively because the Maven plugin
     *     is optional/bundled separately.
     *
     * This is the REAL fix for the "0 classes on warm cache" race: we wait
     * for the platform's own completion event, not a proxy index probe.
     *
     * Caller contract: register BEFORE any index work (so an early-completing
     * import is still caught if it re-fires), then await the latch with a
     * bounded timeout. Non-Maven/Gradle projects fire neither event → the
     * await times out and we proceed on the index-only gate (no hang).
     */
    private fun waitForExternalSystemResolve(
        project: com.intellij.openapi.project.Project
    ): java.util.concurrent.CountDownLatch {
        val latch = java.util.concurrent.CountDownLatch(1)

        // --- Gradle: unified external-system bus ---
        try {
            val bus = com.intellij.openapi.externalSystem.service.notification
                .ExternalSystemProgressNotificationManager.getInstance()
            val listener = object :
                com.intellij.openapi.externalSystem.model.task.ExternalSystemTaskNotificationListener {
                override fun onEnd(id: com.intellij.openapi.externalSystem.model.task.ExternalSystemTaskId) {
                    if (id.type == com.intellij.openapi.externalSystem.model.task.ExternalSystemTaskType.RESOLVE_PROJECT) {
                        val taskProject = id.findProject()
                        if (taskProject == null || taskProject == project) {
                            log.info("onelens-export: Gradle RESOLVE_PROJECT ended (id=$id)")
                            latch.countDown()
                        }
                    }
                }
            }
            bus.addNotificationListener(listener, com.intellij.openapi.util.Disposer.newDisposable())
            log.info("onelens-export: subscribed to Gradle external-system resolve notifications")
        } catch (e: Throwable) {
            log.warn("onelens-export: external-system (Gradle) subscription failed: ${e.message}")
        }

        // --- Maven: typed adapter via optional <depends> ---
        // The Maven plugin uses its OWN message-bus topic (MavenImportListener.TOPIC)
        // — NOT the unified external-system bus above — because it predates the
        // unified framework. MavenHeadlessImport (in headless/maven/, compiled
        // against the Maven plugin classes via the optional maven-headless.xml
        // <depends> + platformBundledPlugins classpath) handles subscription +
        // forced pom discovery + import kickoff with fully-typed API references.
        // We merge its latch into ours by counting ours down when Maven's fires.
        // No-op if the Maven plugin isn't installed (Gradle / plain-Java).
        if (com.onelens.plugin.headless.maven.MavenHeadlessImport.isAvailable()) {
            try {
                val mavenLatch = com.onelens.plugin.headless.maven.MavenHeadlessImport.awaitImport(project)
                Thread {
                    try {
                        if (mavenLatch.await(EXT_RESOLVE_TIMEOUT_SEC.toLong(), java.util.concurrent.TimeUnit.SECONDS)) {
                            latch.countDown()
                        } else {
                            log.error("onelens-export: Maven import latch timed out — proceeding, export may be incomplete")
                        }
                    } catch (_: InterruptedException) {}
                }.apply { isDaemon = true; name = "onelens-maven-wait"; start() }
            } catch (e: Throwable) {
                log.warn("onelens-export: Maven import adapter threw: ${e.message}")
            }
        } else {
            log.info("onelens-export: Maven plugin not available; Maven path skipped")
        }

        return latch
    }

    /**
     * Ensure the VFS knows the project root directory. If
     * [com.intellij.openapi.vfs.LocalFileSystem.findFileByPath] returns null
     * for the root, [com.onelens.plugin.framework.workspace.Workspace.scope]
     * gets an empty `rootDirs` array and returns `EMPTY_SCOPE` → every class
     * is filtered out by `workspace.contains(file.path)` → `0 classes` even
     * with a fully-populated stub index. This happens intermittently on
     * warm-cache runs where the VFS hasn't lazily cached the root.
     *
     * Fix: call `refreshAndFindFileByPath` which forces the VFS to recognize
     * the path, then poll until non-null. This is a directory-existence
     * check, not a content scan, so it does NOT trigger a reindex (unlike
     * `root.refresh(false, true)` which walks the tree and re-enters dumb
     * mode). Safe to call repeatedly.
     */
    private fun waitForVfsRootVisible(project: com.intellij.openapi.project.Project) {
        val basePath = project.basePath ?: return
        val vfs = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
        val deadline = System.currentTimeMillis() + TIMEOUT_SEC * 1000L
        var visible = false
        while (System.currentTimeMillis() < deadline) {
            val root = com.intellij.openapi.application.ReadAction.compute<com.intellij.openapi.vfs.VirtualFile?, Throwable> {
                vfs.refreshAndFindFileByPath(basePath)
            }
            if (root != null && root.isDirectory) { visible = true; break }
            Thread.sleep(200)
        }
        log.info("onelens-export: VFS root ${if (visible) "visible" else "NOT visible after timeout"} ($basePath)")
    }

    /**
     * First fully-qualified class name we can derive from a .java file under
     * the project root, or null if none. Used as the stub-index sentinel.
     * Derivation: package dir path under src/main/java (Maven) or src/ +
     * filename without `.java`. Good enough for a sentinel — we only need ONE
     * class the stub index must have built before ClassCollector runs.
     */
    private fun firstJavaClassFqn(project: com.intellij.openapi.project.Project): String? {
        // Derive the sentinel from the ACTUAL module source roots (what
        // IntelliJ has imported + indexed), NOT the raw filesystem. The
        // filesystem walk would pick files from ignored Maven modules
        // (e.g. aiserver/pom.xml in motadata-itsm-server is in Maven's
        // ignoredFiles list) or worktree copies — classes that will NEVER
        // be in the stub index, causing the gate to wait forever.
        //
        // ModuleRootManager.sourceRoots reflects only the modules IntelliJ
        // actually created from the Maven/Gradle import — ignored modules
        // and excluded paths are filtered out.
        try {
            val moduleManager = com.intellij.openapi.module.ModuleManager.getInstance(project)
            for (module in moduleManager.modules) {
                val roots = com.intellij.openapi.roots.ModuleRootManager.getInstance(module)
                for (srcRoot in roots.sourceRoots) {
                    // Find the first .java file under this source root.
                    val srcPath = java.nio.file.Paths.get(srcRoot.path)
                    if (!java.nio.file.Files.isDirectory(srcPath)) continue
                    val javaFile = java.nio.file.Files.walk(srcPath, 20).use { stream ->
                        stream.filter { it.toString().endsWith(".java") }
                            .findFirst()
                            .map<java.nio.file.Path> { it }
                            .orElse(null)
                    } ?: continue
                    // Derive FQN from the package path under the source root.
                    val rel = srcPath.relativize(javaFile.parent).toString()
                        .replace('\\', '/').replace('/', '.')
                    val cls = javaFile.fileName.toString().removeSuffix(".java")
                    val fqn = if (rel.isEmpty()) cls else "$rel.$cls"
                    log.info("onelens-export: sentinel picked from module '${module.name}' source root $srcRoot → $fqn")
                    return fqn
                }
            }
        } catch (e: Exception) {
            log.warn("onelens-export: module-based sentinel selection failed: ${e.message}")
        }
        // Fallback: raw filesystem walk (pre-fix behavior). Only used if the
        // module manager has no source roots yet (shouldn't happen post-import).
        log.warn("onelens-export: no module source roots found; falling back to filesystem sentinel")
        val base = project.basePath?.let { java.nio.file.Paths.get(it) } ?: return null
        if (!java.nio.file.Files.isDirectory(base)) return null
        val excluded = setOf("/build/", "/target/", "/node_modules/", "/.gradle/", "/out/", "/.claude/worktrees/")
        val javaFile = java.nio.file.Files.walk(base, 20).use { stream ->
            stream.filter { it.toString().endsWith(".java") }
                .filter { p -> excluded.none { p.toString().contains(it) } }
                .findFirst()
                .map<java.nio.file.Path> { it }
                .orElse(null)
        } ?: return null
        val segs = javaFile.parent.toString().split('/')
        val pkgStart = segs.indexOfLast { it == "java" || it == "src" || it == "kotlin" }
        val pkg = if (pkgStart >= 0 && pkgStart + 1 < segs.size) {
            segs.subList(pkgStart + 1, segs.size).joinToString(".")
        } else ""
        val cls = javaFile.fileName.toString().removeSuffix(".java")
        return if (pkg.isEmpty()) cls else "$pkg.$cls"
    }

    companion object {
        /**
         * Max seconds to wait for the stub index to stably resolve the sentinel
         * class. Default 180s (3 min) covers most projects. For very large
         * codebases (10K+ files, cold cache), override via the
         * `ONELENS_INDEX_TIMEOUT_SEC` env var — e.g. a 45K-file enterprise
         * app cold-index can take 5-8 minutes.
         */
        val TIMEOUT_SEC: Int = System.getenv("ONELENS_INDEX_TIMEOUT_SEC")?.toIntOrNull() ?: 180
        /** Max wait for an external-system (Maven/Gradle) RESOLVE_PROJECT task. */
        val EXT_RESOLVE_TIMEOUT_SEC: Int = System.getenv("ONELENS_RESOLVE_TIMEOUT_SEC")?.toIntOrNull() ?: 240
        /**
         * Watchdog: max seconds to wait for graceful `Application.exit()` to
         * terminate the JVM before forcing `exitProcess`. Generous on purpose
         * — closeAndDispose + VFS/index flush on a large project can take
         * tens of seconds, and we only want to fire when something is wedged.
         */
        const val SHUTDOWN_WATCHDOG_SEC = 60

        /** Opt-in verbose diagnostics (structure dump, etc.). Off by default. */
        fun debugEnabled(): Boolean =
            System.getenv("ONELENS_DEBUG")?.let { it == "1" || it.equals("true", ignoreCase = true) } ?: false
    }
}
