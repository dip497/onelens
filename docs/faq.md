# FAQ

### Is this a new code search engine?

No. It's a fact graph of your code plus a semantic index. Search is
one operation on top; the graph's value is the traversals grep
can't do — call chains, blast radius, Spring bean wiring,
endpoint-to-method resolution.

### Does this replace IntelliJ?

No. OneLens *depends on* IntelliJ's PSI engine for accuracy. IntelliJ
remains your IDE; OneLens lifts what IntelliJ already knows out of
the IDE so AI agents can query it.

### Why not just use tree-sitter?

Tree-sitter is great for fast, polyglot, lexical indexing. It
can't resolve Java method overloads, polymorphic dispatch through
interfaces, or Spring DI wiring. On a 10K-class monolith, that's
the difference between a correct call graph and a pile of false
positives.

### Why not just use Sourcegraph / Cody / Aider repo-map?

Those work on any repo, which is a real strength. They also rely on
text-based indexing, which is a real weakness on Spring Boot. Pick
OneLens when accuracy on Java matters more than breadth; pick the
others when you want one tool across many languages and you can
live with approximate call graphs.

### Is this open source?

Yes. Core is dual-licensed MIT OR Apache-2.0. Future paid surface
(hosted retrieval, cross-repo stitching) will live in a separate
repo with separate licensing. Core is never rug-pulled.

### Do you collect telemetry?

No, not by default, not ever unless the user explicitly opts in.
Everything runs locally: FalkorDB, ChromaDB, Qwen3, mxbai.

### Does it work on Kotlin?

Mostly. The collectors use IntelliJ PSI which handles Kotlin, but
we haven't audited Kotlin Spring semantics (annotation processing,
`companion object` factories, etc.) end-to-end. Filing issues with
reproducer projects is the fastest way to improve this.

### Does it work on codebases without Spring?

Yes — Spring-specific collectors simply emit fewer nodes. You
still get classes, methods, fields, call graph, inheritance, and
semantic search. REST-endpoint nodes and bean-type impact
narrowing depend on Spring annotations.

### Windows support?

Works via WSL today. Native Windows packaging is **M2**.

### Do I have to use Claude Code?

No. The CLI is agent-agnostic. The same operations are available
over MCP stdio (`onelens mcp-server`), so any MCP-aware client
(Cursor, Continue, Cline) can consume them. The bundled skill is
the easiest on-ramp for Claude Code specifically.

### How big does the graph get?

Empirically, on a 10K-class Spring Boot monolith:
- ~1.5 GB FalkorDB database
- ~500 MB ChromaDB
- ~20 min first embedding pass; < 5 s delta re-sync

### Does the embedding model need a GPU?

No, but it's faster with one. CPU on a modern laptop runs the
initial embedding pass in ~45 min; a consumer GPU cuts that to
~15–20 min. Delta re-sync is small enough that CPU is fine.

### Where do I get help?

Start with GitHub issues. Security issues: email the address in
[SECURITY.md](../SECURITY.md). A chat server will open when
community size warrants it.
