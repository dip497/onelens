# OneLens — JVM Reference

> **⚠️ Migration notice (2025-01 onwards)** — this file contains JVM/Spring
> deep-dive patterns. Some CLI examples still use the legacy tool names
> (`onelens impact`, `onelens trace`, `onelens search`, `onelens retrieve`,
> `onelens call-tool onelens_status`). Those standalone commands were removed in the unified
> MCP surface. **Translate invocations as follows:**
>
> | Legacy command | New canonical form |
> |---|---|
> | `onelens call-tool onelens_status ...` | `onelens call-tool onelens_status ...` |
> | `onelens call-tool onelens_query --cypher "CYPHER" ...` | `onelens call-tool onelens_query --cypher "CYPHER" ...` |
> | `onelens search "X" ...` | `onelens call-tool onelens_search --term X ...` |
> | `onelens call-tool onelens_retrieve --query "Q" ...` | `onelens call-tool onelens_retrieve --query "Q" ...` |
> | `onelens impact "FQN" ...` | see **`queries-code.md#impact`** — one Cypher pattern via `onelens_query` |
> | `onelens trace "X" ...` | see **`queries-code.md#trace`** — one Cypher pattern |
> | `onelens entry-points ...` | see **`queries-code.md#entry-points`** — Cypher pattern |
>
> The JVM-specific content below (schema, patterns, gotchas) is still current.
> Full tool-name migration of every example is tracked as a follow-up.

Applies when the active graph has `Class`, `Method`, `Field`, `SpringBean`, `Endpoint`, `Module`, or `Annotation` nodes. Covers Java, Kotlin, Scala, Groovy — anything IntelliJ resolves via the JVM classpath.

Source of truth is PSI-resolved, not text-matched: overloads, polymorphism, Spring injection, and external-library calls all resolve accurately.

## Schema

### Nodes

| Label | Key Properties | Description |
|-------|---------------|-------------|
| Class | fqn, name, kind, filePath, packageName, superClass, external | Classes, interfaces, enums, records. `external=true` for library classes |
| Method | fqn, name, classFqn, returnType, isConstructor, filePath, lineStart, external | Methods and constructors. `external=true` for library methods |
| Field | fqn, name, classFqn, type, filePath | Fields |
| SpringBean | name, classFqn, scope, type | Spring-managed beans (SERVICE, COMPONENT, REPOSITORY, REST_CONTROLLER) |
| Endpoint | id, path, httpMethod, handlerMethodFqn | REST API endpoints |
| Module | name, type, sourceRoots | Maven/Gradle modules |
| Annotation | fqn, name | Java annotations |
| EnumConstant | fqn, name, ordinal, enumFqn, args, argList, argTypes | Per-enum-constant node with resolved constructor args — enables module/feature-scope filtering on enum registries |

### Edges

| Type | From → To | Meaning |
|------|-----------|---------|
| CALLS | Method → Method | Method A calls method B |
| EXTENDS | Class → Class | Class inheritance |
| IMPLEMENTS | Class → Class | Interface implementation |
| HAS_METHOD | Class → Method | Class declares this method |
| HAS_FIELD | Class → Field | Class declares this field |
| OVERRIDES | Method → Method | Method overrides parent method |
| ANNOTATED_WITH | Class/Method/Field → Annotation | Has this annotation. Edge carries `attributes` — JSON map of resolved attribute values (arrays, class FQNs, enum names, nested annotations). |
| HAS_ENUM_CONSTANT | Class → EnumConstant | Enum declares this constant |
| HANDLES | Method → Endpoint | Controller method handles this REST endpoint |
| INJECTS | SpringBean → SpringBean | Bean depends on another bean |

## Query Patterns

Match by `name` (short class name) unless the user provides a fully qualified name.

### 1. Impact Analysis — "What calls X?" / "What breaks if I change X?"

```cypher
MATCH (c:Class {name: "MyService"})
MATCH (c)-[:HAS_METHOD]->(m:Method)
MATCH (caller:Method)-[:CALLS]->(m)
WHERE caller.classFqn <> c.fqn
RETURN DISTINCT caller.classFqn + "#" + caller.name AS caller, m.name AS called_method
ORDER BY caller LIMIT 30
```

### 2. Blast Radius — "How many things are affected?"

```cypher
MATCH (c:Class {name: "MyService"})-[:HAS_METHOD]->(m:Method)
MATCH (caller:Method)-[:CALLS]->(m)
WITH DISTINCT caller.classFqn AS affected_class, count(*) AS call_count
RETURN affected_class, call_count ORDER BY call_count DESC LIMIT 20
```

### 3. Endpoint Trace — "What does this API do?"

```cypher
MATCH (e:Endpoint) WHERE e.path CONTAINS "/mypath"
MATCH (handler:Method)-[:HANDLES]->(e)
MATCH (handler)-[:CALLS]->(downstream:Method)
RETURN e.httpMethod + " " + e.path AS endpoint, handler.name AS handler,
       downstream.classFqn + "#" + downstream.name AS calls_into
LIMIT 20
```

### 4. Inheritance — "What extends X?"

```cypher
MATCH (child:Class)-[:EXTENDS]->(parent:Class {name: "BaseService"})
RETURN child.name, child.fqn
```

### 5. Spring Bean Wiring — "What does this depend on?"

```cypher
MATCH (b:SpringBean) WHERE b.name CONTAINS "myservice"
MATCH (b)-[:INJECTS]->(dep:SpringBean)
RETURN b.name AS bean, dep.name AS dependency, dep.classFqn AS class
LIMIT 20
```

### 6. Override Chain — "Who overrides this method?"

```cypher
MATCH (m:Method)-[:OVERRIDES]->(parent:Method)
WHERE parent.name = "myMethod"
RETURN m.classFqn + "#" + m.name AS override, parent.classFqn + "#" + parent.name AS parent
```

### 7. Find Class

```cypher
MATCH (c:Class) WHERE c.name CONTAINS "Request"
RETURN c.name, c.kind, c.fqn, c.filePath LIMIT 20
```

### 8. Annotation Search

```cypher
MATCH (a:Annotation {name: "Transactional"})
MATCH (target)-[:ANNOTATED_WITH]->(a)
RETURN labels(target)[0] AS type, target.fqn AS element LIMIT 20
```

### 9. External Library Usage — "What uses library X?" / "Blast radius of upgrading X?"

Find all your code that calls a specific external library:

```cypher
MATCH (m:Method {external: true}) WHERE m.classFqn CONTAINS "quartz"
MATCH (caller:Method)-[:CALLS]->(m)
RETURN DISTINCT caller.classFqn AS your_class, m.classFqn + "#" + m.name AS library_api
ORDER BY your_class LIMIT 30
```

List all external libraries indexed:

```cypher
MATCH (c:Class {external: true})
WITH split(c.packageName, '.')[0] + '.' + split(c.packageName, '.')[1] AS lib, count(c) AS classes
RETURN lib, classes ORDER BY classes DESC LIMIT 30
```

Find distinct project classes affected by a library:

```cypher
MATCH (m:Method {external: true}) WHERE m.classFqn CONTAINS "elasticsearch"
MATCH (caller:Method)-[:CALLS]->(m)
RETURN DISTINCT caller.classFqn AS affected_class ORDER BY affected_class
```

### 10. Unused Methods

```cypher
MATCH (m:Method)
WHERE NOT EXISTS { MATCH ()-[:CALLS]->(m) }
AND m.isConstructor = false AND m.external IS NULL
AND m.name <> "toString" AND m.name <> "hashCode" AND m.name <> "equals"
RETURN m.classFqn + "#" + m.name AS unused_method, m.filePath LIMIT 30
```

### 11. Full-Text Search — "Find by name pattern"

```bash
onelens call-tool onelens_search --term "User*" --graph <project-name>               # prefix match
onelens call-tool onelens_search --term "auth" --type method --graph <project-name>   # methods only
onelens call-tool onelens_search --term "/api/users" --type endpoint --graph <project-name>
```

Or via raw Cypher:
```cypher
CALL db.idx.fulltext.queryNodes('Class', 'User*') YIELD node
RETURN node.fqn, node.name, node.filePath LIMIT 20
```

### 11b. Hybrid Retrieval — "Find code by intent AND get the actual source" ⭐

**PRIMARY TOOL for any "where is X", "how does Y work", "find code that does Z" question.** Returns top-K ranked hits **with actual source code snippets** — matches Augment Context Engine UX.

Under the hood: parallel FalkorDB FTS + ChromaDB semantic (Qwen3), Reciprocal Rank Fusion (RRF k=60), then reads source from `filePath:lineStart-lineEnd`.

```bash
# Primary: natural language → top-K with code snippets
ONELENS_PROJECT_ROOT=/path/to/project-source \
  onelens call-tool onelens_retrieve --query "<query>" --graph <project-name>

# Options
  -n 10                     # top-K after fusion/rerank (default 10)
  --fanout 50               # candidates per source before fusion (default 50, tune only if recall poor)
  --rerank / --no-rerank    # cross-encoder rerank (default ON; disable with --no-rerank for speed)
  --rerank-pool 50          # candidates to rerank (N>>K principle)
  --neighbors               # include 1-hop callers/callees for method hits
  --no-snippets             # skip source file reads (faster, FQN only)
  --json                    # JSON output for agents / MCP
  --project-root <path>     # filesystem root for source resolution (or ONELENS_PROJECT_ROOT env)
```

**Rerank is ON by default.** Cross-encoder reads the actual code snippet (not just metadata) and reorders results — catches hits buried deep in semantic ranks. Costs ~10s first-query model load + ~0.5-1.5s per query. Pass `--no-rerank` for faster interactive exploration where you don't need top-1 precision. Rerank scores 0-1 (>0.6 = strong hit).

**Empty result = genuine no-match.** A cross-encoder score floor (default 0.02, override with `ONELENS_MIN_RERANK_SCORE`) filters gibberish and off-topic noise. Calibrated such that:
- Gibberish queries (`xyzqqqnonexistentmethod12345`) score ≤ 0.005 → dropped.
- Real queries score 0.5+ for clear hits, 0.03-0.1 for weak but legitimate matches (short queries, broad terms).

If `retrieve` returns empty, the concept isn't in the codebase — don't retry with 5 synonyms hoping for noise-level hits. Reformulate the question (e.g., `"authentication"` → `"login filter chain"`) or broaden scope (`"report export"` → `"report generation"`). If still empty, say so: "This codebase doesn't appear to have X."

**Router behavior (transparent):** The retrieval pipeline picks a strategy based on the query shape:

| Query looks like | Strategy | Latency (warm) |
|---|---|---|
| `VendorController` (exact PascalCase class) | Direct Cypher `MATCH (c:Class {name: ...})` — shortcircuit | ~50ms |
| `com.foo.bar.Baz#method` (FQN fragment) | Direct Cypher `MATCH ... WHERE fqn CONTAINS ...` — shortcircuit | ~50ms |
| `PATCH /users/{id}` (HTTP verb + path) | Graph-first on `Endpoint` nodes; merges into RRF if partial | ~100-300ms |
| `how does authentication work` (natural language) | Full hybrid: parallel FTS + semantic (Qwen3) → RRF → cross-encoder rerank → threshold filter | ~500ms-2s |
| `UserService*` (FTS wildcard) | FTS path via `search` command | ~100ms |

**You don't need to pick the path.** Always call `retrieve` — the router shortcircuits when it has an exact-match graph hit, falls through to hybrid otherwise. The only reason to call `search` instead is when you specifically need FTS wildcards (`User*`, `%auth%1`).

**Example:**
```bash
ONELENS_PROJECT_ROOT=~/path/to/project \
  onelens call-tool onelens_retrieve --query "how password encryption works" --graph my-project --neighbors
```

**Output per hit:**
- `score` — RRF fused score (higher = better; top result typically 0.03+ when both FTS and semantic hit)
- `type` — method / class / endpoint
- `(fts#N/sem#N)` — which source matched and at what rank; a hit in both is a strong signal
- **Full FQN + file path + line range**
- **Actual source code** (syntax-highlighted, line-numbered)
- **Callers / Calls** when `--neighbors` is set

**When to use `retrieve` vs the other commands:**

| User question | Use |
|---------------|-----|
| "how does X work?", "find code that handles Y", "where is Z set up?" | **`retrieve`** — primary tool |
| "what breaks if I change X?" (given an FQN) | `impact` (section 12) |
| "trace this endpoint end-to-end" | `trace` (section 13) |
| Exact class/method name (`User*`, `%auth%`) | `search` with FTS (section 11) |
| Pure semantic with no source needed | `search --semantic` (below) |

**Fallback: standalone semantic search** (returns FQN table, no code):
```bash
onelens call-tool onelens_search --term "<natural query>" --semantic --graph <project-name>
onelens call-tool onelens_search --term "<q>" --semantic --type method --graph <project-name>
```

**When the context graph isn't indexed yet:**
```bash
onelens import <export.json> --graph <name> --clear --context
```
Adds ~20-25 min for ~40K drawers on a laptop GPU; one-time cost. Resumable after OOM/crash (deterministic IDs). Without `--context`, `retrieve` falls back to FTS-only, `--semantic` fails.

### 12. Endpoint Impact — "Which APIs break if I change this method?"

**This is the most useful command for PR review and impact analysis.**

```bash
~/.onelens/venv/bin/onelens impact "com.example.UserService#updateUser(CallContext,long,UserRest)" --graph <project-name>
```

Output: only the affected REST endpoints. Hits are labeled `precise` (direct `CALLS` chain) or `polymorphic` (chain crossed an `OVERRIDES` boundary — interface-typed injection or template method).
```
PATCH /api/users/{id}  →  UserController.updateUser  UserController.java:56  (1 hops)
POST /api/admin/users/bulk  →  AdminController.bulkUpdate  AdminController.java:89  (2 hops)  [poly]

3 endpoints affected  [1 precise, 2 polymorphic]
```

**Both labels are trustworthy.** Polymorphic hits are narrowed by a **bean-type filter** — only controllers whose injected fields are type-compatible with the target's concrete class survive. "Polymorphic" means "runtime-dispatch reachable with a compatible injected bean", not "maybe". Quote the output directly; don't over-caveat.

**Precision modes:**
- **Default (`--polymorphic`)**: walks both `CALLS` and `OVERRIDES`, then narrows polymorphic hits by injected field types. Catches interface-typed Spring injection (`@Autowired FooService foo; foo.bar()`) and template-method dispatch (base calls `this.hook()`, subclass overrides `hook`). Without the bean-type filter, a lifecycle hook in a widely-extended base service would explode to every endpoint that touches any sibling impl; the filter collapses that to endpoints whose controllers actually inject the specific subtype.
- **`--precise-only`**: filter results to direct-CALLS chains only. Often empty when polymorphism is heavy in Spring — honest, not a bug.
- **`--no-polymorphic`**: strict CALLS-only traversal. Mirrors pre-polymorphic-fix behavior.
- **`--no-bean-filter`**: keeps CHA over-approximation. Use only when debugging the filter itself.

**When to use which:**
- Signature-change PR review: use default. Both precise and poly hits deserve a look.
- "This can't possibly break anything" sanity check: `--precise-only`.
- Debugging the graph: `--no-polymorphic` to confirm the direct structure.

Use `--json` for structured output when processing programmatically.

### 13. Execution Flow Trace — "What does this endpoint do end-to-end?"

Forward trace (for understanding code flow):
```bash
~/.onelens/venv/bin/onelens trace "/api/users" --type endpoint --depth 3 --graph <project-name>
~/.onelens/venv/bin/onelens trace "com.example.UserService#create(CallContext,UserRest)" --depth 3 --graph <project-name>
```

List all entry points:
```bash
~/.onelens/venv/bin/onelens entry-points --graph <project-name>
```

### 14. Enum Constants — "Which enum values satisfy tag / feature / role X?"

Enums are often used as per-feature or per-module registries, with each constant
carrying configuration via constructor args (roles a status transitions to,
currencies a payment method supports, tenants a feature rolls out to). OneLens
resolves those args onto the `EnumConstant` node:

- `args` — JSON-encoded arg list, for forensic inspection.
- `argList` — flattened string tokens. Use with FalkorDB's native `IN` predicate.
  No substring traps (`"A"` won't collide with `"APPROVED"`).
- `argTypes` — parallel list of Java type strings.

```cypher
// All constants of OrderStatus that allow transitioning to APPROVED.
MATCH (c:Class {name: 'OrderStatus'})-[:HAS_ENUM_CONSTANT]->(ec:EnumConstant)
WHERE 'APPROVED' IN ec.argList
RETURN ec.name, ec.args
ORDER BY ec.ordinal
```

```cypher
// Diff: constants present in EnumA but missing in EnumB for the same tag X.
MATCH (:Class {name: 'EnumA'})-[:HAS_ENUM_CONSTANT]->(a:EnumConstant)
WHERE 'X' IN a.argList
WITH collect(a.name) AS fromA
MATCH (:Class {name: 'EnumB'})-[:HAS_ENUM_CONSTANT]->(b:EnumConstant)
WHERE 'X' IN b.argList
WITH fromA, collect(b.name) AS fromB
UNWIND fromA AS n
WITH n WHERE NOT n IN fromB
RETURN n AS onlyInA
```

Unresolvable args (runtime-computed, lambdas) render as the literal string
`<dynamic>`. Exclude them when doing negative proofs:

```cypher
MATCH (:Class {name: 'MyEnum'})-[:HAS_ENUM_CONSTANT]->(ec)
WHERE NOT 'FLAG' IN ec.argList AND NOT '<dynamic>' IN ec.argList
RETURN ec.name
```

### 15. Annotation Attributes — "Which targets carry annotation X with value Y?"

`ANNOTATED_WITH` edges carry an `attributes` property — a JSON string mapping
each annotation attribute to its resolved value. Arrays become JSON arrays,
class literals become FQN strings, enum refs become constant names, nested
annotations are preserved as `{"@<fqn>": {...}}`.

```cypher
// Methods gated by a specific Spring Security role.
MATCH (m:Method)-[r:ANNOTATED_WITH]->(a:Annotation {name: 'PreAuthorize'})
WHERE r.attributes CONTAINS '"ROLE_ADMIN"'
RETURN m.classFqn + '#' + m.name AS handler
```

```cypher
// Classes activated only under a given Spring profile.
MATCH (c:Class)-[r:ANNOTATED_WITH]->(:Annotation {name: 'Profile'})
WHERE r.attributes CONTAINS '"prod"'
RETURN c.fqn
```

Substring-on-JSON has false-positive risk when one token is a prefix of another
(`"READ"` vs `"READABLE"`). When precision matters, either (a) wrap the value in
JSON punctuation in the query (`'":"read"'`, `'"read"]'`), or (b) promote the
attribute to a first-class array property on the edge upstream.

## Approach — Answer the Question, Don't Dump Pointers

The tools above are **building blocks**. Users expect **answers**, not ranked lists. Always chain tools, reason about the results, then give a direct answer with file:line evidence.

### The universal pattern

```
1. Pick the right entry tool for the question type (table below)
2. Look at the top hit(s) — read snippets, don't just report FQNs
3. Follow structural edges when the question demands it:
   - "How does it work?" → retrieve + read body
   - "Who uses it?" / "Is it dead?" → impact (or 0-caller check)
   - "What does this endpoint do?" → trace
4. Synthesize a 2-3 sentence answer that starts with the conclusion
5. Back it with file:line references, not raw tool output
```

### Tool selection matrix

| User asks... | Start with | Then | Why |
|--------------|-----------|------|-----|
| "How does X work?" / "Where is Y handled?" / "Find code that does Z" | `retrieve` | read body of top hit | Hybrid FTS+semantic+rerank returns code, not just locations |
| "Is X actually used?" / "Is this dead code?" | `retrieve` → identify FQN | `impact` or Cypher caller count on X | If 0 callers at the top of the chain → it's dead; say so definitively |
| "What breaks if I change X?" (given FQN) | `impact <fqn>` | — | Canonical answer. Returns affected endpoints, not raw callers |
| "Trace endpoint /foo end-to-end" | `trace "/foo" --type endpoint --depth 3` | retrieve for business-logic context if needed | Deterministic call chain from handler down |
| "What extends/implements X?" | Cypher on `EXTENDS` / `IMPLEMENTS` | `retrieve` on base class for concept | Structural edges are more precise than search |
| "Who depends on Spring bean X?" | Cypher on `INJECTS` | `impact` on the bean's interface methods | Spring wiring is graph data, use it |
| "What uses library Y?" | FTS+semantic `retrieve` with library name | Or raw Cypher on `Method {external: true}` CONTAINS Y | Library upgrade blast radius |
| "Where is config Z set?" / "Where is bean X initialized?" | `retrieve` "Z configuration" | Filter for `@Bean`, `@PostConstruct`, `@Value`, `@ConfigurationProperties` | Bodies surface these annotations |
| Known exact name (`User*`, `%auth%`) | `search` with `--type` | `retrieve` if need body | FTS is faster when the name is known |
| Partial FQN to resolve | `search` | — | Fast prefix/fuzzy match |

### The "Is it actually executed?" pattern

**Core principle: structural reachability ≠ runtime execution.** A `CALLS` edge means "call statement exists in source AST" — it does NOT prove the call runs. The graph is blind to `if` guards on constant predicates, dead branches, feature-flag defaults, `@Value` fallbacks, fields never written, and interface defaults never overridden.

**Apply this check whenever the user asks:** "how does X work", "is Y wired up", "does Z actually run", "why isn't X executing", or reports a bug where expected behavior is missing.

Two layers — both required for execution questions:

**Layer 1 — Caller-chain reachability (structural):**

```bash
# Walk up from the candidate method
onelens call-tool onelens_query --cypher "MATCH (c:Method)-[:CALLS]->(m:Method) WHERE m.fqn = '<FQN>' RETURN c.classFqn, c.name" --graph <g>
# Recurse up until chain terminates
```

A method is reachable if the chain ends at a REST endpoint (`HANDLES` edge), `@Scheduled`, `@EventListener`, `main`, or `@PostConstruct`. 0 callers with none of these → dead.

**Layer 2 — Dead-gate detection (read the call site):**

Even if structurally reachable, the specific call may sit inside a permanently-false guard. 3-step check:

1. **Read caller body** at `filePath:lineStart-lineEnd` — ±10 lines around the call site. Is the call wrapped in `if`, early-return, switch, or try-catch?
2. **If guarded, read the predicate method's body.** Is it `return <literal>;`? Or `return this.field;` where the field is never written outside construction?
3. **Verify field writers** when predicate is field-backed:
   ```cypher
   MATCH (c:Method)-[:CALLS]->(s:Method) WHERE s.name = 'setFlag' RETURN c.classFqn
   ```
   Zero non-constructor writers + default `false`/`null` → gate permanently closed → call is dead.

**Generic example — shallow vs proper:**

```java
class Context {
    public boolean isFeatureEnabled() { return false; }  // hardcoded
}

class Handler {
    void process(Context ctx) {
        doWork();
        if (ctx.isFeatureEnabled()) {
            criticalUpdate();   // CALLS edge exists — never runs
        }
        cleanup();
    }
}
```

Shallow (wrong): "`Handler.process` calls `criticalUpdate` — that's how it runs."
Proper (right): "Gated by `Context.isFeatureEnabled()` which returns literal `false`. `criticalUpdate` is dead code. Real flow is `doWork` → `cleanup`."

**When to skip Layer 2:** "what calls X" / "blast radius" / "find class named Y" questions want the structural answer. Don't pay the cost there.

### Combined-query recipes

**"Explain feature X end-to-end"** (scope: full understanding)
```
1. retrieve "<feature>" → top class + method(s)
2. impact <top-method-fqn> → affected endpoints
3. trace <top-method-fqn> --depth 3 → downstream flow
4. Cypher on HAS_METHOD of top class → full surface
5. Synthesize: what it is, how it's triggered, what it does, what breaks it
```

**"Will this refactor be safe?"** (scope: confidence in change)
```
1. Given FQN → impact <fqn> → count endpoints at risk
2. Cypher OVERRIDES to check subclass impact
3. If Spring bean → INJECTS edges to see consumers
```

**"Find the bug around Y"** (scope: debugging)
```
1. retrieve "<error message or behavior>" → candidate methods
2. For each candidate: trace --depth 2 → downstream where bug might live
3. Look for missing error handling, stale annotations, broken call chains in bodies
```

**"Audit dead code in module M"** (scope: cleanup)
```
1. Pattern 10 (unused methods) filtered to M's package
2. For each: verify not reached from an @Scheduled / @EventListener / endpoint
3. Cross-check with Spring beans that might be reflectively invoked
```

### Anti-patterns — don't do these

- **Don't dump `retrieve` results** at the user verbatim. Pick the top hit, read it, synthesize an answer. If showing multiple, explain why each matters.
- **Don't give pointers when the question needs a yes/no.** "Is X dead?" requires "Yes" or "No", backed by caller count. Not a list.
- **Don't use Grep/Bash for code understanding.** `retrieve` fuses keyword + semantic + reranked source bodies — strictly better. Reserve Grep for non-code (logs, configs, error strings).
- **Don't run 5 queries when 2 suffice.** Start minimal; only walk the graph deeper if the user's question demands it.
- **Don't ignore caller count for "how does X work" questions.** Always check if the found code is actually reached. Dead-code answers are as valid as live-code explanations.
- **Don't trust a CALLS edge as proof of runtime execution.** The edge means a call statement exists in the AST — nothing more. Always read the caller body at the call site to check for guards (`if`, early-return, feature flags) before claiming "X calls Y so Y runs".
- **Don't fabricate behavior.** If retrieve bodies don't show what you're claiming, say so and run another query.
- **Don't forget `ONELENS_PROJECT_ROOT`.** Without it `retrieve` returns FQNs but no source snippets — and you can't reason without reading bodies.

### Performance tips

- **In-process CLI** — `onelens call-tool` runs the MCP server in-process;
  no subprocess, no PATH dependency on the `fastmcp` binary. For
  cross-invocation warmth (shell loops, batch scripts) use `onelens daemon
  start` to keep embeddings + reranker loaded between invocations.
- **`--no-rerank`** drops ~2-3s for a slight quality loss — fine for exploratory queries where top-20 is enough.
- **`--no-snippets`** skips source reads — use when you only need FQNs to chain into cross-stack queries.

## Tips

- Use `name` for matching, not `fqn` (unless user provides full path)
- Use `CONTAINS` for fuzzy matching with partial names
- Exclude self-calls: `WHERE caller.classFqn <> c.fqn`
- LIMIT results to 20-30 by default
- FalkorDB variable-length paths (`[:EXTENDS*1..3]`) can be slow — use explicit multi-hop MATCH instead
- External library nodes have `external: true` — filter them out when looking for project-only results
- For library upgrade blast radius, search by library package name using `CONTAINS` on `classFqn`
