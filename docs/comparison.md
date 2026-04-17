# Comparison with related projects

OneLens interoperates with more projects than it competes with.
This document is an honest map of the landscape as of 2026.

## Standards we consume

| Project | What it defines | Our posture |
|---------|-----------------|-------------|
| **Model Context Protocol (MCP)** | Agent ↔ tool stdio protocol | **Consumes.** MCP server is our single source of truth. |
| **Cypher** | Graph query language | **Consumes.** Used verbatim against FalkorDB / Neo4j. |
| **ChromaDB** | Embedded vector store | **Consumes.** Storage for method + class embeddings. |
| **Keep a Changelog 1.1 / SemVer** | Release conventions | **Consumes.** |

## Adjacent tools (complementary)

| Project | What it ships | Relationship |
|---------|---------------|--------------|
| **IntelliJ IDEA** | IDE + PSI | **Depends on.** We borrow the PSI engine; we do not replace IntelliJ. |
| **FalkorDB / Neo4j** | Graph database | **Pluggable dependency.** |
| **Qwen3-Embedding-0.6B** | Sentence embedding model | **Pluggable dependency.** |
| **mxbai-rerank-base** | Cross-encoder | **Pluggable dependency.** |
| **Claude Code / Codex / Cursor** | AI coding agents | **Clients.** Skill + MCP surface targets them. |

## Nearest neighbours

### Tree-sitter-based code indexers (Sourcegraph Cody, Aider repo-map, bloop, Continue.dev codebase retrieval)

Good at: fast, polyglot, works on any repo with no IDE needed.

Bad at: *Spring monoliths*. Tree-sitter cannot resolve
`service.doThing()` when `doThing` is overloaded across
`ServiceImpl`, `ServiceBase`, and an `@Qualifier`-tagged bean.
Call graphs it produces contain false positives (lexical name
matches across unrelated classes) and false negatives (interface
dispatch it can't follow). For a 10K-class Spring Boot codebase,
this is the difference between "correct blast radius" and "grep
hits."

OneLens spends the PSI cost once at sync time to buy accuracy at
query time.

### Joern / CodeQL / Semmle-style semantic analysers

Good at: security queries, precise data-flow, cross-language.

Bad at: *setup cost and interactive latency*. Both are heavy to
run on every save; CodeQL databases are measured in gigabytes.
They're the right tool for nightly CI security scans, not for
"what does Claude need to know right now?"

OneLens sits in the interactive niche: ~30 s full import, < 5 s
delta, all at desk.

### GitNexus, code-review-graph, Potpie (Python-backed PSI-less graph builders)

Good at: multi-language, no IDE dependency.

Bad at: *the same problem as tree-sitter, for the same reason*.
Without a real compiler front-end, Spring DI and overload
resolution are guesswork. We verified this by reading their code,
not their READMEs.

### LightRAG / GraphRAG / general LLM-over-code RAG

Good at: natural-language Q&A on text-heavy corpora.

Bad at: *structural queries with zero tolerance for hallucination*.
"Which endpoints call this method?" must be deterministic.
OneLens uses semantic search only where semantics are the point
(conceptual queries); structural queries short-circuit to Cypher.

## When you should NOT use OneLens

- **Your codebase is not Spring Boot / Java-centric.** Today, the
  collectors are Java-focused. Kotlin mostly works; other languages
  don't.
- **You need cross-repo, cross-language graphs now.** M3 goal, not
  M1.
- **You want a zero-config cloud service.** OneLens runs local and
  stays local by design.
- **Your AI usage is one-off queries in a chat window**, not agent
  workflows. The value compounds with agents; for a human typing
  into ChatGPT, grep + IntelliJ is fine.

## When OneLens earns its keep

- **Spring Boot monoliths with an AI-coding workflow** — the core
  use case. Every metric we track is calibrated here.
- **PR review on Java services** where "which endpoints does this
  touch?" needs a trustworthy answer in seconds.
- **Legacy-Java onboarding** where the graph is the docs nobody
  wrote.
- **Agent-driven refactors** that need a live blast-radius query
  in the loop, not a static analysis report from last night.
