# OneLens

Code knowledge graph for Java/Spring Boot projects. Gives AI 100% type-accurate understanding via IntelliJ PSI, plus semantic search over method bodies.

**IMPORTANT**: Read `docs/LESSONS-LEARNED.md` before making changes. It documents every subtle bug we've already paid for (ReadAction freezes, PSI inherited methods, FalkorDB FTS quirks, ChromaDB metadata schema drift, CLI-rename integration hazards).

## Architecture

Monorepo, three shipped components + one local:

- **`plugin/`** — IntelliJ plugin (Kotlin/Gradle). PSI-based export + auto-sync + skill install action.
- **`python/`** — CLI + graph importer + MCP server (Python). Imports JSON into FalkorDB, embeddings into ChromaDB.
- **`skills/onelens/SKILL.md`** — Claude Code skill for natural-language graph querying. Bundled into the plugin JAR at build time.
- **`python/benchmarks/`** — retrieval quality suite with 64 single-tool cases + 20 multi-step scenarios. **Gitignored** (references local graph names + FQNs).

## How it works

1. IntelliJ plugin collects classes / methods / fields / call graph / inheritance / Spring beans / endpoints via PSI APIs.
2. Exports to `~/.onelens/exports/<project>-full-<ts>.json` or `<project>-delta-<ts>.json`.
3. Plugin invokes Python CLI: `onelens import_graph <json> --graph <name> --context [--clear]`.
4. CLI auto-detects full vs delta from JSON header. Full: `GraphLoader` bulk UNWIND + `CodeMiner.mine` (20-min embedding pass). Delta: `DeltaLoader.apply_delta` + incremental `CodeMiner.mine_upserts` + cascade-delete-by-ID-prefix.
5. Post-import: PageRank prebake writes `Method.pagerank` + `Class.pagerank` properties.
6. AI queries via the `/onelens` skill (Claude Code bash tool) or direct Cypher.

## Key design decisions

- **IntelliJ PSI over tree-sitter**: 100% accurate type resolution. Tree-sitter misses overloads, polymorphism, Spring injection. This is the moat.
- **FalkorDB default**: localhost:3001 browser UI + Cypher. Pluggable via `GraphDB` interface — swap to `falkordblite` (embedded, no Docker) or `neo4j` with one flag.
- **ChromaDB semantic layer**: Qwen3-Embedding-0.6B for method body / javadoc / signature. Mxbai-rerank-base cross-encoder for top-K re-ranking. Optional — install via `pip install onelens[context]`.
- **MCP server = source of truth for the CLI**. `python/src/onelens/mcp_server.py` defines every operation as an `@mcp.tool`. `cli_generated.py` is produced by `fastmcp generate-cli` from that server. Change tools in one place.
- **Plugin bundles the skill**: `skills/onelens/SKILL.md` is copied into the plugin JAR at build (`processResources` in `build.gradle.kts`). `InstallSkillAction` drops it to `~/.claude/skills/onelens/`. No manual copy step.
- **Auto-sync ON by default**: VFS BulkFileListener debounces `.java` saves (5 s), fires `DeltaExportService` → `delta_import`. Toggle via Tools → OneLens.
- **Plugin auto-installs Python**: `PythonEnvManager` creates `~/.onelens/venv/` via `uv` on first sync. Installs `onelens[context]` so semantic retrieval works out of the box.
- **FalkorDB preflight**: `ExportService.syncToGraph` TCP-probes `localhost:17532` before the CLI shell-out; returns a clear message instead of a deep opaque error.
- **Delta-aware embeddings**: `CodeMiner.mine_upserts` re-embeds only changed methods/classes via deterministic IDs (`method:<fqn>`, `class:<fqn>`); `delete_methods_of_classes` cascades by ID prefix so deleted classes purge their method drawers without a metadata schema dependency.
- **PageRank at import**: `importer/pagerank.py` runs NetworkX personalized PageRank seeded by REST endpoints + `@Scheduled` / `@EventListener` / `@PostConstruct`. Scores stored as node properties. Retrieval uses a multiplicative boost on already-matched hits (not as an RRF source — prevents irrelevant but topologically central methods from leaking in).
- **Query router in retrieval**: `hybrid_retrieve` short-circuits to direct Cypher for exact class names / FQN fragments, full RRF+rerank only for conceptual queries. Empty result = real no-match (cross-encoder threshold 0.02 filters gibberish).
- **UNWIND batching**: Import uses Cypher UNWIND for bulk inserts. ~980K edges in ~30 s.

## Building

### Plugin
```bash
cd plugin
./gradlew buildPlugin
# → plugin/build/distributions/onelens-graph-builder-<version>.zip
```

### Python
```bash
cd python
pip install -e ".[context]"
# Or let the plugin auto-install into ~/.onelens/venv on first sync
```

### GitHub Actions
- `.github/workflows/release.yml` — tag `vX.Y.Z` → build plugin + attach ZIP to GitHub Release.
- `.github/workflows/ci.yml` — PR / main push → compile Kotlin + build plugin + Python import + `CodeMiner` API-surface guard + ruff/mypy (advisory).

### Prerequisites
- FalkorDB: `docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest` (or use `--backend falkordblite` for embedded — no Docker)
- IntelliJ IDEA (Community or Ultimate)
- Python 3.10+ and `uv` (or pip)

## Graph schema

Nodes: `Class`, `Method`, `Field`, `SpringBean`, `Endpoint`, `Module`, `Annotation`
Edges: `CALLS`, `EXTENDS`, `IMPLEMENTS`, `HAS_METHOD`, `HAS_FIELD`, `OVERRIDES`, `ANNOTATED_WITH`, `HANDLES`, `INJECTS`

`external` property:
- `true` — library/JDK stubs (auto-created from resolved call targets; no source file)
- `false` — implicit project constructors (PSI didn't export the default ctor)
- unset — normal project code

Derived properties (post-import, from PageRank prebake):
- `Method.pagerank` / `Class.pagerank` — centrality score, higher = more structurally important.

FQN formats:
- Class: `com.example.MyService`
- Method: `com.example.MyService#doWork(java.lang.String)`
- Field: `com.example.MyService#repository`
- Endpoint: `<METHOD>:<path>` (e.g. `PATCH:/vendor/{id}`)

ChromaDB drawer IDs (deterministic):
- `method:<fqn>` / `class:<fqn>` / `endpoint:<METHOD>:<path>:<handler>`
- Metadata schema (unified across full + delta paths): `{wing, room, hall, fqn, type, importance, filed_at}`.
  `wing` = graph name, `room` = package, `hall` = fixed constant. Any drift between full and delta writes silently breaks `wing`-scoped filtering — see LESSONS-LEARNED.

## CLI commands (cyclopts-generated)

```bash
# Core
onelens import-graph <json> --graph <name> --clear --context   # Full import, auto-detects delta vs full
onelens delta-import <delta.json> --graph <name> --context     # Apply a delta export explicitly
onelens stats --graph <name>                                    # Node counts per label
onelens query --cypher "<cypher>" --graph <name>                # Raw Cypher

# Search
onelens search "User*" --node-type class --graph <name>         # FTS with prefix/fuzzy
onelens search "authenticate" --semantic --graph <name>         # ChromaDB semantic only

# Impact analysis (PR review)
onelens impact --method-fqn "<fqn>" --graph <name>              # Which REST endpoints break if this changes?
onelens impact --method-fqn "<fqn>" --precise-only              # Skip polymorphic fan-out
onelens impact --method-fqn "<fqn>" --no-bean-filter            # Disable Spring bean narrowing

# Execution trace
onelens trace --target "/api/users" --entry-type endpoint --depth 3 --graph <name>
onelens trace --target "<method_fqn>" --depth 3 --graph <name>
onelens entry-points --graph <name>

# Retrieval (hybrid FTS + semantic + rerank)
onelens retrieve --query "how password encryption works" --graph <name>

# Daemon (keeps Qwen3 + mxbai warm for semantic tools — optional)
onelens daemon start / stop / status
```

## File layout

```
plugin/src/main/kotlin/com/onelens/plugin/
├── export/
│   ├── ExportService.kt          # Orchestrator (full + delta dispatch, FalkorDB preflight, --context always, --clear full-only)
│   ├── ExportModels.kt
│   ├── ExportState.kt
│   ├── PythonEnvManager.kt       # Auto venv + uv install; installs onelens[context]
│   └── collectors/               # Class, Member, CallGraph, Inheritance, Spring, Module, Annotation
│   └── delta/
│       ├── DeltaTracker.kt       # git diff + VCS change detection
│       └── DeltaExportService.kt # Delta JSON export
├── actions/
│   ├── ExportFullAction.kt       # "Sync Graph" (smart full/delta)
│   └── ToggleAutoSyncAction.kt
├── autosync/
│   ├── AutoSyncService.kt        # Debounced sync on file save (+ dumb-mode retry via triggerSync, not polluting pending files)
│   ├── AutoSyncFileListener.kt
│   └── AutoSyncStartupActivity.kt # Onboarding balloon: Sync now / Install Skill / Later
├── skill/
│   └── InstallSkillAction.kt     # Copies bundled skill to ~/.claude/skills/onelens/
└── settings/
    └── OneLensSettings.kt        # autoSyncEnabled = true (default), autoSyncDebounceMs, firstRunComplete

python/src/onelens/
├── mcp_server.py                 # FastMCP v3 — single source of truth for CLI and MCP agents
├── cli_generated.py              # Auto-generated by `fastmcp generate-cli` (don't edit directly)
├── daemon.py                     # onelens daemon start/stop/status (warm Qwen3 + mxbai)
├── importer/
│   ├── loader.py                 # Full import (UNWIND + context mine + PageRank post-phase)
│   ├── delta_loader.py           # Delta import + context cascade-delete + mine_upserts
│   ├── pagerank.py               # Personalized PageRank at import time
│   └── schema.py                 # FalkorDB node/FTS index DDL (weighted: name=10, javadoc=3, body=1)
├── graph/
│   ├── db.py                     # Abstract GraphDB + factory
│   ├── backends/                 # falkordb, falkordblite, neo4j
│   ├── queries.py                # Pre-built Cypher
│   └── analysis.py               # impact (polymorphic + bean-type filter), trace, endpoint-flow, search
├── context/                      # ChromaDB semantic layer
│   ├── retrieval.py              # hybrid_retrieve: router → FTS+semantic RRF → kind-boost → PageRank boost → cross-encoder rerank → threshold filter
│   ├── searcher.py
│   ├── embedder.py               # Qwen3-Embedding-0.6B
│   └── reranker.py               # mxbai-rerank-base cross-encoder
└── miners/
    └── code_miner.py             # Full mine + mine_upserts + delete_by_ids + delete_methods_of_classes (ID-prefix cascade)

python/benchmarks/                # Local only (gitignored)
├── cases.yaml                    # 64 single-tool cases
├── scenarios.yaml                # 20 multi-step agent scenarios
├── runner.py                     # Single-tool harness
└── scenario_runner.py            # Multi-step harness with variable extraction
```

## Conventions

- Kotlin: IntelliJ Platform conventions, kotlinx.serialization for JSON
- Python: cyclopts (auto-generated CLI), Rich for tables, Pydantic for MCP I/O
- Cypher: match by `name` (short), use `fqn` only when exactness required
- Batch: 1000 nodes / 500 edges per UNWIND
- FalkorDB default port: 17532 (mapped from Docker 6379)
- Before public push: `grep -rIn "<client-name>"` to catch leaked client refs in comments/examples
- Before committing plugin-side changes: run `./gradlew compileKotlin` — the CLI command rename that slipped through once already (`import` → `import_graph`) would have been caught by CI
