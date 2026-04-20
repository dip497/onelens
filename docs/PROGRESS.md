# OneLens — Feature Progress Tracker

Source of truth for what's landed, what's in flight, and what's deferred. Append-only per phase; mark status inline. Links point to the canonical artefact so this file stays skimmable.

Last updated: 2026-04-20.

---

## Legend

- ✅ **Shipped** — code + tests in main branch or on the active feature branch and green.
- 🟡 **In-progress** — partial work on feature branch, not yet verified end-to-end.
- ⬜ **Planned** — on the roadmap, not started.
- 🟥 **Blocked** — needs upstream work or an external dependency.

---

## Core platform (pre-Phase A)

| # | Feature | Status | Where |
|---|---|---|---|
| 1 | OSS scaffold (AGENTS, CODE_OF_CONDUCT, SECURITY, licensing, docs tree) | ✅ | `docs/`, repo root |
| 2 | IntelliJ plugin — PSI collectors for Java/Spring Boot | ✅ | `plugin/src/main/kotlin/com/onelens/plugin/export/collectors/` |
| 3 | FalkorDB graph importer with UNWIND batching | ✅ | `python/src/onelens/importer/loader.py` |
| 4 | ChromaDB semantic layer (Qwen3 embed + mxbai rerank) | ✅ | `python/src/onelens/context/` |
| 5 | Hybrid retrieval (FTS + semantic + RRF + rerank + threshold) | ✅ | `python/src/onelens/context/retrieval.py` |
| 6 | Delta export + incremental embedding upserts | ✅ | `plugin/.../export/delta/`, `miners/code_miner.py` |
| 7 | Auto-sync on file save (debounced) | ✅ Java only | `plugin/.../autosync/` |
| 8 | Skill install action | ✅ | `plugin/.../skill/InstallSkillAction.kt` |
| 9 | Python venv auto-install via `uv` | ✅ | `plugin/.../export/PythonEnvManager.kt` |
| 10 | CLI auto-generated from FastMCP server | ✅ | `python/src/onelens/mcp_server.py`, `cli_generated.py` |
| 11 | FalkorDB TCP preflight | ✅ | `plugin/.../export/ExportService.kt` |
| 12 | PageRank prebake (JVM) | ✅ | `python/src/onelens/importer/pagerank.py` |
| 13 | Multi-backend abstraction (falkordb, falkordblite, neo4j) | ✅ | `python/src/onelens/graph/backends/` |
| 14 | GitHub Actions CI + release workflow | ✅ | `.github/workflows/` |
| 15 | Single-tool + multi-step retrieval benchmarks | ✅ (gitignored) | `python/benchmarks/` |

---

## Phase A — Framework adapter refactor (2026-04-17)

Landed on `feature/context-graph-semantic-search` branch.

| # | Deliverable | Status | Where |
|---|---|---|---|
| A1 | `FrameworkAdapter` SPI + extension point | ✅ | `plugin/src/main/kotlin/com/onelens/plugin/framework/FrameworkAdapter.kt` |
| A2 | `ExportDocument` extended additively: `adapters`, `vue3` subdoc, 9 Vue data classes | ✅ | `plugin/.../export/ExportModels.kt` |
| A3 | `plugin.xml` split — Java now optional via `framework-springboot.xml`; Vue via `framework-vue3.xml`. WebStorm install works. | ✅ | `plugin/src/main/resources/META-INF/` |
| A4 | `SpringBootAdapter` wraps the seven existing Java collectors; `ExportService.exportFull` iterates adapters | ✅ | `plugin/.../framework/springboot/SpringBootAdapter.kt` |
| A5 | Regression guard — sync known Java project and diff node/edge counts | ⬜ | Needs human install of rebuilt ZIP + run on the reference Java backend |

---

## Phase 0 — Vue PSI proof-of-concept

Gate for Phase B. **Passed 2026-04-17.**

| # | Deliverable | Status | Where |
|---|---|---|---|
| P0-1 | 5 Vue fixtures + `BasePlatformTestCase` harness | ✅ | `plugin/src/test/resources/vue-fixtures/`, `plugin/src/test/kotlin/.../VuePsiPoCTest.kt` |
| P0-2 | 6 PSI assertions passing (`defineProps`/`defineEmits`/`defineExpose`/composable resolve/Pinia shape/axios template) | ✅ | 6/6 green, 22.9s run |
| P0-3 | Findings doc — APIs locked for Phase B | ✅ | `docs/vue-psi-poc.md` |
| P0-4 | Gradle setup — `platformType=IU` for dev (JS + Vue bundled); runtime portable via optional config-file deps | ✅ | `plugin/gradle.properties`, `plugin/build.gradle.kts` |

---

## Phase B — Vue 3 adapter (P0 collectors)

Full-import-only. Delta + auto-sync deferred to Phase B2.

| # | Deliverable | Status | Where |
|---|---|---|---|
| B1 | `Vue3Adapter` skeleton + `detect()` regex on `package.json` | ✅ | `plugin/.../framework/vue3/Vue3Adapter.kt` |
| B1 | `OneLensSettings.vueAdapterOverride` per-project on/off/auto | ✅ | `plugin/.../settings/OneLensSettings.kt` |
| B1 | `SymlinkResolver` — `src/` one-level scan, in/out-of-content-root classification | ✅ | `plugin/.../framework/vue3/resolver/SymlinkResolver.kt` |
| B1 | `ViteAliasResolver` — merge tsconfig `paths` + vite.config `resolve.alias`, vite wins on conflicts | ✅ (10/10 unit tests) | `plugin/.../framework/vue3/resolver/ViteAliasResolver.kt` |
| B2 | `SfcScriptSetupCollector` — Components, props (typed+required), emits, exposes, `<script setup>` body ≤2000 chars | ✅ | `plugin/.../framework/vue3/collectors/SfcScriptSetupCollector.kt` |
| B2 | `PiniaStoreCollector` — both options and setup styles, state/getters/actions extraction | ✅ | `plugin/.../framework/vue3/collectors/PiniaStoreCollector.kt` |
| B2 | `ComposableCollector` — `useX` naming + returns-something heuristic, excludes Pinia-defining files | ✅ | `plugin/.../framework/vue3/collectors/ComposableCollector.kt` |
| B3 | `LazyRouteCollector` — 1-hop `config.js` resolution, lazy-import target extraction, DISPATCHES edges | ✅ | `plugin/.../framework/vue3/collectors/LazyRouteCollector.kt` |
| B3 | `ApiCallCollector` — axios/fetch/api literal + template URLs, parametric flag, binding record, CALLS_API edges | ✅ | `plugin/.../framework/vue3/collectors/ApiCallCollector.kt` |
| B4 | `CallThroughResolver` — direct + 1-hop indirect USES_STORE + USES_COMPOSABLE edges | ✅ | `plugin/.../framework/vue3/resolver/CallThroughResolver.kt` |
| B4 | `ModuleNameBinder` — resolves top-level `const X = 'literal'` into parametric URLs, emits literal variant | ✅ | `plugin/.../framework/vue3/resolver/ModuleNameBinder.kt` |
| B4 | `BaseModuleRouteCollector` aggregating `available-modules.js` exports | ⬜ | Deferred — single `LazyRouteCollector` covers the common `*-routes.js` pattern for now |
| B5 | Python `schema.py` — NODE_SCHEMA + FULLTEXT_SCHEMA extended for Component/Composable/Store/Route/ApiCall | ✅ | `python/src/onelens/importer/schema.py` |
| B5 | Python `loader._load_vue3` + `_batch_edges_simple` for Vue nodes + edges | ✅ | `python/src/onelens/importer/loader.py` |
| B5 | `bridge_http.compute_hits` — cross-wing HITS matcher with shared `normalize_path` | ✅ (7/7 normalize smoke) | `python/src/onelens/importer/bridge_http.py` |
| B6 | Vue PageRank — Route-seeded, propagates into Component/Composable/Store | ✅ | `python/src/onelens/importer/pagerank.py` (`compute_vue_pagerank`) |
| B6 | `code_miner` Vue drawers — Component/Composable/Store with canonical metadata schema | ✅ | `python/src/onelens/miners/code_miner.py` (`_mine_vue_components`, etc.) |
| B6 | Skill split — `skills/onelens/SKILL.md` hub + `references/{jvm,vue3}.md` progressive-disclosure | ✅ | `skills/onelens/` |
| B6 | Plugin skill bundling extended for references (`processResources` + `InstallSkillAction`) | ✅ | `plugin/build.gradle.kts`, `plugin/.../skill/InstallSkillAction.kt` |
| B7 | Dogfood run on the reference Vue 3 frontend repo — stats + bridge edges | ⬜ | Needs human install + sync |
| B7 | Vue-specific benchmark cases added to `python/benchmarks/cases.yaml` | ⬜ | |

**Test tally:** 23 tests green — 6 PoC, 10 alias resolver, 7 collector smoke.
**Plugin ZIP:** `plugin/build/distributions/onelens-graph-builder-0.1.0.zip` (2.7 MB, includes SKILL.md + both references).

---

## Phase B2 — in progress (JS business-logic layer + Vue delta)

| # | Deliverable | Status | Where |
|---|---|---|---|
| B2.JS.1 | `JsModuleData` + `JsFunctionData` + `ImportsEdge` models (new Kotlin data classes) | ✅ | `plugin/.../export/ExportModels.kt` |
| B2.JS.2 | `JsModuleCollector` — per-file Module node, exported top-level functions, resolved ES6 imports with 2-hop alias resolve (verified by `ImportResolveTest`) | ✅ | `plugin/.../framework/vue3/collectors/JsModuleCollector.kt` |
| B2.JS.3 | Python loader — `JsModule` / `JsFunction` nodes + `IMPORTS` edges (symbol-resolved via `targetFqn`, module-level fallback when unresolved) | ✅ | `python/src/onelens/importer/loader.py` |
| B2.JS.4 | NODE_TYPES + NODE_SCHEMA + FULLTEXT_SCHEMA extended for JS modules / functions | ✅ | `python/src/onelens/graph/db.py`, `python/src/onelens/importer/schema.py` |
| B2.JS.5 | Dogfood re-sync and verify business-logic `.js` helpers under `src/data/*` become queryable as `JsFunction` nodes | ⬜ | Needs WebStorm plugin re-install + Sync Graph |
| B2.JS.5a | `VuePsiScope` stub-aware `<script>` / `<script setup>` root walk; `ComposableCollector.isLocalTopLevelDecl` gate; alias / relative specifier normalization across `JsModuleCollector` + `LazyRouteCollector`; `fqnFor` project-relative. Kills `useI18n × 378` phantom duplication + restores alias-form IMPORTS / DISPATCHES matching on 1500+ component dogfood. | ✅ (2026-04-18) | `plugin/.../framework/vue3/VuePsiScope.kt`, five vue3 collectors |
| B2.JS.5b | Loader `IMPORTS_FN` Python-side bridge + label-split IMPORTS batching + ES6 candidate expansion + `HAS_FUNCTION` edge + Route `fullPath` walk + `CALLS_API` JsFunction caller rule. | ✅ (2026-04-18) | `python/src/onelens/importer/loader.py`, `python/src/onelens/importer/schema.py` |
| B2.JS.5c | FTS Vue label expansion (7 labels) + prefixed `<type>:<key>` fqn outputs + `_fetch_locations_batch` Vue block + defensive `_dedupe_by_parent`. | ✅ (2026-04-18) | `python/src/onelens/graph/queries.py`, `python/src/onelens/graph/analysis.py`, `python/src/onelens/context/retrieval.py` |
| B2.JS.5d | Modal remote — weights baked into image, CUDA base, rerank sigmoid passthrough, chunk size 96 for L4. | ✅ (2026-04-18) | `python/src/onelens/remote/modal_app.py`, `python/src/onelens/context/reranker.py`, `python/src/onelens/context/embed_backends/modal_backend.py`. See ADR-016, ADR-017. |
| B2.JS.6 | JS `CALLS` edge within + across modules | ⬜ | Raw data (JSCallExpression) available; emitter pending |
| B2.JS.7 | `Channel` node + `EMITS` / `LISTENS` edges for `mitt`/`Bus.emit`/`Bus.on` — differentiator (no surveyed tool does this) | ⬜ | |
| B2.JS.8 | `Constant` node for exported object / array literals (rule tables, config) | ⬜ | |
| B2.JS.9 | `RE_EXPORTS` edge for barrel files | ⬜ | |

## Phase C — Workspaces & multi-module (2026-04-18, design landed)

Unblocks multi-repo / multi-module JVM indexing (classic Spring
plugin monorepos, sibling-common-lib setups, microservice forks).
Architecture generalises beyond JVM — lands as a shared core layer
consumed by every `FrameworkAdapter`.

| # | Deliverable | Status | Where |
|---|---|---|---|
| C0 | Full-loader `MERGE` fix — duplicate FQNs no longer abort bulk UNWIND | ✅ (2026-04-18) | `python/src/onelens/importer/loader.py::_batch_nodes` |
| C0 | Design spec — `docs/workspaces.md` (YAML schema, discovery rules, migration, non-goals) | ✅ (2026-04-18) | `docs/workspaces.md` |
| C0 | ADR-021 — Workspace abstraction for multi-repo / multi-module | ✅ (2026-04-18) | `docs/DECISIONS.md` |
| C0 | ADR-022 — App + Package as adapter-agnostic primitives | ✅ (2026-04-18) | `docs/DECISIONS.md` |
| C0 | ADR-023 — Dual engine (PSI in-IDE, metadata in CI) | ✅ (2026-04-18) | `docs/DECISIONS.md` |
| C1 | `Workspace` Kotlin type + YAML parser + implicit-workspace fallback | ✅ (2026-04-19) | `plugin/.../framework/workspace/Workspace.kt`, `WorkspaceLoader.kt` |
| C1 | `CollectContext.workspace` + `workspace.scope()` — all seven JVM collectors + five Vue3 collectors migrate off `projectScope(project)` | ✅ (2026-04-19) | 7 JVM collectors + 5 Vue3 collectors + `ModuleNameBinder` + `CallThroughResolver` |
| C1 | Workspace-relative file paths (replaces `removePrefix(basePath)`) | ✅ (2026-04-19) | `ClassCollector.kt`, `ModuleCollector.kt`, `AutoSyncFileListener.kt`, `Vue3Context.relativize` via `workspace.primaryRoot` |
| C1 | User-settable graph id (falls back to `workspace.name`, else `project.name`) | ✅ (2026-04-19) | `ExportService.kt`, `ExportFullAction.kt`, `AutoSyncService.kt` |
| C1 | Multi-git `DeltaTracker` — iterates roots, merges change lists, per-root state file | 🟡 partial (2026-04-19) | Primary root tracked; secondary roots fall through to VFS timestamp. Full multi-git = C1.1 |
| C1 | Python loader reads workspace header and respects `duplicateFqn` policy | 🟡 partial (2026-04-19) | `loader.py` reads `workspace.graphId` for wing stamp and logs non-default policies; `merge` enforced, other policies = C1.2 |
| C2 | `App` + `Package` node schema + loader ingest | ✅ (2026-04-20) | `ExportModels.AppData/PackageData`, loader `App`/`Package`/`PARENT_OF`/`CONTAINS` |
| C2 | `SpringBootAdapter` emits `App` per `@SpringBootApplication` with `@ComponentScan` resolution; `CONTAINS` edges | ✅ (2026-04-20) | `AppCollector.kt`, `PackageCollector.kt` |
| C2 | `Vue3Adapter` emits `App` per detected Vue root + `Package` per `src/` subdir | ✅ (2026-04-20) | `ExportService.kt` Vue3-section |
| C2.1 | Per-app PageRank — subgraph seed per `App`, write `Method.pagerank_<appId>` or scoped property | ⬜ | `python/src/onelens/importer/pagerank.py` |
| C2.2 | Skill reference updates — `references/*.md` teach the agent about `App` / `Package` / `CONTAINS` | ⬜ | `skills/onelens/references/` |
| C3a | Spring-plugin model collector — `SpringManager.getCombinedModel` per module; emits @Bean factories / XML / JAM beans with `@Primary` / scope / active profiles. Runtime-guarded so JAR still loads on IC / WebStorm; merged with annotation scraper via `(classFqn, name, factoryMethodFqn)` key | ✅ (2026-04-20) | `plugin/.../framework/springboot/SpringModelCollector.kt`, `SpringBootAdapter.kt#mergeSpring`, `ExportModels.SpringBean` +4 fields, `gradle.properties` bundled plugins |
| C3b | `@Qualifier` on INJECTS + `spring.factories` / `AutoConfiguration.imports` walker emitting `SpringAutoConfig` nodes. `@Profile` / `@Conditional` per-bean = deferred to C3b.1 | ✅ (2026-04-20) | `SpringCollector.extractQualifier`, new `AutoConfigCollector.kt`, loader JPA/autoconfig section |
| C3c | PSI-native JPA collector — `@Entity` / `@Table` / `@Id` / `@Column` / relations + `*Repository extends JpaRepository/CrudRepository/…` detection + derived-query edges. No plugin dep (works on IC) | ✅ (2026-04-20) | `JpaCollector.kt`, `ExportModels.JpaData/JpaEntity/JpaColumn/JpaRepository`, loader `HAS_COLUMN`/`RELATES_TO`/`REPOSITORY_FOR`/`QUERIES` |
| C4 | Headless metadata engine — JAR scan + Spring Boot `spring-configuration-metadata.json` / `AutoConfiguration.imports` / `spring.factories` / `spring.binders` + ASM bytecode → same JSON export shape | ⬜ | `python/src/onelens/engine/metadata/` (new) |
| C6 | SQL surface — Flyway auto-detect + custom query globs, per-statement split, DDL → JpaEntity edges | ✅ (2026-04-20) | `miners/flyway_detector.py`, `miners/sql_miner.py`, `loader._load_sql`, `sql:` yaml section |
| Q.code | Tests as dual-label `:Method:TestCase` with 10-kind taxonomy, `:TESTS`/`:MOCKS`/`:SPIES` edges, CHECK_HIERARCHY detection | ✅ (2026-04-20) | `TestCollector.kt`, `ExportModels.TestCaseData`, `loader._load_tests` |
| L | FalkorDB Lite (embedded Redis subprocess, Unix socket, zero-Docker) as default backend. Full feature parity (FTS, vector, Cypher). Large-project benchmark: 279.7 s vs 219.8 s Docker (+27 %) | ✅ (2026-04-20) | `falkordb_lite.py` rewritten (fixed broken `falkordblite` import → `redislite.falkordb_client`), `pyproject.toml` base-dep, plugin `ExportConfig.graphBackend` default flipped |
| C5 | GitHub Action wrapper (`action/action.yml`) — run metadata engine on PR, post impact summary comment | ⬜ | `action/` |

## Phase B2 — Deferred (Vue delta + auto-sync)

| # | Deliverable | Status | Notes |
|---|---|---|---|
| B2.1 | Extend `DeltaTracker` for `.vue`/`.js`/`.ts` git changes | ⬜ | Current tracker hard-coded to `.java` paths |
| B2.2 | Extend `AutoSyncFileListener` file filter | ⬜ | |
| B2.3 | `VueDeltaExportService` producing `vue3.components/...` deltas | ⬜ | |
| B2.4 | Python `delta_loader.apply_delta` Vue branch | ⬜ | |
| B2.5 | Path-prefix cascade-delete in `code_miner` (`delete_by_id_prefix("component:src/...")`) | ⬜ | |
| B2.6 | Symlink content-root balloon notification | ⬜ | `SymlinkResolver.hasOutOfTreeTargets` exists; UI balloon not yet wired |
| B2.7 | `retrieve` CLI Vue support (currently JVM-biased) | ⬜ | |

---

## Phase C — Deferred (more stacks + federation)

| # | Deliverable | Status |
|---|---|---|
| C.1 | Kotlin adapter (reuse Spring infra + Ktor/Android sub-adapters) | ⬜ |
| C.2 | Vert.x adapter (pure Java PSI, pattern-match on `Router.route()` etc.) | ⬜ |
| C.3 | FastAPI adapter (Python PSI + `CallThroughResolver` for `Depends()`) | ⬜ |
| C.4 | Per-repo graph federation (Python-side multi-hop traversal) | ⬜ Only needed at >10 repo scale |

---

## Repo hygiene

| # | Deliverable | Status | Where |
|---|---|---|---|
| H1 | `PreToolUse` hook (`block-client-names.sh`) refusing Write/Edit that introduces any term from `.claude/hooks/client-names.txt`. Case-insensitive, runs before every plugin / python / docs edit. Block list: client company name + Java package prefix. | ✅ | `.claude/hooks/block-client-names.sh`, `.claude/hooks/client-names.txt`, `.claude/settings.json` |
| H2 | Sanitize existing tree — 12 legacy references to a real-world client repo replaced with generic phrasing across plugin source, tests, docs, CHANGELOG. | ✅ (2026-04-18) | See ADR-015 |
| H3 | Verified remaining `motadata`/`flotomate` occurrences are all in gitignored local-dev files (`python/trial_*.py`, `python/modal_index*.py`, `python/benchmarks/*.yaml`, `.claude/settings.local.json`) — not in the shipped artifact. Any attempt to commit them would fail the hook. | ✅ | — |
| H4 | Git pre-commit hook (`.githooks/pre-commit`) — runs block-list on staged diff, compiles Kotlin when plugin sources changed, warns on tracker drift. Requires one-time `git config core.hooksPath .githooks`. | ✅ | `.githooks/pre-commit` |
| H5 | Pre-commit review pass on Phase B code — fixed Endpoint `wing` property, `_batch_edges_simple` `src_var` parameter (DISPATCHES bug), `_load_vue3` progress-context scope, `UnknownFileType.INSTANCE` replacement for brittle `.name == "UNKNOWN"` across 7 files. All 23 tests remain green. | ✅ | `python/src/onelens/importer/loader.py`, seven `plugin/.../framework/vue3/**.kt` files |
| H6 | Phase B dogfood on a real Vue 3 repo (1538 `.vue` files). `ExportService.exportFull` now iterates every detected adapter instead of hard-coding the Spring branch. Every Vue collector wraps `FileTypeIndex.getFiles()` in `DumbService.runReadActionInSmartMode` to satisfy WebStorm 2026.1's strict read-action guard. Edge match uses `STARTS WITH` on the `<filePath>::<symbol>` caller form + label restriction to `Component OR Composable` so ApiCall/Route/Store nodes don't pollute the caller match. DISPATCHES resolves relative `componentRef` against the routes file's dir before matching. `onelens stats` / `NODE_TYPES` include Vue labels. Dogfood verified: 1538 Components, 157 Composables, 53 Stores, 168 Routes, 998 ApiCalls + 2329 USES_STORE / 2589 USES_COMPOSABLE / 92 DISPATCHES / 2 CALLS_API edges. | ✅ | `ExportService.kt`, seven vue3 collectors, `loader.py`, `db.py` |
| H7 | Known gap — `CALLS_API` edge only covers inline Component / Composable calls (996 of 998 API calls live in plain `.js` helper files; those functions are not graph nodes). `ApiCall.callerFqn` / `filePath` properties retain the source info and cross-stack `ApiCall -> HITS -> Endpoint` traversals work regardless. Import-chain resolution (2-hop `Component -> helper -> ApiCall`) deferred to Phase B2. Documented in `skills/onelens/references/vue3.md`. | ⬜ Phase B2 | — |

## Palace MCP (MemPalace-shaped surface, additive)

| # | Item | Status | Landed |
|---|---|---|---|
| PAL-0 | Scaffold `onelens.palace` package (13 modules, 19 `@mcp.tool` registrations, console entry `onelens-palace`, WAL bootstrap). | ✅ (2026-04-18) | `python/src/onelens/palace/**`, `pyproject.toml` |
| PAL-1 | Read tools — status, list_wings, list_rooms, get_taxonomy, search (cross-wing, rerank), find_tunnels, graph_stats, get_aaak_spec. 30 s taxonomy cache. | ✅ | `palace/taxonomy.py`, `palace/drawers.py`, `palace/tunnels.py` |
| PAL-2 | Drawer writes — add_drawer / delete_drawer with dedup + WAL. | ✅ | `palace/drawers.py`, `palace/wal.py` |
| PAL-3 | Temporal KG — Entity + ASSERTS in dedicated FalkorDB graph `onelens_palace_kg`. kg_add / query / invalidate / timeline / stats. Structural projection auto-joins code CALLS/EXTENDS when entity matches an FQN. | ✅ | `palace/kg.py` |
| PAL-4 | Generic BFS `palace_traverse` over code graphs. | ✅ | `palace/navigation.py` |
| PAL-5 | Diary write/read under `wing=agent:<n>` namespace. | ✅ | `palace/diary.py` |
| PAL-6 | Content-axis halls added to `context/config.py` (HALL_SIGNATURE/EVENT/FACT/DOC). CodeMiner hall split deferred — current `hall_code` preserved to avoid ChromaDB metadata drift. | 🟡 | `context/config.py` |
| PAL-7 | Skill `skills/onelens/PALACE.md`; smoke tests `python/tests/palace/test_smoke.py`; CHANGELOG + ADRs. | ✅ | — |

## Release snapshots (Phase R — OSS-first)

Immutable per-release graph bundles for API-diff / regression-hunt /
zero-setup onboarding. Spec: `docs/design/phase-r-release-snapshots.md`.

| # | Deliverable | Status | Where |
|---|---|---|---|
| R1a | Python `snapshots.publisher` — Lite-first bundler, manifest v3, SHA256, optional Cosign sign, optional `gh release upload` + `snapshots.json` index maintenance | ✅ (2026-04-20) | `python/src/onelens/snapshots/publisher.py` |
| R1b | Python `snapshots.consumer` — list via `snapshots.json`, pull + verify (SHA256 authoritative from index, `.sha256` sidecar fallback, optional cosign verify), `tarfile` safe extract, GRAPH.COPY in-rdb rename so restored `<graph>@<tag>` resolves on FalkorDB Lite | ✅ (2026-04-20) | `python/src/onelens/snapshots/consumer.py` |
| R1c | MCP tools `onelens_snapshot_publish`, `onelens_snapshots_list`, `onelens_snapshots_pull` — 15 → 18 tools | ✅ (2026-04-20) | `python/src/onelens/mcp_server.py` |
| R1d | `scripts/regen_cli.sh` hardened (venv fastmcp path, PATH export for generate-cli internal spawn, `-f`, `main = app` alias) | ✅ (2026-04-20) | `python/scripts/regen_cli.sh` |
| R1e | End-to-end smoke: publish → unpack → GRAPH.COPY rename → `onelens_status --graph myapp@v0.1.0` returns 199,794 nodes / 1,044,467 edges / 2,312 endpoints (parity with live) | ✅ (2026-04-20) | — |
| R2 | Skill additions — SKILL.md decision rows for "compare two releases" / "pull snapshot"; recipe #16 cross-release diff (endpoint surface, signature drift, dead-code, SQL migrations) | ✅ (2026-04-20) | `skills/onelens/SKILL.md`, `skills/onelens/references/recipes.md` |
| R3 | Plugin — Snapshots as a 2nd tab of the OneLens tool window (no secondary window); `SnapshotManager` (HTTP + CLI shell) + `PublishSnapshotAction` (off-EDT git-tag prefill) + `PullSnapshotAction`; right-click on local row → Copy `--graph` / Open folder / Delete (cascades to context dir); HyperlinkLabel opens `onelens.workspace.yaml`; `Workspace.kt` `snapshots: SnapshotsConfig?`; optional `Git4Idea` dep wired via `git-features.xml` | ✅ (2026-04-20) | `plugin/src/main/kotlin/com/onelens/plugin/{ui,snapshots,actions}/…`, `plugin.xml`, `gradle.properties` |
| R4 | Plugin build + install zip + UI smoke | 🟡 | `onelens-graph-builder-0.1.0.zip` built; reinstall + click-through pending |
| R7 | UX gap-close (Stage 1c) — two-section Snapshots (Published + Installed) with install/delete right-click; Status tab branch+HEAD label, 30 s tick on last-sync, demoted Venv line | ✅ (2026-04-21) | `plugin/.../ui/OneLens*.kt`, `SnapshotManager.kt`, `SnapshotModels.kt` |
| R9 | Status tab UX polish (Stage 2) — Prereqs block collapses to one-line `✓ Prerequisites OK` when healthy; console panel hidden until first event; Clear Log also hides panel | ✅ (2026-04-21) | `plugin/.../ui/OneLensToolWindow.kt` |
| R8 | Snapshot-as-seed (Stage 1d) — `onelens_snapshot_promote` MCP tool + atomic rdb/context/rename/marker; DeltaTracker consumes `.onelens-baseline` at entry (one-shot, schema-gated); `StartFromSnapshotAction` with ancestor + overwrite guards; right-click "Start working from this snapshot" on Published & Installed rows | ✅ (2026-04-21) | `python/.../snapshots/seed.py`, `mcp_server.py`, `DeltaTracker.kt`, `StartFromSnapshotAction.kt`, `OneLensSnapshotsToolWindow.kt`, `docs/design/phase-r-stage-1d-snapshot-as-seed.md` |
| R5 | CI snapshot producer (GitHub Actions) | ⬜ | Phase R.1 — blocked on headless collector |
| R6 | Self-host S3/MinIO backend | ⬜ | Phase R.2 |

## Open regression / verification items

1. Phase A5 — sync the reference Java backend with the rebuilt plugin and diff counts against the captured baseline (`Class=11944, Method=81907, Field=58485, SpringBean=2335, Endpoint=2320, Module=26, Annotation=222`).
2. Phase B7 — sync the reference Vue 3 frontend repo and verify `Component ≥ 1400`, `Store ≥ 35`, `Composable ≥ 15`, `Route ≥ 60`, `ApiCall > 500`.
3. Bridge verification — dogfood HITS count when both reference projects are synced into the same FalkorDB graph.
4. Extend `python/benchmarks/cases.yaml` with Vue-specific cases before claiming Phase B "done-done".
