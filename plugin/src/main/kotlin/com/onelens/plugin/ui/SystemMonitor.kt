package com.onelens.plugin.ui

import com.intellij.openapi.diagnostic.logger

/**
 * Tiny shell-out helpers for live system telemetry shown in the OneLens
 * Status tab. All reads are best-effort — `nvidia-smi` isn't on every
 * box, and the poller falls silent instead of surfacing errors.
 */
object SystemMonitor {

    private val LOG = logger<SystemMonitor>()

    /**
     * VRAM in bytes used by the given PID, or -1 if unknown (non-NVIDIA
     * host, `nvidia-smi` missing, PID not on GPU, or command failed).
     * Intended to be polled every 5 s while the MCP server is running.
     */
    fun gpuMemoryBytesForPid(pid: Long): Long {
        if (pid <= 0) return -1L
        return try {
            val proc = ProcessBuilder(
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ).redirectErrorStream(true).start()
            val out = proc.inputStream.bufferedReader().readText().trim()
            proc.waitFor()
            if (proc.exitValue() != 0) return -1L
            // Format: "PID, MB"
            for (line in out.lineSequence()) {
                val parts = line.split(',').map { it.trim() }
                if (parts.size >= 2 && parts[0].toLongOrNull() == pid) {
                    val mb = parts[1].toLongOrNull() ?: return -1L
                    return mb * 1024 * 1024
                }
            }
            -1L
        } catch (_: Throwable) {
            -1L
        }
    }

    /** Returns the pretty provider string from the MCP service helper. */
    fun localProvider(): String =
        com.onelens.plugin.export.PythonEnvManager.detectLocalProvider()
}
