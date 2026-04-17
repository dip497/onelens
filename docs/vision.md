# Vision

> "OneLens is what AI reads before it writes code in your
> monorepo."

A pointer: a more expansive, lived-in statement of intent already
exists at [VISION-AND-ROADMAP.md](./VISION-AND-ROADMAP.md). This
file is the short, wall-friendly version.

## The shift

Two things changed in 2024–2026 that make this the right moment
for a code knowledge graph:

1. **AI-assisted coding is now mainstream.** Claude Code, Codex,
   Cursor, Continue, and Cline all reach for codebase context
   constantly. The ceiling on their quality is no longer the model
   — it's the accuracy of the context the model gets.
2. **Tree-sitter and regex-based context aren't enough for
   Spring.** A monolith's behaviour lives in DI wiring, runtime
   dispatch, and annotation-driven REST routing. Static text
   indexing misses most of it.

What's not yet solved: *giving a language model the same
information IntelliJ's Find Usages uses, on demand, at sub-second
cost, and automatically kept fresh.*

If someone solves this well, every AI assistant on every Spring
Boot codebase gets measurably smarter, overnight, with no model
change.

## The analogy

| Era | Primitive | Distribution | Management |
|-----|-----------|--------------|------------|
| 1990s | Source file | Tarball | Makefile |
| 2000s | Object file | Maven Central | Build server |
| 2010s | Container image | Docker Hub | Kubernetes |
| 2020s | **Knowledge graph of code** | **Plugin + CLI** | **IDE auto-sync** |

## Moonshot in one screen

Concrete outcomes if this works:

- Every AI assistant on a Spring Boot monolith answers blast-radius
  and call-graph questions with IntelliJ-grade accuracy.
- PR review becomes "here are the 3 endpoints this change actually
  affects," not "here are 40 grep hits."
- New team members ship their first real change in days, not
  weeks, because the graph is the onboarding.
- Legacy Java codebases become AI-refactorable — not because
  models got smarter, but because they finally see the code as
  IntelliJ does.

Self-sustaining adopters:

- One well-known Spring Boot OSS project integrating OneLens as the
  default agent context provider.
- One enterprise engineering org publicly citing accuracy
  improvements on internal AI-coding metrics.

What becomes different about the world: *AI coding accuracy on
Java is no longer an open problem.*

## Business model

Open-core. Core (PSI plugin + CLI + graph importer + retrieval
pipeline + Claude skill) is MIT / Apache-2.0 forever. Future paid
surface — if any — is net-new and separate: team-scale managed
graphs, cross-repo stitching, hosted retrieval. No rug-pulls.

## What this is explicitly NOT

- **Not a code search engine.** It's a fact graph. Search is one
  operation; the graph's value is in traversals grep can't do.
- **Not tied to any one LLM.** The skill is Claude-shaped because
  that's where adoption is easiest; the CLI and MCP server are
  model-agnostic.
- **Not trying to replace IntelliJ.** OneLens leans on PSI; IntelliJ
  remains the IDE. The graph is what leaves IntelliJ so other
  tools can use the same truth.
- **Not Java-only by policy — just Java-first by cost.** Adding
  Kotlin / TypeScript / Python later is a scope question, not a
  philosophy question.

## The long arc

If this works, year five looks like:

1. **"Install OneLens" is step 2 of onboarding to any Spring Boot
   monolith**, right after cloning the repo.
2. **Every major AI-coding assistant consumes OneLens as a first-
   class context source** via MCP, not as an add-on.
3. **The graph becomes a shared infrastructure primitive** in
   large engineering orgs — one OneLens instance across many
   repos, queried by humans and agents alike.
