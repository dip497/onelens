# Capabilities — what each flag unlocks

`onelens_status` returns a `capabilities` map. Use it to gate the skill's
decision tree — never assume a feature is present.

| Flag | True when | Unlocks |
|---|---|---|
| `has_structural` | `:Class` or `:Method` nodes present | `onelens_query` for calls / impact / trace; `onelens_search` for FTS name match |
| `has_semantic` | ChromaDB drawer exists for this graph | `onelens_retrieve` — hybrid FTS + semantic with source snippets. If false, fall back to `onelens_search` |
| `has_spring` | `:SpringBean` nodes present | Bean injection chains, `@Primary`, endpoint handler resolution |
| `has_jpa` | `:JpaEntity` nodes present | `HAS_COLUMN` / `RELATES_TO` / `REPOSITORY_FOR` / `QUERIES` edges; entity-level impact |
| `has_sql` | `:SqlQuery` or `:Migration` nodes present | `QUERIES_TABLE` / `CREATES_TABLE` / `ALTERS_TABLE` / `REFERENCES_COLUMN` — see `queries-sql.md` |
| `has_tests` | `:TestCase` nodes present | `:TESTS` / `:MOCKS` / `:SPIES` edges; coverage queries — see `queries-tests.md` |
| `has_vue3` | `:Component` / `:Store` / `:Composable` nodes present | Vue-side traversal; cross-stack `HITS` edges (when backend graph also present) — see `vue3.md` |
| `has_memory` | `:Drawer` / `:Concept` nodes present on any reachable graph | `onelens_kg_*` / `onelens_add_drawer` / `onelens_diary_*` (see SKILL.md tool catalog) |
| `has_apps` | `:App` nodes present | Multi-app monorepo queries; per-app scoping via `(App)-[:CONTAINS]->(Package)-[:CONTAINS]->(Class)` |

## How the agent should use this

```
1. onelens_status(graph=$G) → capabilities
2. if question is conceptual:
     if capabilities.has_semantic: onelens_retrieve
     else:                         onelens_search
3. if question is about SQL / migration / column:
     if capabilities.has_sql:      queries-sql.md patterns via onelens_query
     else:                         say "no SQL indexed for this graph"
4. if question is about test coverage:
     if capabilities.has_tests:    queries-tests.md patterns
     else:                         grep fallback
…
```

**Empty `has_*` is never a bug — it means that layer isn't indexed for this
graph.** Tell the user rather than fabricating an answer.
