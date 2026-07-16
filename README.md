# OneLens

Code knowledge graph for Java/Spring Boot backends **and Vue 3 frontends**. Gives AI 100% type-accurate understanding of your codebase — call graphs, inheritance, Spring bean wiring, REST endpoints, Vue components, Pinia stores, composables, routes, API calls — plus cross-stack traversal via `HITS` edges that link a Vue `ApiCall` to the Spring `Endpoint` it dispatches to.

**Built for AI agents (Claude Code, Cursor, MCP clients).** Two simple tools — `search` and `query` — plus a detailed skill that teaches the agent how to navigate your codebase.

## What it does

OneLens exports your project's code intelligence from IntelliJ using PSI APIs (the same engine that powers IntelliJ's Go-to-Definition), loads it into a graph database (FalkorDB), and makes it queryable via MCP.

**Real numbers on a 10K-class Spring Boot monolith + 7K-file Vue 3 frontend:**
- 81K methods, 678K call edges, 2.8K Spring beans, 2.3K REST endpoints
- 2.5K Vue components, 65 Pinia stores, 1.5K API calls
- Full export: ~4 min • Graph import: ~25 s • Delta re-sync: ~30 s

---

## Three ways to use OneLens

### Way 1: Claude Code + MCP (recommended)

Best for: AI-powered development with Claude Code.

```bash
# 1. Install OneLens
pip install onelens

# 2. Build the IntelliJ plugin (for headless export)
cd plugin && ./gradlew buildPlugin

# 3. Export your project (headless, no IDE needed)
./gradlew headlessExport -PonelensProject=/path/to/your/project

# 4. Import into the graph
onelens call-tool onelens_init \
  --export-path ~/.onelens/exports/myproject-full-*.json \
  --graph myproject

# 5. Configure Claude Code MCP
# Add to ~/.claude/settings.json:
#   "mcpServers": { "onelens": { "command": "onelens", "args": ["mcp-server"] } }

# 6. Install the OneLens skill
cp -r skills/onelens ~/.agents/skills/

# Now ask Claude Code:
#   "what calls UserServiceImpl?"
#   "blast radius of changing OrderService"
#   "trace the /api/orders endpoint"
#   "which Vue components call /api/users?"
```

### Way 2: IntelliJ plugin (IDE users)

Best for: Live development with auto-sync on every save.

1. Start FalkorDB: `docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest`
2. Install plugin: Download `onelens-graph-builder-*.zip` → IntelliJ → Settings → Plugins → Install from Disk
3. Open your project → Tools → OneLens → Sync Graph
4. Auto-sync runs on every `.java` save (5s debounce, incremental delta)
5. Install Skill: Tools → OneLens → Install Skill → ask Claude Code naturally

Or build from source:
```bash
cd plugin && ./gradlew buildPlugin
# → plugin/build/distributions/onelens-graph-builder-*.zip
```

### Way 3: Headless / CI (no IDE)

Best for: CI pipelines, Docker, reproducible builds, no-IDE servers.

```bash
cd plugin

# Full export (cold: ~5 min, warm: ~3 min)
./gradlew headlessExport -PonelensProject=/path/to/project -PonelensOutput=/tmp/exports

# Delta export (only changed files: ~30 s)
ONELENS_DELTA=true ./gradlew headlessExport -PonelensProject=/path/to/project -PonelensOutput=/tmp/exports

# Import into graph
onelens call-tool onelens_import --export-path /tmp/exports/myproject-*.json --graph myproject
```

See [`docs/headless.md`](./docs/headless.md) for delta, auto-sync (watchexec), and multi-project docs.

---

## The two tools

OneLens exposes **2 query tools** via MCP. The skill teaches the agent when to use each.

### `onelens_search` — find code by name or content

Full-text search (RediSearch syntax) across all node types. Fuzzy, prefix, phrase, union.

```bash
onelens call-tool onelens_search --query "auth*" --graph myproject
onelens call-tool onelens_search --query "password encryption" --graph myproject
onelens call-tool onelens_search --query "ticket*" --node-type component --graph myproject
```

Syntax: `auth*` (prefix), `%passwor%` (fuzzy), `login|signin` (union), `"exact phrase"`.

### `onelens_query` — graph traversal (Cypher)

Impact analysis, execution traces, dependency chains, dead code, cross-stack.

```bash
# Impact: what breaks if I change UserService?
onelens call-tool onelens_query --cypher \
  "MATCH (caller:Method)-[:CALLS]->(t:Method)
   WHERE t.classFqn CONTAINS 'UserService'
   RETURN DISTINCT caller.classFqn LIMIT 50" --graph myproject

# Cross-stack: Vue → Spring endpoint mapping
onelens call-tool onelens_query --cypher \
  "MATCH (c:Component)-[:CALLS_API]->(a:ApiCall)-[:HITS]->(e:Endpoint)
   RETURN c.name, e.path LIMIT 50" --graph myproject
```

The [SKILL.md](./skills/onelens/SKILL.md) contains 10+ copy-paste Cypher recipes for impact, trace, dead code, inheritance, bean wiring, and more.

---

## What gets captured

| Data | Source |
|------|--------|
| Classes, interfaces, enums, records | `PsiShortNamesCache` |
| Methods (resolved param + return types) | `PsiClass.getMethods()` |
| Call edges (100% type-accurate, overloads resolved) | `PsiMethodCallExpression.resolveMethod()` |
| Data-flow (field read/write, instantiation) | `PsiReferenceExpression.resolve()` |
| Inheritance, overrides, implements | `PsiClass.superClass/interfaces` |
| Spring beans, endpoints, injections, auto-config | `@Service`/`@RestController` + Spring plugin |
| JPA entities, repositories, columns | `@Entity`/`JpaRepository` detection |
| Vue 3 components (SFC `<script setup>`) | Vue PSI + JS PSI extraction |
| Pinia stores, composables, routes, API calls | JS PSI patterns |
| Vue → Spring cross-stack links | `HITS` bridge (normalized HTTP path matching) |
| Annotation usages | `PsiModifierList.getAnnotations()` |
| External library stubs | Auto-created from resolved call targets |
| Test file tagging (`isTest`) | `__tests__/`, `*.test.js`, `*.spec.js` |
| Method body + javadoc (for semantic search) | Jina-v2-base-code → ChromaDB (optional) |

---

## Architecture

```
┌── Export (IntelliJ PSI, headless or IDE) ──────────────────┐
│  OneLens Plugin (Kotlin)                                   │
│  ├── SpringBootAdapter → Class/Method/CallGraph/Spring/JPA │
│  ├── Vue3Adapter → Component/Store/Composable/Route/ApiCall│
│  └── FrameworkAdapter SPI (extensible — add your own)      │
└──────────────────────┬──────────────────────────────────────┘
                       │ JSON (full or delta)
┌──────────────────────▼──────────────────────────────────────┐
│  onelens MCP server (Python, FastMCP)                      │
│  ├── onelens_search — FTS (RediSearch, fuzzy/prefix)       │
│  ├── onelens_query — Cypher (impact, trace, cross-stack)   │
│  └── onelens_status — wake-up, graph health                │
└───────────┬──────────────────────────┬──────────────────────┘
            │                          │
    ┌───────▼────────┐         ┌───────▼────────────┐
    │ FalkorDB       │         │ ChromaDB (optional)│
    │ Cypher + FTS   │         │ Jina-v2 embeddings │
    │ + browser UI   │         │ (semantic search)  │
    └────────────────┘         └────────────────────┘
```

**Default: falkordblite** (embedded, no Docker). Optional: FalkorDB Docker (with browser UI at `localhost:3001`).

---

## Adding new languages / frameworks

OneLens is designed to be extensible via the **FrameworkAdapter SPI**. Each
language/framework lives in its own adapter and contributes:

1. **Detection** (`detect(project)`) — is this project my framework?
2. **Collectors** (`collectors()`) — what nodes/edges do I extract?
3. **JSON key** — where do my nodes appear in the export document?

### Currently supported

| Framework | Adapter | Node types | Status |
|-----------|---------|-----------|--------|
| Java / Spring Boot | `SpringBootAdapter` | Class, Method, Field, Endpoint, SpringBean, JpaEntity, TestCase | ✅ Production |
| Vue 3 / Pinia | `Vue3Adapter` | Component, Store, Composable, Route, ApiCall, JsFunction, JsModule | ✅ Production |

### How to add a new framework (e.g., Python/FastAPI, Go, Rust, Next.js)

1. **Create the adapter** in `plugin/src/main/kotlin/.../framework/<name>/`:
   ```kotlin
   class FastApiAdapter : FrameworkAdapter {
       override val id = "fastapi"
       override val jsonKey = "fastapi"
       override fun detect(project: Project): Boolean {
           // Check for requirements.txt with fastapi, or pyproject.toml
       }
       override fun collectors(): List<Collector> = listOf(FastApiCollector())
   }
   ```

2. **Register in plugin.xml**:
   ```xml
   <depends optional="true" config-file="framework-fastapi.xml">com.intellij.modules.python</depends>
   ```

3. **Add the PSI plugin** to `platformBundledPlugins` in `gradle.properties`:
   ```
   platformBundledPlugins = ...,PythonCore
   ```

4. **Write collectors** — use the target language's PSI APIs (Python PSI, Go PSI, etc.) to extract:
   - Functions/methods with resolved types
   - Call edges (function calls → resolved targets)
   - Framework-specific data (FastAPI routes, Go interfaces, etc.)

5. **Update the importer** (`python/src/onelens/importer/loader.py`) — add a `_load_<framework>()` method that reads your JSON section and creates graph nodes with the correct `wing` stamp.

6. **Update the skill** — add your framework's node types and edges to `skills/onelens/SKILL.md`.

The export/import pipeline is **language-agnostic** — the JSON schema, FalkorDB import, FTS indexing, and search/query tools work for any node types. The adapter just fills in the nodes/edges; everything else is shared infrastructure.

**Key principle**: OneLens uses IntelliJ PSI for 100% type accuracy. To support a new language, IntelliJ must have a PSI plugin for that language (Java, Kotlin, Python, JavaScript, TypeScript, Go, Rust, PHP, Ruby — all have official JetBrains PSI plugins). Languages without a JetBrains plugin can't achieve the same accuracy.

---

## Multi-project workspaces

Link multiple projects (backend + frontend, or backend + plugin repos) into a single graph via `onelens.workspace.yaml`:

```yaml
version: 1
name: myapp
graph: myapp
roots:
  - path: .                    # primary backend
    buildTool: maven
  - path: ../my-frontend       # Vue 3 frontend
    buildTool: npm
policies:
  duplicateFqn: merge
```

For cross-stack linking (Vue → Spring), import each project into the **same graph** — the `HITS` bridge automatically links Vue `ApiCall` nodes to Spring `Endpoint` nodes by normalized HTTP path.

---

## Graph DB backends

```bash
# Default: embedded (no Docker)
onelens call-tool onelens_import --export-path export.json --graph myproject --backend falkordblite

# Docker FalkorDB (with browser UI at localhost:3001)
docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
onelens call-tool onelens_import --export-path export.json --graph myproject --backend falkordb

# Neo4j (for enterprise)
onelens call-tool onelens_import --export-path export.json --graph myproject --backend neo4j
```

---

## Embeddings (optional semantic search)

OneLens uses [jina-embeddings-v2-base-code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code) (161M params, code-trained, ~320MB) for semantic search. This is **optional** — the FTS search works great without it.

```bash
# Import with embeddings (first run downloads model + embeds ~80K methods)
ONELENS_EMBED_BACKEND=local onelens call-tool onelens_import \
  --export-path export.json --graph myproject --context

# Profiles: balanced (default, code-tuned), gemma (300M, MTEB #1), tiny (130MB, CPU-fast)
export ONELENS_LOCAL_EMBED_PROFILE=balanced  # or: gemma, tiny
```

---

## Why IntelliJ PSI over tree-sitter?

Tree-sitter can't resolve `service.doThing()` to the *correct* overload across `ServiceImpl`, `ServiceBase`, and an injected `@Qualifier`-tagged bean. PSI can — it runs the same type resolution engine as IntelliJ's Go-to-Definition. For a Spring Boot app, that accuracy is the moat: **100% type-accurate call graphs** vs tree-sitter's ~50% accuracy.

---

## Project layout

```
onelens/
├── plugin/              # IntelliJ plugin (Kotlin/Gradle)
│   └── src/main/kotlin/com/onelens/plugin/
│       ├── export/collectors/   # Java collectors (Class, Method, CallGraph, ...)
│       ├── framework/           # FrameworkAdapter SPI
│       │   ├── springboot/      # Spring Boot adapter
│       │   └── vue3/            # Vue 3 adapter
│       └── headless/            # Headless export + delta + state management
├── python/              # MCP server + importer + CLI
│   └── src/onelens/
│       ├── mcp_server.py        # FastMCP server (2 tools + status)
│       ├── importer/            # FalkorDB loader + delta loader
│       └── context/             # Embeddings (Jina/bge) + ChromaDB
├── skills/onelens/      # Claude Code skill (SKILL.md + references/)
├── install.sh           # One-liner installer
├── docs/
│   ├── headless.md              # Headless export + delta + multi-project guide
│   └── LESSONS-LEARNED.md       # Production failure catalog
└── LICENSE              # MIT OR Apache-2.0
```

## Contributing

- **Plugin**: `cd plugin && ./gradlew compileKotlin buildPlugin`
- **Python**: `cd python && pip install -e ".[context]"`; `ruff check .`
- **Adding a framework**: see "Adding new languages" above
- **Skill**: edit `skills/onelens/SKILL.md`, copy to `~/.agents/skills/onelens/`

## License

Dual MIT OR Apache-2.0 at the user's option.
