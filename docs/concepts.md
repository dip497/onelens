# Concepts

The vocabulary OneLens uses. If two readers agree on these terms
they can read the rest of the docs without surprises.

## Graph

A FalkorDB (or Neo4j, or FalkorDBLite) database holding the
structural facts about one project: classes, methods, fields,
Spring beans, REST endpoints, inheritance, call edges. One graph
per project, keyed by `--graph <name>`.

## FQN (Fully Qualified Name)

The canonical identifier for a node.

- Class: `com.example.MyService`
- Method: `com.example.MyService#doWork(java.lang.String)`
- Field: `com.example.MyService#repository`
- Endpoint: `<METHOD>:<path>` — e.g. `PATCH:/vendor/{id}`

Match by `name` when the short form is unambiguous; match by `fqn`
when it isn't.

## External stub

A node representing a library / JDK symbol reached by a resolved
call target but with no source file in the project. Tagged
`external: true`. Used to make "which methods call
`java.util.Map#put`?" answerable without indexing the JDK itself.

## Collector

A single-responsibility Kotlin class inside the plugin that
extracts one slice of PSI data (classes, members, call graph,
inheritance, Spring beans, endpoints, annotations). One pass per
collector; all run inside a single ReadAction.

## Full export vs delta export

- **Full export** — the plugin walks the entire project and emits a
  `~/.onelens/exports/<project>-full-<ts>.json`. Runs on first sync
  and on explicit "Sync Graph" invocations.
- **Delta export** — triggered by VFS file saves (debounced 5 s).
  Writes a `<project>-delta-<ts>.json` that contains only the
  classes in changed files. The CLI auto-detects which is which
  from the JSON header.

## Drawer

A ChromaDB collection entry. Every indexed method, class, and
endpoint is stored as one drawer with a deterministic ID
(`method:<fqn>`, `class:<fqn>`, `endpoint:<method>:<path>:<handler>`)
and a canonical metadata schema (`wing`, `room`, `hall`, `fqn`,
`type`, `importance`, `filed_at`). "Drawer" is borrowed from the
memory-palace metaphor used across the codebase.

## Wing / Room / Hall

Metadata dimensions on a drawer:

- `wing` — graph name (scopes retrieval to one project).
- `room` — Java package.
- `hall` — a fixed constant (reserved for future multi-tenant
  partitioning).

Drift between full-write and delta-write metadata silently breaks
wing-scoped retrieval. See
[LESSONS-LEARNED.md](./LESSONS-LEARNED.md).

## Hybrid retrieve

The `retrieve` command. Three strategies glued together:

1. **Router short-circuit** for queries that look like exact class
   names or FQN fragments → direct Cypher.
2. **RRF (Reciprocal Rank Fusion)** of FTS and semantic results for
   conceptual queries.
3. **PageRank boost** multiplied onto already-matched hits,
   followed by cross-encoder rerank with a 0.02 score threshold to
   filter gibberish.

## PageRank

NetworkX personalized PageRank run at import time. Seeded by
entry points (REST endpoints, `@Scheduled`, `@EventListener`,
`@PostConstruct`). Stored as `Method.pagerank` / `Class.pagerank`.
Used only as a boost on matched hits — never as a ranking source
on its own (doing so leaks central-but-irrelevant methods).

## Impact analysis

The `onelens impact` command. Given a method FQN, walks the call
graph transitively to find every REST endpoint / entry point
reachable. Applies Spring bean-type narrowing to prune polymorphic
fan-out that the caller couldn't actually trigger.

## Auto-sync

A plugin option (on by default) that listens to VFS `.java` saves
and schedules a debounced delta export + import. End-to-end
latency on a save: < 5 s.

## Not concepts

Terms that sound like they belong here but don't:

- **Indexer** — use *collector* (for plugin) or *loader* (for
  Python).
- **Embedding model** — use *embedder* if you must; concretely
  it's Qwen3-Embedding-0.6B.
- **Reranker** — use *cross-encoder*; concretely it's
  mxbai-rerank-base.
