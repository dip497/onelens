package com.onelens.plugin.framework.nextjs

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.onelens.plugin.export.NextjsData
import com.onelens.plugin.framework.CollectContext
import com.onelens.plugin.framework.Collector
import com.onelens.plugin.framework.CollectorOutput
import com.onelens.plugin.framework.FrameworkAdapter
import com.onelens.plugin.framework.jscommon.ApiCallCollector
import com.onelens.plugin.framework.jscommon.JsModuleCollector
import com.onelens.plugin.framework.jscommon.ModuleNameBinder
import com.onelens.plugin.framework.jscommon.SymlinkResolver
import com.onelens.plugin.framework.jscommon.ViteAliasResolver
import com.onelens.plugin.framework.jscommon.WorkspaceAliasResolver
import com.onelens.plugin.framework.nextjs.collectors.ContextProviderCollector
import com.onelens.plugin.framework.nextjs.collectors.DirectiveCollector
import com.onelens.plugin.framework.nextjs.collectors.HookCollector
import com.onelens.plugin.framework.nextjs.collectors.MiddlewareCollector
import com.onelens.plugin.framework.nextjs.collectors.ReactComponentCollector
import com.onelens.plugin.framework.nextjs.collectors.RendersResolver
import com.onelens.plugin.framework.nextjs.collectors.RouteHandlerCollector
import com.onelens.plugin.framework.nextjs.collectors.RouteTreeCollector
import com.onelens.plugin.framework.nextjs.collectors.ServerActionCollector
import com.onelens.plugin.settings.OneLensSettings
import kotlinx.serialization.json.Json
import java.io.File
import java.nio.file.Paths

/**
 * Adapter for Next.js frontend projects. Detects via `package.json` — a
 * `dependencies.next` pinned to a numeric version range. Reuses the
 * framework-agnostic JS/TS collectors ([JsModuleCollector], [ApiCallCollector],
 * [ModuleNameBinder]) over `.ts` / `.tsx` / `.jsx` files behind [NextjsContext].
 */
class NextjsAdapter : FrameworkAdapter {
    override val id: String = "nextjs"
    override val jsonKey: String = "nextjs"

    override fun detect(project: Project): Boolean {
        val override = OneLensSettings.getInstance().nextAdapterEnabled
        if (override != null) return override

        val base = project.basePath ?: return false
        val baseDir = File(base)
        // Scan package.json at the root AND up to two directory levels down, so a
        // monorepo whose Next app lives at `apps/web/package.json` (2 levels) is
        // detected — not just a root-level app. Vendored / VCS dirs are skipped so
        // the probe stays a cheap filesystem walk. `next` in a root pnpm.overrides
        // block also trips detection, which is the correct outcome (it IS a Next repo).
        val pkgJsons = buildList {
            add(File(baseDir, "package.json"))
            fun childDirs(dir: File): List<File> =
                dir.listFiles()?.filter { it.isDirectory && it.name !in SKIP_DIRS } ?: emptyList()
            for (lvl1 in childDirs(baseDir)) {
                add(File(lvl1, "package.json"))
                for (lvl2 in childDirs(lvl1)) add(File(lvl2, "package.json"))
            }
        }
        return pkgJsons.any { it.exists() && looksLikeNext(it) }
    }

    override fun collectors(): List<Collector> = listOf(NextjsCollector())

    private fun looksLikeNext(pkg: File): Boolean = try {
        NEXT_DEP_PATTERN.containsMatchIn(pkg.readText())
    } catch (_: Throwable) {
        false
    }

    companion object {
        private val LOG = logger<NextjsAdapter>()
        private val NEXT_DEP_PATTERN = Regex(""""next"\s*:\s*"[\^~]?\d""")
        private val SKIP_DIRS = setOf("node_modules", ".git", ".next", ".turbo", "dist", "out", "build", ".idea")
    }
}

class NextjsCollector : Collector {
    override val id: String = "nextjs.all"
    override val label: String = "Next.js"

    var lastContext: NextjsContext? = null
        private set

    private val nextJson = Json { encodeDefaults = true }

    override fun collect(ctx: CollectContext): CollectorOutput {
        val project = ctx.project
        val workspace = ctx.workspace
        val base = workspace?.primaryRoot
            ?: project.basePath?.let(Paths::get)
            ?: return emptyOutput()

        val aliases = ViteAliasResolver.resolveFromBase(base)
        val symlinks = try {
            SymlinkResolver.scan(project)
        } catch (_: Throwable) {
            emptyList()
        }
        val nextCtx = NextjsContext(
            projectBase = base,
            aliases = aliases,
            symlinks = symlinks,
            workspace = workspace,
        )
        lastContext = nextCtx

        val indicator = ctx.indicator
        val baseFraction = ctx.progressFraction
        val timings = StringBuilder()
        fun timed(label: String, fraction: Double, block: () -> Unit) {
            indicator?.text = "Next.js: $label…"
            indicator?.fraction = fraction
            val start = System.nanoTime()
            block()
            val ms = (System.nanoTime() - start) / 1_000_000
            timings.append("  $label: ${ms}ms\n")
        }

        timed("API calls", baseFraction) {
            ApiCallCollector.collect(project, nextCtx)
        }
        timed("binding parametric URLs", baseFraction + 0.02) {
            ModuleNameBinder.bind(project, nextCtx)
        }
        timed("JS modules + functions + imports", baseFraction + 0.04) {
            JsModuleCollector.collect(project, nextCtx)
        }
        // P2 — routes + React components + RSC boundary. DirectiveCollector runs first
        // so Page/Layout/SpecialFile/Component nodes get isClient; RENDERS is derived
        // last, once imports + the component set are fully populated.
        timed("use-client directives", baseFraction + 0.06) {
            DirectiveCollector.collect(project, nextCtx)
        }
        timed("route tree", baseFraction + 0.08) {
            RouteTreeCollector.collect(project, nextCtx)
        }
        timed("React components", baseFraction + 0.10) {
            ReactComponentCollector.collect(project, nextCtx)
        }
        // P3 — server actions, route handlers, context, hooks, middleware.
        timed("server actions", baseFraction + 0.12) {
            ServerActionCollector.collect(project, nextCtx)
        }
        timed("route handlers", baseFraction + 0.13) {
            RouteHandlerCollector.collect(project, nextCtx)
        }
        timed("context providers", baseFraction + 0.14) {
            ContextProviderCollector.collect(project, nextCtx)
        }
        timed("hooks", baseFraction + 0.15) {
            HookCollector.collect(project, nextCtx)
        }
        timed("middleware", baseFraction + 0.16) {
            MiddlewareCollector.collect(project, nextCtx)
        }
        // RENDERS last, after the cross-package workspace alias map is built so
        // `<Badge/>` imported from another workspace package resolves.
        val pkgAliases = try {
            WorkspaceAliasResolver.buildAliasMap(base)
        } catch (_: Throwable) {
            emptyMap()
        }
        timed("RENDERS resolution", baseFraction + 0.18) {
            RendersResolver.resolve(nextCtx, pkgAliases)
        }

        System.err.println("[onelens] Next.js collector timings:\n$timings")

        val snapshot: NextjsData = nextCtx.snapshot()
        val nodeCount = snapshot.modules.size + snapshot.functions.size + snapshot.apiCalls.size +
            snapshot.routes.size + snapshot.pages.size + snapshot.layouts.size +
            snapshot.specialFiles.size + snapshot.components.size +
            snapshot.serverActions.size + snapshot.routeHandlers.size + snapshot.endpoints.size +
            snapshot.customHooks.size + snapshot.hooks.size + snapshot.contextProviders.size +
            snapshot.middlewares.size
        val edgeCount = snapshot.imports.size + snapshot.callsApi.size +
            snapshot.hasPage.size + snapshot.hasLayout.size + snapshot.boundaryOf.size +
            snapshot.childOf.size + snapshot.renders.size +
            snapshot.handles.size + snapshot.exposedBy.size + snapshot.usesHook.size +
            snapshot.providesContext.size + snapshot.intercepts.size

        val subdoc = nextJson.encodeToJsonElement(NextjsData.serializer(), snapshot)
        return CollectorOutput(data = subdoc, nodeCount = nodeCount, edgeCount = edgeCount)
    }

    private fun emptyOutput(): CollectorOutput = CollectorOutput(
        data = kotlinx.serialization.json.JsonObject(emptyMap()),
        nodeCount = 0,
        edgeCount = 0
    )
}
