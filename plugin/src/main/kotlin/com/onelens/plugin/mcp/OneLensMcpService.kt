package com.onelens.plugin.mcp

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.logger
import com.onelens.plugin.export.PythonEnvManager
import com.onelens.plugin.settings.OneLensSettings
import com.onelens.plugin.settings.OpenAiSecrets
import java.net.HttpURLConnection
import java.net.URI
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Lifecycle owner for the OneLens MCP server child process.
 *
 * Pattern cribbed from `hechtcarmel/jetbrains-index-mcp-plugin` but adapted
 * for our split: they host an embedded Ktor server inside the JVM because
 * their tools are Kotlin/PSI. Our tools are Python (FalkorDB, ChromaDB,
 * ONNX) so we spawn `python -m onelens.mcp_server --http --port N` as a
 * child instead. Same lifecycle model either way:
 *   - One app-level service (single MCP per IDE instance).
 *   - Starts on first project open (or manually via StartMcpServerAction).
 *   - Stops on IDE shutdown.
 *
 * Port strategy: base 29170 + retry on BindException up to 29200. Chosen
 * port is written to `~/.onelens/mcp.port` so external MCP clients (Claude
 * Code, Codex, Cursor) can discover it — register with
 *   `claude mcp add --scope user --transport http onelens http://127.0.0.1:<port>/mcp/`
 *
 * Stateless mode (`FASTMCP_STATELESS_HTTP=1`) keeps the Kotlin client
 * trivial — no MCP-Session-ID header tracking, every POST is independent.
 */
@Service(Service.Level.APP)
class OneLensMcpService : Disposable {

    companion object {
        private val LOG = logger<OneLensMcpService>()
        private val ONELENS_HOME: Path = Path.of(System.getProperty("user.home"), ".onelens")
        private val PORT_FILE: Path = ONELENS_HOME.resolve("mcp.port")
        private const val BASE_PORT = 29170
        private const val PORT_RANGE = 30
        private const val SHUTDOWN_GRACE_SECONDS = 5L
        // Cold-start budget for Python import + model download + lifespan
        // warmup (ORT init, TRT engine load from cache, multi-shape prime).
        // On a warm venv + warm TRT cache, first probe usually answers in
        // 6-10 s. Allow 60 s for the unlucky first-time case.
        private const val STARTUP_PROBE_TIMEOUT_MS = 60_000L

        fun getInstance(): OneLensMcpService =
            ApplicationManager.getApplication().service()
    }

    private val processRef = AtomicReference<Process?>(null)
    @Volatile private var port: Int = -1

    /** Current MCP endpoint, or null if the server isn't running. */
    // Path is `/mcp` (no trailing slash). `/mcp/` 307-redirects, which
    // Java's HttpClient does not follow on POST without additional config.
    val endpoint: String?
        get() = processRef.get()?.takeIf { it.isAlive }?.let { "http://127.0.0.1:$port/mcp" }

    val isRunning: Boolean
        get() = processRef.get()?.isAlive == true

    /** OS PID of the Python child, or -1 when not running. Used by the
     * Status tab's VRAM poller to filter `nvidia-smi` output. */
    fun pid(): Long = processRef.get()?.takeIf { it.isAlive }?.pid() ?: -1L

    /**
     * Spawn the MCP server as a child Python process on the first available
     * port in [BASE_PORT, BASE_PORT + PORT_RANGE). Idempotent — a no-op if
     * the server is already running. Returns the chosen port, or -1 on
     * failure.
     *
     * Start is synchronous — we wait up to [STARTUP_PROBE_TIMEOUT_MS] for
     * `/mcp/` to answer before returning success. If the probe times out,
     * we tear the child down and retry on the next port. Covers both the
     * "port race" (another process grabbed our free slot between pickPort
     * and bind) and "silent startup failure" (Python crashed in lifespan
     * — missing venv deps, model load OOM, bad env).
     *
     * Env passed through:
     *   - ONELENS_EMBED_BACKEND   / ONELENS_RERANK_BACKEND   from settings
     *   - ONELENS_EMBED_BASE_URL  / _MODEL / _DIM / _API_KEY for openai
     *   - ONELENS_WARM_ON_START=1 so lifespan primes embed + rerank TRT
     *     engines before the first tool call
     *   - FASTMCP_STATELESS_HTTP=1 for simpler Kotlin/Claude-Code clients
     */
    fun start(): Int {
        val existing = processRef.get()
        if (existing != null && existing.isAlive) {
            LOG.info("MCP server already running on port $port")
            return port
        }

        // Phase W5 — reuse an external MCP if one is already up. Another
        // IntelliJ window or a `claude mcp serve` from a terminal may have
        // booted the singleton (see Python `_acquire_singleton_lock` in
        // mcp_server.py). If so, point at it instead of fighting the lock
        // and burning a few seconds losing the race. Probe before spawn.
        val externalPort = readExternalPort()
        if (externalPort > 0 && probeReachable(externalPort)) {
            port = externalPort
            // Don't claim this process — it isn't ours. `pid()` returns -1,
            // `isRunning` returns false, but `endpoint` is live. Telemetry
            // (Status tab VRAM line) gracefully shows "MCP pid=-1" until
            // we adopt the external pid in a follow-up commit.
            LOG.info("Reusing external MCP server on port $externalPort (someone else's child)")
            return externalPort
        }

        val venvPython = PythonEnvManager.getVenvPython()
        if (!venvPython.canExecute()) {
            LOG.warn("Cannot start MCP server: venv python not found at $venvPython")
            return -1
        }

        val env = buildEnv()
        // Cold-load UX: surface the embedder warmup time before the user
        // wonders why nothing is happening. `ONELENS_WARM_ON_START=1`
        // (set in buildEnv) makes the Python lifespan prime the embedder
        // + reranker before answering /mcp/, so the readiness probe wait
        // is dominated by model load. First-ever load on CPU = ~30 s
        // (Jina-v2 ONNX), GPU with TRT cache = ~22 s, GPU without cache =
        // ~90 s for engine compile. Without this message the IDE just
        // shows "OneLens: Syncing Graph" with no progress for 30 s.
        com.onelens.plugin.ui.OneLensEvents.publish(
            com.onelens.plugin.ui.OneLensEvent.Info(
                "→ Starting OneLens MCP — first run loads embedder model (~30 s on CPU, ~22 s on GPU with cache). Subsequent runs reuse the warm process."
            )
        )

        // Try up to 5 ports. Health-probe each spawn; if it fails, move on.
        // The pickPort loop below returns a free candidate, but another
        // process can grab it between ServerSocket.close() and the Python
        // child's actual bind() call. Retrying handles that race cleanly.
        for (attempt in 0 until 5) {
            val chosenPort = pickPort() ?: run {
                LOG.warn("No free port in $BASE_PORT..${BASE_PORT + PORT_RANGE}")
                return -1
            }
            val cmd = listOf(
                venvPython.absolutePath,
                "-m", "onelens.mcp_server",
                "--http",
                "--host", "127.0.0.1",
                "--port", chosenPort.toString(),
            )
            try {
                val pb = ProcessBuilder(cmd).redirectErrorStream(true)
                pb.environment().putAll(env)
                val proc = pb.start()
                processRef.set(proc)
                port = chosenPort
                // Drain stdout async so the pipe buffer doesn't fill and
                // block the child. Uvicorn logs land here (useful on debug).
                Thread({ proc.inputStream.bufferedReader().forEachLine { LOG.info("[mcp] $it") } },
                    "OneLens-MCP-stdout").apply { isDaemon = true }.start()

                if (waitUntilReachable(chosenPort)) {
                    writePortFile(chosenPort)
                    LOG.info("MCP server ready on port $chosenPort (pid=${proc.pid()})")
                    return chosenPort
                }
                LOG.warn("MCP server on port $chosenPort did not answer /mcp/ within ${STARTUP_PROBE_TIMEOUT_MS}ms — tearing down, retrying")
                proc.destroyForcibly()
                processRef.set(null)
                port = -1
            } catch (e: Exception) {
                LOG.warn("Failed to spawn MCP server on port $chosenPort: ${e.message}")
                processRef.set(null)
                port = -1
            }
        }
        return -1
    }

    /** Phase W5 helper — read `~/.onelens/mcp.port` if present. Returns
     * the port value (1..65535) or -1 if missing/unparseable. */
    private fun readExternalPort(): Int {
        return try {
            if (!PORT_FILE.toFile().isFile) return -1
            val text = PORT_FILE.toFile().readText().trim()
            val p = text.toIntOrNull() ?: return -1
            if (p in 1..65535) p else -1
        } catch (_: Throwable) {
            -1
        }
    }

    /** One-shot reachability probe — same shape as `waitUntilReachable`
     * but without the polling deadline. Returns true if `GET /mcp` answers
     * 2xx/4xx within 500 ms. Used to decide if an external MCP is alive
     * before we spawn our own. */
    private fun probeReachable(p: Int): Boolean {
        return try {
            val conn = URI("http://127.0.0.1:$p/mcp").toURL().openConnection() as HttpURLConnection
            conn.connectTimeout = 500
            conn.readTimeout = 500
            conn.requestMethod = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code in 200..499
        } catch (_: Exception) {
            false
        }
    }

    /** Poll GET /mcp/ until 2xx/4xx (server listening) or timeout. */
    private fun waitUntilReachable(p: Int): Boolean {
        val deadline = System.currentTimeMillis() + STARTUP_PROBE_TIMEOUT_MS
        val url = "http://127.0.0.1:$p/mcp"
        while (System.currentTimeMillis() < deadline) {
            val proc = processRef.get()
            if (proc == null || !proc.isAlive) return false  // died → give up
            try {
                val conn = URI(url).toURL().openConnection() as HttpURLConnection
                conn.connectTimeout = 500
                conn.readTimeout = 500
                conn.requestMethod = "GET"
                val code = conn.responseCode
                conn.disconnect()
                if (code in 200..499) return true  // 4xx still means server is up
            } catch (_: Exception) { /* not up yet */ }
            Thread.sleep(250)
        }
        return false
    }

    /**
     * SIGTERM the child, wait up to [SHUTDOWN_GRACE_SECONDS], then SIGKILL.
     * Safe to call when no server is running.
     */
    fun stop() {
        val proc = processRef.getAndSet(null) ?: return
        if (!proc.isAlive) return
        try {
            proc.destroy()  // SIGTERM on Linux/macOS
            if (!proc.waitFor(SHUTDOWN_GRACE_SECONDS, TimeUnit.SECONDS)) {
                LOG.warn("MCP server did not exit within ${SHUTDOWN_GRACE_SECONDS}s; SIGKILL")
                proc.destroyForcibly()
            }
        } catch (e: Exception) {
            LOG.warn("Error stopping MCP server: ${e.message}")
        } finally {
            clearPortFile()
            port = -1
            // Drop the SDK session + HttpClient so the next start() gets a
            // fresh connection against whichever port we pick next.
            OneLensMcpClient.reset()
        }
    }

    /** Quick TCP probe — returns true if the /mcp/ endpoint answers. */
    fun isReachable(): Boolean {
        val url = endpoint ?: return false
        return try {
            val conn = URI(url).toURL().openConnection() as HttpURLConnection
            conn.connectTimeout = 500
            conn.readTimeout = 500
            conn.requestMethod = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code in 200..499  // 4xx still means "server is up"
        } catch (_: Exception) {
            false
        }
    }

    override fun dispose() {
        // Phase W2.5 — DON'T kill the child on IDE shutdown. Singleton MCP
        // is meant to outlive its spawner so:
        //   • Claude Code keeps working when the user closes IntelliJ.
        //   • A second IDE window opening tomorrow reuses today's warm
        //     model instead of paying ~30 s lifespan reload.
        //   • The kernel-held flock at ~/.onelens/mcp.lock is the singleton
        //     guarantee, not the JVM-side processRef.
        // Drop only the in-process bookkeeping (HTTP client, refs). The
        // OS process keeps running. To stop it explicitly, the user can
        // `kill $(cat ~/.onelens/mcp.port.pid)` or use the Stop MCP
        // toolbar action which calls stop() directly.
        try {
            OneLensMcpClient.reset()
        } catch (_: Throwable) {
        }
        // Note: we deliberately do NOT call stop() here, do NOT
        // destroyForcibly() the Process, do NOT clear mcp.port. The child
        // is now orphaned to the OS init process. Standard Unix daemon
        // behavior; on Windows the Process handle is closed but the
        // executable keeps running because we never set a ChildProcessJob.
    }

    private fun buildEnv(): Map<String, String> {
        val s = OneLensSettings.getInstance().state
        val env = mutableMapOf(
            "ONELENS_WARM_ON_START" to "1",
            "FASTMCP_STATELESS_HTTP" to "1",
        )
        when (s.embedderBackend.lowercase()) {
            "local" -> {
                env["ONELENS_EMBED_BACKEND"] = "local"
                env["ONELENS_RERANK_BACKEND"] = "local"
                // ALWAYS write profile + quant — even when set to defaults
                // ("balanced" / "fp32"). `pb.environment().putAll(env)`
                // overlays the IDE's inherited environment; if a user (or
                // wrapper script) had `ONELENS_LOCAL_EMBED_PROFILE=gemma`
                // exported in the parent shell and then flips Settings UI
                // back to "balanced", omitting the key would leak the
                // inherited value to the child. Writing the explicit
                // current value makes the plugin Settings the
                // authoritative source.
                env["ONELENS_LOCAL_EMBED_PROFILE"] = s.localEmbedderProfile.lowercase().ifBlank { "balanced" }
                env["ONELENS_LOCAL_EMBED_QUANT"] = s.localEmbedderQuant.lowercase().ifBlank { "fp32" }
            }
            "openai" -> {
                env["ONELENS_EMBED_BACKEND"] = "openai"
                env["ONELENS_RERANK_BACKEND"] = "none"
                env["ONELENS_EMBED_BASE_URL"] = s.openaiBaseUrl
                env["ONELENS_EMBED_MODEL"] = s.openaiEmbedModel
                env["ONELENS_EMBED_DIM"] = s.openaiEmbedDim.toString()
                OpenAiSecrets.get()?.let { env["ONELENS_EMBED_API_KEY"] = it }
            }
            else -> env["ONELENS_EMBED_BACKEND"] = s.embedderBackend
        }
        return env
    }

    private fun pickPort(): Int? {
        for (p in BASE_PORT until BASE_PORT + PORT_RANGE) {
            if (isPortFree(p)) return p
        }
        return null
    }

    private fun isPortFree(port: Int): Boolean = try {
        java.net.ServerSocket(port).use { true }
    } catch (_: Exception) { false }

    private fun writePortFile(p: Int) {
        try {
            Files.createDirectories(ONELENS_HOME)
            Files.writeString(
                PORT_FILE, p.toString(),
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING,
            )
        } catch (e: Exception) {
            LOG.warn("Could not write $PORT_FILE: ${e.message}")
        }
    }

    private fun clearPortFile() {
        try { Files.deleteIfExists(PORT_FILE) } catch (_: Exception) {}
    }
}
