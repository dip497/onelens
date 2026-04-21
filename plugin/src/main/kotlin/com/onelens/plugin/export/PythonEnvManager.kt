package com.onelens.plugin.export

import com.intellij.openapi.diagnostic.logger
import com.onelens.plugin.ui.OneLensEvents
import com.onelens.plugin.ui.OneLensState
import java.io.File
import java.net.JarURLConnection
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardCopyOption

/**
 * Manages a self-contained Python venv with onelens installed via uv.
 *
 * On first use, creates ~/.onelens/venv and installs the onelens package.
 * Uses `uv` for fast installs (falls back to pip if uv not found).
 *
 * Layout:
 *   ~/.onelens/
 *     venv/           ← auto-created
 *       bin/onelens   ← CLI entry point
 *     graphs/         ← FalkorDBLite data
 *     exports/        ← JSON exports
 */
object PythonEnvManager {

    private val LOG = logger<PythonEnvManager>()

    private val ONELENS_HOME: Path = Paths.get(System.getProperty("user.home"), ".onelens")
    private val VENV_DIR: Path = ONELENS_HOME.resolve("venv")

    /** Path to the venv python binary — callers use it to spawn onelens CLI
     * or the MCP server child. Always points at the managed venv even when
     * the binary doesn't yet exist (e.g. pre-first-sync). */
    fun getVenvPython(): java.io.File =
        VENV_DIR.resolve("bin").resolve("python").toFile()
    private val ONELENS_BIN: Path = VENV_DIR.resolve("bin").resolve("onelens")
    // Extracted Python source lives here; keyed by plugin version so a plugin
    // upgrade rewrites the tree and triggers a reinstall.
    private val BUNDLED_SOURCE_DIR: Path = ONELENS_HOME.resolve("source")

    /**
     * Get the path to the onelens CLI, auto-installing if needed.
     * Returns the path to the binary, or null if setup failed.
     */
    fun getOneLensCli(onelensSourcePath: String = ""): String? {
        // Already installed AND matches current plugin version?
        // After a plugin upgrade the venv is still on disk but its Python
        // source is stale; treat version mismatch as "needs reinstall" so
        // new collectors / CLI changes actually take effect.
        if (ONELENS_BIN.toFile().exists() && installedMatchesPluginVersion()) {
            return ONELENS_BIN.toString()
        }

        LOG.info("OneLens CLI setup required (missing or plugin upgraded)...")
        return setup(onelensSourcePath)
    }

    private fun installedMatchesPluginVersion(): Boolean {
        // Dev-mode override via settings always skips the version check —
        // an editable install in a source tree is always "current".
        val marker = BUNDLED_SOURCE_DIR.resolve(".version").toFile()
        if (!marker.exists()) {
            // No marker means CLI came from somewhere other than a bundled
            // extract (e.g. dev-mode sourcePath or manual install). Trust it.
            return true
        }
        return marker.readText().trim() == pluginVersion()
    }

    /**
     * Check if the environment is ready.
     */
    fun isReady(): Boolean = ONELENS_BIN.toFile().exists()

    /**
     * Create venv and install onelens.
     */
    private fun setup(onelensSourcePath: String): String? {
        OneLensEvents.status(OneLensState.SETTING_UP)
        val homeDir = ONELENS_HOME.toFile()
        homeDir.mkdirs()

        // 1. Create venv using uv (fast) or python -m venv (fallback)
        OneLensEvents.progress("Creating Python venv", 0.1)
        if (!createVenv()) {
            OneLensEvents.error("Failed to create venv — neither uv nor python3 available")
            OneLensEvents.status(OneLensState.ERROR)
            return null
        }

        // 2. Install onelens package — structural layer only (~30 MB).
        //    Semantic stack (chromadb + onnxruntime + numpy, ~80 MB, ~5 min)
        //    installs lazily via installSemanticStack() when the user toggles
        //    Semantic Index ON. Keeps first-sync install under ~30 s for the
        //    common structural-only case.
        OneLensEvents.progress("Installing onelens (structural) ~30 MB", 0.3)
        if (!installOneLens(onelensSourcePath)) {
            OneLensEvents.error("Failed to install onelens — see idea.log for uv output")
            OneLensEvents.status(OneLensState.ERROR)
            return null
        }

        // 3. Verify
        if (ONELENS_BIN.toFile().exists()) {
            LOG.info("OneLens CLI ready at: $ONELENS_BIN")
            OneLensEvents.info("OneLens CLI ready at: $ONELENS_BIN")
            // Best-effort symlink into ~/.local/bin so a bare `onelens` works
            // in external shells (Claude Code terminal, /onelens skill, CI).
            // No-op on failure (Windows without developer mode, read-only FS).
            linkIntoLocalBin()
            OneLensEvents.status(OneLensState.READY)
            return ONELENS_BIN.toString()
        }

        LOG.warn("OneLens CLI not found after install")
        OneLensEvents.error("Install claimed success but CLI binary is missing at $ONELENS_BIN")
        OneLensEvents.status(OneLensState.ERROR)
        return null
    }

    private fun createVenv(): Boolean {
        val venvDir = VENV_DIR.toFile()
        if (venvDir.exists()) return true

        // Try uv first (check common locations since IntelliJ PATH may differ from shell)
        val uvBin = findUv()
        if (uvBin != null && runCommand(listOf(uvBin, "venv", venvDir.absolutePath), ONELENS_HOME.toFile())) {
            LOG.info("Created venv with uv at $uvBin")
            OneLensEvents.info("Created venv with uv ($uvBin) → $venvDir")
            return true
        }

        // Fallback to python -m venv (check common locations)
        for (python in findPythonCandidates()) {
            if (runCommand(listOf(python, "-m", "venv", venvDir.absolutePath), ONELENS_HOME.toFile())) {
                LOG.info("Created venv with $python")
                OneLensEvents.info("Created venv with $python → $venvDir")
                return true
            }
        }

        LOG.error("Failed to create venv — neither uv nor python found")
        return false
    }

    private fun installOneLens(sourcePath: String): Boolean {
        val pip = VENV_DIR.resolve("bin").resolve("pip").toString()
        val uvBin = findUv()

        // Install the structural-only stack. Semantic deps (chromadb +
        // onnxruntime + numpy, ~80 MB, ~5 min on a fresh venv) move to
        // installSemanticStack() — user pays that cost only when they
        // explicitly toggle Semantic Index ON.
        // Resolution order:
        //   1. Explicit dev sourcePath from settings (editable install).
        //   2. Bundled Python source extracted from plugin JAR (default).
        //   3. PyPI fallback (future — not published yet; will fail today).
        val resolvedSource = if (sourcePath.isNotEmpty() && File(sourcePath).exists()) {
            sourcePath
        } else {
            extractBundledSource()?.toString() ?: ""
        }
        val packageSpec = if (resolvedSource.isNotEmpty()) {
            resolvedSource
        } else {
            "onelens"  // PyPI without context extra — structural only
        }

        val venvPython = VENV_DIR.resolve("bin").resolve("python").toString()
        // No second-step install here — semantic deps moved out.
        val devExtras: String? = null

        // Try uv pip install first (10x faster)
        if (uvBin != null) {
            val primary = runCommand(
                listOf(uvBin, "pip", "install", packageSpec, "--python", venvPython),
                ONELENS_HOME.toFile()
            )
            if (primary) {
                if (devExtras != null) {
                    runCommand(
                        listOf(uvBin, "pip", "install", devExtras, "--python", venvPython),
                        ONELENS_HOME.toFile()
                    )
                }
                LOG.info("Installed onelens with uv (context extra included)")
                return true
            }
        }

        // Fallback to regular pip
        if (runCommand(listOf(pip, "install", packageSpec), ONELENS_HOME.toFile())) {
            if (devExtras != null) {
                runCommand(listOf(pip, "install", devExtras), ONELENS_HOME.toFile())
            }
            LOG.info("Installed onelens with pip (context extra included)")
            return true
        }

        LOG.error("Failed to install onelens")
        return false
    }

    /**
     * Extract the Python source tree bundled inside the plugin JAR to
     * `~/.onelens/source/python/` and return that path.
     *
     * Re-extraction is keyed by plugin version: a `.version` marker is
     * written alongside the tree and compared on subsequent runs. A plugin
     * upgrade therefore triggers one re-extract + reinstall; no-op otherwise.
     *
     * Returns null only if the plugin JAR has no bundled python/ directory
     * (should never happen in a shipped plugin — only during dev against a
     * raw `.class` layout). Caller then falls through to PyPI / failure.
     */
    private fun extractBundledSource(): Path? {
        val currentVersion = pluginVersion()
        val pythonDir = BUNDLED_SOURCE_DIR.resolve("python")
        val versionMarker = BUNDLED_SOURCE_DIR.resolve(".version")

        // Fast path: already extracted for this version.
        if (pythonDir.toFile().exists()
            && versionMarker.toFile().exists()
            && versionMarker.toFile().readText().trim() == currentVersion
        ) {
            LOG.info("Bundled Python source already extracted for plugin $currentVersion")
            return pythonDir
        }

        // Locate the bundled resource root. We use a sentinel file inside
        // the bundle (pyproject.toml) to get a URL into the classpath, then
        // walk sibling entries. Works for both JAR (production) and plain
        // directory (dev) classloaders.
        val sentinel = javaClass.classLoader.getResource("python/pyproject.toml") ?: run {
            LOG.warn("No bundled python/pyproject.toml in plugin JAR — is the plugin built from this repo?")
            return null
        }

        LOG.info("Extracting bundled Python source ($sentinel) → $pythonDir")
        // Wipe any previous extract to avoid stale files lingering after
        // a file is removed from the repo between plugin versions.
        if (BUNDLED_SOURCE_DIR.toFile().exists()) {
            BUNDLED_SOURCE_DIR.toFile().deleteRecursively()
        }
        Files.createDirectories(pythonDir)

        val ok = try {
            when (sentinel.protocol) {
                "jar" -> extractFromJar(sentinel, pythonDir)
                "file" -> extractFromDirectory(sentinel, pythonDir)
                else -> {
                    LOG.warn("Unsupported classpath protocol for bundled source: ${sentinel.protocol}")
                    false
                }
            }
        } catch (e: Exception) {
            LOG.warn("Failed to extract bundled Python source: ${e.message}", e)
            false
        }

        if (!ok) return null

        Files.writeString(versionMarker, currentVersion)
        LOG.info("Bundled Python source extracted for plugin $currentVersion")
        return pythonDir
    }

    private fun extractFromJar(sentinel: java.net.URL, pythonDir: Path): Boolean {
        val conn = sentinel.openConnection() as JarURLConnection
        conn.jarFile.use { jar ->
            val prefix = "python/"
            val entries = jar.entries().toList().filter { it.name.startsWith(prefix) }
            for (entry in entries) {
                val relative = entry.name.removePrefix(prefix)
                if (relative.isEmpty()) continue
                val target = pythonDir.resolve(relative)
                if (entry.isDirectory) {
                    Files.createDirectories(target)
                    continue
                }
                Files.createDirectories(target.parent)
                jar.getInputStream(entry).use { input ->
                    Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING)
                }
            }
        }
        return true
    }

    private fun extractFromDirectory(sentinel: java.net.URL, pythonDir: Path): Boolean {
        // The sentinel's URL points at `.../python/pyproject.toml` on disk;
        // its parent is the bundled python/ root. Copy the tree.
        val sourceRoot = Paths.get(sentinel.toURI()).parent
        Files.walk(sourceRoot).use { stream ->
            for (path in stream) {
                val relative = sourceRoot.relativize(path)
                val target = pythonDir.resolve(relative.toString())
                if (Files.isDirectory(path)) {
                    Files.createDirectories(target)
                } else {
                    Files.createDirectories(target.parent)
                    Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING)
                }
            }
        }
        return true
    }

    private fun pluginVersion(): String = try {
        com.intellij.ide.plugins.PluginManagerCore
            .getPlugin(com.intellij.openapi.extensions.PluginId.getId("com.onelens.plugin"))
            ?.version ?: "unknown"
    } catch (_: Throwable) {
        "unknown"
    }

    private fun findUv(): String? {
        val home = System.getProperty("user.home")

        // Check common locations for uv
        val candidates = listOf(
            "$home/.local/bin/uv",
            "$home/.cargo/bin/uv",
            "/usr/local/bin/uv",
            "/usr/bin/uv",
            "/home/linuxbrew/.linuxbrew/bin/uv",
            "$home/.linuxbrew/bin/uv",
        )

        for (path in candidates) {
            if (File(path).canExecute()) {
                LOG.info("Found uv at $path")
                return path
            }
        }

        // Fallback: try which
        val whichPath = try {
            val process = ProcessBuilder("which", "uv")
                .redirectErrorStream(true)
                .start()
            val path = process.inputStream.bufferedReader().readText().trim()
            process.waitFor()
            if (process.exitValue() == 0 && path.isNotEmpty()) path else null
        } catch (_: Exception) {
            null
        }
        if (whichPath != null) return whichPath

        // Still missing — try to auto-install via the upstream installer so
        // users don't get stuck on the "uv not found" hint. Needs network on
        // first sync; no-op if installer fails (user can then install manually).
        return autoInstallUv()
    }

    /**
     * Best-effort: shell-out to `curl -LsSf https://astral.sh/uv/install.sh | sh`
     * and re-probe. The script lands uv at `~/.local/bin/uv`. We surface
     * progress via OneLensEvents so the sync panel doesn't look hung.
     */
    private fun autoInstallUv(): String? {
        OneLensEvents.progress("Installing uv (first-run, needs internet)", 0.05)
        LOG.info("uv not found; attempting auto-install via astral.sh/uv/install.sh")
        val home = System.getProperty("user.home")
        val target = "$home/.local/bin/uv"
        try {
            val cmd = listOf(
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            )
            val proc = ProcessBuilder(cmd)
                .redirectErrorStream(true)
                .start()
            val out = proc.inputStream.bufferedReader().readText()
            val ok = proc.waitFor() == 0
            if (!ok) {
                LOG.warn("uv auto-install failed: ${out.take(500)}")
                return null
            }
        } catch (e: Throwable) {
            LOG.warn("uv auto-install threw: ${e.message}")
            return null
        }
        return if (File(target).canExecute()) {
            LOG.info("Auto-installed uv at $target")
            target
        } else {
            LOG.warn("uv install script ran but binary not at $target")
            null
        }
    }

    private fun findPythonCandidates(): List<String> {
        val home = System.getProperty("user.home")

        val candidates = mutableListOf<String>()

        // Check common locations
        val paths = listOf(
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/home/linuxbrew/.linuxbrew/bin/python3",
            "$home/.linuxbrew/bin/python3",
            "$home/.local/bin/python3",
        )

        for (path in paths) {
            if (File(path).canExecute()) {
                candidates.add(path)
            }
        }

        // Also try bare names (might be in IntelliJ's PATH)
        candidates.add("python3")
        candidates.add("python")

        return candidates
    }

    /**
     * Run a shell command, streaming each stdout line to the event bus so the
     * tool window log stays live during long installs. Full output is also
     * buffered and logged on failure for diagnostics. Returns exitCode == 0.
     */
    private fun runCommand(command: List<String>, workDir: File): Boolean {
        return try {
            LOG.info("Running: ${command.joinToString(" ")}")
            OneLensEvents.info("\$ ${command.joinToString(" ")}")
            val process = ProcessBuilder(command)
                .directory(workDir)
                .redirectErrorStream(true)
                .start()
            val buffered = StringBuilder()
            process.inputStream.bufferedReader().use { reader ->
                while (true) {
                    val line = reader.readLine() ?: break
                    buffered.appendLine(line)
                    OneLensEvents.info(line)
                }
            }
            val exitCode = process.waitFor()
            if (exitCode != 0) {
                LOG.debug("Command failed (exit $exitCode): $buffered")
                OneLensEvents.warn("Command exit $exitCode: ${command.first()}")
            }
            exitCode == 0
        } catch (e: Exception) {
            LOG.debug("Command failed: ${e.message}")
            OneLensEvents.warn("Command raised: ${e.message}")
            false
        }
    }

    private fun linkIntoLocalBin() {
        val isWindows = System.getProperty("os.name").lowercase().contains("win")
        if (isWindows) return // symlinks need dev-mode / admin; skip silently
        val localBin = Paths.get(System.getProperty("user.home"), ".local", "bin")
        try {
            Files.createDirectories(localBin)
            val link = localBin.resolve("onelens")
            if (Files.isSymbolicLink(link) || Files.exists(link)) {
                Files.delete(link)
            }
            Files.createSymbolicLink(link, ONELENS_BIN)
            LOG.info("Symlinked $link → $ONELENS_BIN")
            OneLensEvents.info("Linked 'onelens' into ~/.local/bin (available in any shell on PATH)")
        } catch (e: Exception) {
            LOG.info("Could not create ~/.local/bin/onelens symlink: ${e.message}")
        }
    }

    /**
     * Lazy install of the semantic stack. Dispatches on OneLensSettings.embedderBackend:
     *   - "modal" / "openai" → just chromadb (~80 MB; remote inference does the heavy lift).
     *   - "local"            → chromadb + onnxruntime-gpu + cuDNN + cuBLAS + tokenizers +
     *                          huggingface_hub (~1 GB). Optional tensorrt-cu12 (+1 GB)
     *                          when localEmbedderUseTRT is on.
     *
     * Called from ToggleSemanticIndexAction. Idempotent — re-running is a
     * no-op once `chromadb` imports in the venv, so switching backends later
     * requires a manual re-install (we don't delete prior wheels).
     */
    fun installSemanticStack(): Boolean {
        if (isSemanticInstalled()) {
            OneLensEvents.info("Semantic stack already installed — skipping")
            return true
        }
        val settings = com.onelens.plugin.settings.OneLensSettings.getInstance().state
        val backend = settings.embedderBackend.lowercase()
        val pkgs: List<String>
        val label: String
        when (backend) {
            "local" -> {
                // Local path ships BOTH embed (Jina v2) AND rerank (BGE base) —
                // onnxruntime reuses the same GPU session for both. TRT is
                // installed separately via installTensorrt() (the button on
                // the Semantic settings screen), so it's absent here even
                // when the user already toggled it on — flipping to "local"
                // the first time requires the base install regardless.
                pkgs = listOf(
                    "chromadb>=1.0.0",
                    "onnxruntime-gpu>=1.20",
                    "nvidia-cudnn-cu12>=9,<10",
                    "nvidia-cublas-cu12",
                    "nvidia-cuda-runtime-cu12",
                    "nvidia-cuda-nvrtc-cu12",
                    "huggingface_hub>=0.24",
                    "tokenizers>=0.20",
                )
                label = "Installing local embedder + reranker (~1 GB: onnxruntime-gpu + CUDA 12, first run only)"
            }
            "openai" -> {
                // Cloud BYOK path — only needs chromadb (vector store) and
                // httpx (bulk-concurrent embedding HTTP). No GPU/CUDA wheels.
                pkgs = listOf("chromadb>=1.0.0", "httpx>=0.27")
                label = "Installing semantic stack (~80 MB: chromadb + httpx — remote inference)"
            }
            else -> {
                pkgs = listOf("chromadb>=1.0.0")
                label = "Installing semantic stack (~80 MB: chromadb — backend=$backend)"
            }
        }
        OneLensEvents.progress(label, 0.1)
        val uvBin = findUv() ?: run {
            OneLensEvents.error("uv not found — cannot install semantic stack")
            return false
        }
        val venvPython = VENV_DIR.resolve("bin").resolve("python").toString()
        val ok = runCommand(
            listOf(uvBin, "pip", "install") + pkgs + listOf("--python", venvPython),
            ONELENS_HOME.toFile(),
        )
        if (ok) {
            OneLensEvents.info("Semantic stack installed (backend=$backend). Re-sync to rebuild the embedding index.")
        } else {
            OneLensEvents.error("Semantic install failed — see idea.log for uv output")
        }
        return ok
    }

    /**
     * Lazy install of TensorRT FP16 acceleration on top of the base local
     * stack. Adds ~1 GB (`tensorrt-cu12`). Called from the "Install
     * TensorRT…" button on the Semantic settings screen. Idempotent.
     *
     * Returns true on success; the caller flips [OneLensSettings.localEmbedderUseTRT]
     * so subsequent syncs (and the screen label) know TRT is live.
     */
    fun installTensorrt(): Boolean {
        if (isTensorrtInstalled()) {
            OneLensEvents.info("TensorRT already installed — skipping")
            return true
        }
        OneLensEvents.progress(
            "Installing TensorRT fp16 acceleration (~1 GB, first run only)",
            0.1,
        )
        val uvBin = findUv() ?: run {
            OneLensEvents.error("uv not found — cannot install TensorRT")
            return false
        }
        val venvPython = VENV_DIR.resolve("bin").resolve("python").toString()
        val ok = runCommand(
            listOf(uvBin, "pip", "install", "tensorrt-cu12>=10", "--python", venvPython),
            ONELENS_HOME.toFile(),
        )
        if (ok) {
            OneLensEvents.info("TensorRT installed. Next sync will use fp16 (~3× faster).")
        } else {
            OneLensEvents.error("TensorRT install failed — see idea.log for uv output")
        }
        return ok
    }

    /**
     * Introspect the managed venv and report which ORT provider the local
     * embedder will pick. Used by the Semantic settings screen to show the
     * user what they're actually running. Returns one of:
     *   "trt-fp16"  — tensorrt importable + onnxruntime-gpu loaded
     *   "cuda-fp32" — onnxruntime-gpu loaded, no TRT
     *   "cpu"       — fallback
     *   "not-installed" — venv missing onnxruntime entirely
     */
    fun detectLocalProvider(): String {
        val py = VENV_DIR.resolve("bin").resolve("python").toFile()
        if (!py.canExecute()) return "not-installed"
        return try {
            // Single subprocess — avoids starting python 3 times.
            val probe = """
                |import importlib, sys
                |try:
                |    import onnxruntime as ort
                |except Exception:
                |    sys.stdout.write('not-installed'); sys.exit(0)
                |try:
                |    importlib.import_module('tensorrt'); sys.stdout.write('trt-fp16'); sys.exit(0)
                |except Exception: pass
                |if 'CUDAExecutionProvider' in ort.get_available_providers():
                |    sys.stdout.write('cuda-fp32')
                |else:
                |    sys.stdout.write('cpu')
            """.trimMargin()
            val p = ProcessBuilder(py.absolutePath, "-c", probe)
                .redirectErrorStream(true)
                .start()
            val out = p.inputStream.bufferedReader().readText().trim()
            p.waitFor()
            if (out.isNotBlank()) out else "not-installed"
        } catch (_: Throwable) {
            "not-installed"
        }
    }

    /** Probe whether tensorrt is importable in the managed venv. */
    fun isTensorrtInstalled(): Boolean {
        val py = VENV_DIR.resolve("bin").resolve("python").toFile()
        if (!py.canExecute()) return false
        return try {
            val p = ProcessBuilder(py.absolutePath, "-c", "import tensorrt")
                .redirectErrorStream(true)
                .start()
            p.waitFor() == 0
        } catch (_: Throwable) {
            false
        }
    }

    /** Probe whether chromadb is importable in the managed venv. */
    fun isSemanticInstalled(): Boolean {
        val py = VENV_DIR.resolve("bin").resolve("python").toFile()
        if (!py.canExecute()) return false
        return try {
            val p = ProcessBuilder(py.absolutePath, "-c", "import chromadb")
                .redirectErrorStream(true)
                .start()
            p.waitFor() == 0
        } catch (_: Throwable) {
            false
        }
    }
}
