# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
