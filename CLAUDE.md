# OneLens

Code knowledge graph for Java/Spring Boot projects. Helps AI understand codebases.

**IMPORTANT**: Read `docs/LESSONS-LEARNED.md` before making changes. It documents what was tried, what failed, and critical pitfalls (ReadAction freezes, PSI inherited methods, FalkorDB quirks, etc.).

## Architecture

Two components in a monorepo:

- **`plugin/`** — IntelliJ plugin (Kotlin/Gradle). Exports code intelligence to JSON using PSI APIs.
- **`python/`** — CLI + graph DB importer (Python). Imports JSON into FalkorDB, exposes query tools.
- **`skills/`** — Claude Code skill for querying the graph with natural language.

## How it works

1. IntelliJ plugin collects classes, methods, fields, call graph, inheritance, Spring beans/endpoints via PSI APIs
2. Exports to `~/.onelens/exports/<project>-full-<timestamp>.json`
3. Python CLI imports JSON into FalkorDB using batch UNWIND queries
4. AI queries the graph via the `/onelens` skill or CLI

## Key design decisions

- **IntelliJ PSI over tree-sitter**: PSI gives 100% accurate type resolution. Tree-sitter can't resolve overloads, polymorphism, or Spring injection.
- **FalkorDB over embedded DB**: FalkorDB gives visual browser (localhost:3001) + Cypher queries. KuzuDB was considered but is now archived.
- **Pluggable backends**: `python/src/onelens/graph/db.py` defines abstract `GraphDB` interface. Backends in `graph/backends/` — swap FalkorDB for Neo4j with one flag.
- **Plugin auto-installs Python**: `PythonEnvManager.kt` creates `~/.onelens/venv/` via `uv` on first use. No manual pip install.
- **Small ReadAction blocks**: Each class processed in its own ReadAction to avoid IDE freezes. Call graph uses parallel threads (half CPU cores).
- **UNWIND batching**: Import uses Cypher UNWIND for batch inserts. 980K edges in 30 seconds.
- **Smart sync**: Plugin detects changes via git diff + VCS ChangeListManager. Full export on first run, delta on subsequent runs.

## Building

### Plugin
```bash
cd plugin
./gradlew buildPlugin
# Output: plugin/build/distributions/onelens-graph-builder-0.1.0.zip
# Install: IntelliJ → Settings → Plugins → Install from Disk
```

### Python
```bash
cd python
pip install -e .
# Or the plugin auto-installs into ~/.onelens/venv/ on first sync
```

### Prerequisites
- FalkorDB running: `docker run -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest`
- IntelliJ IDEA with Java project open
- Python 3.10+ and `uv` (or pip)

## Graph schema

Nodes: Class, Method, Field, SpringBean, Endpoint, Module, Annotation
Edges: CALLS, EXTENDS, IMPLEMENTS, HAS_METHOD, HAS_FIELD, OVERRIDES, ANNOTATED_WITH, HANDLES, INJECTS

Class and Method nodes have an `external` property:
- `external: true` — library/JDK stubs (auto-created from resolved call targets, no source file)
- `external: false` — implicit project constructors (class exists but default constructor wasn't exported by PSI)
- unset — normal project code

FQN formats:
- Class: `com.example.MyService`
- Method: `com.example.MyService#doWork(java.lang.String)`
- Field: `com.example.MyService#repository`

## Testing queries

```bash
onelens query "MATCH (c:Class) RETURN c.name, c.kind LIMIT 10" --graph <name>
onelens stats --graph <name>
```

## File layout

```
plugin/src/main/kotlin/com/onelens/plugin/
├── export/
│   ├── ExportService.kt          # Orchestrator with progress indicator
│   ├── ExportModels.kt           # JSON data classes (@Serializable)
│   ├── ExportState.kt            # Persisted per-project state
│   ├── PythonEnvManager.kt       # Auto venv + uv install
│   ├── collectors/
│   │   ├── ClassCollector.kt     # PsiShortNamesCache → all classes
│   │   ├── MemberCollector.kt    # PsiClass.methods/fields
│   │   ├── CallGraphCollector.kt # PsiMethodCallExpression.resolveMethod() — parallel
│   │   ├── InheritanceCollector.kt # extends/implements/overrides
│   │   ├── SpringCollector.kt    # @Service/@Controller beans + endpoints
│   │   ├── ModuleCollector.kt    # Maven/Gradle modules
│   │   └── AnnotationCollector.kt
│   └── delta/
│       ├── DeltaTracker.kt       # git diff + VCS change detection
│       └── DeltaExportService.kt # Delta JSON export
├── actions/
│   └── ExportFullAction.kt       # "Sync Graph" menu action (smart full/delta)
└── settings/
    └── OneLensSettings.kt

python/src/onelens/
├── cli.py                         # Click CLI (import, query, stats, serve)
├── importer/
│   ├── loader.py                  # UNWIND batch import with rich progress
│   ├── delta_loader.py            # Delta import (delete + upsert)
│   └── schema.py                  # FalkorDB index definitions
├── graph/
│   ├── db.py                      # Abstract GraphDB interface + factory
│   ├── backends/                  # Pluggable: falkordb, falkordblite, neo4j
│   ├── queries.py                 # Pre-built Cypher for impact analysis
│   └── analysis.py                # Blast radius, caller/callee traversal
└── mcp/
    └── server.py                  # FastMCP server for AI tools
```

## Conventions

- Kotlin: IntelliJ Platform conventions, kotlinx.serialization for JSON
- Python: Click for CLI, Rich for progress/tables, Pydantic for models
- Cypher: match by `name` (short), use `fqn` only when needed
- Batch size: 1000 nodes, 500 edges per UNWIND
- FalkorDB default port: 17532 (mapped from Docker 6379)
