# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — scripts/bundle.sh multi-graph (2026-04-18)

- `scripts/bundle.sh` accepts N graph names or `--all`; packs one
  `chroma/<graph>.tgz` per requested graph. Manifest bumped to
  `schema_version: 2` with `graphs[]` + `chroma_graphs[]` arrays.
  Single-graph invocation still works (archive name preserves old
  `onelens-bundle-<graph>-<ts>.tgz` form).
- `scripts/restore.sh` parses both v1 (single-graph, legacy
  `chroma.tgz`) and v2 (multi-graph `chroma/<g>.tgz`) manifests,
  verifies every listed graph loaded from the RDB, and restores each
  graph's chroma dir independently. RDB itself already shipped whole
  falkor state; this closes the gap on embeddings + manifest.

### Added — Vue 3 graph + retrieval hardening (2026-04-18)

- **`VuePsiScope`**: Stub-aware `<script>` / `<script setup>` root
  resolution via `org.jetbrains.vuejs.index.findModule`. All five Vue
  collectors (`ApiCall`, `Composable`, `JsModule`, `PiniaStore`,
  `SfcScriptSetup`) migrated from raw `PsiTreeUtil` walks; kills the
  `useI18n × 378` phantom composable duplication that showed up on a
  1500+ component dogfood when stub-backed trees silently missed
  declarations inside embedded `<script>` nodes.
- **Composable local-decl gate**: `isLocalTopLevelDecl` filter on
  `ComposableCollector` restricts emission to declarations in the
  current file whose parent chain terminates at the file (no nested
  helpers, no cross-file stub phantoms).
- **Alias / relative specifier normalization**: `JsModuleCollector.
  normalizeModuleSpecifier` + `LazyRouteCollector.resolveComponentRef`
  turn `@/views/Foo.vue` → `src/views/Foo.vue` using `ctx.aliases`.
  Without this, every alias-form IMPORTS / DISPATCHES edge silently
  dropped at the Python join.
- **JsModuleCollector stub-aware import walk**:
  `findImportDeclarations` uses `JSResolveUtil.getStubbedChildren(scope,
  ES6_IMPORT_DECLARATION)` on `.vue` files — matches Vue plugin's own
  `VueExtractComponentDataBuilder` pattern. Textual regex fallback
  widened to `[\s\S]*?` so Prettier-formatted multi-line imports land
  and `import type { X }` clauses are parsed correctly.
- **`fqnFor` relativization**: JsFunction import-resolve fqns now
  use project-relative paths so they join cleanly against the
  `JsFunctionData.fqn` target shape.
- **Route `fullPath`**: Parent-walk roll-up of vue-router nested
  routes (`r.fullPath CONTAINS '/ticket'` now works); absolute child
  paths override the parent prefix per vue-router semantics.
- **`HAS_FUNCTION` edge**: `JsModule -[:HAS_FUNCTION]-> JsFunction` by
  shared filePath. Cross-stack traversal `Component -[IMPORTS]->
  JsModule -> JsFunction -[CALLS_API]-> ApiCall` drops the filePath
  join in Cypher.
- **`IMPORTS_FN` Python-side bridge**: Derives function-level import
  edges from module-level IMPORTS by joining `importedName` to
  `JsFunction {name, filePath}` on the target module. Workaround for
  stub-empty `importedBindings`. Composite `(name, filePath)` range
  index (`JsFunction_name_file` in `schema.py`) keeps it O(log N).
- **Label-split IMPORTS batching**: Loader now splits imports-resolved
  and imports-modulelevel UNWINDs by source label (`Component` /
  `Composable` / `Store` / `JsModule`) so each batch uses the
  per-label `filePath` range index instead of a label-less full-node
  scan. Eliminates minute-scale waits on 22 k+ edge batches.
- **ES6 candidate expansion**: Bare `./config` resolves to `./config.js`
  / `./config.ts` / `./config/index.js` / `./config/index.ts` before
  the JsModule join. Without this, extensionless imports dropped.
- **`CALLS_API` label widening**: Matches JsFunction callers (by exact
  fqn) in addition to Component / Composable (by `STARTS WITH
  <filePath>::`). Split avoids the 15-20× amplification that would
  fire if JsFunction used the same `STARTS WITH` rule (every function
  in the same file would then absorb the edge). Dogfood: 22 974 bogus
  edges → 1 404 real edges.
- **FTS Vue label expansion**: `search_code` now covers Component /
  Composable / Store / Route / ApiCall / JsModule / JsFunction in
  addition to the JVM trio. All seven queries in `queries.py` return
  prefixed `<type>:<key>` fqns that match ChromaDB drawer ids and the
  `_fetch_locations_batch` prefix partition.
- **Retrieval `_dedupe_by_parent`**: Defensive collapse of sub-chunks
  via `@@<role>` separator — no-op on current single-drawer mining but
  ready for later chunking.
- **`_fetch_locations_batch` Vue block**: Resolves `filePath` +
  `lineStart` / `lineEnd` for seven Vue labels via one UNWIND per
  label; grouped by prefix, identifier stripped back to the graph
  node's key_prop.
- **`_strip_js_imports`**: Shared utility in `code_miner` that strips
  ES6 imports from Component / Composable / Store bodies before they
  become embedding documents. Page-level files routinely used 10-30
  import lines of their 2 000-char budget on pure boilerplate.
- **Store id dedup**: `_mine_vue_stores` collapses duplicate
  `defineStore('id', …)` registrations across feature modules — first
  row wins. Prevents ChromaDB duplicate-id batch rejection.

### Fixed — Rerank squash + FTS prefix + Modal snapshot (2026-04-18)

- **Rerank 0-1 squash**: `Reranker.score` sigmoid-normalizes raw
  cross-encoder logits before returning. Retrieval's
  `ONELENS_MIN_RERANK_SCORE=0.02` assumed a 0-1 range — without the
  squash every hit dropped below threshold and `hybrid_retrieve`
  returned empty. Modal wrapper simplified to a pass-through so local
  and remote paths share one normalization point.
- **FTS Vue id prefix**: Route / ApiCall / JsModule / JsFunction FTS
  queries now return `<type>:<key>` fqns instead of raw node values.
  Without this, RRF treated FTS and semantic hits as different
  entries and `_fetch_locations_batch`'s prefix-partitioned Vue block
  never resolved file paths / snippets.
- **Modal weights-in-image**: `onelens-models` Volume removed; weights
  baked via `run_function(_prefetch_weights)` at image build.
  Triggered by recurring 9p snapshot-restore failures (Modal docs:
  *"Deleting files in a Volume used during restore will cause restore
  failures"*). Image grows ~2.5 GB; restore failure rate → 0. Base
  switched to `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` so
  `onnxruntime-gpu` actually loads CUDAExecutionProvider instead of
  silently CPU-falling back on `debian_slim`.
- **`DEFAULT_CHUNK_SIZE` 128 → 96**: L4 24 GB OOMs at 256 on Qwen3
  seq=512 attention; server-side `ONELENS_EMBED_BATCH=32` caps it.
- **Vue-only export null-spring crash**: `data.get("spring") or {}`;
  explicit `"spring": null` used to raise `AttributeError` in
  `_build_indexes` and `_mine_endpoints`.
- **MCP `import_graph` stdout chatter**: Prior fix stands; listed here
  only for context since the underlying Rich-console redirect interacts
  with the sigmoid / Modal changes above.

### Added — Enum constants + annotation attributes (2026-04-18)

- New `EnumConstant` node + `HAS_ENUM_CONSTANT` edge. Each constant carries
  `ordinal`, `enumFqn`, `args` (JSON), `argList` (flat string array for `IN`
  predicates), `argTypes`, and source location. Resolves enum-as-config
  registries like `OrderStatus(canTransitionTo=Set.of(APPROVED, REJECTED))`
  so per-constant feature / module / role questions answer from Cypher
  instead of source grep.
- `ANNOTATED_WITH` edge gains an `attributes` JSON property holding the resolved
  values of every annotation attribute — arrays, class literals (FQN), enum
  refs (name), nested annotations. Legacy `params` map is preserved for
  back-compat with the pre-1.1 importer.
- `plugin/.../collectors/ExpressionResolver.kt` — shared PSI-native resolver.
  Delegates to `PsiConstantEvaluationHelper` for JLS constant expressions;
  handles collection factories via a semantic heuristic (`static` method
  returning `Collection` / `Map` / `Iterable` — covers JDK, Guava, Eclipse
  Collections, Vavr, user builders without a library list), array initializers,
  class literals, enum refs, and nested annotations. Unresolvable fragments
  render as `<dynamic>`.
- `DeltaLoader`: enum constants cascade-delete with their owning class and
  re-upsert on every class modification. Also fixes a latent pre-existing gap
  where `ANNOTATED_WITH` edges on modified classes were never re-applied —
  annotation add/remove on a changed file used to silently drift from the
  graph until the next full import.
- Export version bumped to `1.1.0`. Older exports still load (new fields
  default to empty); older importers ignore the new fields.
- New skill cookbook sections (`skills/onelens/references/jvm.md` §14-15)
  with Cypher recipes for module-scoped enum filtering and annotation
  attribute searches.

### Added — Phase B2 · JS business-logic layer (first cut, 2026-04-18)

- `JsModule` node per `.js` / `.ts` / `.vue` file. Container for the import
  graph; always present even when the file is also modelled as a Component /
  Composable / Store so `IMPORTS` edges always have a valid anchor.
- `JsFunction` node per top-level `export function`, `export const x = () =>`,
  `export default …`. Closes the Phase B gap where plain JS helper modules
  (`src/data/*.js`, module-local `helpers/*.js`, `*-api.js`) produced zero
  nodes even when several components imported them. Mirrors tree-sitter's
  `@definition.function` set; uses PSI for accuracy.
- `IMPORTS` edge (source = `JsModule` / `Component` / `Composable` / `Store`;
  target = `JsFunction` when symbol-resolved, else `JsModule` when only the
  file resolves). Resolution goes through IntelliJ JS PSI with a 2-hop
  `ES6ImportSpecifierAlias → original declaration` step that covers
  `import { X as Y }` — the one failing case from `ImportResolveTest`.
- `NODE_TYPES`, `NODE_SCHEMA`, `FULLTEXT_SCHEMA` updated: `JsModule` FTS
  indexed on `filePath`; `JsFunction` indexed `name` (w=10) / `filePath`
  (w=3) / `body` (w=1) for semantic retrieval by intent.
- Known deferred: JS `CALLS` edges (raw data present, emitter pending),
  `Channel` / `EMITS` / `LISTENS` for `mitt` / `Bus` (no other indexer in the
  surveyed set — potpie, SCIP, aider — does this), `Constant` node for
  exported literals, `RE_EXPORTS` edge for barrel files.

### Fixed — Phase B dogfood round (2026-04-18)

- `ExportService.exportFull` now iterates EVERY detected adapter's collectors
  instead of hard-coding the Spring branch. Earlier the document assembled
  `adapters: ["vue3"]` but `vue3: null` because the Vue collector never ran —
  each adapter's collector is now invoked, typed state (`lastResult` /
  `lastContext`) pulled out, and the Vue3Data is stitched into the document.
- Every Vue collector + resolver wraps `FileTypeIndex.getFiles()` in
  `DumbService.runReadActionInSmartMode(Computable { … })`. WebStorm 2026.1
  throws "Read access is allowed from inside read-action only" for the
  raw call; the earlier unit tests never hit it because `BasePlatformTestCase`
  runs in smart mode by default.
- Loader edge match relaxed to accept the canonical
  `<filePath>::<symbol>` caller form emitted by Vue collectors
  (component-sourced edges) via `e.caller STARTS WITH (c.filePath + '::')`.
  Without this, only composable-sourced edges matched — 345/2484 USES_STORE
  edges, 251/2583 USES_COMPOSABLE edges. After the fix: 2329 / 2589.
- `DISPATCHES` matcher uses filePath equality after resolving the
  route's relative componentRef against the routes file's own directory.
  Previous `filePath ENDS WITH` clause over-matched by 18× (1698 vs
  expected 95); now lands on 92.
- `CALLS_API` / `USES_STORE` / `USES_COMPOSABLE` caller match is label-
  restricted to `Component` or `Composable` so the untyped MATCH does not
  also pick up `ApiCall` / `Route` / `Store` nodes (which carry
  `filePath`). Unconstrained earlier this ballooned `CALLS_API` from the
  expected 979 to 19 041 as every ApiCall got paired with every caller.
- Known gap documented: `CALLS_API` only emits when the calling site is
  itself a Component or Composable node. API calls inside plain JS
  helper files (`ticket-api.js` etc) preserve `ApiCall.callerFqn` /
  `ApiCall.filePath` as properties but have no node to anchor the edge to.
  Phase B2 adds import-chain resolution so the 2-hop edge
  `Component → helper → ApiCall` materialises. See `references/vue3.md`.
- `onelens stats` / `NODE_TYPES` now include Vue labels (Component,
  Composable, Store, Route, ApiCall, EnumConstant) so the counts surface
  in default CLI output.

### Fixed — Pre-commit review (2026-04-18)

- `loader._load_vue3` + Spring path: every `Endpoint` / `SpringBean` node now
  carries a `wing` property. Without it, `bridge_http.compute_hits`'s
  `WHERE e.wing IS NOT NULL` check was always false and the cross-wing
  `HITS` edge emission was silently zero.
- `_batch_edges_simple` took a new `src_var` parameter. Previously the
  hard-coded `WITH e, c` broke the DISPATCHES batch (src bound as `r`,
  not `c`), so every DISPATCHES edge was swallowed by the generic except.
- `_load_vue3` is now called *inside* the `with Progress(...)` context so
  `progress.add_task` has a live progress bar.
- Every Vue collector / resolver that checks file-type registration now
  compares against `UnknownFileType.INSTANCE` instead of the brittle
  string literal `"UNKNOWN"`.
- `.githooks/pre-commit` — new git pre-commit hook that re-runs the
  client-name block check on the staged diff, compiles Kotlin when
  plugin sources changed, and warns if code changed without a tracker
  update. Install via `git config core.hooksPath .githooks` (one-time
  per clone).

### Changed — Repo hygiene (2026-04-18)

- All plugin source / tests / docs / CHANGELOG entries referring to a specific
  real-world test repo by name are now rewritten generically ("a large Vue 3
  repo", "the reference Java backend"). 12 occurrences across 7 files.
- New `PreToolUse` hook (`.claude/hooks/block-client-names.sh`) reads a
  maintained block list (`.claude/hooks/client-names.txt`) and refuses any
  Write / Edit tool call whose `file_path`, `content`, or `new_string`
  contains a forbidden term (case-insensitive). Wired into
  `.claude/settings.json` so future sessions can't reintroduce the same
  pattern; add / retire block terms in the txt file as review uncovers them.
- Documented as ADR-015 in `docs/DECISIONS.md`.

### Added — Phase B · Vue 3 adapter (2026-04-17)

- Framework-adapter SPI (`com.onelens.plugin.framework.FrameworkAdapter`) plus
  an `ExportDocument.vue3` subdoc carrying Component / Composable / Store /
  Route / ApiCall nodes and USES_STORE / USES_COMPOSABLE / DISPATCHES /
  CALLS_API edges.
- `Vue3Adapter` detects `package.json` with a Vue 3 range and drives a composite
  `Vue3Collector` that runs:
  - `SfcScriptSetupCollector` — every `.vue` file, `<script setup>` macros
    (`defineProps` / `defineEmits` / `defineExpose`), body truncated to 2000 chars.
  - `PiniaStoreCollector` — both options-style and setup-style `defineStore` with
    state / getters / actions extraction.
  - `ComposableCollector` — `useX` naming convention + returns-something
    heuristic, skips files that define Pinia stores.
  - `LazyRouteCollector` — `*-routes.js` + sibling `config.js` substitution,
    lazy-import target resolution, DISPATCHES edges.
  - `ApiCallCollector` — axios/fetch/api clients, literal and template URLs
    with a `parametric` flag plus binding source.
  - `CallThroughResolver` — direct USES_STORE plus 1-hop indirect edges via
    helper wrappers (`via` records the wrapper name).
  - `ModuleNameBinder` — top-level `const x = 'literal'` resolution turns
    parametric URLs into extra literal variants the bridge matcher can use.
- `ViteAliasResolver` merges `jsconfig.json` / `tsconfig.json` `compilerOptions.paths`
  with `vite.config.{js,ts,mjs}` `resolve.alias`, vite winning on conflicts.
  Picks up 27/27 aliases on a large real-world Vue 3 repo used as the test target.
- `SymlinkResolver` walks `src/` for symlinks, classifies targets as
  inside/outside project content roots.
- Python — `bridge_http.compute_hits` emits cross-wing `HITS` edges between
  Vue `ApiCall` and Spring `Endpoint` nodes after `normalize_path` collapses
  `/users/{id}` / `/users/${id}` / `/users/{userId}` into `/users/{}`.
- Python — `loader._load_vue3` + `_batch_edges_simple` import the Vue subdoc
  with the same `wing` property used for JVM wings, enabling single-graph
  full-stack traversals.
- Python — `pagerank.compute_vue_pagerank` seeds Route nodes as entry points
  and writes Component / Composable / Store `pagerank`.
- Python — `code_miner._mine_vue_components` / `_mine_vue_composables` /
  `_mine_vue_stores` create ChromaDB drawers (`component:<filePath>` /
  `composable:<fqn>` / `store:<id>`) on the unified metadata schema, enabling
  semantic retrieval over frontend code.
- Skills — split `onelens` into a hub `SKILL.md` plus
  `references/jvm.md` and `references/vue3.md` for progressive disclosure.
  Plugin bundling extended to ship all three files; `InstallSkillAction` copies
  the references directory too.
- 23 new tests — Vue PSI PoC (6), ViteAliasResolver unit (10), collector smoke
  including Pinia / SFC / Composable / Route / ApiCall / CallThrough /
  ModuleNameBinder (7).
- Documentation — `docs/PROGRESS.md` (feature tracker), `docs/vue-psi-poc.md`
  (PSI API inventory locked for Phase B).

### Added — Phase A · Framework adapter refactor (2026-04-17)

- `FrameworkAdapter` / `Collector` / `CollectContext` / `CollectorOutput`
  interfaces under `com.onelens.plugin.framework`.
- `plugin.xml` split: core declares only `com.intellij.modules.platform`;
  Java/Spring lives in `framework-springboot.xml` via optional
  `com.intellij.modules.java` dependency; Vue lives in `framework-vue3.xml`.
  Plugin now installs on WebStorm, PyCharm, and IDEA Community/Ultimate.
- Gradle `platformType` switched to `IU` so the Ultimate-bundled JavaScript +
  Vue plugins are on the compile/test classpath; runtime portability preserved
  via the optional `config-file` dependency pattern.
- Settings — `vueAdapterOverride` on `OneLensSettings` (auto/on/off).

### Added

- Full OSS scaffolding via `project-ignition`: `AGENTS.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md`, dual
  MIT/Apache-2.0 licensing, `docs/` tree (introduction, concepts,
  architecture, vision, roadmap, philosophy, comparison,
  contributing, governance, security, faq, terms, SESSION-START,
  DECISIONS), and `.claude/` dogfood setup (subagents + hooks +
  settings).
- Semantic retrieval layer: Qwen3-Embedding-0.6B + ChromaDB +
  mxbai-rerank-base cross-encoder. Exposed via `onelens retrieve`
  and `onelens search --semantic`.
- Delta-aware embeddings with deterministic drawer IDs
  (`method:<fqn>`, `class:<fqn>`). Cascade delete via ID prefix when
  a class is removed.
- PageRank prebake at import (NetworkX, personalized by REST
  endpoints / `@Scheduled` / `@EventListener` / `@PostConstruct`).
  Stored as `Method.pagerank` / `Class.pagerank` and used as a
  multiplicative boost in hybrid retrieval.
- Query router in `hybrid_retrieve`: short-circuits to direct Cypher
  for exact class names / FQN fragments; full FTS + semantic RRF +
  rerank only for conceptual queries.
- FastMCP v3 server as the single source of truth for the CLI.
  `onelens` command is auto-generated by `fastmcp generate-cli`.
- IntelliJ plugin: auto-sync on file save (debounced 5 s), onboarding
  balloon, bundled skill install action, Python venv auto-create via
  `uv`, FalkorDB TCP preflight.
- GitHub Actions: CI (Kotlin compile + plugin build + Python import
  + CodeMiner API-surface guard) and tagged releases (`vX.Y.Z` →
  plugin ZIP attached to GitHub Release).

### Changed

- Weighted FTS indexes in FalkorDB (`name: 10`, `javadoc: 3`,
  `body: 1`).
- Reranker pool + threshold calibrated (0.02) to filter gibberish
  while preserving conceptual matches.
- Unified ChromaDB metadata schema across full and delta write
  paths (`wing`, `room`, `hall`, `fqn`, `type`, `importance`,
  `filed_at`).

### Fixed

- Delta import no longer passes `--clear` (would wipe the graph
  every auto-sync).
- CLI command name alignment: plugin now invokes `import_graph`
  (previously shelled out to the old `import` name).
- Cascade delete uses ID-prefix scan instead of nonexistent
  `class` metadata key.
- `_compatible_bean_types` now unions target's class ancestors with
  caller classes; fixes 408→1 over-approximation on impact analysis
  of polymorphic methods.
- Dumb-mode retry no longer injects empty string into
  `pendingChangedFiles`.

### Security
