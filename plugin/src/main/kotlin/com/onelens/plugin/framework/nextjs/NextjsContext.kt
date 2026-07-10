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

    // --- P2: routes + React components + RSC boundary ---
    val routes: MutableList<NextRouteData> = mutableListOf()
    val pages: MutableList<PageData> = mutableListOf()
    val layouts: MutableList<LayoutData> = mutableListOf()
    val specialFiles: MutableList<SpecialFileData> = mutableListOf()
    val components: MutableList<ReactComponentData> = mutableListOf()
    val hasPage: MutableList<HasPageEdge> = mutableListOf()
    val hasLayout: MutableList<HasLayoutEdge> = mutableListOf()
    val boundaryOf: MutableList<BoundaryOfEdge> = mutableListOf()
    val childOf: MutableList<ChildOfEdge> = mutableListOf()
    val renders: MutableList<RendersEdge> = mutableListOf()

    // --- P3: server actions, route handlers, hooks, context, middleware ---
    val serverActions: MutableList<ServerActionData> = mutableListOf()
    val routeHandlers: MutableList<RouteHandlerData> = mutableListOf()
    val endpoints: MutableList<NextEndpointData> = mutableListOf()
    val customHooks: MutableList<CustomHookData> = mutableListOf()
    val hooks: MutableList<HookData> = mutableListOf()
    val contextProviders: MutableList<ContextProviderData> = mutableListOf()
    val middlewares: MutableList<MiddlewareData> = mutableListOf()
    val handles: MutableList<HandlesEdge> = mutableListOf()
    val exposedBy: MutableList<ExposedByEdge> = mutableListOf()
    val usesHook: MutableList<UsesHookEdge> = mutableListOf()
    val providesContext: MutableList<ProvidesContextEdge> = mutableListOf()
    val intercepts: MutableList<InterceptsEdge> = mutableListOf()

    /** Transient (not serialized): relative filePaths of modules with a "use client" directive. */
    val clientModules: MutableSet<String> = mutableSetOf()

    /**
     * Transient (not serialized): JSX render sites collected during the component /
     * page / layout PSI passes. Resolved to [RendersEdge] rows in a post-pass once
     * imports + the component set are fully populated.
     */
    val renderSites: MutableList<RenderSite> = mutableListOf()

    /** True when [filePath] carries a module-level "use client" directive. */
    fun isClient(filePath: String): Boolean = filePath in clientModules

    // scriptRoots uses the default (plain file) — correct for .tsx/.jsx.
    fun snapshot(): NextjsData = NextjsData(
        modules = modules.toList(), functions = functions.toList(), imports = imports.toList(),
        apiCalls = apiCalls.toList(), callsApi = callsApi.toList(),
        routes = routes.toList(), pages = pages.toList(), layouts = layouts.toList(),
        specialFiles = specialFiles.toList(), components = components.toList(),
        hasPage = hasPage.toList(), hasLayout = hasLayout.toList(),
        boundaryOf = boundaryOf.toList(), childOf = childOf.toList(), renders = renders.toList(),
        serverActions = serverActions.toList(), routeHandlers = routeHandlers.toList(),
        endpoints = endpoints.toList(), customHooks = customHooks.toList(), hooks = hooks.toList(),
        contextProviders = contextProviders.toList(), middlewares = middlewares.toList(),
        handles = handles.toList(), exposedBy = exposedBy.toList(), usesHook = usesHook.toList(),
        providesContext = providesContext.toList(), intercepts = intercepts.toList(),
    )
    override fun relativize(abs: Path): String = try {
        projectBase.relativize(abs).toString().replace('\\', '/')
    } catch (_: Throwable) { abs.toString() }
}

/**
 * A place where a symbol (page / layout / React component) renders JSX. Collected
 * during the PSI passes; [sourceFqn] is the rendering symbol, [jsxTagNames] are the
 * PascalCase JSX element identifiers found in its body (resolved to component fqns later).
 */
data class RenderSite(
    val sourceFqn: String,
    val filePath: String,
    val jsxTagNames: Set<String>,
)
