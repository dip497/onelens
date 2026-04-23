# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Phase U · Status tab UX + reindex tool (2026-04-23)

- **Toggle Semantic Index toolbar button** in the OneLens tool window.
  Starts/stops the MCP HTTP service inline — no Settings round-trip.
  `OneLensToolWindow.kt:ToggleSemanticToolbarAction`.
- **Rebuild Semantic Only button.** Re-embeds the current graph from
  the newest `<graph>-full-*.json` without a fresh graph import.
  Backed by new `onelens_reindex_semantic` MCP tool
  (`mcp_server.py`) which replays `CodeMiner.mine()` against the
  latest export. ~2–3 min GPU / ~30 min CPU.
- **Clean Up danger zone** dropdown — Clear exports / Reset semantic
  / Delete graph. Auto-restarts MCP after "Reset semantic" if
  Semantic Index was on. New `ui/GraphCleanupService.kt`.
- **VRAM display** next to the semantic label. `SystemMonitor.kt`
  shells `nvidia-smi --query-compute-apps=pid,used_memory` and
  filters to the MCP child process PID so only OneLens's VRAM shows,
  not the whole card.
- **Compact `onelens_retrieve` response shape.** Drops `context_text`,
  `callers`, `callees`; caps `snippet` to 600 chars (~5 lines).
  Agents use Read tool at `file_path`+line range for full code, per
  token-efficiency feedback. Augment-style docstring documents the
  compact shape + when-to-use examples.

### Added — Phase U.1 · Cancellable sync + cleanup guard (2026-04-24)

- **Sync is now actually cancellable.** `ExportService.syncToGraph`
  previously called `process.waitFor()` with no cancellation polling —
  the IDE's Stop button did nothing; the Python child ran to
  completion while the status bar lied about "Stopping…". The reader
  now runs on a daemon thread, the main thread polls
  `ProgressManager.progressIndicator.isCanceled` every 200 ms, and on
  cancel both the child and its descendants are
  `destroyForcibly()`'d before throwing `ProcessCanceledException`.
- **Cross-entry-point sync guard.** New app-level
  `SyncCoordinator` service tracks one active sync across the toolbar
  Sync action, the Tools menu `ExportFullAction`, and
  `AutoSyncService`. Starting a second sync while one is in flight
  now surfaces a clear warning instead of racing.
- **Clean Up blocks while a sync is running.** `GraphCleanupService`
  throws `SyncInProgressException` if `SyncCoordinator.isRunning()`;
  the DangerZone dropdown is disabled during syncs and surfaces a
  dialog otherwise. Fixes the race where "Delete graph" could remove
  an `exports/*.json` the live CLI was about to read —
  manifested as a `FileNotFoundError` on an older timestamp than the
  just-written one.

### Fixed — Phase U (2026-04-23)

- **Empty `snippet` in retrieval hits.** `ONELENS_PROJECT_ROOT` was
  not passed to the MCP child — `_read_snippet` couldn't resolve
  project-relative `file_path`s. Plugin now sets `project.basePath`
  in both the CLI subprocess and the MCP HTTP path
  (`ExportService.kt`, `ToggleSemanticIndexAction.kt`).
- **TRT OOM on 4 GB consumer cards.** Embedder + reranker each
  requested 2 GB workspace → second model failed to allocate on
  RTX A2000 Laptop / 3050 mobile. Capped default to 512 MB via new
  `ONELENS_LOCAL_TRT_WORKSPACE_MB` env (`local_backend.py`).
- **TRT engine-cache collision between embedder and reranker.**
  Both wrote to `trt-cache/jina-v2-code/` — second model loaded the
  wrong engine topology at runtime. `_build_providers` now takes
  `cache_slug`; `LocalReranker` passes `"bge-reranker-base"`
  (`local_backend.py`, `local_reranker.py`).
- **`SnapshotManager` `InstantiationException` at runtime.** The
  `@Service(Project, CoroutineScope)` constructor compiled fine but
  failed reflective lookup after Ktor pulled a different
  `kotlinx-coroutines-core` into the plugin classpath. Dropped the
  unused scope param (`SnapshotManager.kt`).
- **Numpy truthiness crash in ChromaBackend dim sanity check.**
  `if stored and len(stored[0])...` raised on ndarrays. Removed the
  whole check — ChromaDB's native dim-mismatch error is sufficient
  signal, and the `peek()` added startup cost on every graph open
  (`backends/chroma.py`).
- **TRT settings drift after install-via-button.** User would install
  TensorRT but `localEmbedderUseTRT` stayed false (if venv was
  created before the button shipped). Settings panel now self-heals
  by flipping the flag when `isTensorrtInstalled()` returns true
  (`SemanticSettingsConfigurable.kt`).

### Added — Phase T · Plugin ⇄ MCP HTTP (warm process) (2026-04-21)

- **Embedded MCP HTTP server lifecycle.** New
  `plugin/.../mcp/OneLensMcpService.kt` app-level service spawns the
  Python MCP server as a child process (`python -m onelens.mcp_server
  --http`) on first project open when `buildSemanticIndex` is on.
  Writes the chosen port to `~/.onelens/mcp.port` for external MCP
  clients to discover. Graceful SIGTERM on IDE shutdown via
  `Disposable`. Port strategy: base 29170, retry up to +30 on
  `BindException`. Pattern cribbed from `hechtcarmel/jetbrains-index-mcp-plugin`
  adapted for Python-child instead of in-JVM Ktor.
- **JSON-RPC client over Java 11 HttpClient** in
  `plugin/.../mcp/OneLensMcpClient.kt` (~130 LoC). Stateless mode
  (`FASTMCP_STATELESS_HTTP=1`) skips MCP-Session-ID tracking. Parses
  FastMCP's Server-Sent Events response (walks `data:` lines) and
  unwraps `result.structuredContent` → plain JSON for callers.
- **`ExportService.syncToGraph` fast path.** When the MCP server is
  reachable, the sync POSTs `onelens_import` via HTTP instead of
  spawning a fresh Python subprocess — first delta goes through, then
  every subsequent delta reuses the warm embedder + reranker. Cold
  fallback to the CLI subprocess on any MCP failure, preserving
  today's reliability floor.
- **Python entry point** — `mcp_server.py`'s `__main__` gained
  `--http --host --port` flags so the plugin can spawn the HTTP
  transport directly (`fastmcp run` is not a hard requirement).
- **Multi-shape daemon warmup.** `ONELENS_WARM_ON_START=1` now primes
  batch shapes `[1, 32]` for the embedder and `[30]` for the rerank
  cross-encoder, so TRT engines are cache-hot for production shapes
  before the first user query lands. Previously warmed only batch=1,
  which left delta syncs paying a ~60 s engine build for the
  typical batch=32 Kotlin-side chunk size.
- **Docs**: ADR-028 covers the plugin-owned Python child model vs
  hechtcarmel's in-JVM Ktor approach. Claude Code / Codex / Cursor
  users register the server with
  `claude mcp add --scope user --transport http onelens http://127.0.0.1:<port>/mcp/`
  (discover the port via `cat ~/.onelens/mcp.port`).

### Added — Phase S · Local semantic embedder + reranker (2026-04-21)

- **Fully-local embed + rerank via onnxruntime.** New backends under
  `python/src/onelens/context/embed_backends/`:
  - `local_backend.py` — Jina-embeddings-v2-base-code (161M, 768-dim,
    Apache 2.0) over ONNX. Auto-picks `TensorrtExecutionProvider` (fp16)
    when `tensorrt-cu12` is importable, else `CUDAExecutionProvider`
    (fp32), else CPU. Preloads `libnvinfer*.so` via `ctypes.CDLL` so
    the TRT EP works without `LD_LIBRARY_PATH` surgery.
  - `local_reranker.py` — `BAAI/bge-reranker-base` cross-encoder, same
    provider-pick logic. Keeps Modal-path retrieval parity.
- **Measured on RTX A2000 Laptop 4 GB**: CPU 46 ms/item → ~77 min / 100k;
  CUDA fp32 4.5 ms/item → ~7.6 min; TRT fp16 1.2 ms/item → ~2 min. All
  top-1 semantic hits identical to the Qwen3 baseline on spot checks.
- **New Semantic settings screen** at `Preferences → Tools → OneLens
  Semantic`. Two user-visible backends:
  - **Local** (default) — shows live provider label
    (`cpu`/`cuda-fp32`/`trt-fp16`) and a one-click "Install TensorRT
    fp16 acceleration (+1 GB, ~3× faster)" button.
  - **OpenAI-compat** — Base URL + API key + model + dimension. API
    key lives in IntelliJ PasswordSafe (`OpenAiSecrets.kt`), never in
    plaintext XML.
- **Plugin install branching.** `PythonEnvManager.installSemanticStack()`
  dispatches on `embedderBackend`:
  - `local`  → chromadb + onnxruntime-gpu + cuDNN + cuBLAS + tokenizers
    + HF hub (~1 GB).
  - `openai` → chromadb + httpx only (~80 MB).
  - New `installTensorrt()` + `detectLocalProvider()` helpers.
- **Env wiring** in `ExportService.syncToGraph`: passes
  `ONELENS_EMBED_BACKEND` / `ONELENS_RERANK_BACKEND` + (for openai)
  `ONELENS_EMBED_BASE_URL/MODEL/DIM/API_KEY` to every CLI subprocess.
  Local path always sets rerank=local so retrieval uses BGE cross-encoder.
- **Dim-mismatch guard** in `chroma.py`: at query time, peeks one stored
  vector and compares dim vs active embedder; raises a clear re-sync
  instruction if they diverge (prevents silently-wrong cosine scores
  when the user swaps Jina ↔ OpenAI without `--clear`).
- **`pyproject.toml` extras**: new `context-local` (1 GB, default for
  plugin) + `context-local-trt` (adds `tensorrt-cu12`). `context`
  retained for Modal/OpenAI-only users.

### Changed — Phase R Stage 2 · Status tab UX polish (2026-04-21)

- **Prerequisites block collapses when healthy.** If backend + uv + venv
  + CLI are all ✓, the full checklist hides behind a single green
  `✓ Prerequisites OK (click to expand)` line. Click to toggle. Failures
  auto-expand the full list. Reclaims ~30 % of panel height.
- **Event log hidden until useful.** Console panel starts collapsed.
  First published event (Info/Warn/Error/SyncComplete/…) shows it. The
  toolbar's `Clear Log` action renamed → `Clear / Hide Log` — clears
  text + hides panel in one shot.

### Added — Phase R Stage 1d · Snapshot-as-seed for onboarding (2026-04-21)

"Start working from this snapshot" — new dev installs a shared release
snapshot and seeds their live graph from it, so the next Sync Graph
deltas only the branch diff since the tag's commit instead of a 20-min
full reindex.

- `python/src/onelens/snapshots/seed.py` (new, ~140 LoC) — atomic
  promote with bail-on-failure ordering (rdb → GRAPH.COPY rename →
  context → marker). Tag-commit fallback resolves missing `commitSha`
  via `git rev-parse <tag>` when publisher ran outside a git context.
- `python/src/onelens/snapshots/consumer.py` — install path now copies
  `manifest.json` alongside the rdb so promote can read
  `commitSha`/`schemaVersion` without re-extracting the tgz.
- `python/src/onelens/mcp_server.py` — new `@mcp.tool`
  `onelens_snapshot_promote(graph, tag)`. Tool count: 18 → 19.
- `plugin/.../export/delta/DeltaTracker.kt` — consumes
  `~/.onelens/graphs/<g>/.onelens-baseline` at entry (one-shot, delete
  before diff runs, race-safe). Schema-version mismatch discards the
  marker + falls back to full sync (SharedIndexes precedent). Overrides
  the "No previous export → full" path when a valid seed is present.
- `plugin/.../actions/StartFromSnapshotAction.kt` (new) — off-EDT ancestor
  check via `git merge-base --is-ancestor`, confirm dialog with 2
  guards (live-overwrite, non-ancestor), install-then-promote via CLI
  in a `Task.Backgroundable`. Notification on completion.
- `plugin/.../ui/OneLensSnapshotsToolWindow.kt` — right-click `Start
  working from this snapshot` added to both Published and Installed
  rows.
- `docs/design/phase-r-stage-1d-snapshot-as-seed.md` (new) — full
  spec: UX guards, atomicity order, marker format, risk register,
  validation smoke test. Design validated against SCIP/LSIF, Bazel
  remote cache, Nix substituters, Docker BuildKit, IntelliJ
  SharedIndexes before implementation.

### Added — Phase R Stage 1c · Snapshots UX gap-close (2026-04-21)

Plugin UI UX pass closing gaps surfaced during Stage 1b smoke-test: the
Snapshots tab only listed extracted snapshots from `~/.onelens/graphs/`
and silently hid published tgz archives in `~/.onelens/bundles/`, so a
fresh publish looked like nothing happened.

- `plugin/.../snapshots/SnapshotModels.kt` — new `PublishedBundle` data
  class (graph/tag/tgzPath/tgzBytes/lastModified).
- `plugin/.../snapshots/SnapshotManager.kt`:
  - `listPublished(graph)` scans `~/.onelens/bundles/onelens-snapshot-<g>-<t>.tgz`.
  - `install(bundle, indicator)` shells `onelens_snapshots_pull --repo local`
    for the published → installed flow (same code path as remote pull).
- `plugin/.../ui/OneLensSnapshotsToolWindow.kt`:
  - Two-section list: `⇡ Published (N)` + `⌂ Installed (N)`.
  - Published row shows `✓ installed` badge when its tag is also in the
    extracted graphs dir; download icon otherwise.
  - Double-click Published → install + auto-refresh list.
  - Right-click Published → `Install / Re-install`, `Open bundles
    folder`, `Delete tgz…` (cascades to `.sha256` sidecar; preserves
    installed copy).
  - Right-click Installed unchanged (`Copy --graph`, `Open folder`,
    `Delete…`).
- `plugin/.../ui/OneLensToolWindow.kt` (Status tab UX):
  - Header shows `Branch: <cur> · HEAD: <sha7>` below the backend line
    (git info computed off-EDT during `refreshAsync`).
  - Swing Timer ticks the "Last sync: X ago" label every 30 s using the
    cached timestamp — no status poll, no git shell-out.
  - Resources line (`Venv: X GB · Exports on disk: Y MB`) demoted to
    smaller, dimmer font so it reads as secondary detail.

### Added — Phase R Stage 1b · Plugin UI for snapshots (2026-04-20)

Plugin-side UI for publish + list + delete of **local** release
snapshots, merged into the existing OneLens tool window. No new panels
clutter the sidebar — Snapshots is a second tab next to Status. GitHub
Releases publish + remote list/pull are **not** surfaced in the plugin
UI (scoped out per explicit preference — Python MCP tools remain for
CLI use).

- `plugin/.../snapshots/SnapshotManager.kt` — project service wrapping the
  Python CLI (`onelens call-tool onelens_snapshot_*`). Uses `HttpRequests`
  for the `snapshots.json` fetch with 404 → empty-index fallback, and
  `GeneralCommandLine` + `CapturingProcessHandler` for publish/pull with
  30-min timeout under a `Task.Backgroundable` indicator.
- `plugin/.../snapshots/PublishSnapshotDialog.kt` — tag, repo,
  include-embeddings toggle, local-vs-GitHub backend radios. Pre-fills
  tag from `GitInfo.latestTag()` (semver-sorted). Shows
  `Branch: <cur> · HEAD: <sha7>` info line, computed off-EDT.
- `plugin/.../snapshots/GitInfo.kt` — thin wrapper over `git4idea.repo`
  gated by `safe {}` (catches `NoClassDefFoundError` when Git4Idea
  isn't loaded). Returns `null` gracefully on missing Git plugin or no
  repo, so the dialog still opens with defaults.
- `plugin/.../snapshots/SnapshotModels.kt` — `SnapshotIndex`,
  `SnapshotEntry`, `LocalSnapshot` (kotlinx.serialization).
- `plugin/.../actions/PublishSnapshotAction.kt` — reads tag/branch/sha in
  `Task.Backgroundable`, opens dialog on EDT via `invokeLater`, then runs
  the CLI in another `Task.Backgroundable`. Fixes an EDT violation that
  tripped IntelliJ's `checkEdtAndReadAction` guard on `git tag -l`.
- `plugin/.../actions/PullSnapshotAction.kt` — programmatic entrypoint
  for the Snapshots tab row-activate.
- `plugin/.../ui/OneLensSnapshotsToolWindow.kt` — `OneLensSnapshotsPanel`
  with JBList of remote/local snapshot rows, bold section headers,
  install-state badges. Hyperlink in the header opens
  `onelens.workspace.yaml` when repo not configured. Right-click on a
  local row → `Copy --graph`, `Open folder`, `Delete…` (confirm dialog;
  cascade-deletes both the graph dir and the matching
  `~/.onelens/context/<graph>@<tag>/` drawer dir).
- `plugin/.../ui/OneLensToolWindow.kt` — factory now registers two
  `Content`s: Status + Snapshots. Publish action mirrored on the Status
  toolbar via `ActionManager` lookup (`onelens.PublishSnapshot`) so users
  don't need to switch tabs for the common case.
- `plugin/.../framework/workspace/Workspace.kt` — optional
  `snapshots: { repo: <org/repo> }` block. Loader parses + exposes
  `SnapshotsConfig`.
- `plugin/src/main/resources/META-INF/plugin.xml` — removes the second
  `OneLens Snapshots` tool window declaration (merged). Adds
  `onelens.PublishSnapshot` action registration + optional
  `<depends optional="true" config-file="git-features.xml">Git4Idea</depends>`
  so `git4idea.*` resolves in our classloader when the bundled Git
  plugin is present.
- `plugin/src/main/resources/META-INF/git-features.xml` — empty config
  stub required by the optional-dep contract.
- `plugin/gradle.properties` — `Git4Idea` added to
  `platformBundledPlugins` so the devkit resolves `git4idea` classpath
  at compile time.

### Added — Phase R Stage 1a · Release snapshots (CLI + skill) (2026-04-20)

Developer-triggered release snapshots — immutable per-release graph
bundles, shareable via GitHub Releases, queryable side-by-side with the
live dev graph for API-diff / regression-hunt workflows.

- `python/src/onelens/snapshots/publisher.py` — Lite-first producer.
  Reads `~/.onelens/graphs/<graph>/<graph>.rdb` + optional context dir,
  writes `manifest.json` v3 (schemaVersion, commitSha, embedder,
  falkordbLite, includesEmbeddings), packages as
  `onelens-snapshot-<graph>-<tag>.tgz`, computes SHA256, and optionally
  (a) signs via `cosign sign-blob` keyless when the binary is on PATH,
  (b) uploads to GitHub Release `<tag>` on `<repo>` via `gh release
  upload`, and (c) maintains a pinned `onelens-index` tag hosting a
  stable-URL `snapshots.json` catalog.
- `python/src/onelens/snapshots/consumer.py` — list + pull + verify +
  unpack. Fetches `snapshots.json` (one HTTPS GET), downloads bundle,
  verifies SHA256 against the index (authoritative) with sidecar
  fallback, cosign-verifies when the `.sig` asset is present, and
  unpacks to `~/.onelens/graphs/<graph>@<tag>/`. Critically: runs
  `GRAPH.COPY` + `GRAPH.DELETE` inside the restored rdb so the internal
  graph key matches the `<graph>@<tag>` name (FalkorDB Lite binds the
  graph key into the rdb — file rename alone doesn't rename the graph).
  Guards against tarball path traversal via `extractall(filter='data')`.
- `python/src/onelens/mcp_server.py` — 3 new `@mcp.tool` entries:
  `onelens_snapshot_publish`, `onelens_snapshots_list`,
  `onelens_snapshots_pull`. Tool count: 15 → 18.
- `python/scripts/regen_cli.sh` hardened — resolves `fastmcp` via
  `$HOME/.onelens/venv/bin/fastmcp`, exports the venv bin on PATH for
  `generate-cli`'s internal subprocess spawn, adds `-f` (overwrite),
  appends `main = app` alias so pyproject's `onelens` entry point
  resolves. Previously the script failed silently on a fresh regen.
- `skills/onelens/SKILL.md` — decision-tree rows for "compare two
  releases / API diff" and "pull a release snapshot".
- `skills/onelens/references/recipes.md` — recipe #16 cross-release diff
  (endpoint surface, method signature drift, dead-code delta, SQL
  migration inventory) with FalkorDB-safe two-query set-diff pattern.
- `docs/design/phase-r-release-snapshots.md` — full spec covering OSS
  vs Cloud split, signing (Sigstore keyless + SLSA L3), distribution
  (GitHub Releases primary, S3/MinIO self-host planned), schema-version
  forward-compat, risks, and a staged OSS-first ship order.

Smoke-tested end-to-end on myapp:
`onelens_snapshot_publish --backend local` → 31.3 MB tarball →
GRAPH.COPY rename on unpack → `onelens_status --graph
myapp@v0.1.0` returns the same 199,794 nodes / 1,044,467 edges /
2,312 endpoints as the live graph.

Plugin UX (Stage 1b — snapshot tool window + Publish / Pull actions)
tracked separately.

### Fixed — CLI no longer needs `fastmcp` on PATH (2026-04-20)

`cli_generated.py` previously spawned `fastmcp run mcp_server.py` as a
subprocess, which failed with `[Errno 2] No such file or directory:
'fastmcp'` whenever the venv's `bin/` wasn't on `PATH` (common when users
invoke `~/.onelens/venv/bin/onelens` directly). Rewired `CLIENT_SPEC` to
the in-process `FastMCPTransport` — `Client(mcp_server)` talks to the
server object in memory, no subprocess, no PATH dependency. Also faster
startup (no Python re-import).

Since `fastmcp generate-cli` has no flag for transport selection (confirmed
against fastmcp docs + repo — manual `CLIENT_SPEC` edit is the documented
pattern), added `python/scripts/regen_cli.sh` which wraps the generator and
re-applies the patch. CLAUDE.md now points at the script instead of the raw
generator to keep the fix alive across regenerations.

### Changed — Dual-label consolidation (2026-04-20)

Four conceptually-duplicate node pairs collapsed to single dual-labeled
nodes. Same queries still work — both labels resolve to the same node.

- `Field` ∪ `JpaColumn` → one node carrying both labels. Was emitting a
  `JpaColumn` node per entity field AND the `Field` node MemberCollector
  already wrote (~5.8k duplicates on motadata).
- `Field` ∪ `EnumConstant` → one node. PSI returns enum constants as
  fields; MemberCollector already emitted them. Was ~10k duplicates.
- `Class` ∪ `JpaEntity` → one node (~748 duplicates).
- `Class` ∪ `JpaRepository` → one node (~504 duplicates).

Implementation: new `_batch_add_label` loader helper MERGEs the base
node (`Field` / `Class`) and `SET n:ExtraLabel` tags the richer label
while writing its domain props. Edges rewired to match on the base
node's primary key (`fqn`), not the extra label's legacy key
(`fieldFqn` / `classFqn`) — so `HAS_COLUMN`, `RELATES_TO`,
`REPOSITORY_FOR`, `QUERIES` now query `fqn` on both sides.

Bridge, not collapse: `Class -[:REGISTERED_AS]-> SpringBean` — @Bean
factories don't have 1:1 class identity (bean class = return type, not
the declaring class), so SpringBean stays separate. The edge still
gives one-hop "is this class exposed as a bean?" queries.

Breaking for cached Cypher: queries that did
`MATCH (e:JpaEntity {classFqn: 'x'})` must now use `{fqn: 'x'}`.
Same for `:JpaRepository`, `:JpaColumn` (use `fqn` not `fieldFqn`).
Skill references + mental model updated in same push.

### Fixed — No-duplicate pass on C2 / C3 collectors (2026-04-20)

- `JpaCollector` now iterates `psiClass.fields` (own only) — inherited
  fields from `@MappedSuperclass` are no longer re-emitted per subclass,
  which was inflating `JpaColumn` counts and creating duplicate
  `HAS_COLUMN` edges.
- `AutoConfigCollector` dedupes by `classFqn` with autoconfig.imports
  winning over spring.factories during Boot 2.7 migrations.
- `SpringModelCollector` replaces the `bean.javaClass.getMethod` reflection
  hack with direct PSI annotation reads for `@Scope` / `@Primary`
  (handles annotation, `@Bean`, JAM, XML variants uniformly). Factory
  method resolution now uses `CommonSpringBean.identifyingPsiElement`.
- Loader side: `JpaColumn`, `HAS_COLUMN`, and Vue3 `Package→…` edges all
  carry a collector-level `seen` set so re-entry is harmless. Vue3
  `Package` now has `CONTAINS` edges to `Component` / `Composable` /
  `Store` / `JsModule` via segment match on their `filePath`.

### Changed — Phase 0.2 · Skill rewrite (wake-up protocol + reference split) (2026-04-20)

Skill reorganised around the mempalace-style wake-up pattern that the new
`onelens_status` enables.

- **`SKILL.md`** rewritten — opens with the mandatory first-call protocol
  (`onelens_status`), a decision tree keyed on `capabilities.*`, and a
  Reads/Writes-split tool catalog. No project-specific graph names in
  examples — generic placeholders for OSS portability.
- **`references/capabilities.md`** (new) — what each status flag unlocks
  and how the agent should branch.
- **`references/graph-schema.md`** (new) — full node + edge vocabulary
  (Class, Method, SpringBean, Endpoint, JpaEntity, JpaColumn, Migration,
  SqlQuery, SqlStatement, TestCase, Drawer, …) with primary keys and key
  properties.
- **`references/queries-code.md`** (new) — Cypher patterns that replace
  the dropped `impact` / `trace` / `entry_points` tools: polymorphic impact
  via `OVERRIDES*0..` + `CALLS*1..5`, BFS trace, entry-point union,
  bean injection, cross-stack trace.
- **`references/queries-sql.md`** (new) — C6/C6.1 patterns: migration
  timeline per entity, column-rename impact, exact-SELECT lookup,
  coupling analysis.
- **`references/queries-tests.md`** (new) — Q.code patterns: testKind
  breakdown, coverage gaps, `MOCKS`/`SPIES` queries, tag taxonomy.
- **`references/retrieval.md`** (new) — when to call `onelens_retrieve`
  vs fallback to `onelens_search`; parameter guide.
- `references/memory.md` / `PALACE.md` both deleted — memory/palace is
  still an internal capability (not yet an OSS-user-facing feature), so
  the deep guide is held back. Individual tools (`onelens_kg_*`,
  `onelens_add_drawer`, `onelens_diary_*`, `onelens_find_tunnels`) stay
  registered in the MCP server and listed in `SKILL.md`'s tool catalog
  for agents that need them.
- **`references/jvm.md`** / **`references/vue3.md`** — kept; prepended
  migration banners mapping legacy tool commands to new call-tool forms.
  Full body rewrite deferred (tracked follow-up).
- Deleted `skills/onelens/PALACE.md` — content absorbed into `memory.md`.

### Changed — Phase 0.1 · Unified MCP server, `onelens_*` namespace, tool consolidation (2026-04-20)

One MCP server, one CLI, one namespace. The separate `onelens-palace` server
and its `palace_*` tools are gone; all 15 surviving tools live under
`onelens_*` in a single `mcp_server.py`.

**Tool naming (all renamed to `onelens_*`)**:
```
Wake-up                 :: onelens_status
Universal query         :: onelens_query
Search                  :: onelens_search
Hybrid retrieval        :: onelens_retrieve
Imports (writes)        :: onelens_import, onelens_delta_import
Memory (palace merged)  :: onelens_add_drawer, onelens_delete_drawer,
                           onelens_check_duplicate,
                           onelens_kg_add, onelens_kg_invalidate, onelens_kg_timeline,
                           onelens_find_tunnels,
                           onelens_diary_read, onelens_diary_write
```

**Tools dropped — promoted to skill patterns** (parameterised Cypher, no
real app-side logic, keeping them was tool-surface bloat):
- `trace`, `impact`, `entry_points` — replaced by documented Cypher in
  `skills/onelens/references/queries-code.md` (skill rewrite in Phase 0.3).
- `stats`, `context_stats`, `context_wakeup`, `context_recall`,
  `context_import`, `context_search` — folded into `onelens_status` (the
  capabilities probe tells the agent which paths are live) and
  `onelens_import --context`.
- `palace_status`, `palace_kg_query`, `palace_list_wings`,
  `palace_list_rooms`, `palace_get_taxonomy`, `palace_search`,
  `palace_kg_stats`, `palace_graph_stats`, `palace_traverse`,
  `palace_get_aaak_spec` — folded into `onelens_status` / `onelens_query`.

**`onelens_status` capabilities probe** — returned on every wake-up call so
the skill's decision tree branches without guessing:
```json
"capabilities": {
  "has_structural": true, "has_semantic": false,
  "has_spring": true,     "has_jpa": true,
  "has_sql": true,        "has_tests": false,
  "has_vue3": false,      "has_memory": false,
  "has_apps": true
}
```

**Files**:
- Deleted: `python/src/onelens/palace/server.py`,
  `python/src/onelens/palace/cli_palace_generated.py`
- Kept: palace business modules (`kg.py`, `drawers.py`, `diary.py`,
  `tunnels.py`, `store.py`, `taxonomy.py`, `navigation.py`, `wal.py`,
  `schemas.py`, `aaak.py`, `paths.py`, `protocol.py`) — the new unified
  server imports them directly.
- Regenerated: `python/src/onelens/cli_generated.py` via
  `fastmcp generate-cli src/onelens/mcp_server.py`.
- Dropped: `onelens-palace` entry point from `pyproject.toml`.

**Breaking change for MCP clients**: any caller using the old
`palace_*` or `impact` / `trace` / `entry_points` / `context_*` / `stats`
tool names must migrate. Skill reference in Phase 0.3 documents the
replacements.

### Changed — Phase L · FalkorDB Lite is now the default backend (2026-04-20)

Zero-Docker OSS UX. `pip install onelens` bundles Redis + FalkorDB as shared
objects via `falkordblite`; the Python CLI spawns a local Redis subprocess
with FalkorDB loaded, talking over a Unix socket. No TCP port, no
`docker run`.

- `ExportConfig.graphBackend` default flipped from `"falkordb"` → `"falkordblite"`.
  Existing users who want the Docker path (for the :3001 browser UI or multi-
  process access) can pin `graphBackend: falkordb` in settings; ExportService
  preflight unchanged.
- `pyproject.toml`: `falkordblite>=0.9.0` moved from `[lite]` extra into base
  dependencies. The `[lite]` extra remains as a no-op for backward compat.
- `falkordb_lite.py` rewritten — the previous version had a broken import
  (`from falkordblite import FalkorDB`; real module is `redislite.falkordb_client`).
  Never worked before this fix because Docker was the plugin default. Now
  properly persists via per-graph `<db_path>/<graph_name>.rdb` files and
  rebinds the graph handle after `clear()`.
- **Benchmark** (motadata, 548 MB export, 10k classes, 80k methods, 630k call
  edges): Docker 219.8 s vs Lite 279.7 s. ~27 % slower — acceptable for the
  zero-setup win. Slowest delta is small-batch edge writes (higher Unix-socket
  per-roundtrip latency).
- **Feature parity verified**: Cypher, FTS (`db.idx.fulltext.createNodeIndex`),
  vector indexes (`CREATE VECTOR INDEX ... cosine`), UNWIND batching — all
  work identically to the Docker backend.
- **Platform**: Linux + macOS only for v0.2 (bundled `.so` / `.dylib`). Windows
  users must use the Docker backend until FalkorDB ships Windows binaries.
- **No browser UI** — FalkorDB Docker ships :3001; Lite has none. Not a blocker
  for CLI / skill / MCP-driven workflows; power users who want the visual
  graph explorer keep using Docker.

### Added — Phase Q.code · Test cases as first-class graph nodes (2026-04-20)

Tests become a dual-labelled `:Method:TestCase` in the graph with structured
classification. Detection is PSI-native via IntelliJ's `AnnotationUtil.CHECK_HIERARCHY`
flag — same annotation-resolution Spring itself uses, so:

- Direct `@SpringBootTest` on a test class ✅
- `@SpringBootTest` on a superclass up the chain (motadata's
  `CommonTest → MockHelper → BaseTest → …` pattern) ✅
- `@SpringBootTest` on a meta-annotation (`@MyIntegrationTest`) ✅
- Slices (`@DataJpaTest`, `@WebMvcTest`, `@JsonTest`, `@RestClientTest`, other `@AutoConfigureXxx`) ✅
- Mockito-driven unit tests (`@ExtendWith(MockitoExtension.class)`) ✅
- Cucumber step defs (`@Given` / `@When` / `@Then` / `@And`) ✅
- JUnit 4 `@Test`, JUnit 5 `@Test` / `@ParameterizedTest` / `@RepeatedTest` /
  `@TestFactory` / `@TestTemplate`, TestNG `@Test` ✅

**`testKind` vocabulary** (10 fixed values for cross-project Cypher portability):
`unit` · `unit-mocked` · `integration` · `slice-jpa` · `slice-web` ·
`slice-json` · `slice-rest-client` · `slice-other` · `bdd` · `unknown`.

**Captured properties**: `testClass`, `testFramework`, `tags` (@Tag values),
`disabled`, `activeProfiles`, `springBootApp`, `usesMockito`, `usesTestcontainers`,
`displayName`.

**Edges added**:
- `(:TestCase)-[:TESTS]->(:Method)` — derived from direct CALLS where the
  target isn't itself a test. One-Cypher-pass post-dual-label.
- `(:Class)-[:MOCKS]->(:SpringBean)` — from `@MockBean` fields.
- `(:Class)-[:SPIES]->(:SpringBean)` — from `@SpyBean` fields.

**Files**: `plugin/.../export/collectors/TestCollector.kt`,
`ExportModels.TestCaseData/TestBeanBinding`, `loader._load_tests`.

**OSS-ready**: zero yaml config for standard Spring/JUnit layouts — pet
clinic, plain JUnit, and deep-hierarchy projects all classify correctly
out of the box via CHECK_HIERARCHY.

### Performance — orjson JSON parse (2026-04-20)

- `loader.py`, `delta_loader.py`, `code_miner.py` swap stdlib `json.load` →
  `orjson.loads` (falls back cleanly when orjson missing). Benchmarked 25%
  faster on 120 MB synthetic exports; ~2-3 s saved per sync on motadata's
  500 MB exports. Zero API change — same dicts out.
- `pyproject.toml` adds `orjson>=3.9`.
- `loader.load_full()` now logs JSON parse time so future perf regressions
  surface in the log.

### Added — Phase C6.1 · Column-level SQL → JPA mapping (2026-04-20)

Beyond table-level edges, each `:SqlStatement` now links to the specific
`:JpaColumn` nodes it references.

- `sql_miner.StatementOut.columnRefs` — `[(tableName, columnName)]` extracted
  via sqlglot's `scope.build_scope` for alias resolution. Qualified refs
  (`r.priorityId`) bind via alias → table; unqualified refs bind only when
  the scope has exactly one FROM source (otherwise dropped — ambiguous).
  Nested subqueries/CTEs handled via recursive scope walk.
- Loader: `(SqlStatement)-[:REFERENCES_COLUMN]->(JpaColumn)` edge. Lookup
  map built via `:EXTENDS*0..6` walk so inherited columns
  (e.g. `Request` table inherits `priorityId` from `TicketBase`,
  `createdTime` from `FlotoBase`) resolve correctly.
- Enables precise impact queries: "rename `Request.priorityId` — what
  reports break?", "every query that reads FlotoBase.createdTime", column
  popularity rankings.
- 77.9% alias-resolution rate on motadata's 201 customer queries (9807
  column refs, 7640 resolved). Remaining unresolved = unqualified columns
  in multi-FROM statements (kept honest rather than guessing).

### Added — Phase C6 · SQL surface (Flyway migrations + custom queries) (2026-04-20)

First-class SQL in the graph alongside Java/JPA. Two opt-in kinds: `migration`
(Flyway V-files) and `query` (custom customer SQL). Both split per-statement,
so Cypher can pinpoint the exact `SELECT`/`ALTER` that touches an entity.

- `miners/flyway_detector.py` — auto-scans `application*.{properties,yml}` for
  `spring.flyway.locations`, resolves `classpath:X` → `src/main/resources/X/`
  across every workspace root and every nested Maven module. Falls back to the
  Flyway default (`classpath:db/migration`) when the dep is present but no
  explicit location. `extraLocations` knob for non-standard setups (e.g.
  motadata's `classpath:db/migration/tenants` which uses a custom loader).
- `miners/sql_miner.py` — sqlglot-based parser, Postgres dialect,
  `error_level=IGNORE`. Per-statement split (one `:SqlStatement` node per
  `;`-separated statement), `opKind` vocabulary (`SELECT` / `CREATE_TABLE` /
  `ALTER_TABLE` / `DROP_TABLE` / `UPDATE` / etc.), case-insensitive table
  extraction. Body-size cap 200 KB per file + per statement.
- Loader: new `_load_sql()` phase emits
  `:Migration {version, description, dbKind, body}` /
  `:SqlQuery {filename, body}` / `:SqlStatement {sql, opKind}` nodes,
  wired via `:HAS_STATEMENT` (file → statement), `:QUERIES_TABLE`
  (statement → JpaEntity), and DDL-specific `:CREATES_TABLE` /
  `:ALTERS_TABLE` / `:DROPS_TABLE` edges.
- Workspace yaml schema:
  ```yaml
  sql:
    flyway:
      autoDetect: true              # default
      extraLocations: [classpath:…] # optional
    queries:
      - "<glob relative to any root>"
  ```
- `pyproject.toml` — adds `sqlglot>=25.0`.
- Fixed-kind decision documented (see ADR-024 when landed).

### Added — Phase C2 · App + Package primitives (2026-04-20)

- `ExportDocument.apps: List<AppData>` / `ExportDocument.packages: List<PackageData>`
  top-level keys. Spring: one `App` per `@SpringBootApplication` with
  `scanBasePackages` / `scanBasePackageClasses` / `@ComponentScan` aliases
  resolved. Vue3: one `App` per workspace root with `package.json` + `src/`
  child folders as packages.
- New collectors: `AppCollector.kt`, `PackageCollector.kt`. PSI-native
  (Spring side) and filesystem-only (Vue3 side). No new plugin deps.
- Loader emits `App` + `Package` nodes and three edge kinds: `PARENT_OF`
  (Package→Package hierarchy), `CONTAINS` (App→Package, Package→Class).
  `Class.packageName` is already stamped, so traversals like
  `MATCH (a:App {type:'spring-boot'})-[:CONTAINS]->(:Package)-[:CONTAINS]->(c:Class) RETURN c.fqn`
  work out of the box.
- Package→App assignment uses longest-prefix match against each app's
  scan packages; a class in `com.acme.order.service` correctly binds to
  the order-service app even when the auth-service shares `com.acme`.
- Per-app PageRank deferred to C2.1 — today's PageRank prebake runs
  globally and remains correct; per-app scoping is a re-run of the same
  algorithm over a sub-selection of (Method, CALLS) and lands next.

### Added — Phase C3b · @Qualifier + spring.factories / AutoConfiguration.imports (2026-04-20)

- `SpringInjection.qualifier: String?` — `SpringCollector` now reads
  `@Qualifier("…")` on fields and constructor params; propagated to
  `INJECTS` edges as an edge property so Cypher can filter wiring by
  qualifier name.
- `SpringAutoConfig` nodes — `AutoConfigCollector` scans the project's
  filename index for `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`
  (Boot 2.7+) and `META-INF/spring.factories` (legacy, keys ending in
  `EnableAutoConfiguration` only). Each discovered class lands as a
  `SpringAutoConfig` node with `source` (`autoconfig.imports` | `spring.factories`)
  and originating file path.

### Added — Phase C3c · JPA / Spring Data entity + repository graph (2026-04-20)

- `JpaData` payload — new collector `JpaCollector` emits `JpaEntity` /
  `JpaColumn` / `JpaRepository` nodes via PSI annotation scanning
  (jakarta.persistence + javax.persistence). Captures `@Table` name and
  schema, `@Id` / `@Column` / `@JoinColumn` metadata, and OneToOne /
  OneToMany / ManyToOne / ManyToMany relations with inferred target
  entity FQN.
- Repository detection via `ClassInheritorsSearch` on Spring Data's
  `Repository` / `CrudRepository` / `PagingAndSortingRepository` /
  `JpaRepository` / `ReactiveCrudRepository` / `MongoRepository`. Type
  parameter resolves the entity. Derived-query methods (`findBy…`,
  `countBy…`, `existsBy…`, `deleteBy…`, etc.) emit `QUERIES` edges from
  repo → method.
- Loader wiring: `HAS_COLUMN` (`JpaEntity → JpaColumn`), `RELATES_TO`
  (`JpaEntity → JpaEntity`, relation + owning field on the edge),
  `REPOSITORY_FOR` (`JpaRepository → JpaEntity`), `QUERIES`
  (`JpaRepository → Method`).
- PSI-native — does NOT require `com.intellij.jpa` / `com.intellij.spring.data`
  plugins. Works on IC, IU, WebStorm, PyCharm alike.

### Added — Phase C3a · Spring-plugin model collector (2026-04-20)

- `plugin/.../framework/springboot/SpringModelCollector.kt` — enumerates
  beans via `SpringManager.getCombinedModel(module).getAllCommonBeans()`
  per module. Picks up @Bean factory methods, XML beans, JAM beans,
  aliases, @Primary, and scope resolved by the Spring plugin. Filtered
  to `workspace.contains(file.path)` so library beans (starters, JDK)
  don't pollute the graph.
- `SpringBootCollector` merges annotation-scraped beans (existing
  `SpringCollector`) with Spring-model beans. Dedupe key is
  `classFqn|name|factoryMethodFqn` so an XML or @Bean definition for
  the same class doesn't collapse into the stereotype bean. Runtime
  guard `PluginManagerCore.getPlugin("com.intellij.spring")?.isEnabled`
  prevents the JVM from resolving `SpringManager` on IDEs without the
  Spring plugin (JAR still loads on IC / WebStorm).
- `SpringBean` schema gets four additive fields: `primary: Boolean`,
  `source: String` (`annotation | java-config | xml | jam`),
  `factoryMethodFqn: String?`, `activeProfiles: List<String>`. All
  default to stable values so legacy annotation-only output is
  byte-compatible.
- `gradle.properties` — `com.intellij.spring` and `com.intellij.spring.boot`
  added to `platformBundledPlugins` so the Spring API jars are on the
  compile classpath (IU ships them bundled).

### Changed — Phase C1 · Workspace is now mandatory (non-null) (2026-04-19)

- `CollectContext.workspace`, all JVM + Vue3 collector parameters, and
  `Vue3Context.workspace` are non-nullable. Dual-path code
  (`workspace?.scope(project) ?: projectScope(project)` and the
  equivalent path-relativisation fork) is gone — one resolution at each
  entry boundary (`ExportService.exportFull`,
  `DeltaExportService.exportDelta*`, `ExportFullAction.actionPerformed`,
  `AutoSyncFileListener`), propagated down.
- `WorkspaceLoader.load(project)` returns non-null; implicit single-root
  fallback handles the zero-config case inside the loader. Throws on
  `project.basePath == null`; callers handle once, not every collector.
- `ModuleCollector.detectBuildSystem` now probes every workspace root
  (not just the primary) — a sibling Gradle root no longer resolves to
  UNKNOWN because the primary root is Maven.
- `ExportFullAction.countJavaFiles` sums every workspace root for the
  >30% change heuristic.
- Unused `GlobalSearchScope` imports stripped from JVM + Vue3 files.

### Added — Phase C1 · Workspace abstraction landed (2026-04-19)

- `plugin/.../framework/workspace/Workspace.kt` — adapter-agnostic
  data class carrying N roots, a stable `graphId`, and policy knobs
  (`duplicateFqn`, `deltaTracker`, `pagerankPerApp`). Exposes
  `scope(project)` (GlobalSearchScope union across roots) and
  `relativePath(file)` (first root match wins) so collectors no
  longer depend on `project.basePath` / `projectScope(project)`.
- `plugin/.../framework/workspace/WorkspaceLoader.kt` — parses
  `onelens.workspace.yaml` (SnakeYAML) with relative `../sibling`
  roots resolving against the config's directory, so the motadata
  pattern (`- path: ../motadata_plugins`) just works. Absent config
  falls back to an implicit single-root workspace → zero-config
  compatibility with every existing single-repo user.
- `CollectContext.workspace` — new field plumbed through
  `FrameworkAdapter` SPI. SpringBoot + Vue3 adapters forward it.
- All 7 JVM collectors (`ClassCollector`, `MemberCollector`,
  `CallGraphCollector`, `InheritanceCollector`, `AnnotationCollector`,
  `SpringCollector`, `ModuleCollector`) accept `workspace: Workspace?`
  and swap `projectScope(project)` → `workspace.scope(project)` when
  provided; null = legacy behaviour.
- All 5 Vue3 collectors + `ModuleNameBinder` + `CallThroughResolver`
  read `ctx.workspace?.scope(project)` with the same fallback.
- `DeltaExportService` resolves the workspace per invocation and
  resolves relative file paths against every root (first hit wins) —
  lets a delta on a sibling-repo root work without the caller
  knowing which root the file lives in.
- `AutoSyncFileListener` filters events via `workspace.contains(path)`
  and derives relative paths via `workspace.relativePath(file)`, so
  auto-sync on a file in a secondary root no longer emits an
  absolute path that the importer can't reconcile.
- `ExportModels.ExportDocument` gains `workspace: WorkspaceInfo?` —
  Python loader reads `graphId` for the `wing` stamp and logs when
  `duplicateFqnPolicy` is non-default (only `merge` is enforced
  today; other policies land in a follow-up).
- `ExportService` / `ExportFullAction` / `AutoSyncService` now use
  `workspace.graphId` (falling back to `project.name`) for the
  graph name passed to `onelens import_graph`, plus the output JSON
  filename — so a user-chosen `graph: myapp` in the YAML
  lands consistently across full sync, delta, and auto-sync.

Known limitations tracked in Phase C PROGRESS:

- `DeltaTracker` still runs `git diff` against the primary root
  only; secondary-root commits fall through to VFS timestamp /
  ChangeListManager. Multi-git tracker per root is C1.1 follow-up.
- `duplicateFqn` policy values other than `merge` log a warning and
  fall back to `merge`; `warn` / `error` / `suffix-by-module`
  enforcement is C1.2 follow-up.
- App / Package adapter-agnostic primitives (ADR-022) not yet
  emitted — targeted for C2.

### Fixed — Full loader tolerates duplicate FQNs (2026-04-18)

- `python/src/onelens/importer/loader.py::_batch_nodes` now uses
  `MERGE` instead of `CREATE` in the bulk UNWIND query (and in the
  per-item fallback path). Duplicate primary keys within a single
  export — or across re-imports — now upsert with last-write-wins
  semantics instead of aborting the batch. Unblocks multi-module
  and plugin-fork JVM workspaces where the same class FQN
  legitimately appears in multiple compile units (e.g. one-off
  `com.acme.Constants` forks per client plugin).
- Behaviour on non-duplicate graphs is unchanged; `MERGE` on the PK
  when no existing node matches is equivalent to `CREATE` plus
  property assignment.

### Added — Workspace abstraction design spec (2026-04-18)

- `docs/workspaces.md` — design doc for a declarative
  `onelens.workspace.yaml` that names N roots, a stable graph id,
  and policies for duplicate FQNs / multi-git delta / per-app
  PageRank. Backward-compatible: absent config = current single-
  root implicit workspace.
- `docs/DECISIONS.md` ADR-021 — "Workspace abstraction for
  multi-repo / multi-module indexing" records the motivation (three
  independent hardcoded assumptions around `project.basePath`,
  `projectScope`, and `CREATE` that all fall out of the same
  missing concept) and the migration contract.
- `docs/DECISIONS.md` ADR-022 — "App and Package as adapter-
  agnostic graph primitives" — promotes `App` (per
  `@SpringBootApplication`, per Vue root, per future entrypoint)
  and `Package` to core node types owned by the schema, emitted by
  whichever `FrameworkAdapter` detects them. Enables
  cross-adapter queries like "which Vue apps hit endpoints defined
  by which Spring apps" without per-adapter vocabulary
  negotiation.
- `docs/DECISIONS.md` ADR-023 — "Dual engine — PSI in-IDE,
  metadata in CI" — long-term architecture for an
  IntelliJ-optional import path that parses Spring Boot's
  standardised metadata files
  (`spring-configuration-metadata.json`,
  `AutoConfiguration.imports`, `spring.factories`,
  `spring.binders`) plus ASM bytecode. Same export schema, same
  loader, either engine.

### Added — Palace MCP (2026-04-18)

- New parallel MCP server `onelens-palace` (console entry `onelens-palace`),
  mirroring MemPalace's 19-tool surface over OneLens's FalkorDB + ChromaDB.
  Existing `onelens.mcp_server` untouched. HTTP transport on port **8766**
  (distinct from existing onelens MCP at 8765) when
  `ONELENS_PALACE_HTTP=1`; otherwise stdio.
- `onelens-palace` CLI auto-generated via `fastmcp generate-cli` →
  `python/src/onelens/palace/cli_palace_generated.py`. Regen script
  `scripts/regenerate-palace-cli.sh` post-processes fastmcp 3.x output
  (flattens `call-tool` subcommand to top-level, pins fastmcp binary to
  the venv, renames app). Console script points at the generated `app`.
- `python/src/onelens/palace/`: 13 modules — `server` (FastMCP app),
  `store`, `taxonomy`, `drawers`, `kg`, `tunnels`, `navigation`, `diary`,
  `wal`, `paths`, `schemas`, `aaak`, `protocol`.
- Tools: status / list_wings / list_rooms / get_taxonomy / search /
  check_duplicate / get_aaak_spec / add_drawer / delete_drawer /
  kg_add / kg_query / kg_invalidate / kg_timeline / kg_stats /
  traverse / find_tunnels / graph_stats / diary_write / diary_read.
  Positional args mirror MemPalace exactly; OneLens extensions are
  keyword-only for drop-in compatibility.
- Temporal KG lives in dedicated FalkorDB graph `onelens_palace_kg`
  (Entity + ASSERTS edges). `kg_query` auto-projects structural edges
  (CALLS/EXTENDS/...) from code wings when `entity` matches an FQN —
  hand-authored facts and code structure unify in a single call.
- WAL at `~/.onelens/palace/wal/write_log.jsonl` records every write.
- Content-axis halls (`hall_signature`, `hall_event`, `hall_fact`,
  `hall_doc`) added to `context/config.py` alongside existing
  source-axis halls.
- Skill cheat sheet `skills/onelens/PALACE.md` with tool-use guide.
- New activated skill at `~/.claude/skills/onelens-palace/SKILL.md` (global) — triggers on
  fact/memory/diary/cross-repo prompts (wings, rooms, tunnels,
  kg_add/query, diary_write/read) with per-playbook tool sequences.
- Design doc `docs/design/palace-mcp.md` (rev-1 plan).
- Approved implementation plan captured at
  `~/.claude/plans/parsed-launching-wolf.md`.

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
