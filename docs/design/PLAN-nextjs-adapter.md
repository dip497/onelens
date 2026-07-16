# PLAN — Next.js / React FrameworkAdapter

Status: **DRAFT — awaiting approval**. Target validation repo: `~/Desktop/<next-app>`
(Next 16, React 19, App Router, pnpm+turbo monorepo, 12 packages).

## Context

OneLens today ships exactly two `FrameworkAdapter`s — `SpringBootAdapter` (Java) and
`Vue3Adapter` (Vue SFC frontends). A **Next.js/React** frontend (e.g. `the validation repo`)
has **no adapter**: pointed at it, the Vue collectors emit ~0 useful nodes and the graph
is a shallow file list — no routes, no components, no client/server boundary, no
frontend→backend call bridge. This plan adds a first-class `NextjsAdapter` as a peer,
so React/Next projects get the same graph depth Vue enjoys, including the cross-stack
`HITS` bridge (frontend API call → Spring `Endpoint`).

Decisions locked with the user:
- **Scope: comprehensive** — routes, RSC server/client boundary + propagation, server
  actions (module + inline), route handlers, hooks (origin-classified), Context
  providers, TanStack-Query bridge, middleware. Collectors that have no target in
  `the validation repo` (0 route handlers, 0 module-level server actions) are still built,
  but must tolerate absence gracefully (emit nothing, never crash).
- **Delta: wired now** — Next nodes participate in incremental `delta-import` + cascade
  delete. This makes Next.js the **first** frontend wired into the delta path (Vue is
  not), so the delta plumbing is net-new and gets its own tests.

## Non-goals (v1)

- No new embedding model / retrieval algorithm changes — Next bodies flow through the
  existing ChromaDB mine + hybrid retrieve.
- No generalization of the delta export *collector* SPI (the `.java`-only export-side
  filter stays; Next delta uses the same git-diff mechanism the headless path already
  has, routed to the Next collectors). Unifying full+delta collector SPI is a separate
  effort (`delta-language-agnostic.md`).
- Vue is not retrofitted into delta here (tracked separately); we only wire Next.

---

## Architecture at a glance

```
package.json has "next"  ──detect()──►  NextjsAdapter (EP: com.onelens.plugin.frameworkAdapter)
                                              │ collectors() = [NextjsCollector]  (single composite)
                                              ▼
   NextjsCollector.collect(ctx)  ── builds NextjsContext (accumulator) ──► lastContext side-channel
       ├─ RouteTreeCollector        app/ dir walk → Route/Page/Layout/SpecialFile + tree edges
       ├─ ReactComponentCollector   .tsx/.jsx JSX-returning fns → ReactComponent + RENDERS/USES_HOOK
       ├─ DirectiveCollector        "use client"/"use server" → boundary props + CLIENT_BOUNDARY
       ├─ ServerActionCollector     module + inline "use server" → ServerAction
       ├─ RouteHandlerCollector     route.ts GET/POST/... → RouteHandler + Endpoint(+HANDLES)
       ├─ HookCollector             use* call sites → Hook/CustomHook + USES_HOOK
       ├─ ContextProviderCollector  createContext/<Provider>/useContext → ContextProvider
       ├─ MiddlewareCollector       middleware.ts → Middleware + matcher
       ├─ JsModuleCollector    (REUSED)  module/function/import graph over .tsx/.jsx/.ts/.js
       ├─ ApiCallCollector     (REUSED)  ky/fetch/axios call sites → ApiCall + CALLS_API
       └─ ModuleNameBinder     (REUSED)  const-literal URL substitution
                                              ▼
   ExportService merges  ExportDocument.nextjs = ctx.snapshot(): NextjsData   (new nullable field)
                                              ▼
   Python import: NextLoader.load_full → FalkorDB nodes/edges  +  CodeMiner nextjs pass → ChromaDB
```

The single biggest structural fact from research: the SPI's `CollectorOutput.data`/
`jsonKey` merge is **vestigial**. Real dispatch is a concrete-type side-channel
(`lastContext`) + explicit `when`-branches in `ExportService.exportFull` + a dedicated
field in `ExportDocument`. We follow the Vue precedent exactly, not the SPI KDoc.

---

## Graph schema — new labels & edges

Reuse (no new schema, gets cross-stack + trace/impact/search for free):
`JsModule`, `JsFunction`, `ApiCall`, `Endpoint`, `IMPORTS`, `CALLS_API`, `HITS`.

New node labels: `Route`, `Page`, `Layout`, `SpecialFile`, `RouteHandler`,
`ReactComponent`, `Hook`, `CustomHook`, `ServerAction`, `Middleware`, `ContextProvider`.

New edges: `HAS_PAGE`, `HAS_LAYOUT`, `BOUNDARY_OF`, `CHILD_OF`, `WRAPS`, `RENDERS`,
`USES_HOOK`, `CLIENT_BOUNDARY`, `EXPOSED_BY`, `INTERCEPTS`, `PROVIDES_CONTEXT`,
`HANDLES` (reused).

FQN conventions (keep identical to the JS side so edges interop):
- symbol: `<repo-relative-path>::<exportName>`
- route: URL path (`/admin/users/:id`), groups stripped, `[x]`→`:x`, `[...x]`→`*x`
- endpoint (route handler): `<METHOD>:<path>` (matches Spring `Endpoint` format → HITS)
- ChromaDB drawer ids: `reactcomponent:<fqn>`, `route:<urlPath>`, `serveraction:<fqn>`,
  `routehandler:<METHOD>:<path>` (prefix convention is mandatory — retrieval snippet
  lookup drops silently without it).

---

## Kotlin plugin work

### New package `plugin/.../framework/nextjs/`

| File | Responsibility |
|---|---|
| `NextjsAdapter.kt` | `id="nextjs"`, `jsonKey="nextjs"`. `detect()` = filesystem probe: `"next"` in `package.json` deps at base + one subdir level (mirror `Vue3Adapter.looksLikeVue3`, regex on dep block, no JSON parse, no PSI). Settings override hook like `vueAdapterEnabled`. `collectors()` = `listOf(NextjsCollector())`. |
| `NextjsCollector.kt` | Composite. `id="nextjs.all"`. Exposes `var lastContext: NextjsContext? by private set`. Builds `NextjsContext` (base root, tsconfig `paths` aliases via reused `ViteAliasResolver.paths` extraction, `SymlinkResolver.scan`), runs sub-collectors in fixed order via a `timed()` helper, returns `snapshot()` in `CollectorOutput` (ignored downstream). |
| `NextjsContext.kt` | Mutable accumulator (copy `Vue3Context` shape): lists for routes, pages, layouts, specialFiles, routeHandlers, components, hooks, customHooks, serverActions, middleware, contextProviders + edge lists; `snapshot(): NextjsData`; `relativize(Path)`. Reuses `modules/functions/imports/apiCalls` lists so the reused JS collectors write here. |
| `collectors/RouteTreeCollector.kt` | **Net-new.** Walk `app/` (and `pages/` if present) bottom-up. A dir with ≥1 special file → `Route` node; compute `urlPath` by joining segments, stripping `(group)`, mapping `[x]`/`[...x]`/`@slot`. Emit `Page`/`Layout`/`SpecialFile` nodes + `HAS_PAGE`/`HAS_LAYOUT`/`BOUNDARY_OF`/`CHILD_OF` edges. Tolerate `pages/` Router too. |
| `collectors/ReactComponentCollector.kt` | **Net-new.** Over `.tsx/.jsx` (+ `.ts/.js` exporting components): find exported functions/arrows whose body returns JSX (`JSXElement` PSI) — PascalCase heuristic + JSX-return. Props from TS param type. `RENDERS` edges by resolving JSX element identifiers → import → component node. `USES_HOOK` via HookCollector output. |
| `collectors/DirectiveCollector.kt` | **Net-new.** Detect module-first-statement string literal `"use client"`/`"use server"`; set `isClient/isServer` on component/module nodes; emit `CLIENT_BOUNDARY` (module→module) and a transitive propagation pass (imports of a client module are client). |
| `collectors/ServerActionCollector.kt` | **Net-new.** Module-level `"use server"` files → all exports are actions; **inline** `"use server"` as first statement of a function body → that function is an action. `ServerAction` + `EXPOSED_BY` edge to enclosing page/component. |
| `collectors/RouteHandlerCollector.kt` | **Net-new.** `route.ts/route.tsx` exporting named `GET/POST/PUT/PATCH/DELETE` → `RouteHandler` + synthesized `Endpoint` (`<METHOD>:<urlPath>`) + `HANDLES`. Zero-target-safe. |
| `collectors/HookCollector.kt` | **Net-new (loose reuse of use\* scanner).** Call sites matching `/^use[A-Z]/`; classify origin (react builtin / `@tanstack/react-query` / custom / pkg). Exported `function use*` → `CustomHook` definition. `USES_HOOK` edges. |
| `collectors/ContextProviderCollector.kt` | **Net-new.** `createContext(...)`, `<X.Provider>`, `useContext(X)` / custom consumer hooks → `ContextProvider` + `PROVIDES_CONTEXT`/consumer edges. (Replaces the Vue Pinia collector — repo has no zustand/redux.) |
| `collectors/MiddlewareCollector.kt` | **Net-new.** root/`src` `middleware.ts` exporting `middleware` + `config.matcher` → `Middleware` + `INTERCEPTS` to matched routes. Absence-safe. |

### Reused as-is (add `jsx`,`tsx` to every `FileTypeManager.getFileTypeByExtension` list; skip the `VuePsiScope`/`findModule` Vue branch, use plain `PsiTreeUtil` over `.tsx/.jsx`)
`framework/vue3/collectors/JsModuleCollector.kt`, `ApiCallCollector.kt`,
`resolver/ModuleNameBinder.kt`, `resolver/SymlinkResolver.kt`, `SmartRead.kt`,
`VueTestDetection.isTestFile`, `resolver/ViteAliasResolver.kt` (tsconfig `paths` part only).

→ **Refactor:** promote these six genuinely-framework-agnostic helpers out of `vue3/`
into a shared `framework/jscommon/` package so both adapters depend on them without
Next `depends`-ing on the Vue plugin. (JsModuleCollector's one `VueFile` branch is
guarded by extension, so it stays correct for `.tsx`.)

### Core files touched (the only non-additive plugin edits)
- `export/ExportModels.kt` — add `val nextjs: NextjsData? = null` to `ExportDocument`
  (peer to `vue3` at ~L30); add `NextjsData` container + all new node/edge `@Serializable`
  data classes (mirror the `Vue3Data` block).
- `export/ExportService.kt` — (1) `discoverAdapters` already EP-driven, no change;
  (2) add `is NextjsCollector -> nextCtx = collector.lastContext` in the dispatch `when`
  (~L118-121); (3) `progressFraction` branch (~L101); (4) `nextjs = nextCtx?.snapshot()`
  in the `ExportDocument(...)` build (~L187-237); (5) synthesize `AppData(type="nextjs")`
  + `PackageData` per workspace package (~L152-177, mirror Vue); (6) `SyncComplete` stats
  fields for Next node/edge counts (~L282-294).
- `META-INF/plugin.xml` + new `META-INF/framework-nextjs.xml` — register the adapter
  gated on the bundled `JavaScript` plugin: `<depends optional="true"
  config-file="framework-nextjs.xml">JavaScript</depends>`.
- Headless `OneLensExportStarter.kt` — **no change** (it doesn't enumerate adapters;
  EP discovery picks Next up automatically).
- `settings/OneLensSettings.kt` — add `nextAdapterEnabled: Boolean?` override (parallel
  to `vueAdapterEnabled`).

---

## Python work

### New: `importer/loaders/nextjs.py` — `NextLoader(SubdocLoader)`
- `json_key = "nextjs"`. `load_full(writer, progress, data, wing)` maps each `nextjs`
  array → nodes/edges via `_batch_nodes`/`_batch_edges_simple` equivalents on `writer`.
  Stamp every row with `wing`. **Always label the MATCH pattern** (FalkorDB PK-index —
  loader.py documents a 6000× penalty for label-less matches).
- Reuse labels `ApiCall`/`JsModule`/`JsFunction`/`Endpoint` for the JS-common arrays so
  the existing `bridge_http.compute_hits` ApiCall↔Endpoint bridge fires with zero new code.
- `apply_delta(writer, upserted, wing)` = strip-and-re-apply (copy `loaders/tests.py`).
- Register in `importer/loaders/__init__.py` (currently empty registry).

### `importer/loader.py`
- After the `vue3` dispatch (~L401) add:
  `nextjs = data.get("nextjs");  if nextjs: NextLoader().load_full(self.writer, progress, data, graph_wing)`
- Package→member `CONTAINS` block for a `next:` package prefix (mirror the `vue:` block ~L403-439).

### `importer/schema.py`
- `NODE_SCHEMA`: RANGE index on PK for each new label (`Route.urlPath`,
  `ReactComponent.fqn`, `RouteHandler.fqn`, `ServerAction.fqn`, `Page.fqn`, `Layout.fqn`,
  `Hook.name`/`CustomHook.fqn`, `Middleware.fqn`, `ContextProvider.fqn`) + `filePath`
  indexes where path-keyed edges land.
- `FULLTEXT_SCHEMA`: FTS entry per searchable label weighting `name` 10× / `filePath` /
  `body` (copy `Component_name`). **Without this, `onelens_search` silently returns
  nothing for that label.**
- `REL_SCHEMA`: doc-only entries for the new edges.

### `miners/code_miner.py`
- Add `if data.get("nextjs"):` gate (mirror the Vue gate ~L182-185) calling new
  `_mine_next_components` / `_mine_route_handlers` / `_mine_server_actions` (copy
  `_mine_vue_components` ~L900-937; reuse `_strip_js_imports`, unified metadata schema
  `wing/room/hall/fqn/type/importance/filed_at`).
- `mine_upserts` (delta) — add Next component/action re-embed on incremental apply.
- `delete_by_ids` cascade — purge `reactcomponent:`/`serveraction:`/`route:` drawers
  for removed files.

### `importer/delta_loader.py` (net-new frontend delta)
- Dispatch `NextLoader().apply_delta(self.writer, data, graph_wing)` next to the JVM
  loaders (~L353).
- Cascade-delete for removed `.tsx/.jsx` files: label-aware node deletes (mirror the
  class-delete block ~L53-75) + ChromaDB `delete_by_ids` for the Next drawer prefixes.
- Ensure the headless delta export (`ONELENS_DELTA=true`) routes changed `.tsx/.jsx`
  files to the Next collectors — requires the export-side delta tracker to stop being
  `.java`-only for the Next adapter (scoped: only when NextjsAdapter is active).

### Search / MCP surface
- `graph/queries.py` `search()` — add `elif node_type in {"route","reactcomponent",
  "routehandler","serveraction","hook"}:` branches (copy the `component` branch ~L167,
  keep `'<type>:'+pk` drawer-id prefix).
- `graph/analysis.py` `search_code` — append the new types to `types_to_search` (~L40-46).
- `mcp_server.py` — add labels to `onelens_status` probe list (~L153-155); update
  `onelens_search` `node_type` doc (~L404-406) + `onelens_graph_schema` text (~L312-370).
- Trace / impact / retrieve tools are label-generic (`:Method`/`:CALLS`/reused
  `JsFunction`/`ApiCall`/`Endpoint`) → work for Next with no change.

---

## Phasing (each phase independently testable, lands green)

- **P1 — Adapter skeleton + JS-common reuse.** `framework/jscommon/` refactor,
  `NextjsAdapter.detect()`, `NextjsCollector` running only the reused JsModule/ApiCall
  collectors over `.tsx/.jsx`, `ExportModels`+`ExportService`+`plugin.xml` wiring,
  `NextLoader.load_full` for JsModule/JsFunction/ApiCall/IMPORTS + HITS bridge.
  *Exit:* export the validation repo headless → import → `onelens_status` shows JsModule/
  JsFunction/ApiCall counts + HITS edges to any Spring graph.
- **P2 — Route tree + components + RSC boundary.** RouteTree/ReactComponent/Directive
  collectors; new labels + schema/FTS; loader mapping; `queries.search` + `analysis`
  branches; miner Next-component pass.
  *Exit:* `onelens_search reactcomponent`, route count = 30, client/server split visible.
- **P3 — Server actions, route handlers, hooks, context, middleware.** Remaining
  collectors + labels + loader/schema/search.
  *Exit:* inline server-action found in `forms/[formId]/page.tsx`; hooks origin-classified.
- **P4 — Delta.** `NextLoader.apply_delta` + `delta_loader` dispatch + cascade delete +
  Next-scoped delta export routing + `mine_upserts`.
  *Exit:* edit one `.tsx`, `resync` → only that component re-embeds, removed file purges.

---

## Verification

- **Unit/collector:** add fixtures under `python/tests/` + a minimal Next fixture app
  (a handful of `app/` route files, one `"use client"`, one inline `"use server"`,
  one `ky` call). Kotlin: collector tests asserting node/edge counts (test-author agent).
- **End-to-end (real repo):**
  `scripts/onelens-headless.sh all ~/Desktop/<next-app> the validation repo --frontend`
  (frontend content-root path; delta uses `resync`). Then:
  - `onelens_status --graph the validation repo` → non-zero Route/ReactComponent/ServerAction.
  - `onelens_query "MATCH (r:Route) RETURN count(r)"` ≈ 30 (page count).
  - `onelens_search "UserProfileForm" --node-type reactcomponent`.
  - Client/server: `MATCH (c:ReactComponent {isClient:true}) RETURN count(c)` ≈ 26.
  - Cross-stack: `MATCH (a:ApiCall)-[:HITS]->(e:Endpoint) RETURN a,e` once a Spring graph
    for the gateway exists (or assert `CALLS_API` to external prefixes otherwise).
  - Delta: touch a `.tsx`, `resync`, confirm delta JSON (`exportType:"delta"`) + only the
    changed component's drawer re-mined.
- **CI guard:** extend the `CodeMiner` API-surface guard for the new mine methods; ruff/mypy.

## Doc-tracker updates (same session as the code, per CLAUDE.md)
- `docs/PROGRESS.md` — new rows for the Next adapter (per phase, ✅ as they land).
- `CHANGELOG.md` — `[Unreleased] → Added — Next.js/React adapter`.
- `docs/DECISIONS.md` — ADR: "NextjsAdapter — file-system routing + RSC boundary; reuse
  JS-common collectors; Next is first frontend wired into delta." Alternatives: tree-sitter
  (rejected — PSI already there), copy-Vue (rejected — SFC/router model inverted).
- `CLAUDE.md` graph-schema section — add the new labels/edges.
- Update memory `delta-export-is-java-only` once Next delta lands (it becomes Java+Next).

## Risks / watch-items
- **PSI JSX support** depends on the bundled `JavaScript` plugin (present in IU; Next
  needs no Vue plugin). Confirm `.tsx` PSI resolves in headless before P2.
- **RSC transitive client propagation** can explode on deep import graphs — bound it
  (mark direct, let queries traverse) rather than eagerly flooding, mirroring the Vue
  `useI18n ×378` stub-explosion lesson in LESSONS-LEARNED.
- **Delta export routing** is the riskiest bit — the `.java`-only export filter must be
  bypassed *only* when NextjsAdapter is active, or we regress Java delta. Gate carefully.
- **Zero-target collectors** (route handlers, module server actions) — must be provably
  no-op-safe; add a tiny synthetic fixture so they're not untested.
