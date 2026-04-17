# OneLens

Code knowledge graph for Java/Spring Boot projects. Gives AI 100% type-accurate understanding of your codebase — call graphs, inheritance, Spring bean wiring, REST endpoints — plus semantic search over method bodies and javadoc.

## What it does

OneLens exports your project's code intelligence from IntelliJ using PSI APIs (the same engine that powers IntelliJ's own code navigation), loads it into a graph database (FalkorDB), and embeds method bodies + classes into ChromaDB for semantic retrieval.

**Real numbers on a 10K-class Spring Boot monolith:**
- 74K methods, 605K call edges, 2.3K Spring beans, 2.3K REST endpoints
- Full export: ~4 minutes • Graph import: ~30 s • Embedding pass: ~20 min
- Delta re-sync (single file save): < 5 s end-to-end

## Quick Start

### Prerequisites

- IntelliJ IDEA (Community or Ultimate)
- Docker (for FalkorDB — or use `--backend falkordblite` for embedded)
- [uv](https://docs.astral.sh/uv/) — plugin auto-installs the Python env on first sync

### 1. Start FalkorDB

```bash
docker run -d --name falkordb -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
```

Graph browser: http://localhost:3001

### 2. Install the plugin

Download `onelens-graph-builder-0.1.0.zip` from the [latest release](../../releases), then:

IntelliJ → **Settings → Plugins → Gear → Install from Disk** → select the zip.

Or build from source:

```bash
cd plugin
./gradlew buildPlugin
# → plugin/build/distributions/onelens-graph-builder-0.1.0.zip
```

### 3. First sync

The plugin auto-runs on first open and shows a balloon with:

- **Sync Now** — export + import (creates `~/.onelens/venv/` via uv, installs `onelens[context]`, runs full import with embeddings + PageRank)
- **Install Skill** — drops `~/.claude/skills/onelens/SKILL.md` so Claude Code can query the graph in natural language
- **Later**

After the first full sync, **auto-sync is on by default**: every `.java` save triggers a debounced delta export (5 s) that incrementally updates the graph *and* re-embeds changed methods/classes. Toggle via **Tools → OneLens → Auto-sync**.

### 4. Query with Claude Code

Install the skill (via the balloon or **Tools → OneLens → Install Skill**), then ask naturally:

- "what calls UserServiceImpl?"
- "blast radius of changing OrderService"
- "which endpoints break if I change PaymentService?"
- "trace the /api/orders endpoint"
- "how does password encryption work in this codebase?" *(semantic)*

The skill lives at `skills/onelens/SKILL.md` — bundled inside the plugin jar, so no manual copy step.

### 5. Or use the CLI directly

```bash
onelens=~/.onelens/venv/bin/onelens

# Structural search (FTS, weighted: name > javadoc > body)
$onelens search "User*" --node-type class --graph my-project
$onelens search "authenticate" --node-type method --graph my-project

# Semantic search (ChromaDB + cross-encoder rerank)
$onelens search "password hashing" --semantic --graph my-project

# Hybrid retrieval (FTS + semantic RRF + PageRank boost + rerank threshold)
$onelens retrieve --query "how password encryption works" --graph my-project

# Impact analysis — which REST endpoints break if a method changes?
$onelens impact --method-fqn "com.example.UserService#updateUser(long,UserRest)" --graph my-project

# Execution trace
$onelens trace --target "/api/users" --entry-type endpoint --depth 3 --graph my-project
$onelens trace --target "com.example.UserService#updateUser(long,UserRest)" --depth 3 --graph my-project

# Entry points (REST + @Scheduled + @EventListener + @PostConstruct)
$onelens entry-points --graph my-project

# Raw Cypher
$onelens query --cypher "MATCH (c:Class {name:'MyService'})-[:HAS_METHOD]->(m) RETURN m.name LIMIT 10" --graph my-project

# Stats
$onelens stats --graph my-project
```

## MCP server mode

The CLI is generated from a FastMCP server — the same operations are available to MCP-aware agents:

```bash
$onelens mcp-server  # stdio transport; wire into your MCP-compatible client
```

## Daemon (optional, speeds up semantic queries)

Keeps Qwen3-Embedding-0.6B and mxbai-rerank-base warm in memory across CLI invocations:

```bash
$onelens daemon start
$onelens daemon status
$onelens daemon stop
```

## What gets captured

| Data | Source |
|------|--------|
| Classes, interfaces, enums | `PsiShortNamesCache` |
| Methods with resolved parameter + return types | `PsiClass.getMethods()` |
| Fields | `PsiClass.getFields()` |
| Call edges (type-accurate, including overloads) | `PsiMethodCallExpression.resolveMethod()` |
| Inheritance (extends/implements) | `PsiClass.superClass/interfaces` |
| Method overrides | `PsiMethod.findSuperMethods()` |
| Spring beans | `@Service/@Component/@Repository` detection |
| REST endpoints | `@RequestMapping/@GetMapping` etc. |
| Spring injections | `@Autowired` + constructor injection |
| Annotation usages | `PsiModifierList.getAnnotations()` |
| External library stubs | Auto-created from resolved call targets |
| Method body + javadoc embeddings | Qwen3-Embedding-0.6B → ChromaDB |
| PageRank (personalized, seeded by entry points) | NetworkX, stored as node property |

## Why IntelliJ PSI over tree-sitter?

Tree-sitter can't resolve `service.doThing()` to the *correct* overload across `ServiceImpl`, `ServiceBase`, and an injected `@Qualifier`-tagged bean. PSI can — it's the same engine driving IntelliJ's Go-to-Definition. For a Spring app, that accuracy is the moat.

## Graph schema

Nodes: `Class`, `Method`, `Field`, `SpringBean`, `Endpoint`, `Module`, `Annotation`
Edges: `CALLS`, `EXTENDS`, `IMPLEMENTS`, `HAS_METHOD`, `HAS_FIELD`, `OVERRIDES`, `ANNOTATED_WITH`, `HANDLES`, `INJECTS`

FQN formats:
- Class: `com.example.MyService`
- Method: `com.example.MyService#doWork(java.lang.String)`
- Endpoint: `<METHOD>:<path>` (e.g. `PATCH:/vendor/{id}`)

Derived properties (written at import by PageRank prebake):
- `Method.pagerank`, `Class.pagerank` — centrality score, higher = more structurally important. Used as a multiplicative boost on hybrid retrieval hits.

## Architecture

```
┌── IntelliJ IDE ──────────────────────────────────────┐
│  OneLens Plugin (Kotlin)                             │
│  ├── Collectors (PSI APIs)                           │
│  ├── Tools → OneLens → Sync / Install Skill / Toggle │
│  ├── VFS listener → debounced delta export (5 s)     │
│  └── Shells out to onelens CLI                       │
└────────────────────────┬─────────────────────────────┘
                         │ JSON (full or delta)
┌────────────────────────┴─────────────────────────────┐
│  onelens CLI (Python, cyclopts-generated)            │
│  ├── import-graph — auto-detects full vs delta       │
│  ├── retrieve / impact / trace / search / query      │
│  ├── daemon — warm Qwen3 + mxbai                     │
│  └── mcp-server — same ops via MCP stdio             │
└───────────┬──────────────────────────┬───────────────┘
            │                          │
    ┌───────┴────────┐         ┌───────┴────────────┐
    │ FalkorDB       │         │ ChromaDB           │
    │ Cypher + FTS   │         │ Qwen3 embeddings   │
    │ + browser UI   │         │ + mxbai rerank     │
    └────────────────┘         └────────────────────┘
```

## Graph DB backends

Default: FalkorDB (Docker). Swap with `--backend`:

```bash
onelens import-graph export.json --graph myproject --backend falkordb      # default
onelens import-graph export.json --graph myproject --backend falkordblite  # embedded
onelens import-graph export.json --graph myproject --backend neo4j         # Neo4j server
```

## Delta-aware embeddings

Deterministic drawer IDs (`method:<fqn>`, `class:<fqn>`) make delta re-embedding idempotent. On delete, method drawers cascade via ID-prefix scan so removed classes purge cleanly without depending on metadata filters (which are fragile across schema migrations).

## Project layout

```
onelens/
├── plugin/          # IntelliJ plugin (Kotlin/Gradle)
├── python/          # CLI + importer + miners + MCP server
├── skills/onelens/  # Claude Code skill (bundled into plugin jar)
├── docs/
│   ├── LESSONS-LEARNED.md
│   └── VISION-AND-ROADMAP.md
├── .github/workflows/  # CI + tagged-release plugin build
├── CLAUDE.md        # Project context for AI
└── LICENSE          # MIT
```

## Contributing

- Before PR: `cd plugin && ./gradlew compileKotlin buildPlugin`
- Python: `cd python && pip install -e ".[context]"`; `ruff check .` and `mypy src/onelens` (advisory)
- CI runs Kotlin compile + plugin build + Python import check on every PR

## License

MIT
