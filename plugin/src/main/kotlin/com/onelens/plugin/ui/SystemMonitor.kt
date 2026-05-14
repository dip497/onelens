package com.onelens.plugin.ui

import com.intellij.openapi.diagnostic.logger
import java.util.concurrent.TimeUnit

/**
 * Tiny shell-out helpers for live system telemetry shown in the OneLens
 * Status tab. All reads are best-effort — `nvidia-smi` isn't on every
 * box, and the poller falls silent instead of surfacing errors.
 *
 * **Threading contract:** every call here MAY block (subprocess spawn,
 * NVML driver-lock contention can stall `nvidia-smi` for tens of
 * seconds when another process is mid-TRT-engine-build). Callers
 * MUST invoke from a pooled thread, never the EDT. The Status-tab
 * timer at `OneLensToolWindow` enforces this.
 */
object SystemMonitor {

    private val LOG = logger<SystemMonitor>()

    // Hard cap so a hung NVML lock can't wedge the pool thread either.
    private const val SUBPROCESS_TIMEOUT_SEC = 1L

    /**
     * VRAM in bytes used by the given PID, or -1 if unknown (non-NVIDIA
     * host, `nvidia-smi` missing, PID not on GPU, or command failed
     * within [SUBPROCESS_TIMEOUT_SEC]).
     */
    fun gpuMemoryBytesForPid(pid: Long): Long {
        if (pid <= 0) return -1L
        var proc: Process? = null
        return try {
            proc = ProcessBuilder(
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ).redirectErrorStream(true).start()
            // Bounded wait — NVML driver lock can hang the call indefinitely
            // when another process is mid-TRT-engine-build or mid-CUDA-init.
            // Past 1 s we'd rather report unknown than block the poller.
            if (!proc.waitFor(SUBPROCESS_TIMEOUT_SEC, TimeUnit.SECONDS)) {
                proc.destroyForcibly()
                return -1L
            }
            if (proc.exitValue() != 0) return -1L
            val out = proc.inputStream.bufferedReader().readText().trim()
            for (line in out.lineSequence()) {
                val parts = line.split(',').map { it.trim() }
                if (parts.size >= 2 && parts[0].toLongOrNull() == pid) {
                    val mb = parts[1].toLongOrNull() ?: return -1L
                    return mb * 1024 * 1024
                }
            }
            -1L
        } catch (_: Throwable) {
            proc?.destroyForcibly()
            -1L
        }
    }

    /** Returns the pretty provider string from the MCP service helper. */
    fun localProvider(): String =
        com.onelens.plugin.export.PythonEnvManager.detectLocalProvider()
}
