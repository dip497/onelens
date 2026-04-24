package com.onelens.plugin.mcp

import com.intellij.openapi.diagnostic.logger
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.sse.SSE
import io.modelcontextprotocol.kotlin.sdk.client.Client
import io.modelcontextprotocol.kotlin.sdk.client.StreamableHttpClientTransport
import io.modelcontextprotocol.kotlin.sdk.types.CallToolRequest
import io.modelcontextprotocol.kotlin.sdk.types.CallToolRequestParams
import io.modelcontextprotocol.kotlin.sdk.types.CallToolResult
import io.modelcontextprotocol.kotlin.sdk.types.Implementation
import io.modelcontextprotocol.kotlin.sdk.types.TextContent
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.concurrent.atomic.AtomicReference

/**
 * MCP client for calling tools on the plugin-owned Python MCP child.
 *
 * Uses the official `io.modelcontextprotocol:kotlin-sdk-client:0.9.0`
 * wired to Ktor CIO — no hand-rolled JSON-RPC parsing, proper SSE
 * streaming, typed request/response. Pinned to 0.9.0 per the version
 * constraint documented in `build.gradle.kts`.
 *
 * Shared singleton: one [HttpClient] + one [Client] for the plugin
 * lifetime, re-bound when the Python child's port changes (server
 * restart). The Python server runs in stateless mode
 * (`FASTMCP_STATELESS_HTTP=1` set by [OneLensMcpService]).
 */
object OneLensMcpClient {

    private val LOG = logger<OneLensMcpClient>()

    private data class Session(val endpoint: String, val http: HttpClient, val client: Client)

    private val current = AtomicReference<Session?>(null)

    /**
     * Invoke [toolName] with [arguments]. Returns the result's
     * `structuredContent` (OneLens tools always return dicts). Falls
     * back to `content[0].text` wrapped as a [JsonPrimitive] when the
     * tool returned a plain string. Returns null if the server is
     * unreachable, the call errors, or the result shape is unexpected —
     * callers fall back to the CLI subprocess in that case.
     */
    fun callToolStructured(toolName: String, arguments: Map<String, Any?>): JsonElement? {
        val result = callTool(toolName, arguments) ?: return null
        result.structuredContent?.let { return it }
        val first = result.content.filterIsInstance<TextContent>().firstOrNull() ?: return null
        return JsonPrimitive(first.text ?: return null)
    }

    /**
     * Low-level tool call. Returns the raw SDK [CallToolResult] (or null
     * on any failure). Use [callToolStructured] unless you need the
     * `isError` flag or the raw content array.
     */
    fun callTool(toolName: String, arguments: Map<String, Any?>): CallToolResult? {
        val endpoint = OneLensMcpService.getInstance().endpoint ?: return null
        val session = ensureSession(endpoint) ?: return null
        val jsonArgs = toJsonObject(arguments)
        // No timeout here on purpose. Real imports can run 20+ min on a
        // CPU-only box (100k-method embedding pass), and the user can
        // always hit Stop — the Backgroundable.onCancel path in
        // ExportFullAction / AutoSyncService kills the MCP child. Adding
        // an artificial cap risks false-positive aborts on slow hardware.
        // The handshake path in ensureSession has its own 30 s cap to
        // catch a wedged initialize, which was the actual failure mode.
        return try {
            runBlocking {
                session.client.callTool(
                    CallToolRequest(
                        CallToolRequestParams(name = toolName, arguments = jsonArgs)
                    )
                )
            }
        } catch (e: Exception) {
            LOG.warn("MCP callTool($toolName) failed: ${e.message}")
            null
        }
    }

    /**
     * Release any cached HTTP session. Called from [OneLensMcpService.stop]
     * when the Python child is killed — the next `callTool` will lazily
     * reconnect against whichever port the server picks on restart.
     */
    fun reset() {
        val prev = current.getAndSet(null) ?: return
        try { prev.http.close() } catch (_: Exception) {}
    }

    private fun ensureSession(endpoint: String): Session? {
        val existing = current.get()
        if (existing != null && existing.endpoint == endpoint) return existing
        existing?.let { try { it.http.close() } catch (_: Exception) {} }

        return try {
            val http = HttpClient(CIO) { install(SSE) }
            val client = Client(
                clientInfo = Implementation(name = "onelens-plugin", version = "0.2.0")
            )
            val transport = StreamableHttpClientTransport(client = http, url = endpoint)
            // Cap handshake at 30s. A stalled initialize → indefinite wedge
            // was observed against FastMCP in stateless mode: plugin thread
            // blocked in session init forever, no fallback fired. On
            // timeout we bail so callers drop to the cold CLI path.
            runBlocking { kotlinx.coroutines.withTimeout(30_000L) { client.connect(transport) } }
            val session = Session(endpoint, http, client)
            current.set(session)
            session
        } catch (e: Exception) {
            LOG.warn("MCP connect($endpoint) failed: ${e.message}")
            null
        }
    }

    private fun toJsonObject(args: Map<String, Any?>): JsonObject = buildJsonObject {
        for ((k, v) in args) when (v) {
            null -> put(k, JsonNull)
            is Boolean -> put(k, v)
            is Int -> put(k, v)
            is Long -> put(k, v)
            is Double -> put(k, v)
            is Float -> put(k, v.toDouble())
            is String -> put(k, v)
            is JsonElement -> put(k, v)
            else -> put(k, v.toString())
        }
    }
}
