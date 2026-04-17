# Introduction

OneLens is a code knowledge graph that gives AI 100% type-accurate
understanding of a Java/Spring Boot codebase.

Most AI coding assistants reason about code by reading text. That
works for a greenfield script; it falls over on a 10K-class Spring
Boot monolith where a single `service.doThing()` call might resolve
to any of five overloads across two interface hierarchies, routed
by the Spring container at runtime. OneLens extracts that truth
from IntelliJ PSI — the same engine powering IntelliJ's own
Go-to-Definition — and writes it to a graph database plus a
semantic index. Every call edge, override, bean wiring, and REST
endpoint becomes a first-class fact your agent can query.

## The problem

"What breaks if I change `UserService#updateUser`?"

An LLM answering from source code alone will guess. A grep-based
tool will return false positives (unrelated `updateUser` methods
on other classes) and false negatives (polymorphic calls through
an interface it can't resolve). The wrong answer here costs
production incidents.

## The answer

```bash
# One command in IntelliJ: Tools → OneLens → Sync Graph
# Then ask Claude Code:
"blast radius of changing UserService#updateUser"
# → exact list of REST endpoints, Spring beans, scheduled jobs
#   that transitively call the target.
```

Or directly:

```bash
onelens impact --method-fqn "com.example.UserService#updateUser(long,UserRest)" \
  --graph my-project
```

## Who this is for

**Engineers on medium-to-large Spring Boot codebases** who use AI
assistants day-to-day and want answers that match the accuracy of
IntelliJ's Find Usages — without clicking through it manually.

**PR reviewers** who want to know which endpoints a diff actually
touches, not which ones the LLM thinks it touches.

**Teams adopting Claude Code / Codex / Cursor on legacy Java
monoliths** where tree-sitter-based indexers misread half the call
graph.

## What makes this different

1. **PSI, not tree-sitter.** Call edges, overloads, injected beans,
   and inheritance are resolved by the same compiler-grade type
   system IntelliJ uses. Tree-sitter cannot do this.
2. **Hybrid retrieval.** Direct Cypher for exact facts, semantic
   search with cross-encoder rerank for conceptual questions,
   PageRank centrality boost so "important" methods rank first.
   One pipeline, three strategies.
3. **Zero manual indexing.** The plugin auto-installs a Python
   venv, auto-syncs on file save (debounced), and ships the Claude
   Code skill bundled in the plugin JAR.

## Next reading

- [Concepts](./concepts.md) — the vocabulary.
- [Architecture](./architecture.md) — system design.
- [Vision](./vision.md) — where this is going.
- [Roadmap](./roadmap.md) — what ships when.
- [Lessons Learned](./LESSONS-LEARNED.md) — every subtle bug already paid for.
