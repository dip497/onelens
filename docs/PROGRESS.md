# OneLens — Feature Progress Tracker

Source of truth for what's landed, what's in flight, and what's deferred. Append-only per phase; mark status inline. Links point to the canonical artefact so this file stays skimmable.

Last updated: 2026-05-07.

## Embedder profiles · low-end CPU UX (2026-05-07 → 2026-05-08)

| # | Feature | Status | Where |
|---|---|---|---|
| EP-1 | `ONELENS_LOCAL_EMBED_PROFILE=balanced\|gemma\|tiny` shorthand | ✅ | `local_backend.py::PROFILE_MODELS`, `LocalEmbedder.__init__` |
| EP-2 | `ONELENS_LOCAL_EMBED_QUANT=q4\|q8\|fp32` ONNX variant picker | ✅ | `local_backend.py::_resolve_onnx_filename` |
| EP-3 | `model.onnx_data` external-weights sidecar in `allow_patterns` | ✅ | `local_backend.py::_download_model` |
| EP-4 | Quant-variant-missing fallback to fp32 model.onnx | ✅ | `local_backend.py::LocalEmbedder.__init__` |
| EP-5 | Re-run benchmark on `gemma` + `tiny` profiles, document recall delta | ⬜ | `python/benchmarks/` (gitignored) |
| EP-6 | **Drawer version stamp** — write `onelens_embedder_model` + `onelens_embedder_dim` into ChromaDB collection metadata; raise `EmbedderMismatchError` on retrieve when current process's embedder ≠ what wrote the drawers. Stops silent corruption on profile flip. | ✅ | `chroma.py::ChromaBackend.get_collection`, `EmbedderMismatchError` |
| EP-7 | **TRT engine cache slug includes quant variant** — `~/.onelens/trt-cache/<model-slug>-<quant>/` so flipping `q4 → q8` doesn't reuse a wrong-graph engine | ✅ | `local_backend.py::LocalEmbedder.__init__` (cache_slug arg to `_build_providers`) |
| EP-8 | **Plugin cold-load progress message** — `OneLensMcpService.start()` publishes a status-panel event explaining the ~30 s embedder warmup before spawning, instead of a 30 s silent hang | ✅ | `OneLensMcpService.kt::start` |
| EP-9 | **Delete legacy `embedder.py`** (Qwen3-0.6B Modal-internal path) — last user was a docstring; removes future risk of someone re-wiring it as default | ✅ | `python/src/onelens/context/embedder.py` deleted; chroma docstrings + Modal app comment + CLAUDE.md/architecture.md refreshed |
| EP-10 | **Profile + quant pickers in plugin Settings** — Preferences → Tools → OneLens Semantic gains `Embedder profile` + `ONNX quant` ComboBoxes; values flow to `ONELENS_LOCAL_EMBED_PROFILE` / `_QUANT` env via `OneLensMcpService.buildEnv` (only when ≠ default to keep env clean) | ✅ | `OneLensSettings.kt`, `SemanticSettingsConfigurable.kt`, `OneLensMcpService.kt::buildEnv` |
| EP-11 | TOML/JSON profile config so users can register custom profiles without editing `PROFILE_MODELS` | ⬜ | `local_backend.py` + `~/.onelens/profiles.toml` (deferred) |
| EP-12 | Air-gap HF cache check — try local cache before `snapshot_download` to honour the air-gapped install promise | ⬜ | `local_backend.py::_download_model` (deferred) |
| EP-13 | Periodic embedder health heartbeat (NaN check on dummy encode) | ⬜ | new `mcp_server.py` background task (deferred) |
| EP-14 | Multi-graph FalkorDB port (Phase C alignment) | ⬜ | `graph/db.py` factory + plugin settings (deferred) |
| EP-15 | MCP queue / per-client serialization for concurrent retrieve calls | ⬜ | `mcp_server.py` + ORT thread-safety check (deferred) |
| EP-16 | **Warm-aware CLI routing** — `cli_generated.py` probes `~/.onelens/mcp.port` per invocation, hits warm daemon over HTTP when reachable, falls back to in-process FastMCP otherwise. Plugin's CLI shell-out fallback path inherits the same warmth automatically. `ONELENS_FORCE_LOCAL_CLIENT=1` opt-out for benchmarks. Patch survives `fastmcp generate-cli` regeneration via updated `regen_cli.sh`. Validated against FastMCP `StreamableHttpTransport` URL-inference (v2.3.0+). | ✅ | `cli_generated.py::_resolve_client_spec`, `python/scripts/regen_cli.sh` |
| EP-17 | Idle-shutdown timer in MCP server (precondition for safe CLI auto-spawn). Track last-tool-call timestamp, exit cleanly after N min idle. Releases lock + port file. | ⬜ | `mcp_server.py` lifespan + signal handler |
| EP-18 | **Annotation attribute values as flat edge properties.** Plugin `AnnotationCollector` emits `attrValues` map of primitive resolved values; loader promotes each to `attr_<key>` on the `ANNOTATED_WITH` edge via Cypher `SET r += $map`. Queries can now match exact attribute values without JSON substring traps (`WHERE r.attr_value = '/users'`). Arrays + nested annotations stay JSON-only in `attributes`. Same shape on full + delta loader paths. | ✅ | `AnnotationCollector.kt`, `ExportModels.kt::AnnotationUsage`, `loader.py::_batch_annotation_edges`, `delta_loader.py` annotation block |

## Phase W — MCP-only runtime + EDT fix (2026-04-30)

Collapse OneLens runtime to a single long-lived MCP server per user.
Drop the per-IDE child-process model that caused 2× VRAM use and the
port/venv/data-dir races. Plugin role narrows to "ensure MCP up + speak
HTTP." Local embedder gets correctness fixes that were blocking Phase V
headless installs.

| # | Feature | Status | Where |
|---|---|---|---|
| W0 | Research + plan (FastMCP lifespan, claude mcp scopes, fcntl/msvcrt singleton, jina-v2 dim/maxlen) | ✅ | `docs/design/PLAN-mcp-only.md` |
| W1 | EDT off-thread telemetry — `updateSemanticLine` runs on pooled thread; only `JBLabel.text` on EDT | ✅ | `plugin/.../ui/OneLensToolWindow.kt::updateSemanticLine` |
| W1 | `nvidia-smi` 1 s `Process.waitFor(timeout)` + `destroyForcibly()` on overrun | ✅ | `plugin/.../ui/SystemMonitor.kt::gpuMemoryBytesForPid` |
| W1 | `detectLocalProvider()` cached for IDE session | ✅ | `OneLensToolWindow.kt::cachedProvider` |
| W2 | Singleton lock (`fcntl.lockf` POSIX / `msvcrt.locking` Windows) on `~/.onelens/mcp.lock` | ✅ | `python/src/onelens/mcp_server.py::_acquire_singleton_lock` |
| W2 | Atomic `mcp.port` write via `os.replace` | ✅ | `mcp_server.py::_write_port_atomic` |
| W2 | Second `onelens mcp serve --http` invocation reads existing port + exits 0 | ✅ | `mcp_server.py::__main__` |
| W3 | `local_backend.py` honors `ONELENS_LOCAL_EMBED_MODEL` (was documented but ignored) | ✅ | `local_backend.py::LocalEmbedder.__init__` |
| W3 | Embedding dim probed from `session.get_outputs()[0].shape` (was hard-coded 768) | ✅ | `local_backend.py::LocalEmbedder.__init__` |
| W3 | `ONELENS_LOCAL_EMBED_MAXLEN` default 256 → 512 (matches Jina v2 training length) | ✅ | `local_backend.py` |
| W3 | `embed_backends/__init__.py` defaults flipped to `local`; `RerankerBase` annotation fix | ✅ | `embed_backends/__init__.py` |
| W4 | Plugin: MCP-first sync — auto-start singleton when not reachable + semantic on; CLI fallback only as cold-path safety net for users without a working venv yet (full CLI rip blocked on Phase V installer guarantee) | 🟡 partial | `plugin/.../export/ExportService.kt::syncToGraph` |
| W5 | Plugin: read existing `mcp.port` before spawning; reuse if reachable (multi-IDE convergence on one MCP) | ✅ | `plugin/.../mcp/OneLensMcpService.kt::start` (`readExternalPort` + `probeReachable`) |
| W2.5 | Plugin: don't kill MCP child on `dispose()` — singleton is meant to outlive its spawner so Claude Code keeps working when IDE closes + next IDE reuses warm model | ✅ | `OneLensMcpService::dispose` |
| W6 | Per-node TRT placement verification (opt-in `ONELENS_LOCAL_LOG_PLACEMENT=1`) | ⬜ | follow-up |
| W7 | DeltaTracker rename parser fix — parse `git diff --name-status` 3-col `R100\tfrom\tto` rows correctly, treat `from` as deleted + `to` as modified (was producing corrupt `"from\tto"` filePath, orphaning renamed classes) | ✅ | `plugin/.../export/delta/DeltaTracker.kt::getGitChanges` |
| W7-ext | Extension whitelist (`.kt`/`.vue`/`.js`/`.ts`) in DeltaTracker — blocked on Phase B2.1–B2.7 (Vue delta export support) before widening filter is useful | 🟥 blocked | depends on B2 |
| W8 | Inference-runtime research — runtime comparison matrix (TEI / Triton / Ollama / vLLM / Ray / Bento / FastAPI) | ✅ | `docs/design/PLAN-mcp-only.md` §9 |
| W8 | TEI reranker backend (opt-in via `ONELENS_RERANK_BACKEND=tei`) | ✅ | `python/src/onelens/context/embed_backends/tei_backend.py` |
| W8 | TEI embedding path documented — already supported via `openai_compat` pointed at TEI's `/v1/embeddings` | ✅ | `tei_backend.py` docstring |
| W9 | Competitive landscape doc — Graphify + GitNexus capability matrix, what to copy vs not chase | ✅ | `docs/competitive-landscape.md` |

---

## Phase X — Multi-repo global registry (planned, design from GitNexus)

Mirror GitNexus's `~/.gitnexus/registry.json` pattern so one MCP
server can list + serve every indexed graph on the user's machine.
Folds into the singleton MCP we just built (Phase W2): the lock owns
the process, the registry owns the graph catalogue. Lazy graph-
connection eviction after 5 min idle (max 5 concurrent) keeps the
process light when many repos are indexed but only a few are hot.

| # | Feature | Status | Where |
|---|---|---|---|
| X0 | Design — file format + concurrency rules + registry write atomicity (atomic rename, fcntl lock during write) | ⬜ | `docs/competitive-landscape.md` action #2 + Phase X spec doc TBD |
| X1 | `~/.onelens/registry.json` — schema `{ "graphs": { "<graphId>": { "path": str, "lastSync": ts, "vueRoot": str?, "appCount": int } } }` | ⬜ | `python/src/onelens/registry.py` |
| X2 | `onelens_list_graphs` MCP tool + auto-detect-`graph` when only one indexed | ⬜ | `mcp_server.py` |
| X3 | Lazy graph connection + 5-min idle eviction (LRU cache, max 5 concurrent) | ⬜ | `python/src/onelens/graph/db.py::create_backend` wrapper |
| X4 | Plugin: register on first sync; deregister on `Delete graph` action | ⬜ | `plugin/.../export/ExportService.kt` + `ui/GraphCleanupService.kt` |
| X5 | CI guard — registry write race regression test (concurrent `onelens import-graph` from two terminals must not corrupt) | ⬜ | `python/tests/registry/` |
| X6 | `onelens_route_map` MCP tool — joins Endpoint nodes with Vue ApiCall HITS edges (data already in graph) | ⬜ | `mcp_server.py` — see landscape doc §C |
| X7 | `onelens_shape_check` MCP tool — Vue components accessing fields not in endpoint return type. Walks ApiCall.bindings + JPA entity columns + return-type chain | ⬜ | `mcp_server.py` |
| X8 | `onelens_api_impact` MCP tool — pre-change risk (LOW/MEDIUM/HIGH) per GitNexus thresholds (0-3 / 4-9 / 10+ consumers) | ⬜ | `mcp_server.py` |
| X9 | `confidence` + `reason` properties on edges — surface PSI-resolved (1.0) vs polymorphic-fanout (0.8) vs path-matched (0.6) per Graphify's tagging system | ⬜ | `loader.py` + `analysis.py` |
| X10 | `onelens_processes` MCP tool — BFS forward from PageRank entry-point seeds, dedupe + heuristic naming. Persistent `Process` node + `STEP_IN_PROCESS` edges | ⬜ | `python/src/onelens/importer/processes.py` (new) — see landscape doc §H |
| X11 | `RationaleCollector` (Java + Kotlin + Vue) — extract `// WHY:` / `// FIXME:` / `// HACK:` / javadoc as `Rationale` nodes with `RATIONALE_FOR` edges. Surface in `onelens_context` so agent sees *why* not just *what*. ~80 LOC | ⬜ | `plugin/.../export/collectors/RationaleCollector.kt` — see landscape doc §L |
| X12 | Connection pool with LRU + idle TTL (5 min, max 5 concurrent) — direct port of GitNexus `pool-adapter.ts` pattern. Required by Phase X3 | ⬜ | `python/src/onelens/registry/pool.py` (new) — see landscape doc §K |
| X13 | Optional `format="text"` parameter on heavy MCP tools (`onelens_retrieve`, `onelens_impact`) for token-tight contexts | ⬜ | `mcp_server.py` — see landscape doc §M |
| X14 | Confidence-fusion when multiple sources agree (PSI=1.0 + Vue HITS=0.6 capped at 1.0; PSI=0.0 + SCIP=0.85 → 0.85). Extends X9 | ⬜ | `loader.py` — see landscape doc §F + §N |

---

## Phase Y — Cross-repo bridge graph (planned, design from GitNexus)

Bridge multiple OneLens-indexed graphs via shared contract IDs (HTTP,
gRPC, Kafka topics, shared libraries). Mirror's GitNexus's
`group.yaml` + bridge-db pattern. Builds on Phase X registry.

| # | Feature | Status | Where |
|---|---|---|---|
| Y0 | Design — `docs/design/PLAN-cross-repo-bridge.md`, group.yaml schema, bridge-db FalkorDB schema | ⬜ | TBD |
| Y1 | `onelens.group.yaml` config (repos, links, detect toggles, matching thresholds) | ⬜ | `python/src/onelens/group/config.py` |
| Y2 | `~/.onelens/bridges/<groupId>.rdb` separate FalkorDB instance for cross-repo contracts | ⬜ | `python/src/onelens/group/bridge_db.py` |
| Y3 | `HttpRouteExtractor` — already done as `bridge_http.compute_hits` for in-graph; promote to cross-graph | 🟡 partial | `python/src/onelens/importer/bridge_http.py` |
| Y4 | `GrpcExtractor` — parse `.proto` + scan `pb.RegisterXxxServer` (Go) / `XxxStub(channel)` (Python) / Java grpc-java patterns | ⬜ | `python/src/onelens/group/extractors/grpc.py` |
| Y5 | `TopicExtractor` — Kafka `@KafkaListener` / `KafkaTemplate.send` / NATS / RabbitMQ | ⬜ | `python/src/onelens/group/extractors/topics.py` |
| Y6 | `SharedLibsExtractor` — cross-repo Java import detection (we have App/Package primitives within a repo; extend) | ⬜ | `python/src/onelens/group/extractors/libs.py` |
| Y7 | Exact-match cascade (`runGroupSync` — open each member graph, run extractors, normalize contractId, write contracts.json + bridge-db) | ⬜ | `python/src/onelens/group/sync.py` |
| Y8 | `onelens_group_sync` MCP tool | ⬜ | `mcp_server.py` |
| Y9 | `onelens_group_impact` MCP tool — local walk + bridge fan-out via Cypher (max depth 1 like GitNexus) | ⬜ | `mcp_server.py` + `group/impact.py` |
| Y10 | `onelens_group_query` / `onelens_group_status` / `onelens_group_contracts` MCP tools | ⬜ | `mcp_server.py` |
| Y4-SCIP | SCIP index ingestion when `scip-java` present — fuse with PSI graph, increase confidence on edges both agree (codemem-style additive). Solves the headless-CI story for free when scip-java is on PATH | ⬜ | `python/src/onelens/importer/scip_loader.py` (new) — see landscape doc §N |

---

## Phase Z — Skill multi-targeting (planned, design from Graphify)

Port `skills/onelens/SKILL.md` to Codex / Cursor / Cline / Aider /
Gemini CLI. Same MCP tool surface, different shell idioms.

| # | Feature | Status | Where |
|---|---|---|---|
| Z0 | `skills/onelens/codex.md` — Codex flavor + `multi_agent = true` config note | ⬜ | new |
| Z1 | `skills/onelens/cursor.md` — Cursor MDC rules format | ⬜ | new |
| Z2 | `skills/onelens/cline.md` — Cline shell syntax | ⬜ | new |
| Z3 | `skills/onelens/aider.md` — Aider shell syntax | ⬜ | new |
| Z4 | `skills/onelens/gemini.md` — Gemini CLI syntax | ⬜ | new |
| Z5 | Plugin `InstallSkillAction` detects installed agents (`~/.codex/`, `~/.cursor/`, `~/.claude/skills/`, `~/.aider/`) and drops matching manifest | ⬜ | `plugin/.../skill/InstallSkillAction.kt` |
| Z6 | CI guard — `skills/onelens/*.md` all reference the same `onelens_*` MCP tool names (drift detection) | ⬜ | `.github/workflows/ci.yml` |

ADR: `docs/DECISIONS.md` ADR-W01 (MCP-only runtime).

---

## Phase V — Onboard CLI + MCP decoupling (2026-04-26, design landed)

Move bootstrap from plugin (`PythonEnvManager`, ~400 LOC) to global Python CLI. Per-project `onelens onboard` asks local-vs-cloud embedder, validates + stores keys (keyring → file fallback), registers MCP with Claude Code at project scope. Plugin shells out; MCP lifecycle independent of IDE.

| # | Feature | Status | Where |
|---|---|---|---|
| V0 | Research + plan (uv tool install, voyage-code-3 default cloud, project-scope MCP, keyring fallback semantics, idempotency #8288) | ✅ | `docs/design/PLAN-onboard-cli.md` |
| V1 | `cli_only/setup.py` — extract `installOneLens` + `installSemanticStack` + `installTensorrt` from PythonEnvManager | ⬜ | — |
| V2 | `cli_only/installers/uv.py` — extract `autoInstallUv` | ⬜ | — |
| V3 | `cli_only/secrets.py` — env > keyring > file (chmod 600) + `--insecure-storage` flag | ⬜ | — |
| V4 | `cli_only/config.py` — `~/.onelens/config.toml` RW | ⬜ | — |
| V5 | `cli_only/onboard.py` — interactive flow (Continue.dev pattern) | ⬜ | — |
| V6 | `cli_only/installers/claude_mcp.py` — `claude mcp add --scope project` with idempotency parsing | ⬜ | — |
| V7 | `cli_only/doctor.py` — preflight (python, uv, gpu/driver, falkor, keyring backend, claude CLI) | ⬜ | — |
| V8 | Plugin slimdown — delete ~350 LOC from `PythonEnvManager` | ⬜ | `plugin/.../export/PythonEnvManager.kt` |
| V9 | `scripts/install.sh` — uv bootstrap + `uv tool install onelens` | ⬜ | — |
| V10 | PyPI publish — name reservation + first release | ⬜ | — |
| V11 | CI guard: `grep -r "@mcp.tool" python/src/onelens/cli_only/` returns empty | ⬜ | `.github/workflows/ci.yml` |
| V12 | CI guard: secrets never in MCP tool result / log / `idea.log` | ⬜ | tests |

ADR: `docs/DECISIONS.md` ADR-V01 (CLI owns bootstrap, MCP independent of plugin).

---

## Phase U.1 — Cancellable sync + cleanup guard (2026-04-24)

| # | Feature | Status | Where |
|---|---|---|---|
| U1.1 | `SyncCoordinator` app service — single-sync guard + active-process handle | ✅ | `plugin/.../export/SyncCoordinator.kt` |
| U1.2 | Cancel propagation — daemon reader thread + 200 ms indicator poll + `destroyForcibly()` on cancel + `ProcessCanceledException` | ✅ | `plugin/.../export/ExportService.kt` |
| U1.3 | `ExportFullAction` + `AutoSyncService` acquire/release coordinator, `onCancel()` kills active child | ✅ | `plugin/.../actions/ExportFullAction.kt`, `plugin/.../autosync/AutoSyncService.kt` |
| U1.4 | `GraphCleanupService` refuses clearExports / resetSemantic / deleteGraph while sync in flight (SyncInProgressException) | ✅ | `plugin/.../ui/GraphCleanupService.kt` |
| U1.5 | DangerZone toolbar item disabled while syncing; user-facing dialog on race attempt | ✅ | `plugin/.../ui/OneLensToolWindow.kt` |
| U1.6 | Fix: snapshot Publish passed `--include-embeddings true` — cyclopts rejected explicit token (`addParameter` presence-only) | ✅ | `plugin/.../snapshots/SnapshotManager.kt` |

---

## Phase U — Status tab UX + reindex tool (2026-04-23)

| # | Feature | Status | Where |
|---|---|---|---|
| U1 | Toggle Semantic Index toolbar button (starts/stops MCP inline) | ✅ | `plugin/.../ui/OneLensToolWindow.kt:ToggleSemanticToolbarAction` |
| U2 | Rebuild Semantic Only — re-embed without re-import | ✅ | `OneLensToolWindow.kt:RebuildSemanticAction` + `mcp_server.py::onelens_reindex_semantic` |
| U3 | Clean Up danger zone — clear exports / reset semantic / delete graph | ✅ | `plugin/.../ui/GraphCleanupService.kt` + `OneLensToolWindow.kt:DangerZoneAction` |
| U4 | VRAM display per MCP pid (nvidia-smi --query-compute-apps) | ✅ | `plugin/.../ui/SystemMonitor.kt` + `semanticLabel` 5s tick |
| U5 | Compact `onelens_retrieve` response — cap snippet 600 chars, drop context_text/callers/callees | ✅ | `mcp_server.py:onelens_retrieve` |
| U6 | Augment-style `onelens_retrieve` docstring (when-to-use + compact shape) | ✅ | `mcp_server.py` + `python/src/onelens/SKILL.md` |
| U7 | Fix: empty `snippet` — thread `ONELENS_PROJECT_ROOT` through `syncToGraph(projectBasePath)` | ✅ | `ExportService.kt`, `ExportFullAction.kt`, `AutoSyncService.kt`, `ToggleSemanticIndexAction.kt` |
| U8 | Fix: TRT workspace 2GB→512MB (A2000/3050 fit) + `ONELENS_LOCAL_TRT_WORKSPACE_MB` override | ✅ | `context/embed_backends/local_backend.py` |
| U9 | Fix: TRT engine-cache collision — per-model `cache_slug` ("jina-v2-code" vs "bge-reranker-base") | ✅ | `local_backend.py`, `local_reranker.py` |
| U10 | Fix: `SnapshotManager` `InstantiationException` — drop unused `CoroutineScope` ctor param (Ktor coroutines-core clash) | ✅ | `plugin/.../snapshots/SnapshotManager.kt` |
| U11 | Fix: ChromaBackend dim-check numpy truthiness crash — delete the check (ChromaDB native dim error is sufficient) | ✅ | `context/backends/chroma.py` |
| U12 | Fix: TRT settings auto-heal when tensorrt installed outside the plugin button | ✅ | `plugin/.../settings/SemanticSettingsConfigurable.kt` |

---

## Phase T — Plugin ⇄ MCP HTTP (2026-04-21)

| # | Feature | Status | Where |
|---|---|---|---|
| T1 | Python MCP server HTTP entry (`--http --host --port`) | ✅ | `python/src/onelens/mcp_server.py` |
| T2 | Multi-shape daemon warmup (embed [1,32] + rerank [30]) | ✅ | `mcp_server.py` lifespan |
| T3 | `OneLensMcpService` — app-level Python-child lifecycle + port retry + SIGTERM | ✅ | `plugin/.../mcp/OneLensMcpService.kt` |
| T4 | `OneLensMcpClient` — official MCP Kotlin SDK 0.9.0 + Ktor CIO | ✅ | `plugin/.../mcp/OneLensMcpClient.kt` |
| T5 | Auto-start MCP server on project open (when Semantic ON) | ✅ | `plugin/.../autosync/AutoSyncStartupActivity.kt` |
| T6 | `ExportService` fast-path via MCP when reachable; CLI fallback | ✅ | `plugin/.../export/ExportService.kt` |
| T7 | Port file (`~/.onelens/mcp.port`) for external MCP client discovery | ✅ | `OneLensMcpService.writePortFile()` |
| T8 | Stateless mode (`FASTMCP_STATELESS_HTTP=1`) for simpler clients | ✅ | `OneLensMcpService.buildEnv()` |

---

## Phase S — Local semantic (2026-04-21)

| # | Feature | Status | Where |
|---|---|---|---|
| S1 | Local ONNX embedder (Jina v2 base code, TRT/CUDA/CPU auto-pick) | ✅ | `python/src/onelens/context/embed_backends/local_backend.py` |
| S2 | Local cross-encoder reranker (BGE base) | ✅ | `python/src/onelens/context/embed_backends/local_reranker.py` |
| S3 | Semantic settings screen (Preferences → Tools → OneLens Semantic) | ✅ | `plugin/.../settings/SemanticSettingsConfigurable.kt` |
| S4 | API key in PasswordSafe (no plaintext XML) | ✅ | `plugin/.../settings/OpenAiSecrets.kt` |
| S5 | One-click TensorRT install button (+1 GB, ~3× faster) | ✅ | `PythonEnvManager.installTensorrt()` |
| S6 | Live provider label (cpu / cuda-fp32 / trt-fp16) | ✅ | `PythonEnvManager.detectLocalProvider()` |
| S7 | Backend-dispatching `installSemanticStack` (local vs openai) | ✅ | `PythonEnvManager.kt` |
| S8 | Env wiring (ExportService → CLI: embed + rerank + OpenAI creds) | ✅ | `plugin/.../export/ExportService.kt` |
| S9 | Dim-mismatch guard at query time | ✅ | `python/src/onelens/context/backends/chroma.py` |
| S10 | pyproject.toml extras: context-local + context-local-trt | ✅ | `python/pyproject.toml` |
| S11 | POC measured on RTX A2000: 77 min CPU / 7.6 min CUDA / 2 min TRT per 100k | ✅ | `/tmp/jina_local_poc.py`, `/tmp/trt_bench.py` |

---

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
| H3 | Verified remaining client-name occurrences are all in gitignored local-dev files (`python/trial_*.py`, `python/modal_index*.py`, `python/benchmarks/*.yaml`, `.claude/settings.local.json`) — not in the shipped artifact. Any attempt to commit them would fail the hook. | ✅ | — |
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

## Phase D — Delta correctness + graph enrichment (2026-06)

Multi-reviewer audit (delta-correctness, delta-UX, graph-richness gap-finder). Findings: `docs/design/delta-and-enrichment-findings.md`.

| ID | Item | Status | Pointer |
|----|------|--------|---------|
| D1 | Delta Spring `wing` stamp + full bean props + REGISTERED_AS + SpringAutoConfig + INJECTS qualifier — fixes zeroed Vue↔Spring HITS bridge after any delta | ✅ | `delta_loader.py::_replace_spring` |
| D2 | Delta phantom-CALLS fix — clear outbound CALLS for every upserted method, not just `affected_callers` | ✅ | `delta_loader.py` step 6 |
| D3 | Delta EnumConstant dual-label parity (`MERGE Field SET :EnumConstant`, REMOVE-label cleanup) + `enclosingClass` prop | ✅ | `delta_loader.py` step 4b |
| D4 | Auto-sync data-loss fix — snapshot diff-base, gate advance on `isImportSuccess`, roll back + sticky stale error on failure; `lastSuccessfulImportTimestamp` | ✅ | `ExportState.kt`, `AutoSyncService.kt` |
| D5 | Tier-0 graph enrichment — `RETURNS`/`THROWS`/`HAS_PARAMETER` edges + method props (visibility/static/abstract/deprecated/paramCount/transactional/async); full + delta parity, verified vs falkordblite | ✅ | `loader.py`, `delta_loader.py` `_enrich_method`/`_normalize_type` |
| D6 | Delta JPA/Tests re-derivation — ship `jpa`+`tests`/`mockBeans`/`spyBeans` in DeltaDocument (full re-scan), `_replace_jpa`/`_replace_tests` strip+re-apply dual-labels (`:JpaEntity`/`:JpaColumn`/`:JpaRepository`/`:TestCase`) + HAS_COLUMN/RELATES_TO/REPOSITORY_FOR/QUERIES/MOCKS/SPIES/TESTS. Verified: modified entity stays `[Class,JpaEntity]`, no demotion. (Apps/Packages CONTAINS still pending) | ✅ | `DeltaExportService.kt`, `delta_loader.py::_replace_jpa/_replace_tests` |
| D7 | Tier-1 data-flow — `READS_FIELD`/`WRITES_FIELD`/`INSTANTIATES` via new `DataFlowCollector` body walk; full + delta parity (delete-then-recreate on upsert), verified vs falkordblite | ✅ | `DataFlowCollector.kt`, `ExportModels.kt`, `SpringBootAdapter.kt`, `DeltaExportService.kt`, `loader.py`, `delta_loader.py` |
| D8a | Delta UX — merge-base `--is-ancestor` guard before git diff: branch switch / rebase forces full re-export instead of a garbage whole-branch "delta" | ✅ | `DeltaTracker.kt::getGitChanges` |
| D8b | Delta UX — queue saves landing mid-sync (dropped today); `.kt`/`.vue` save triggers (Java-only today) | ⬜ | `AutoSyncFileListener.kt`, `AutoSyncService.kt` |
| D9 | Plugin audit fixes — tool-window timer/console leak (Disposable), delta per-collector guards + `ProcessCanceledException` rethrow | ✅ | `OneLensToolWindow.kt`, `DeltaExportService.kt::guardCollect` |

## Phase E — Multi-language / multi-framework architecture (2026-06)

3-agent architecture audit (Python importer duplication, Kotlin plugin quality, N-language extensibility). Design: `docs/design/multi-language-architecture.md`; ADR-032/033/034.

| ID | Item | Status | Pointer |
|----|------|--------|---------|
| E1 | Universal SymbolGraph JSON contract documented (`source` accuracy tag; framework blocks all `if`-gated → core is language-neutral) | ✅ | `tools/extractors/README.md` |
| E2 | Standalone Python extractor (stdlib `ast`) — emits universal JSON; existing `GraphLoader` imports it; verified on OneLens's own source (104 cls / 370 mth / 312 calls, GraphDB subclasses + PageRank correct) | ✅ | `tools/extractors/python_ast_extractor.py` |
| E3 | Go reference extractor (`go/ast`) against the same contract | ✅ (reference; needs go/types for FQN call resolution) | `tools/extractors/go/main.go` |
| E4 | Plugin two-SPI split — `LanguageExtractor` ⊗ `FrameworkAdapter`; honor opaque `CollectorOutput` (kill `ExportService` downcast); relocate Spring/JPA collectors under `framework/` | ⬜ | design §3 step 2-3 |
| E5 | Importer `SubdocLoader` registry — extract spring/jpa/tests/vue3/core into loaders shared by full + delta; kills the drift-bug class | 🟡 | staged; gate `python/scripts/parity_check.py` (19 checks) |
| E5.0 | Parity gate — synthetic all-subsystem full+delta import, 19 invariants | ✅ | `python/scripts/parity_check.py` |
| E5.1 | Stage 1 — `graph_writer.py`: shared batch primitives (`GraphWriter`) + `_enrich_method`/`_normalize_type` helpers out of loader; delta re-points off loader. Behavior-preserving, 19/19 green. Implemented by delegated Sonnet agent against `docs/design/E5-stage1-graph-writer.md`. | ✅ | `importer/graph_writer.py` |

## Open regression / verification items

1. Phase A5 — sync the reference Java backend with the rebuilt plugin and diff counts against the captured baseline (`Class=11944, Method=81907, Field=58485, SpringBean=2335, Endpoint=2320, Module=26, Annotation=222`).
2. Phase B7 — sync the reference Vue 3 frontend repo and verify `Component ≥ 1400`, `Store ≥ 35`, `Composable ≥ 15`, `Route ≥ 60`, `ApiCall > 500`.
3. Bridge verification — dogfood HITS count when both reference projects are synced into the same FalkorDB graph.
4. Extend `python/benchmarks/cases.yaml` with Vue-specific cases before claiming Phase B "done-done".
