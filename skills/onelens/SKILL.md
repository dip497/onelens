---
name: onelens
description: >
  Query the OneLens code knowledge graph to understand a codebase. Use this skill
  whenever the user asks about code impact, dependencies, call chains, blast radius,
  Spring bean wiring, REST endpoint tracing, inheritance hierarchies, library
  usage, dead code, Vue component/store/composable/route relationships, which
  components call which APIs, or any cross-stack question like "what breaks on the
  frontend if I change this Java endpoint". Also trigger when the user says "what
  calls X", "who depends on X", "trace this endpoint", "blast radius of upgrading Y",
  "how does feature Z work", "where is X set up" — even without the words OneLens
  or graph. Supports Java / Kotlin / Spring Boot backends and Vue 3 / Pinia /
  vue-router frontends. Skip only when the active project is in an unsupported
  language (Python, Go, Rust, plain JS) — fall back to Grep / ripgrep / native LSP
  there.
---

# OneLens: Code Knowledge Graph

OneLens exports a code knowledge graph into FalkorDB. Each project lives in a **wing** (the `--graph` name); one FalkorDB instance holds many wings. When a JVM backend and a Vue 3 frontend share the same instance, cross-wing `HITS` edges link Vue `ApiCall` nodes to Spring `Endpoint` nodes after URL normalization — enabling full-stack traversals.

This skill is the entry point. Detect the stack, then read the matching reference for schema, query patterns, and gotchas.

## CLI (shared across stacks)

```bash
~/.onelens/venv/bin/onelens query "<CYPHER>" --graph <wing-name>
~/.onelens/venv/bin/onelens stats --graph <wing-name>
~/.onelens/venv/bin/onelens retrieve "<natural query>" --graph <wing-name>   # JVM today
```

The commands `impact`, `trace`, `entry-points`, `search` are JVM-specific; use them only against a wing that has Java node labels.

## Step 1 — Detect the stack

Run `stats` against the target wing and read the `nodes` map. The label set tells you which reference to load:

| Labels present | Stack | Reference to read |
|---|---|---|
| `Class`, `Method`, `SpringBean`, `Endpoint` | JVM (Java / Kotlin / Spring Boot) | `references/jvm.md` |
| `Component`, `Store`, `Route`, `ApiCall`, `Composable` | Vue 3 | `references/vue3.md` |
| Both sets | Full-stack (single wing or two wings with `HITS` edges) | **both** references, plus the cross-stack section below |

```bash
~/.onelens/venv/bin/onelens stats --graph <wing-name>
```

If the user hasn't named a wing, list candidates first (`onelens stats` with no args shows them) and then pick based on the file paths and repo context at hand.

## Step 2 — Load the right reference

- **`references/jvm.md`** — JVM schema (Class/Method/Field/SpringBean/Endpoint/Module/Annotation), edges (CALLS/EXTENDS/IMPLEMENTS/HANDLES/INJECTS/ANNOTATED_WITH/…), all Cypher patterns, hybrid `retrieve` usage, `impact` + `trace` flows, library-upgrade blast radius, dead-gate detection, answer principles.
- **`references/vue3.md`** — Vue 3 schema (Component/Composable/Store/Route/ApiCall), edges (USES_STORE with indirect flag, USES_COMPOSABLE, DISPATCHES, CALLS_API, HITS), parametric URL handling, Pinia store shape, component-to-store/API traversals.

Read only the reference(s) that match the active stack. Don't load both up front — progressive disclosure keeps the context budget lean.

## Cross-stack bridge (when both stacks live in one graph)

`HITS` edges emit when a Vue `ApiCall` and a Spring `Endpoint` normalize to the same `(method, path)` pair. Path normalization collapses `/vendor/{id}` and `` `/vendor/${id}` `` into `/vendor/{}` — see `python/src/onelens/importer/bridge_http.py` for the algorithm. No `HITS` edges exist unless both the frontend wing and backend wing have been synced.

### Full-stack blast radius — "who on the frontend breaks if I change this Java method?"

```cypher
MATCH (m:Method)-[:HANDLES]-(e:Endpoint)<-[:HITS]-(a:ApiCall)<-[:CALLS_API]-(c)
WHERE m.fqn = '<target_method_fqn>'
RETURN DISTINCT labels(c)[0] AS caller_type,
                coalesce(c.name, c.fqn) AS caller,
                a.method + ' ' + a.path AS api_call
ORDER BY caller
```

### Front-to-back feature trace — "trace login end-to-end"

```cypher
MATCH (r:Route)-[:DISPATCHES]->(comp:Component)-[:CALLS_API]->(a:ApiCall)-[:HITS]->(e:Endpoint)<-[:HANDLES]-(m:Method)
WHERE r.path CONTAINS '/login'
RETURN r.path AS route, comp.name AS component,
       a.method + ' ' + a.path AS api,
       m.classFqn + '#' + m.name AS handler
LIMIT 20
```

### Dead endpoint sweep — "which endpoints no frontend calls?"

```cypher
MATCH (e:Endpoint)
WHERE NOT (e)<-[:HITS]-()
RETURN e.httpMethod + ' ' + e.path AS unused_endpoint, e.handlerMethodFqn
ORDER BY e.path
LIMIT 50
```

Caveat: only meaningful when the Vue wing is indexed on the same graph. Otherwise every endpoint looks unused.

### Orphan API call — "frontend calls that hit no backend"

```cypher
MATCH (a:ApiCall)
WHERE NOT (a)-[:HITS]->() AND a.parametric = false
RETURN a.method, a.path, a.callerFqn
ORDER BY a.path
LIMIT 50
```

Orphans mean either (a) stale frontend after a backend rename, or (b) the `ModuleNameBinder` couldn't resolve a parametric URL — inspect the call site before declaring the route dead.

## Answer principles (shared across stacks)

- **Answer the question; don't dump pointers.** Top-hit synthesis with `file:line` evidence, not ranked lists.
- **Structural reachability ≠ runtime execution.** A graph edge proves a call statement exists in source, not that it runs. When the user asks "does X actually execute", read the call site and any predicate bodies before claiming "yes". See the dead-gate detection section in `references/jvm.md`.
- **Empty retrieval = genuine no-match.** If nothing is in the graph for a concept, say so plainly — don't keep inventing synonyms hoping for a weak hit.
- **Use `name` for matching, `fqn` / `filePath` only when the user provides full paths.** LIMIT results to 20-30 by default so context doesn't drown in noise.

## Unsupported stacks

Python, Go, Rust, plain JS (no Vue), C#, Ruby: not in the graph yet. Use Grep / ripgrep / native LSP there. `retrieve` / `impact` / `trace` on an unsupported wing returns empty or nonsense.
