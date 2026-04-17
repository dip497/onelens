# Session Start — Warmup

Read this first when opening a new session on OneLens, or when a
new contributor joins. Ten-minute warmup; no need to re-read the
entire design tree.

## What OneLens is, in one sentence

A code knowledge graph for Java/Spring Boot projects — 100%
type-accurate understanding via IntelliJ PSI, plus semantic
search over method bodies and javadoc, served to AI agents via
a Claude Code skill and an MCP server.

## Where we are right now

- **M1 shipping.** End-to-end pipeline works: plugin PSI export →
  Python import → FalkorDB + ChromaDB → retrieval → Claude skill.
- **Auto-sync on by default.** File save triggers a debounced
  delta in < 5 s.
- **95%+ on the internal retrieval benchmark suite** (64 single-
  tool + 20 multi-step scenarios).
- **Going OSS.** Full docs tree, dual MIT/Apache-2.0 licensing,
  CI, tagged release workflow.

## The 2-minute mental model

1. **Graph** — one FalkorDB graph per project, keyed by
   `--graph <name>`. Contains classes, methods, fields, Spring
   beans, REST endpoints, and every call/inherit/override edge.
2. **Drawer** — a ChromaDB entry for a method / class / endpoint,
   with deterministic ID (`method:<fqn>`) and canonical metadata
   schema (`wing, room, hall, fqn, type, importance, filed_at`).
3. **Hybrid retrieve** — router-first: exact name → Cypher; else
   FTS + semantic RRF → kind-boost → PageRank boost →
   cross-encoder rerank → 0.02 threshold.

See [concepts.md](./concepts.md) for the full vocabulary.

## Dependency graph

See [architecture.md](./architecture.md) for the module table and
data flows.

## Locked design decisions

See [DECISIONS.md](./DECISIONS.md) for the full ADR log with
reasoning. Short version:

- Name: `onelens`
- License: **dual MIT OR Apache-2.0**
- Target agents: Claude Code, Codex (MCP-compatible = works
  anywhere)
- Graph backend default: **FalkorDB** (pluggable to FalkorDBLite
  or Neo4j)
- Embedder: **Qwen3-Embedding-0.6B**
- Reranker: **mxbai-rerank-base** (0.02 threshold)
- MCP server = **source of truth for CLI**; don't hand-edit
  `cli_generated.py`

## Dev commands

```
# Python
cd python
pip install -e ".[context]"
ruff format . && ruff check .
pytest -q              # if tests present
mypy src/onelens       # advisory

# Plugin
cd plugin
./gradlew compileKotlin
./gradlew buildPlugin

# End-to-end smoke
docker run -d --name falkordb -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
onelens import-graph <json> --graph myproj --context --clear
onelens stats --graph myproj
```

## Before touching anything

**Read [LESSONS-LEARNED.md](./LESSONS-LEARNED.md)** if your change
touches:

- graph import / delta / FalkorDB FTS
- ChromaDB metadata or drawer IDs
- retrieval routing, PageRank boost, or reranker threshold
- plugin ↔ CLI subprocess contract

Every lesson in that file is a bug that cost us hours.

## How to act in a new session

1. Check the task list.
2. Pick an in-progress task or the next pending one.
3. Read only the relevant doc(s) — not all of them.
4. Delegate research-heavy work to the `spec-writer` subagent.
5. Delegate architecture review to `architecture-guardian` before
   merging any cross-module change.
6. If a decision is non-trivial, log it in
   [DECISIONS.md](./DECISIONS.md).

## How to communicate

Match the project lead's tone. Keep technical substance exact.
