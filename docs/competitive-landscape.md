# Competitive landscape — code knowledge graphs for AI coding assistants

Snapshot 2026-04-30. Built from Exa search + DeepWiki on Graphify
(`safishamsi/graphify`), GitNexus (`abhigyanpatwari/GitNexus`),
neo4j-graphrag-python, and adjacent GraphRAG-MCP projects.

This doc exists so we don't re-research the same competitors every
quarter and so feature decisions cite a real positioning, not vibes.

## TL;DR

**Three durable advantages OneLens should keep doubling down on:**

1. **IntelliJ PSI parsing** — every other tool ships tree-sitter.
   Tree-sitter cannot resolve overloaded methods, generic types, or
   Spring autowire candidates. PSI does, deterministically, with
   100% type accuracy. This is the moat.
2. **Spring/JPA / Vue cross-stack semantics.** Graphify and GitNexus
   both punt on Spring beyond `extends`/`implements`. JPA, `@Bean`
   factories, `@Profile`/`@Conditional`, autoconfig walker, derived-
   query repositories, Vue→Java `HITS` edges — all unique to us.
3. **Plugin distribution.** Graphify is skill-only (no IDE), GitNexus
   is CLI-only. We ship a real IntelliJ plugin with VFS auto-sync,
   so our graph is always live without a manual reindex command.

**Two patterns worth copying from GitNexus:**

1. Global multi-repo registry (`~/.gitnexus/registry.json`). One MCP
   server, many indexed repos, lazy connections evicted after 5 min.
   Solves multi-IDE / multi-project the same way the singleton lock
   solves it for one repo.
2. Bridge HTTP server (`gitnexus serve`) so the same backend powers
   CLI + web UI + MCP. We already have this shape — `OneLensMcpService`
   HTTP transport — but should harden it.

**One pattern from Graphify worth copying:**

1. Skill multiplication. Graphify ships `/graphify` as a command in
   Claude Code, Codex, Cursor, OpenCode, Cline, Aider, Trae, Kiro,
   Gemini CLI, Hermes, Factory Droid, Google Antigravity. We target
   Claude Code only. Phase Z candidate: port `SKILL.md` to other
   slash-command shells.

**Out of scope:** multi-modal (PDFs / images / audio / video). Graphify
chases this; we don't. Code is the contract.

## Capability matrix

| Capability | Graphify | GitNexus | **OneLens** |
|---|---|---|---|
| **Parsing engine** | tree-sitter | tree-sitter | **IntelliJ PSI** (100% type-accurate) |
| Languages | 25 (incl. Vue / Svelte / Dart / Verilog) | 16 (incl. COBOL) | Java + Kotlin + Vue 3 + JS/TS modules |
| Multi-modal (PDF/img/audio/video) | ✅ Claude subagents + Whisper | ❌ | ❌ (intentional) |
| Java `extends` / `implements` | ✅ (PR #482, v0.4.31, Apr 2026) | ✅ | ✅ |
| Java `@RestController` / endpoint mapping | ❌ | ❌ (roadmap) | ✅ HTTP method + path + handler with Endpoint nodes |
| Spring `@Bean` / `@Autowired` / `@Qualifier` | ❌ | ❌ | ✅ (collector + Spring-plugin model) |
| Spring `@Profile` / `@Conditional` | ❌ | ❌ | partial (C3b.1 deferred) |
| Spring autoconfig (`spring.factories`, `AutoConfiguration.imports`) | ❌ | ❌ | ✅ (`AutoConfigCollector.kt`) |
| JPA entities / columns / relations | ❌ | ❌ (Prisma + Supabase only) | ✅ `JpaCollector.kt` + derived-query edges |
| Spring Data repository derived queries | ❌ | ❌ | ✅ `QUERIES` edges |
| Polymorphic / overloaded method resolution | ❌ | ❌ | ✅ |
| Vue 3 SFC (`<script setup>`, props, emits) | ❌ | ❌ | ✅ Phase B |
| Vue → Java cross-stack `HITS` edges | ❌ | ❌ | ✅ `bridge_http.compute_hits` |
| Pinia / composables / lazy routes | ❌ | ❌ | ✅ |
| **Graph database** | NetworkX (in-mem) + JSON | LadybugDB (Cypher, embedded) | FalkorDB (Cypher + FTS) + falkordblite default |
| Persistent graph between sessions | ✅ JSON | ✅ embedded DB | ✅ FalkorDB instance |
| Cypher exposed to agent | partial (Neo4j export) | ✅ tool | ✅ tool |
| **Embeddings** | none (by design) | Snowflake arctic-embed-xs 384d | Jina-v2-code 768d (configurable) |
| Local embeddings runtime | n/a | transformers.js (WebGPU/WASM/ONNX) | ONNX Runtime + TensorRT opt-in |
| Cross-encoder rerank | n/a | ❌ (BM25+vector RRF only) | ✅ BGE base ONNX |
| Cloud embedding fallback | via Claude API | Modal/HF/OpenAI | Modal / OpenAI-compat / TEI (opt-in) |
| **MCP integration** | optional stdio | core stdio | core HTTP (singleton, Phase W) |
| MCP tool count | 4 (`query_graph`, `get_node`, `get_neighbors`, `shortest_path`) | 16 (11 per-repo + 5 group) | 18 (`onelens_*` + palace) |
| Multi-repo global registry | ❌ (per-folder `graphify-out/`) | ✅ `~/.gitnexus/registry.json` | partial — Workspace abstraction Phase C |
| Lazy connection eviction | n/a | ✅ 5 min idle, max 5 concurrent | ❌ (one connection per process today) |
| Bridge HTTP for web UI | ❌ | ✅ `gitnexus serve` | ✅ FastMCP HTTP transport |
| **IDE integration** | skill only (12+ assistants) | CLI only | IntelliJ plugin with VFS auto-sync |
| Auto-sync on file save | ❌ | ❌ (`detect_changes` git-diff-based) | ✅ debounced VFS listener (5 s) |
| Slash-command skill | ✅ Claude / Codex / Cursor / OpenCode / 8 more | ❌ (MCP-only) | ✅ Claude Code `/onelens` |
| Plugin marketplace presence | n/a | n/a | JetBrains Marketplace (planned) |
| **Distribution** | `pip install graphifyy` | `npm install -g gitnexus` | plugin ZIP + `pip install onelens` |
| Token-reduction claim | 71.5× | not published | 95.3% benchmark pass |
| License | MIT | MIT | MIT-Apache-2.0 dual |

## What each one is optimised for

### Graphify — "the multi-modal generalist"

- **Strength.** Pulls structure out of *anything* — PDFs, whiteboard
  photos, video transcripts, code, docs — and merges into one graph.
  Slash-command UX is brilliant for distribution; `/graphify` works
  in 12+ AI coding assistants out of the box.
- **Weakness.** Per-language extraction stops at AST. Java was
  generic-AST until v0.4.31 (Apr 2026) shipped `extends`/`implements`.
  No Spring awareness at all. NetworkX in-memory caps it at single-
  user single-machine; no shared state across IDE windows.
- **What to learn.** Distribution-as-skill. We can multi-target Codex
  / Cursor / Cline with the same SKILL.md plus per-shell adapters.

### GitNexus — "the cross-language graph engine"

- **Strength.** Engineering depth: 12-phase DAG pipeline, per-language
  MRO strategies, unified capture tags, browser+CLI dual runtime,
  global registry, bridge HTTP, 16 MCP tools including `route_map` /
  `api_impact` / `shape_check` that pre-compute REST surface analysis.
  This is the closest competitor architecturally.
- **Weakness.** Tree-sitter ceiling — same as Graphify on type
  resolution. Spring annotations / JPA explicitly missing. Decorator
  detection is on the roadmap, not built. Embeddings are 384-d
  Snowflake xs (smaller than ours, possibly worse on code retrieval —
  warrants a benchmark).
- **What to learn.** **Multi-repo registry pattern.** `~/.gitnexus/
  registry.json` mapping `<repo-name>` → `<index path>`, MCP serves
  all, lazy connections evicted after 5 min. This is exactly the UX
  shape Phase C "Workspace abstraction" wants. We should mirror the
  registry file format and the lazy-connect+evict policy. **Bridge
  HTTP** mode (`gitnexus serve`) — same backend powers CLI + web UI
  + MCP. We have FastMCP HTTP today; should add a thin web UI later.

### Smaller players

- **neo4j-graphrag-python / mcp-neo4j-graphrag** — generic GraphRAG
  toolkits. Need you to bring the graph yourself. Not code-specific.
  Useful as a backend swap for users who already run Neo4j.
- **graphrag-hybrid (rileylemm)** — Markdown-only, Neo4j + Qdrant.
  Doc-RAG, not code-RAG. Out of scope.

## Concrete action items for OneLens

| # | Action | Source | Phase |
|---|---|---|---|
| 1 | Document PSI moat in README + comparison page | this doc | Phase W |
| 2 | Add `~/.onelens/registry.json` global multi-repo registry | GitNexus | Phase X (new) |
| 3 | Lazy graph connection + 5-min idle eviction in MCP server | GitNexus | Phase X |
| 4 | Cross-repo MCP tool — `onelens_list_graphs` (already partial) + `repo` param defaulting when only one indexed | GitNexus | Phase X |
| 5 | Pre-computed `route_map` / `api_impact` tools for the agent | GitNexus | already partial via `onelens impact --method-fqn …` — add a route-first variant |
| 6 | Skill port to Codex / Cursor / Cline / OpenCode | Graphify | Phase Z (later) |
| 7 | Benchmark Snowflake arctic-embed-xs (384d) vs our Jina-v2-code (768d) on `python/benchmarks/` | GitNexus | Phase W follow-up |
| 8 | Token-reduction A/B claim on README — not "71.5×" cargo-cult, real before/after on a representative repo | both | Phase Y |

## Docs indexing — current state + gap

### What we do today (post-check)

- **Inline javadoc / docstrings** — extracted by code-side collectors,
  embedded into the `Method` body for retrieval. Searchable via
  `onelens_retrieve`. Not standalone nodes.
- **Palace memory layer** — has `HALL_DOCS` constant defined
  (`python/src/onelens/context/config.py:23`) plus
  `HALL_DECISIONS` / `HALL_GIT` / `HALL_ISSUES` / `HALL_CICD` /
  `HALL_RUNTIME`. `palace.drawers.add_drawer()` accepts arbitrary
  text with dedup + WAL. ChromaDB embed + rerank is hall-agnostic.
- **Snapshots include `docs/` paths** in `exports/<project>-full-*.json`
  but as filesystem refs only — not indexed as content.

### What we DON'T do

- ❌ Walk `*.md` / `*.markdown` / `*.mdx` / `*.adoc` files into the graph or
  drawer layer.
- ❌ Index `README*`, `CHANGELOG.md`, ADR files, `docs/**`.
- ❌ Parse markdown links `[text](path/to/Foo.java)` as cross-refs to
  code nodes.
- ❌ PDF / image / video extraction (intentional non-goal — see §"What
  we should not chase").

### What competitors do

| Tool | Doc support | Approach | Cross-ref to code? |
|---|---|---|---|
| **Graphify** | first-class | Claude subagents extract concepts from PDF/MD/images/video | INFERRED edges via Claude reasoning |
| **GitNexus** | markdown only | Phase 3 of 12: `Section` nodes + `CONTAINS` parent-child | ❌ no Section→Symbol link |
| **Sourcegraph Cody** | full-text everything | SCIP for code, plain text search for docs | partial (string matches) |
| **graphrag-hybrid** | markdown only | Neo4j sections + Qdrant chunks; markdown-only — no code | n/a |
| **Aider repo-map** | none | Tree-sitter tags only | n/a |
| **Repomix / code2prompt** | dump-as-text | No structure | no |
| **blarify** | LLM-generated docs from code | Auto-summarises code into Documentation nodes (different problem) | ✅ but inverse direction |

**Nobody links existing Doc-section text to type-resolved code symbols.** Graphify gets close via Claude inference but it's heuristic, not resolved. **This is a niche we can own** because PSI lets us resolve `[text](path/to/Foo.java)` deterministically.

### Why our infrastructure is 70 % ready

1. `HALL_DOCS` constant exists (palace config) but no producer.
2. `palace.drawers.add_drawer()` accepts arbitrary text with dedup + WAL — drop-in for doc chunks.
3. ChromaDB layer doesn't care if content is code or prose; same `wing/room/hall/fqn/type/importance/filed_at` schema.
4. `onelens_retrieve` already cross-searches all halls when `hall` filter is unset.

### Two-stage plan (Phase X-DOCS, queued in PROGRESS)

- **Stage 1 — drawer-only (~120 LOC).** `python/src/onelens/miners/doc_miner.py` walks `*.md`/`*.adoc`/`README*`/`docs/**`, heading-bounded chunks, emits drawers in `HALL_DOCS`. Retrieval works immediately. No new MCP tool, no graph schema change.
- **Stage 2 — Doc + Section nodes + MENTIONS edges (~150 LOC).** Add `Doc` and `Section` to `NODE_TYPES`. Parse markdown links → `MENTIONS` edges to existing `Class`/`Method`/`Endpoint` nodes. New `onelens_doc_for(fqn)` MCP tool: "which docs mention this symbol?" Inverse direction is already free via Cypher.
- **Stage 3 — `.md` delta on auto-sync.** Include doc files in `AutoSyncFileListener`; cascade-delete drawers by ID prefix `doc:<relpath>:` on file delete (existing pattern from Phase B2.5).

### Why this matters more than it looks

- **Enterprise Spring repos document architecture in `docs/`** — runbooks, ADRs, API contracts, on-call playbooks. Today an agent asking "what's our auth strategy?" gets only what's in code comments + javadoc.
- **The Doc↔Code link is unique.** Graphify and GitNexus both index docs but neither resolves `[link](path)` against the actual code graph. PSI gives us this for free.
- **Multi-modal still off the table.** Adding Markdown is not the same as chasing Graphify's PDF/audio/video pipeline. Markdown is text; the existing pipeline ingests text.

## What we should not chase

- **Multi-modal (PDFs / images / video).** Graphify already owns this
  niche; chasing it dilutes the "100%-accurate code intelligence"
  positioning. Code-only is the discipline.
- **Browser WASM runtime.** GitNexus does it well; the engineering
  cost (Tree-sitter WASM, Kuzu/Ladybug WASM, transformers.js) is
  enormous and unrelated to our PSI moat. Plugin + CLI is enough.
- **AST-based decorator detection in Java.** Graphify and GitNexus
  will eventually ship this, and they'll still miss Spring's runtime
  semantics (autowire by type, `@Primary`, profile activation,
  `spring.factories`). PSI + Spring's own model is the right answer
  and we already have it.

## Deep dive — implementation specifics worth copying

Sourced from DeepWiki second-pass on `abhigyanpatwari/GitNexus` and
`safishamsi/graphify`. Concrete enough to build from without re-reading
their codebases.

### A. GitNexus's CrossFile type propagation algorithm

This is the engineering they use to **approach PSI quality without an
LSP**. Phase 9 of the 12-phase pipeline. Language-agnostic. Worth
understanding because it reveals what a tree-sitter tool must build to
match what we get for free from IntelliJ PSI.

**Step 1 — Topological import order.** Kahn's BFS over file→file import
edges. Cycles in the final level, no cross-cycle propagation (cycles
get a single resolution pass and stop).

**Step 2 — Three enrichment mechanisms (run in order):**

- **E1 `seedCrossFileReceiverTypes`** — pre-seeds `receiverTypeName` for
  single-hop imported receivers. Zero re-parse — works off the symbol
  index built in Phase 5.
- **E2 `ExportedTypeMap`** — seeds exported types into
  `importedBindings` so a downstream file can re-resolve `import X` →
  full type info.
- **E3 `buildImportedReturnTypes`** — propagates cross-file return
  types for imported callables.

**Step 3 — Fixpoint loop.** Iterate over pending assignments
(`copy`, `callResult`, `fieldAccess`, `methodCallResult`) until no new
bindings are produced. This is what resolves `let x = getUser();
x.address.city.getName()` chains across files without a real type
checker.

**Step 4 — Per-language field extractors.** Generic table-driven
factory; per-language config supplies the AST node names and
visibility/static/readonly modifiers, plus the declared-type capture.

**OneLens implication:** PSI gives us *all* of this natively, with full
generic resolution, overload selection, and Spring autowire candidate
narrowing. Writing this comparison into the README is worth a marketing
paragraph: "GitNexus reverse-engineered this in 1500 lines of TypeScript
across two phases; OneLens gets it from `PsiReference.resolve()` in one
call." This is the moat in concrete terms.

### B. GitNexus's MRO plug-in pattern

```ts
// LanguageProvider field
mroStrategy: 'c3' | 'first-wins'

// Resolver dispatch
if (provider.mroStrategy === 'c3') {
    mroOrder = c3Linearize(classId, parentMap, c3Cache) ?? ancestors;
} else {
    // first-wins: collect methods grouped by name, detect collisions,
    // apply per-language resolution rules
}
```

C3 for Python, first-wins for Java/C#/TS. PSI handles this for us by
default; we don't need the plug-in. **But the pattern is worth copying
elsewhere** — our `FrameworkAdapter` SPI already has this shape (see
`SpringBootAdapter` vs `Vue3Adapter` plug-in points). Reuse the language-
provider table-driven config style if we add Kotlin/Scala/Groovy
adapters later.

### C. GitNexus's MCP tool return shapes (worth copying)

DeepWiki confirmed the public shapes. Implementation details aren't in
the wiki context, so the shapes below are derived from the wiki's
tool-description copy.

| Tool | Returns |
|---|---|
| `query` | BM25 + semantic merged via RRF K=60. Results grouped **by process** (not by file) with symbol IDs and definitions. |
| `context` | 360° view: incoming refs (calls, imports, extends, implements), outgoing refs (callees, methods, properties, overrides), process participation, file location. **Disambiguation candidates ranked** when symbol name is ambiguous. |
| `detect_changes` | Maps git diff hunks → indexed symbols → impacted processes → risk summary. |
| `route_map` | `{routes: [{method, path, handler, middlewares: [...], consumers: [...]}]}` |
| `shape_check` | Detects `MISMATCH` when a consumer accesses a key not in the route's response shape. |
| `api_impact` | Combines `route_map` + `shape_check` + `impact`. **Risk thresholds:** LOW (0–3 consumers), MEDIUM (4–9 OR any mismatches), HIGH (10+ consumers OR mismatches with ≥4 consumers). |

**OneLens implication.** We have `onelens_impact` (handler-first) and
`onelens_trace` (path-first), but no `route_map` / `shape_check` /
`api_impact`. We're **better positioned than GitNexus** for these
because PSI gives us the actual response type via `@RestController`
return type → JPA entity → DTO chain, not just signature shape.
Concrete additions for Phase X:

```python
# python/src/onelens/mcp_server.py — new tools
@mcp.tool
def onelens_route_map(graph: str, method: str = None, path_glob: str = None) -> dict:
    """Returns {routes: [{method, path, handler_fqn, vue_consumers: [...]}]}.
    Joins Endpoint nodes with Vue ApiCall HITS edges. Already in graph."""

@mcp.tool
def onelens_shape_check(graph: str, endpoint: str) -> dict:
    """Detect Vue components accessing fields not present in the
    endpoint's return type. Walks ApiCall.bindings + JPA entity columns
    + return-type chain. We have this data; just need the diff."""

@mcp.tool
def onelens_api_impact(graph: str, endpoint: str) -> dict:
    """Pre-change risk: route_map + shape_check + impact merged.
    Risk LOW/MEDIUM/HIGH per GitNexus's thresholds."""
```

### D. GitNexus's cross-repo / group features (Phase Y candidate)

This is the **bigger architectural pattern** — separate from the
single-repo registry (Phase X). Worth a dedicated phase.

**Configuration — `group.yaml`:**

```yaml
repos:
  api-gateway: api-gateway
  user-service: user-service
  notification-service: notification-service
links:                            # optional manual contracts
  - provider: user-service
    consumer: api-gateway
    contract: GET /users/{id}
detect:
  http: true
  grpc: true
  topics: false
  shared_libs: true
matching:
  bm25_threshold: 0.7
  embedding_threshold: 0.65
```

**bridge-db.** Separate LadybugDB instance storing cross-repo
contracts. Read-only during cross-impact analysis. Populated by
`gitnexus group sync`:

1. Open each member's per-repo LadybugDB.
2. Run `GrpcExtractor` (parses `.proto`, scans `pb.RegisterXxxServer`
   in Go, `XxxStub(channel)` in Python), `HttpRouteExtractor`,
   `TopicExtractor` over each member's source.
3. Apply manifest `links` from `group.yaml`.
4. **Exact-match cascade** — join providers and consumers sharing a
   normalized `contractId`.
5. Write `contracts.json` + the bridge-db.

**Cross-impact — `runGroupImpact`:**

1. **Local walk** within the anchor repo (standard impact).
2. **Bridge fan-out** — hop across the bridge-db using
   `CY_NEIGHBORS_UPSTREAM` / `CY_NEIGHBORS_DOWNSTREAM` Cypher.
3. `MAX_SUPPORTED_CROSS_DEPTH = 1` (no multi-hop yet).

**OneLens implication.** Our `bridge_http.compute_hits` already does
the exact-match cascade for HTTP (Vue ApiCall.path → Endpoint.path).
What we don't have:

- A separate **bridge graph** stored at `~/.onelens/bridges/<groupId>.rdb`
  populated by `onelens group sync`.
- **gRPC extractor** (we don't index .proto today).
- **Topic / Kafka extractor** (likewise).
- **Shared-libs extractor** (cross-repo class import detection — our
  Phase C App/Package primitives already model this within a repo).
- **Cross-repo `impact`** that hops across the bridge graph.

Phase Y deliverables (deferred, design-only here):

```
docs/design/PLAN-cross-repo-bridge.md      # new
~/.onelens/bridges/<groupId>.rdb           # bridge graph schema
python/src/onelens/group/sync.py           # extractors + cascade
python/src/onelens/group/impact.py         # local walk + bridge fan-out
mcp_server.py:onelens_group_sync           # tool
mcp_server.py:onelens_group_impact         # tool
```

### E. GitNexus's embedding integration (worth comparing, not copying)

- Model: **Snowflake arctic-embed-xs (384d)** via local ONNX OR remote HTTP.
- Env vars: `GITNEXUS_EMBEDDING_DIMS`, `GITNEXUS_EMBEDDING_URL`,
  `GITNEXUS_EMBEDDING_MODEL`.
- Stored in a separate `Embedding` table in LadybugDB.
- Hybrid search: BM25 + vector via **RRF K=60** (formula:
  `score = Σ 1 / (K + rank_i)` for each ranking method).

**OneLens implication.** We use **Jina-v2-base-code (768d)** — bigger
model, code-tuned. Worth a benchmark pass: arctic-embed-xs may be
faster (smaller, browser-friendly) but probably worse on code-specific
recall. Add to Phase W follow-up:

```bash
# python/benchmarks/embedding_compare.py
# Run all 64 single-tool cases + 20 multi-step scenarios twice:
# once with Jina-v2-code, once with Snowflake arctic-embed-xs.
# Report recall@5, recall@10, MRR, latency.
```

### F. Graphify's confidence-tag system (worth a partial copy)

**Tags assigned by Claude semantic extractor:**

- `EXTRACTED` → `confidence_score = 1.0` (deterministic, AST or PSI)
- `INFERRED` → `0.6–0.9` (Claude reasons individually per edge)
- `AMBIGUOUS` → `0.1–0.3` (low-confidence heuristic)

Stored on every edge; clustering treats them equally (no differential
weighting in Leiden).

**OneLens has the data, just doesn't surface it as a unified tag:**

- Today: `external` property (`true`=library stub, `false`=implicit
  ctor, unset=normal). Our actual confidence varies edge-by-edge but
  isn't reported.
- Cross-stack `HITS` edges (Vue → Java) — confidence is "path
  matches" only. Should be `INFERRED`.
- Polymorphic call resolution via `--no-precise-only` — should be
  `AMBIGUOUS` for the fan-out targets.
- PSI direct-resolve `CALLS` / `EXTENDS` / `IMPLEMENTS` — `EXTRACTED`.

Concrete add: a `confidence` property on every relationship + a
`reason` (e.g. `"psi_resolve" | "polymorphic_fanout" | "path_match"`).
Surface in `onelens_impact` results so the agent can choose what to
trust:

```python
{
  "endpoint": "PATCH:/vendor/{id}",
  "callers": [
    {"fqn": "com.example.VendorController#patch", "confidence": 1.0, "reason": "psi_resolve"},
    {"fqn": "com.example.VendorService#update", "confidence": 0.8, "reason": "polymorphic_fanout"},
  ],
  "vue_consumers": [
    {"file": "src/views/Vendor.vue", "confidence": 0.6, "reason": "path_match"},
  ],
}
```

~50 LOC change, mostly mechanical. Deferred to Phase X follow-up.

### G. Graphify's skill multi-targeting pattern (Phase Z exact spec)

**Layout in their repo:**

```
graphify/
├── skill.md              # Claude Code (default)
├── skill-codex.md        # Codex CLI
├── skill-aider.md        # Aider
├── skill-trae.md         # Trae
├── skill-kiro.md         # Kiro / Google Antigravity
├── skill-windows.md      # PowerShell
└── extract.py            # the actual pipeline
```

**Differences are syntactic only.** All manifests:

- Detect → Extract → Build → Cluster → Analyze → Report → Export.
- Share an identical Claude semantic-extraction prompt template
  (FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE substitutions).
- Identical JSON output schema.

**Per-platform deltas:**

- Codex needs `multi_agent = true` under `[features]` in
  `~/.codex/config.toml` for parallel extraction.
- Factory Droid uses the `Task` tool; OpenClaw/Aider use sequential.
- PowerShell vs bash command syntax differs.
- Some platforms have `spawn_agent`, others have `Task`.

**Cute trick:** they write the chosen Python interpreter path to
`graphify-out/.graphify_python` so subsequent bash invocations use the
same interpreter without re-detecting.

**OneLens Phase Z spec.** Already partial — `skills/onelens/SKILL.md`
exists for Claude Code with progressive-disclosure references. Add:

```
skills/onelens/
├── SKILL.md                       # current — Claude Code
├── codex.md                       # new
├── cursor.md                      # new — Cursor MDC rules
├── cline.md                       # new
├── aider.md                       # new
├── gemini.md                      # new
└── references/                    # already exists
    ├── jvm.md
    ├── vue3.md
    └── recipes.md
```

Plugin `InstallSkillAction` extended to detect installed agents
(`~/.codex/`, `~/.cursor/`, `~/.claude/skills/`, `~/.aider/`, etc.) and
drop the matching manifest. Each manifest invokes the same MCP tools
(`onelens_*`) — only the surrounding shell command syntax and
agent-spawning idioms differ.

### H. GitNexus's process detection + entry-point scoring (worth copying)

Phase 12 of the 12-phase pipeline. Language-agnostic.

**Algorithm:**

1. **Entry-point identification.** Functions with no internal callers,
   scored by:
   - Framework patterns (HTTP route, scheduled task, message handler).
   - Inbound call ratio (zero in-edges = root).
2. **BFS forward** via `CALLS` edges. Group + dedupe similar paths.
3. **Heuristic naming.** Pattern-match entry-point names:
   `handleLogin` → "LoginFlow: handler → validator → repo → response."

**OneLens has the seeds.** PageRank already starts from REST endpoints,
`@Scheduled`, `@EventListener`, `@PostConstruct`. Missing: the
forward BFS + naming + persisted Process node. Concrete add:

```python
# python/src/onelens/importer/processes.py — new
def trace_processes(db, graph_name: str) -> list[dict]:
    """For each entry point, BFS forward via CALLS edges, dedupe similar
    paths, name by heuristic. Write Process node + STEP_IN_PROCESS edges
    to FalkorDB. Run as post-import phase like PageRank."""
```

Then `onelens_processes` MCP tool returns the named flows; `context`
gains a `process_participation` field showing which flows a symbol is
part of. Aligns with our Vue routes too — Vue Route → Component →
ApiCall → Endpoint becomes a `Process` "VendorEditFlow."

## Second deep-pass — code-level specifics

Got source-level detail on a third DeepWiki round + Exa sweep. Codeable
patterns, not just architecture sketches.

### I. GitNexus's exact RRF + BM25 implementation

```typescript
// BM25 path
results.forEach((row, i) => {
    rrfScore = 1 / (60 + i);   // 0-indexed
    merged.set(nodeId, (merged.get(nodeId) ?? 0) + rrfScore);
});

// Semantic path — same formula
embedHits.forEach((hit, i) => {
    rrfScore = 1 / (60 + i);
    merged.set(hit.nodeId, (merged.get(hit.nodeId) ?? 0) + rrfScore);
});
// Same node in both rankings → scores SUMMED, not max.
```

**OneLens parity check.** `python/src/onelens/context/retrieval.py::hybrid_retrieve` already does this — `1/(K+rank)` with K=60 default, scores summed across BM25 + semantic. Confirmed from the deep dive. **No change needed.**

### J. GitNexus's BM25 = LadybugDB native FTS + Porter stemmer

Five FTS indexes: `File`, `Function`, `Class`, `Method`, `Interface`. Each uses **Porter stemmer** for indexing AND query. Cypher procedure call shape:

```cypher
CALL QUERY_FTS_INDEX('Function', $query, { conjunctive: false })
YIELD node, score
RETURN node, score
```

`conjunctive: false` = OR logic, allows partial matches.

**OneLens delta.** FalkorDB FTS is what we use; weight schema: `name=10, javadoc=3, body=1`. **No stemming.** Porter stemming on code identifiers is debatable — `userService` doesn't stem to anything useful, and over-stemming `getUser` → `getus` hurts exact-match. Worth a benchmark pass before adopting. Defer.

### K. GitNexus's connection pool — exact data structure

```typescript
interface PoolEntry {
    available: Connection[];
    checkedOut: number;
    lastUsed: number;       // ms timestamp
}

const pool = new Map<string, PoolEntry>();
const MAX_POOL_SIZE = 5;
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;

// Idle reaper — runs every 60s
setInterval(() => {
    const now = Date.now();
    for (const [repoId, entry] of pool) {
        if (entry.checkedOut === 0 && now - entry.lastUsed > IDLE_TIMEOUT_MS) {
            entry.available.forEach(c => c.close());
            pool.delete(repoId);
        }
    }
}, 60_000);

// LRU evict when at cap
function evictLRU() {
    if (pool.size < MAX_POOL_SIZE) return;
    let oldest = null, oldestTs = Infinity;
    for (const [repoId, entry] of pool) {
        if (entry.checkedOut === 0 && entry.lastUsed < oldestTs) {
            oldest = repoId;
            oldestTs = entry.lastUsed;
        }
    }
    if (oldest) pool.delete(oldest);
}
```

**OneLens Phase X3 spec.** Direct port to Python:

```python
# python/src/onelens/registry/pool.py
import threading, time
from contextlib import contextmanager
from onelens.graph.db import create_backend

_MAX = 5
_IDLE_TIMEOUT_S = 300
_pool: dict[str, _Entry] = {}
_lock = threading.Lock()

class _Entry:
    __slots__ = ("backend", "checked_out", "last_used")
    def __init__(self, backend):
        self.backend = backend
        self.checked_out = 0
        self.last_used = time.time()

def _idle_reaper():
    while True:
        time.sleep(60)
        now = time.time()
        with _lock:
            stale = [k for k, e in _pool.items()
                     if e.checked_out == 0 and now - e.last_used > _IDLE_TIMEOUT_S]
            for k in stale:
                _pool[k].backend.close()
                del _pool[k]

threading.Thread(target=_idle_reaper, daemon=True).start()

@contextmanager
def get_backend(graph_name: str):
    with _lock:
        e = _pool.get(graph_name)
        if e is None:
            if len(_pool) >= _MAX:
                _evict_lru_locked()
            e = _Entry(create_backend(graph_name=graph_name))
            _pool[graph_name] = e
        e.checked_out += 1
        e.last_used = time.time()
    try:
        yield e.backend
    finally:
        with _lock:
            e.checked_out -= 1
            e.last_used = time.time()
```

### L. Graphify's rationale-comment regex (worth Java port)

```python
_RATIONALE_PREFIXES = (
    "# NOTE:", "# IMPORTANT:", "# HACK:", "# WHY:",
    "# RATIONALE:", "# TODO:", "# FIXME:",
)

# Detection — split source into lines, check prefix
for line in source.splitlines():
    stripped = line.lstrip()
    if any(stripped.startswith(p) for p in _RATIONALE_PREFIXES):
        # Emit node {file_type: "rationale", text: stripped, line: ln}
        # Emit edge {relation: "rationale_for", source: rationale_node, target: enclosing_symbol}
```

Plus tree-sitter walk for `class_definition` / `function_definition` first-string-literal docstring extraction. **Python-only today**; other languages not handled.

**OneLens Java port (Phase X11 candidate, ~80 LOC):**

```kotlin
// plugin/src/main/kotlin/com/onelens/plugin/export/collectors/RationaleCollector.kt
private val PREFIXES = listOf(
    "// NOTE:", "// IMPORTANT:", "// HACK:", "// WHY:",
    "// RATIONALE:", "// TODO:", "// FIXME:",
)

class RationaleCollector(...) {
    fun collect(file: PsiJavaFile): List<RationaleData> {
        val out = mutableListOf<RationaleData>()
        // Pass 1: line comments matching the prefix list, attach to enclosing PsiMember
        file.accept(object : JavaRecursiveElementVisitor() {
            override fun visitComment(c: PsiComment) {
                val text = c.text.trim()
                if (PREFIXES.any { text.startsWith(it) }) {
                    val enclosing = PsiTreeUtil.getParentOfType(c, PsiMember::class.java)
                    out += RationaleData(
                        text = text, line = lineOf(c),
                        targetFqn = enclosing?.fqn(),
                        kind = "comment",
                    )
                }
            }
        })
        // Pass 2: javadoc on class/method/field — attach as rationale with kind="javadoc".
        // (We already export javadoc body for embedding; this adds it as a graph node too.)
        return out
    }
}
```

Loader emits `Rationale` node + `RATIONALE_FOR` edge → enclosing symbol. Surfaces in `onelens_context` so the agent sees *why* a method exists, not just what calls it. Cheap differentiation. Works in Vue too — `<!-- WHY: -->` HTML comments + `// FIXME:` in JS.

### M. Graphify's MCP-as-text-not-JSON design choice

Graphify's `serve.py` returns formatted **strings** for every tool:

```
NODE [VendorService] [src=services/vendor.py loc=42 community=auth]
EDGE [VendorService] --[calls] [[EXTRACTED]]--> [VendorRepo]
EDGE [VendorService] --[uses] [[INFERRED 0.7]]--> [TimeUtils]
```

vs OneLens's JSON:

```json
{
  "node": {"label": "VendorService", "src": "...", "loc": 42, "community": "auth"},
  "edges": [{"target": "VendorRepo", "relation": "calls", "confidence": "EXTRACTED"}, ...]
}
```

**Tradeoff matrix:**

|   | text | JSON |
|---|---|---|
| Token cost | lower (no `{}`, `:`, quotes) | higher |
| Agent parsing | LLM reads naturally, no `JSON.parse` | structured, programmatic |
| Multi-tool composability | weaker — agent must re-parse | stronger — pipe-able |

**OneLens choice.** Stick with JSON (current). Reason: agents like Claude Code routinely chain tool calls (`onelens_impact` → feed into `onelens_trace`); JSON keeps that pipeline clean. Add a `format: "text" | "json"` parameter on heavy tools (`onelens_retrieve`, `onelens_impact`) so power users on token-tight contexts can switch. ~10 LOC.

### N. Sourcegraph SCIP — the real other contender

Found it on the second pass. **SCIP (Source Code Intelligence Protocol)** = Sourcegraph's compiler-grade alternative to tree-sitter and to PSI.

- **scip-java** is a **javac compiler plugin** that emits SemanticDB during regular compilation, then converts to SCIP. Java + Scala + Kotlin.
- **Compiler-grade type accuracy**: same level as PSI. "Zero false positives" per Sourcegraph's docs. Cross-repo navigation via classpath inspection.
- **blarify** (223 stars MIT) uses SCIP optionally — claims "330× faster reference resolution vs LSP."
- **codemem-storage** (Rust) **fuses tree-sitter + SCIP edges with additive confidence**: `0.10 + 0.15 = 0.25` when both agree. Multi-source agreement boosts edge weight.

**PSI vs SCIP — actual comparison:**

| | PSI (OneLens) | SCIP-java (Sourcegraph) |
|---|---|---|
| Type accuracy | 100% | 100% |
| Generic resolution | ✅ | ✅ |
| Polymorphic dispatch | ✅ | ✅ |
| Live during editing | ✅ (no build needed) | ❌ (needs `mvn compile`) |
| In-IDE work-in-progress | ✅ | ❌ (only what compiles) |
| CI without Ultimate license | ❌ | ✅ |
| Spring annotation awareness | ✅ (via our adapters) | ❌ (generic Java only) |
| JPA semantics | ✅ | ❌ |
| Cross-repo via bytecode classpath | partial (Phase Y) | ✅ |
| Build dependency | none — IntelliJ runs PSI on read | mvn/gradle/sbt/Bazel build |
| Cold-cycle indexing time | minutes (on big monorepos) | minutes |
| Ecosystem | IntelliJ-only | language-agnostic protocol |

**Key insight.** PSI and SCIP-java are **complementary**, not competing. PSI wins on live editing + framework awareness. SCIP-java wins on CI / headless / cross-repo classpath.

**OneLens opportunity (Phase Y4 candidate):** ingest SCIP indices when they exist. Use codemem's confidence-fusion pattern:

```python
# python/src/onelens/importer/scip_loader.py — new
def fuse_scip_into_graph(scip_index_path, graph_db):
    """Read SCIP index from CI runs. For each (callerFqn, calleeFqn)
    edge, check if PSI already emitted it.
      - Both present → bump edge.confidence to min(1.0, psi_score + 0.15)
      - SCIP only (e.g. CI saw a call PSI missed because IDE was stale)
        → emit edge with confidence=0.85 (compiler-grade, but no
        framework context to apply our 1.0 PSI adapter)."""
```

Aligns with Phase V plan §4.2 where the headless metadata engine is a CI alternative. SCIP-java solves the headless story for free — no scip-java on PATH means no fusion, but when present we get a proper CI-validated graph for ~zero engineering.

### O. Other tools surveyed (depth varies)

| Tool | Stars | What it actually does | Notable |
|---|---|---|---|
| **Aider repo-map** | 40k (built-in to Aider) | Tree-sitter tags + PageRank, dynamically scoped per chat. ~1k tokens output. | Most compact. Locked to Aider. |
| **Sourcegraph Cody** | enterprise | SCIP-indexed code graph + RAG, $59/user/mo. ISO 27001. | 1M-token context via Gemini Flash. SCIP is the moat. |
| **blarify** | 223 (MIT) | Code → Neo4j/FalkorDB graph via **multilspy LSP or SCIP**. | Started LSP, ships SCIP for 330× speedup. Has incremental update + workflows + LLM-generated docs. |
| **codemem-storage** | (Rust) | Tree-sitter + SCIP fusion with **additive confidence** (both agree → score sums). | **Confidence-stacking pattern worth copying** — see §F. |
| **Repomix** | 22k | XML/MD/JSON full-file dump. ~70% token reduction via tree-sitter compression. | No graph. Just compression. |
| **CodeGraphContext** | smaller (MIT) | GitNexus-shaped knowledge graph alternative. | Similar architectural goals, less polished. |
| **Microsoft GraphRAG** | (large) | Generic RAG-from-graphs. Not code-specific. | Out of scope. |
| **Stacklit** | (Go) | Tree-sitter + module map + ~250 token compact map. Committable artifact. | Single binary, no deps. |
| **amplihack** | — | Vendors blarify + Kuzu embedded DB. Memory system that links code to past LLM observations. | Memory-first design — opposite of OneLens's structure-first. |
| **claude-mem / cognee** | — | Memory tools, not code-graph specifically. | Out of scope. |

### P. New action items from the second pass

| # | Action | Source | Phase |
|---|---|---|---|
| 11 | RationaleCollector for Java/Kotlin/Vue (`// WHY:` / `// FIXME:` / javadoc) → `Rationale` nodes + `RATIONALE_FOR` edges + emitted into `onelens_context` | Graphify §L | Phase X11 (~80 LOC) |
| 12 | Connection pool with LRU + idle TTL (5 min, max 5 concurrent) per Phase X3 — concrete code in §K | GitNexus | Phase X3 — direct port |
| 13 | Confidence-fusion when multiple sources agree (PSI=1.0 + Vue HITS=0.6 → max 1.0; PSI=0.0 + SCIP=0.85 → 0.85) — extends Phase X9 | codemem-storage | Phase X9 follow-up |
| 14 | SCIP index ingestion when scip-java present — fuse with PSI graph, increase confidence on edges both agree | SCIP / blarify / codemem | Phase Y4 (after cross-repo bridge) |
| 15 | Optional `format="text"` parameter on heavy MCP tools (`onelens_retrieve`, `onelens_impact`) for token-tight contexts | Graphify §M | Phase X follow-up |
| 16 | Don't add Porter stemming to FalkorDB FTS without a benchmark — `getUser` → `getus` likely hurts code retrieval | GitNexus J — comparison | benchmark before adopting |

### Q. What we already do parity-or-better than them

Confirmed during the dive — call out for the README:

- **RRF K=60 hybrid retrieval** — matches GitNexus formula exactly. ✅
- **PageRank prebake** — Aider has it; we have it personalised by REST/Scheduled/EventListener entry points. ✅
- **Live IDE updates** — only Sourcegraph Cody matches us, and that's via continuous SCIP re-index, not real-time PSI. ✅
- **Spring framework semantics** — nobody else has this. ✅
- **Vue cross-stack HITS** — nobody. ✅
- **Persistent graph survives sessions** — Graphify (JSON), GitNexus (LadybugDB), us (FalkorDB / falkordblite). ✅
- **MCP HTTP transport** — only us (others are stdio). ✅ post-Phase W.

## References

- Graphify — https://github.com/safishamsi/graphify, https://graphify.net/
- GitNexus — https://github.com/abhigyanpatwari/GitNexus,
  https://abhigyanpatwari-gitnexus.mintlify.app/advanced/architecture
- DeepWiki dives — `safishamsi/graphify`, `abhigyanpatwari/GitNexus`
- neo4j-graphrag-python — https://github.com/neo4j/neo4j-genai-python
- mcp-neo4j-graphrag — https://github.com/neo4j-field/mcp-neo4j-graphrag
- Graphify pipeline blog (PyShine, 2026-04-20) — 71.5× token claim
- GitNexus paperclipped writeup, ByteIota, hoangyell.com
- DeepWiki second pass — `safishamsi/graphify::serve.py` MCP tool string
  return shapes, `extract.py` `_RATIONALE_PREFIXES` regex, SHA256
  per-file cache layout
- DeepWiki second pass — `abhigyanpatwari/GitNexus` BM25/RRF code,
  `pool-adapter.ts` Map<string, PoolEntry> + setInterval idle reaper
- scip-java — https://sourcegraph.github.io/scip-java/ (Java/Scala/
  Kotlin compiler plugin emitting SemanticDB → SCIP)
- blarify — https://github.com/blarApp/blarify (LSP + SCIP optional,
  Neo4j/FalkorDB, MIT, 223 stars)
- codemem-storage — https://crates.io/crates/codemem-storage
  (tree-sitter + SCIP fusion with additive confidence)
- Sourcegraph context-compare — https://sourcegraph.com/resources/context-compare
- Aider repo-map docs — https://aider.chat/docs/repomap.html
- glincker/stacklit COMPARISON.md — broad survey table
