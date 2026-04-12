# OneLens

Code knowledge graph for Java/Spring Boot projects. Gives AI 100% accurate understanding of your codebase — call graphs, inheritance, Spring bean wiring, REST endpoints — in one click.

## What it does

OneLens exports your entire project's code intelligence from IntelliJ using PSI APIs (the same engine that powers IntelliJ's own code navigation), then loads it into a graph database for instant querying.

**10K classes, 600K call edges, 2K Spring beans — indexed in 4 minutes, imported in 30 seconds.**

## Quick Start (Linux)

### Prerequisites

- IntelliJ IDEA (Community or Ultimate)
- Docker (for FalkorDB)
- Python 3.10+ and [uv](https://docs.astral.sh/uv/)

### 1. Start FalkorDB

```bash
docker run -d --name falkordb -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
```

Graph browser available at http://localhost:3001

### 2. Build & Install Plugin

```bash
cd plugin
./gradlew buildPlugin
```

Install: IntelliJ → Settings → Plugins → Gear icon → Install from Disk → select `plugin/build/distributions/onelens-graph-builder-0.1.0.zip`

### 3. Sync Graph

In IntelliJ: **Tools → OneLens → Sync Graph**

First time, the plugin will:
1. Export all code intelligence to `~/.onelens/exports/`
2. Auto-create a Python venv at `~/.onelens/venv/` (via uv)
3. Install the `onelens` CLI
4. Import into FalkorDB

Subsequent syncs detect changes and do delta imports (seconds).

### 4. Query & Analyze

```bash
# Search by name (full-text, supports prefix and fuzzy)
~/.onelens/venv/bin/onelens search "User*" --graph my-project
~/.onelens/venv/bin/onelens search "authenticate" --type method --graph my-project

# Which REST endpoints break if I change this method?
~/.onelens/venv/bin/onelens impact "com.example.UserService#updateUser(CallContext,long,UserRest)" --graph my-project

# Trace endpoint execution flow
~/.onelens/venv/bin/onelens trace "/api/users" --type endpoint --depth 3 --graph my-project

# List all entry points (REST endpoints, scheduled jobs)
~/.onelens/venv/bin/onelens entry-points --graph my-project

# Raw Cypher
~/.onelens/venv/bin/onelens query "MATCH (c:Class {name: 'MyService'})-[:HAS_METHOD]->(m) RETURN m.name LIMIT 10" --graph my-project

# Stats
~/.onelens/venv/bin/onelens stats --graph my-project
```

### 5. Use with Claude Code

Copy the skill from `skills/onelens/` to `~/.claude/skills/onelens/` and ask naturally:

- "what calls UserServiceImpl?"
- "blast radius of changing OrderService"
- "which endpoints break if I change FlotoBaseService?"
- "trace the /api/orders endpoint"
- "search for methods related to schedule"

## What gets exported

| Data | Count (real project) | Source |
|------|---------------------|--------|
| Classes, interfaces, enums | 10,299 | `PsiShortNamesCache` |
| Methods with resolved types | 74,557 | `PsiClass.getMethods()` |
| Fields | 58,420 | `PsiClass.getFields()` |
| Call edges (100% accurate) | 605,736 | `PsiMethodCallExpression.resolveMethod()` |
| Inheritance (extends/implements) | 9,839 | `PsiClass.superClass/interfaces` |
| Method overrides | 12,530 | `PsiMethod.findSuperMethods()` |
| Spring beans | 2,335 | `@Service/@Component/@Repository` detection |
| REST endpoints | 2,320 | `@RequestMapping/@GetMapping` etc. |
| Spring injections | 7,854 | `@Autowired` + constructor injection |
| Annotation usages | 68,396 | `PsiModifierList.getAnnotations()` |
| External library stubs | 1,609 classes / 5,403 methods | Auto-created from resolved call targets |

## Architecture

```
┌── IntelliJ IDE ─────────────────────────┐
│  OneLens Plugin (Kotlin)                │
│  ├── 7 Collectors (PSI APIs)            │
│  ├── Menu: Tools → OneLens → Sync       │
│  └── Writes JSON + auto-imports         │
└─────────────────┬───────────────────────┘
                  │ JSON export
┌─────────────────┴───────────────────────┐
│  OneLens CLI (Python)                   │
│  ├── onelens import <json> --graph X    │
│  ├── onelens query "<cypher>" --graph X │
│  └── Pluggable backends (FalkorDB,      │
│      FalkorDBLite, Neo4j)               │
└─────────────────┬───────────────────────┘
                  │ Cypher queries
          ┌───────┴────────┐
          │ FalkorDB       │
          │ + Browser UI   │
          └────────────────┘
```

## Graph DB Backend

Default: FalkorDB (Docker). Pluggable via `--backend` flag:

```bash
onelens import export.json --graph myproject --backend falkordb     # default
onelens import export.json --graph myproject --backend falkordblite  # embedded, no Docker
onelens import export.json --graph myproject --backend neo4j         # Neo4j server
```

## Project Structure

```
onelens/
├── plugin/          # IntelliJ plugin (Kotlin/Gradle)
├── python/          # CLI + graph importer (Python)
├── skills/          # Claude Code skill
├── CLAUDE.md        # Project context for AI
├── LICENSE          # MIT
└── README.md
```

## License

MIT
