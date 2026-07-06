package com.onelens.plugin.framework.nextjs
import com.onelens.plugin.export.*
import com.onelens.plugin.framework.jscommon.JsCommonSink
import com.onelens.plugin.framework.jscommon.SymlinkResolver
import com.onelens.plugin.framework.workspace.Workspace
import java.nio.file.Path
class NextjsContext(
    override val projectBase: Path,
    override val aliases: Map<String, Path>,
    override val symlinks: List<SymlinkResolver.SymlinkEntry>,
    override val workspace: Workspace,
) : JsCommonSink {
    override val modules: MutableList<JsModuleData> = mutableListOf()
    override val functions: MutableList<JsFunctionData> = mutableListOf()
    override val imports: MutableList<ImportsEdge> = mutableListOf()
    override val apiCalls: MutableList<ApiCallData> = mutableListOf()
    override val callsApi: MutableList<CallsApiEdge> = mutableListOf()
    // scriptRoots uses the default (plain file) — correct for .tsx/.jsx.
    fun snapshot(): NextjsData = NextjsData(
        modules = modules.toList(), functions = functions.toList(), imports = imports.toList(),
        apiCalls = apiCalls.toList(), callsApi = callsApi.toList(),
    )
    override fun relativize(abs: Path): String = try {
        projectBase.relativize(abs).toString().replace('\\', '/')
    } catch (_: Throwable) { abs.toString() }
}
