package com.onelens.plugin.export

import com.intellij.openapi.diagnostic.logger
import java.io.File
import java.nio.file.Path
import java.nio.file.Paths

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
    private val ONELENS_BIN: Path = VENV_DIR.resolve("bin").resolve("onelens")

    /**
     * Get the path to the onelens CLI, auto-installing if needed.
     * Returns the path to the binary, or null if setup failed.
     */
    fun getOneLensCli(onelensSourcePath: String = ""): String? {
        // Already installed?
        if (ONELENS_BIN.toFile().exists()) {
            return ONELENS_BIN.toString()
        }

        LOG.info("OneLens CLI not found, setting up environment...")
        return setup(onelensSourcePath)
    }

    /**
     * Check if the environment is ready.
     */
    fun isReady(): Boolean = ONELENS_BIN.toFile().exists()

    /**
     * Create venv and install onelens.
     */
    private fun setup(onelensSourcePath: String): String? {
        val homeDir = ONELENS_HOME.toFile()
        homeDir.mkdirs()

        // 1. Create venv using uv (fast) or python -m venv (fallback)
        if (!createVenv()) {
            return null
        }

        // 2. Install onelens package
        if (!installOneLens(onelensSourcePath)) {
            return null
        }

        // 3. Verify
        if (ONELENS_BIN.toFile().exists()) {
            LOG.info("OneLens CLI ready at: $ONELENS_BIN")
            return ONELENS_BIN.toString()
        }

        LOG.warn("OneLens CLI not found after install")
        return null
    }

    private fun createVenv(): Boolean {
        val venvDir = VENV_DIR.toFile()
        if (venvDir.exists()) return true

        // Try uv first (check common locations since IntelliJ PATH may differ from shell)
        val uvBin = findUv()
        if (uvBin != null && runCommand(listOf(uvBin, "venv", venvDir.absolutePath), ONELENS_HOME.toFile())) {
            LOG.info("Created venv with uv at $uvBin")
            return true
        }

        // Fallback to python -m venv (check common locations)
        for (python in findPythonCandidates()) {
            if (runCommand(listOf(python, "-m", "venv", venvDir.absolutePath), ONELENS_HOME.toFile())) {
                LOG.info("Created venv with $python")
                return true
            }
        }

        LOG.error("Failed to create venv — neither uv nor python found")
        return false
    }

    private fun installOneLens(sourcePath: String): Boolean {
        val pip = VENV_DIR.resolve("bin").resolve("pip").toString()
        val uvBin = findUv()

        // Install with [context] extra so ChromaDB + Qwen3 embedder + mxbai
        // reranker are available out of the box. Without this, `onelens retrieve`
        // and `context_search` silently fall back / fail. Adds ~1 GB to venv
        // (torch + transformers) but unlocks semantic search.
        val extras = "[context]"
        val packageSpec = if (sourcePath.isNotEmpty() && File(sourcePath).exists()) {
            // Editable dev install: use the local path unchanged. pip accepts
            // `-e path` but not `-e path[context]` syntax cleanly across
            // versions; rely on pyproject.toml [project.optional-dependencies]
            // and install the extra separately.
            sourcePath
        } else {
            "onelens$extras"  // PyPI with context extra
        }

        val venvPython = VENV_DIR.resolve("bin").resolve("python").toString()
        // For local/editable installs (dev mode), pip accepts `path[extra]`
        // syntax in recent versions. If sourcePath is provided, also install
        // the [context] extra explicitly so chromadb + embedder deps land.
        val isDev = sourcePath.isNotEmpty() && File(sourcePath).exists()
        val devExtras = if (isDev) "chromadb>=1.0.0" else null

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
        return try {
            val process = ProcessBuilder("which", "uv")
                .redirectErrorStream(true)
                .start()
            val path = process.inputStream.bufferedReader().readText().trim()
            process.waitFor()
            if (process.exitValue() == 0 && path.isNotEmpty()) path else null
        } catch (_: Exception) {
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

    private fun runCommand(command: List<String>, workDir: File): Boolean {
        return try {
            LOG.info("Running: ${command.joinToString(" ")}")
            val process = ProcessBuilder(command)
                .directory(workDir)
                .redirectErrorStream(true)
                .start()
            val output = process.inputStream.bufferedReader().readText()
            val exitCode = process.waitFor()
            if (exitCode != 0) {
                LOG.debug("Command failed (exit $exitCode): $output")
            }
            exitCode == 0
        } catch (e: Exception) {
            LOG.debug("Command failed: ${e.message}")
            false
        }
    }
}
