---
name: onelens
description: >
  Query the OneLens code knowledge graph — Java / Kotlin / Spring Boot backends,
  Vue 3 / Pinia / vue-router frontends, JPA entities, Flyway migrations, custom
  SQL, and test coverage. Use whenever the user asks about code impact,
  dependencies, call chains, blast radius, Spring bean wiring, REST endpoint
  tracing, SQL → entity mapping, which tests cover X, inheritance, dead code,
  or any cross-stack question like "what breaks on the frontend if I change
  this Java endpoint". Trigger even without the words OneLens / graph when the
  user says "what calls X", "who depends on X", "trace this endpoint", "impact
  of renaming Y", "which report breaks if I change this column", "how does
  feature Z work", or similar. Skip only when the active project is in an
  unsupported stack (Python, Go, Rust, plain JS) — fall back to Grep / LSP.
---

# OneLens: Code + SQL + Test Knowledge Graph

OneLens indexes a codebase as a graph of **Class / Method / Field /
SpringBean / Endpoint / JpaEntity / Migration / SqlQuery / TestCase / …**
nodes plus the edges between them. Each project lives in a **graph** (the
`--graph` name); many graphs coexist on one backend (FalkorDB Lite by
default — embedded, no Docker — or FalkorDB server on port 17532).

All operations are exposed as **19 MCP tools** under the `onelens_*`
prefix.

## Transport modes

Two ways Claude Code reaches the tools. Both support the same tool
names and arguments — only the invocation syntax differs.

1. **MCP server (remote or local)** — preferred when `~/.claude/settings.json`
   has an `mcpServers.onelens` entry (stdio or http). Tools appear in
   the agent's tool list directly; call them by name with keyword args,
   e.g. `onelens_status(graph="myapp")`. No shell needed.
2. **CLI fallback** — if MCP isn't configured, shell-out via the bundled
   CLI: `onelens call-tool <tool> --key val --key val`. Same tools,
   translated to flags. Shapes below document the canonical keys; both
   modes use the same ones.

If you see an agent running examples as `onelens call-tool …`, they're
the CLI form; MCP clients just call the tool directly with the same
key/value pairs.

---

## Wake-up protocol (MANDATORY first step)

**Every session, call `onelens_status` first.** It returns the graph's
capabilities — the rest of the skill branches off those flags. Without this
call you will mis-pick tools (e.g. invoke `onelens_retrieve` when the
semantic layer isn't indexed).

**Never invent the graph name.** IDE project dir ≠ graph name. If
`total_nodes == 0` **and** `available_graphs` is non-empty, auto-pivot to
`available_graphs[0].graph` (the largest indexed one — list is sorted by
name, usually only one candidate anyway). No need to ask the user. Only
fall back to Grep/LSP when `available_graphs` is empty — meaning the
graph really isn't indexed; then tell the user to run Sync Graph.

**Hard rule — the first `onelens_status` is a probe, not a verdict.**
Always parse `.available_graphs` before *any* other tool (IDE search, Grep,
LSP). If you even think "let me fall back to…" on the first empty status,
stop and re-call against the populated graph first.

```bash
onelens call-tool onelens_status --graph <name>
```

Returns (shape — concrete values vary per project):

```json
{
  "protocol": "onelens/v1",
  "graph": "<graph-name>",
  "backend": "falkordblite",
  "capabilities": {
    "has_structural": true,   "has_semantic": false,
    "has_spring": true,       "has_jpa": true,
    "has_sql": true,          "has_tests": true,
    "has_vue3": false,        "has_memory": false,
    "has_apps": true
  },
  "counts": { "Class": 10000, "Method": 80000, "JpaEntity": 700, "…": "…" },
  "edge_counts": { "CALLS": 630000, "HAS_METHOD": 80000, "ANNOTATED_WITH": 70000, "…": "…" },
  "total_nodes": 190000,
  "total_edges": 1040000
}
```

`edge_counts` is sorted desc by count — you can see at a glance which
relations dominate (CALLS ≫ everything else on a mature code graph) and
pick the most selective edge for traversals. No need to follow up with
`MATCH ()-[r]->() RETURN type(r), count(r)`.

When the requested graph is empty, the payload adds `available_graphs`:

```json
{ "total_nodes": 0,
  "available_graphs": [ { "graph": "my-app", "rdb_bytes": 51346823 } ] }
```
Re-call `onelens_status` against the populated one — **parse the field,
don't guess a fallback name**. One-liner:

```bash
graph=$(onelens call-tool onelens_status --graph <guess> \
  | jq -r '.available_graphs[0].graph // empty')
onelens call-tool onelens_status --graph "$graph"
```
Do NOT use `|| --graph default` — there is no `default` graph.

`capabilities` → see `references/capabilities.md` for what each flag unlocks.

---

## Decision tree

After reading `onelens_status`, pick the tool based on question type:

```
user's question                               tool to call
──────────────────────────────────────────────────────────────────────
"what's the FQN / name / class called X"     → onelens_search
"impact / rename / trace / call-graph"       → onelens_query + queries-code.md
"schema / migration / column / report SQL"   → onelens_query + queries-sql.md
"which test covers X" / coverage             → onelens_query + queries-tests.md
"how does X work" / conceptual question      → onelens_retrieve  (ONLY if has_semantic=true;
                                                                  else onelens_search)
"frontend ↔ backend integration trace"       → onelens_query + queries-code.md (cross-stack)
"decisions / notes / cross-session memory"   → onelens_kg_* / onelens_add_drawer / onelens_diary_*
"how many / stats / counts / distribution"   → onelens_status (already has it) or
                                               onelens_query with aggregate Cypher
"what labels / edges exist / schema shape"   → onelens_status (counts + edge_counts) +
                                               graph-schema.md for semantics
"does A reference/link/point-to B"           → onelens_query, scan HAS_COLUMN,
                                               HAS_FIELD, method param/return,
                                               ANNOTATED_WITH.attributes,
                                               SqlStatement.sql  (recipes.md #12)
"is method X really dead code?"              → onelens_query, also check
                                               HANDLES, ANNOTATED_WITH (Scheduled/
                                               EventListener/PostConstruct),
                                               OVERRIDES, then grep reflection
                                               (recipes.md #14)
"what runs on startup/schedule/event"        → unified entry points (recipes.md #13)
"compare two releases / API diff / churn"    → pull snapshots via onelens_snapshots_pull;
                                               then cross-graph diff (recipes.md #16)
"pull a release snapshot"                    → onelens_snapshots_list → onelens_snapshots_pull
```

## Naming vs Referencing — the split that catches agents

Two question shapes agents conflate:

- **Naming** ("is there a class/method/table called X") → `onelens_search`
  on `name` / `fqn`. Cheap, one hop.
- **Referencing** ("does A link to B", "does A store B's id", "what touches
  B") → traverse edges. **A reference almost never lives in a class name.**
  It lives in a **column** (`HAS_COLUMN`), a **field type** (`HAS_FIELD` +
  `Field.typeFqn`), a **method param/return type**, an **annotation
  attribute** (`ANNOTATED_WITH.attributes` JSON), an **SQL statement**, or
  an **enum-arg registry** (`EnumConstant.argList`). Class-name search
  misses all six.

Rule of thumb: user verb is "named/called/has class" → *naming*. Verb is
"reference/link/point/knows/stores/maps to/touches" → *referencing*.

**Think in two buckets:** *node probes* (`onelens_search`, `onelens_retrieve`,
`MATCH (n:Label)`) vs *edge/fact probes* (`MATCH ()-[r]->()`, traversals in
`queries-code.md` / `queries-sql.md` / recipes.md). Users asking "what X"
are on node side; "which X connects to Y", "what breaks if", "what touches"
are on edge side. Pick the bucket first, then the tool.

---

## Cypher dialect — FalkorDB quirks (read this before writing queries)

FalkorDB ≠ Neo4j. These differences burn agents in every session:

- **No `=~` regex.** Use `CONTAINS`, `STARTS WITH`, `ENDS WITH`, or
  `toLower(x) CONTAINS 'y'` for case-insensitive substring match.
- **No variable-length paths in plain MATCH** (`[:REL*1..3]` is slow and
  sometimes unsupported). Prefer explicit multi-hop: `MATCH (a)-[:R]->(b)-[:R]->(c)`.
- **Property names are camelCase** — `fqn`, `filePath`, `classFqn`,
  `returnType`, not `fq_n` or `file_path`. See `graph-schema.md`.
- **`CALL { ... }` subqueries do not accept `$param`** — inline literals
  or let the outer query pass them via WITH.
- **No `apoc.*`, no `date()` helpers.** Timestamps are epoch numerics.
- **Always include `LIMIT`** — unbounded MATCH on a 200k-node graph
  returns everything and hangs the client.

If a Cypher call errors, **rewrite and retry 2-3 times** before falling
back to Grep. Most errors are dialect mismatches, not "graph doesn't
have the data."

## Retry protocol (when the first query doesn't land)

1. **Empty result, graph is populated?** Relax the predicate:
   `name = 'X'` → `name CONTAINS 'X'` → `toLower(name) CONTAINS 'x'`.
   Try FQN fragments: `classFqn CONTAINS 'package.Sub'`.
2. **Cypher error?** Check the dialect quirks above. Rewrite, don't grep.
3. **Overwhelming results (hundreds of rows)?** Add filters:
   `WHERE NOT n.external`, `WHERE n.wing = '<graph>'`, tighter LIMIT,
   `ORDER BY n.pagerank DESC` to surface the important ones first.
4. **Still stuck after 3 tries** *and* `has_semantic = true`? Pivot to
   `onelens_retrieve` — conceptual queries benefit from embeddings.
5. **Only then** fall back to Grep/LSP. Graph is populated → graph has
   the answer; grep is a last resort, not a parallel path.

## Schema probe (before complex queries)

When you need properties you haven't used before, sample 1 node:

```cypher
MATCH (n:JpaEntity) RETURN keys(n) AS props, n LIMIT 1
```

Cheaper than guessing property names and getting zero rows because you
typed `tableName` but the schema has `table`.

## Dual labels — don't over-filter

Some nodes carry two labels so queries can hit either:

- `JpaEntity` ∪ `Class` — every JpaEntity is also a Class.
- `JpaRepository` ∪ `Class` — same.
- `JpaColumn` ∪ `Field` — every column is also a Field.
- `EnumConstant` ∪ `Field` — enum constants are Fields.
- `TestCase` ∪ `Method` — tests are Methods.

This means `MATCH (c:Class)` returns entities + repositories too. If you
want *only* plain Classes (no entity/repo), add `WHERE NOT c:JpaEntity AND NOT c:JpaRepository`.

**Traversal gotcha:** when following `[:EXTENDS]` from a `JpaEntity`, the
parent may *also* be a `JpaEntity` (dual-labeled). Match the superclass
with `:Class` — it hits both. Don't assume only the leaf is labeled.

```cypher
// Wrong — drops parents also labeled JpaEntity
MATCH (e:JpaEntity {name:'Request'})-[:EXTENDS]->(p:Class) WHERE NOT p:JpaEntity
// Right — hits abstract JPA parents too
MATCH (e:JpaEntity {name:'Request'})-[:EXTENDS]->(p:Class)
```

## Anti-patterns (things agents get wrong)

- ❌ Falling back to Grep after one Cypher error. Graph still has the data.
- ❌ `name = '<string>'` when the user gave a partial. Default to `CONTAINS`.
- ❌ Querying `fqn` when the user pasted a short class name — use `name`.
- ❌ Running structural queries without filtering `external: true` — project signal drowned by JDK/library stubs.
- ❌ `onelens_retrieve` on a graph where `has_semantic: false` — returns empty; use `onelens_search` / `onelens_query` instead.
- ❌ Asking a conceptual question with `onelens_query`. If "how does X work" / "show me the logic": prefer `onelens_retrieve` when semantic is on, else read `onelens_search` top hits' source.
- ❌ Inventing tool flag names. See invocation shapes below.
- ❌ **Searching class names for cross-entity linkage.** "Does Order link to Customer?" is answered by `HAS_COLUMN` on `customerId` — not by a class named `OrderCustomer`. See *Naming vs Referencing* above.
- ❌ **Treating "0 CALLS callers" as dead code.** Rule out `HANDLES` (REST), `ANNOTATED_WITH {Scheduled, EventListener, PostConstruct, PreDestroy}` (lifecycle), `OVERRIDES` (polymorphic dispatch), and reflection (`Class.forName`, `getBean`, string-based dispatch) before declaring anything dead. Recipe #14.
- ❌ **Stopping at the abstract declaration.** `(caller)-[:CALLS]->(m)` on an abstract `m` — real implementation lives on subclasses. Walk `(m)<-[:OVERRIDES]-(impl)`.
- ❌ **Missing inherited columns/annotations.** `@Table` / `@Column` / `@RequestMapping` often sit on an abstract parent or `@MappedSuperclass`. Walk `[:EXTENDS*1..5]` before concluding "not annotated."
- ❌ **Ignoring runtime gates.** `@ConditionalOnProperty("feature.x.enabled")` + missing property = structurally reachable but runtime-dead. Check `ANNOTATED_WITH.attributes` before claiming execution.
- ❌ **Wrong property for the question.** References in `Field.typeFqn` / `Method.parameterTypes` / `Method.returnType` — not `name`. Check `graph-schema.md` for which property carries what.

---

## Tool catalog — reads

| Tool | Use when |
|---|---|
| `onelens_status` | session start — wake-up, capabilities probe, counts |
| `onelens_query` | raw Cypher — any graph. Default tool for structural questions |
| `onelens_search` | FTS by name / FQN / pattern (`User*`, `%auth%`). Node-type filter optional |
| `onelens_retrieve` | hybrid FTS + semantic with source snippets. **Only when `has_semantic: true`** |
| `onelens_kg_timeline` | time-series over facts touching an entity |
| `onelens_find_tunnels` | concepts shared across wings (semantic similarity threshold) |
| `onelens_diary_read` | per-wing diary log |
| `onelens_check_duplicate` | semantic dedup before adding a drawer |

### Canonical invocation shapes (exact flags)

```bash
onelens call-tool onelens_status   --graph <name>
onelens call-tool onelens_query    --cypher "<CYPHER>" --graph <name> [--limit 30]
onelens call-tool onelens_search   --term "<text>" --graph <name> [--node-type Method]
onelens call-tool onelens_retrieve --query "<conceptual phrase>" --graph <name>
```
`--cypher`, `--term`, `--query` are *required positional-like* — omitting
the value yields `requires an argument`. Quote the value when it contains
spaces.

**Flag-name traps (seen in real sessions):**

| Tool | Right flag | Common wrong guess |
|---|---|---|
| `onelens_search` | `--term` | ❌ `--query` (that's `onelens_retrieve`) |
| `onelens_search` | `--node-type Method` | ❌ `--nodeType` / `--type` |
| `onelens_query` | `--cypher` | ❌ `--q` / positional |
| `onelens_retrieve` | `--query` | ❌ `--term` / `--q` |

If you see `parameter '--X' requires an argument. Did you mean '--Y'?`,
fastmcp already told you the fix — use Y, don't guess further.

## Tool catalog — writes (agents rarely invoke; mostly CLI)

| Tool | Use when |
|---|---|
| `onelens_import` | index a JSON export into a graph |
| `onelens_delta_import` | apply a delta export explicitly |
| `onelens_add_drawer` / `onelens_delete_drawer` | store / remove a note |
| `onelens_kg_add` / `onelens_kg_invalidate` | assert / retract a temporal fact |
| `onelens_diary_write` | append to per-wing diary |

---

## Reference files — load on demand

| File | Load when |
|---|---|
| `references/recipes.md` | **first stop for any user question** — canonical multi-step recipes for 10 common intents (impact, endpoint-to-table, test coverage, bean graph, dead code, migrations, cross-stack) |
| `references/capabilities.md` | interpreting the flags in `onelens_status` |
| `references/graph-schema.md` | need node-label + edge-type vocabulary |
| `references/queries-code.md` | impact, trace, entry-points, call-graph, inheritance |
| `references/queries-sql.md` | migrations, custom SQL queries, column lineage, report impact |
| `references/queries-tests.md` | test coverage, unit vs integration split, MOCKS/SPIES |
| `references/retrieval.md` | `onelens_retrieve` usage + fallback rules |
| `references/jvm.md` | Spring / JPA deep patterns (`@Qualifier` injection, bean graph) |
| `references/vue3.md` | Vue 3 / Pinia / vue-router patterns |

Don't load everything up-front. Read the ones the question actually needs.

---

## Answer principles (shared)

- **Answer the question; don't dump pointers.** Top-hit synthesis with
  `file:line` evidence beats ranked lists of FQNs.
- **Structural reachability ≠ runtime execution.** A graph edge proves a
  call statement exists in source, not that it runs. When the user asks
  "does X actually execute", read the call site + any predicate bodies
  before claiming yes. See the dead-gate detection section in `jvm.md`.
- **Empty result = genuine no-match.** If `onelens_query` returns zero rows
  for a concept, say so plainly — don't keep inventing synonyms.
- **Default `LIMIT 20-30`**, `name` matching over `fqn`, to keep context
  budget lean. Only switch to `fqn` / `filePath` when the user pasted one.
- **Gate semantic tools on the flag.** `onelens_retrieve` on a graph where
  `has_semantic: false` returns empty; fall back to `onelens_search`.
- **Commit to an interpretation; don't ask.** If the user says "custom
  SQL for X" — answer with SQL. If they say "trace the endpoint" — answer
  with Cypher. Don't end with "Did you mean SQL or Cypher?" — pick the
  literal reading of their words, deliver, and let them redirect.
- **Surface coverage gaps in the answer, not just in internal thinking.**
  If the user asks about graph X but X is empty (or `available_graphs`
  redirected you elsewhere), say so up front: *"The `foo-frontend` graph
  is empty — answer below is backend-only. Run Sync Graph on the frontend
  project to get cross-stack coverage."* Silent coverage loss is worse
  than a partial answer.
- **BUG claims require evidence.** Before asserting *"off-by-one in gate
  5"* / *"strict `<` should be `<=`"* / *"dead branch"*, cite exact
  `file:line` and quote the operator. No naked bug accusations from graph
  reachability alone — read the source, quote the 1-2 lines, then assert.
- **Don't bypass the graph when the user asked a graph-scoped question.**
  If you find yourself reading only raw source via grep/context-mode after
  the status probe, you've silently abandoned OneLens. Use the graph to
  find the entry-point (endpoint, controller, service class) *first*,
  then drop into source for logic. Raw-source-only answers miss the
  structural claims the graph can make cheaply.

---

## Unsupported stacks

Python, Go, Rust, C#, Ruby, plain JS (no Vue): not in the graph yet. Use
Grep / LSP there. `onelens_retrieve` / `onelens_query` on a graph without
the relevant labels returns empty or nonsense — check `capabilities` first.
