# Philosophy

Design principles for OneLens. When a decision is ambiguous,
consult this document first.

## 1. Accuracy before breadth

PSI-grade correctness on Java beats tree-sitter-grade coverage on
ten languages. The value proposition is "the AI sees what
IntelliJ sees." Compromising that to add another language early
would kill the reason anyone reaches for OneLens.

## 2. Silence is a bug

Overwrites, clobbers, unreported errors, silent schema drift — all
of these are bugs. `docs/LESSONS-LEARNED.md` is proof of what
silent drift cost us already. Every new write path must preserve
schema; every error path must surface a readable message.

## 3. One source of truth per concern

- The **MCP server** is the source of truth for CLI commands. The
  CLI is generated, not hand-maintained.
- The **collectors** are the source of truth for graph facts. The
  importer consumes what they emit; it does not infer.
- The **JSON export** is the wire format between plugin and CLI.
  Both sides validate against the same schema.

When two code paths write the same data, they converge on one
schema (the ChromaDB metadata episode).

## 4. Distribution > spec

Where a standard exists, we consume it: MCP, Cypher, ChromaDB,
sentence-transformers, cross-encoders, NetworkX PageRank,
cyclopts. OneLens adds the glue, not new primitives.

## 5. Zero-friction install

The plugin auto-installs the Python venv, auto-probes FalkorDB,
auto-syncs on save, and ships the Claude skill bundled. A user
who clicks "Install plugin" and "Sync Graph" has done everything.
Manual steps are the enemy of adoption.

## 6. Open seams, closed opinions

Graph backend is pluggable (FalkorDB / FalkorDBLite / Neo4j), but
default is FalkorDB. Embedder is pluggable, but default is
Qwen3-Embedding-0.6B. The first release ships one opinionated
path through each seam; extensibility never delays shipping.

## 7. Privacy first

Zero telemetry. Everything runs locally: IntelliJ PSI, FalkorDB,
ChromaDB, embedding models. An air-gapped Spring Boot shop should
be able to use OneLens without punching a hole.

## 8. PageRank is a boost, not a source

A method being central doesn't make it relevant to the query. We
use PageRank to rank among already-matched candidates, not to
pick candidates. Every time we've violated this, irrelevant-but-
famous methods leaked into results.

## 9. Benchmark everything that retrieves

Retrieval quality is the product. We track single-tool accuracy
on 64 curated cases and multi-step accuracy on 20 scenarios.
Every change to `retrieval.py`, FTS weights, or reranker
thresholds gets measured before it merges.

## 10. Respect the cost of delta correctness

Delta imports must preserve the invariants of full imports.
Deterministic drawer IDs, ID-prefix cascade deletes, unified
metadata schema — none of these are optional. `docs/LESSONS-LEARNED.md`
is the permanent memorial to the tests we skipped.

## 11. Be honest about limits

We do not yet do Kotlin perfectly. We do not yet do cross-repo
stitching. We do not yet do incremental PageRank. These are
written plainly in the roadmap — not buried in an issue tracker.

## 12. Ship small, ship often

Every tagged release has a CHANGELOG entry, passes CI, and ships
the plugin ZIP as a GitHub release artifact. No other release
theatre.
