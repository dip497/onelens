---
name: onelens
description: >
  Query the OneLens code knowledge graph — Java / Kotlin / Spring Boot backends,
  Vue 3 / Pinia / vue-router frontends, JPA entities, SQL migrations, and test
  coverage. Use whenever the user asks about code impact, dependencies, call
  chains, blast radius, Spring bean wiring, REST endpoint tracing, SQL to entity
  mapping, which tests cover X, dead code, or cross-stack questions like "what
  breaks on the frontend if I change this Java endpoint". Trigger even without
  the words OneLens / graph when the user says "what calls X", "who depends on
  X", "trace this endpoint", "impact of renaming Y", "how does feature Z work",
  or similar. Skip only when the project is in an unsupported stack (Python, Go,
  Rust, plain JS without Vue) — fall back to Grep.
---

<overview>
OneLens indexes a codebase as a knowledge graph: every class, method, field,
Spring bean, REST endpoint, Vue component, Pinia store, composable, route, API
call, JPA entity, SQL statement, and test case — plus the edges between them
(CALLS, EXTENDS, IMPLEMENTS, INJECTS, USES_STORE, HITS, etc.).

The graph lives in FalkorDB (embedded falkordblite by default — no Docker
needed — or FalkorDB server on port 17532). Each project is a named graph.

You have exactly **2 query tools** plus a mandatory wake-up:

1. **`onelens_search`** — Full-text search (RediSearch syntax) across all node
   types. Fuzzy, prefix, phrase, union. Weighted by field (name > body).
   Use for "find me X by name or content."

2. **`onelens_query`** — Raw Cypher against the graph. Use for traversal:
   impact analysis, execution traces, dependency chains, dead code, cross-stack.

0. **`onelens_status`** — MANDATORY first call. Returns what's indexed.
</overview>

<wake_up>
## Step 0 — ALWAYS call onelens_status first

```
onelens_status(graph="<project-name>")
```

Returns node counts, edge counts, and capability flags. If `total_nodes == 0`,
the response includes `available_graphs` — switch to the populated one
automatically. Do NOT ask the user. Do NOT invent graph names.

Parse the response to learn:
- What node types exist (Class: 10K, Method: 80K, Endpoint: 2K, Component: 2K, ...)
- What edge types exist (CALLS: 600K, INJECTS: 8K, USES_STORE: 2K, HITS: 1K, ...)
- Capabilities: has_spring, has_jpa, has_vue3, has_sql, has_tests
- Scale: total_nodes / total_edges

This tells you which Cypher patterns work and which node_types are valid for search.
</wake_up>

<decision_tree>
## Which tool to use — decide before calling

| User asks | Tool | Why |
|-----------|------|-----|
| "Find UserService" / "is there a class called X" | `onelens_search` | Name lookup = FTS |
| "Find all auth methods" | `onelens_search` | Prefix wildcard: `auth*` |
| "Where is password encryption?" | `onelens_search` | Body search: `password encryption` |
| "Find Vue components for tickets" | `onelens_search` | `ticket*` + `node_type="component"` |
| "What calls UserService?" / "impact of X" | `onelens_query` | Traverse CALLS edges |
| "Trace /api/users endpoint" | `onelens_query` | Traverse HANDLES → CALLS chain |
| "Who injects AuthService?" | `onelens_query` | Traverse INJECTS edges |
| "Is this method dead code?" | `onelens_query` | Check for inbound CALLS |
| "What REST endpoints exist?" | `onelens_query` | `MATCH (e:Endpoint)` |
| "What breaks on frontend?" | `onelens_query` | Cross-stack HITS traversal |
| "How many classes?" | `onelens_status` | Already in wake-up response |

**Naming questions (find X) → search. Relationship questions (X connects to Y) → query.**
</decision_tree>

<search_tool>
## onelens_search — full-text search

### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | YES | — | Search terms (RediSearch syntax) |
| `graph` | string | no | `"onelens"` | Graph name |
| `node_type` | string | no | `""` (all) | Filter to one type |
| `n_results` | int | no | `20` | Max results |

### Search syntax (RediSearch — FalkorDB FTS)

| Syntax | Example | What it matches |
|--------|---------|-----------------|
| Prefix | `auth*` | authenticate, authorize, authentication |
| Fuzzy | `%passwor%` | password, passwd, passw0rd (edit-distance) |
| Union (OR) | `login\|signin\|authenticate` | Any of the terms |
| Phrase | `"password encryption"` | Exact contiguous phrase |
| Intersection | `password encryption` | Both terms anywhere (AND) |
| Exact | `BCrypt` | Exact term |

### Valid node_type values

When `node_type` is empty (default), searches ALL types simultaneously.

**Java / Spring backend:**
| Value | Node label | Key fields |
|-------|-----------|------------|
| `"class"` | Class | `fqn`, `name`, `kind` (CLASS/INTERFACE/ENUM/ABSTRACT_CLASS/RECORD), `filePath`, `superClass`, `packageName` |
| `"method"` | Method | `fqn` (format: `com.example.Foo#bar(String,int)`), `name`, `classFqn`, `body`, `javadoc`, `returnType`, `visibility`, `isStatic`, `isConstructor`, `isAbstract` |
| `"endpoint"` | Endpoint | `path` (e.g. `/api/users/{id}`), `httpMethod` (GET/POST/PATCH/DELETE), `consumes`, `produces` |
| `"springbean"` | SpringBean | `name`, `classFqn`, `scope`, `primary` |
| `"field"` | Field | `fqn` (format: `com.example.Foo#bar`), `name`, `type` |

**Vue 3 frontend:**
| Value | Node label | Key fields |
|-------|-----------|------------|
| `"component"` | Component | `fqn` (format: `src/views/X.vue::X`), `name`, `filePath`, `props`, `emits`, `scriptSetup`, `body`, `isTest` |
| `"store"` | Store | `fqn`, `name`, `id` (Pinia store id like `"user"`), `state`, `getters`, `actions`, `style` (options/setup), `isTest` |
| `"composable"` | Composable | `fqn`, `name`, `body`, `isTest` |
| `"route"` | Route | `name`, `path`, `fullPath`, `componentRef` |
| `"apicall"` | ApiCall | `method` (GET/POST/etc.), `path`, `callerFqn` |
| `"jsfunction"` | JsFunction | `fqn`, `name`, `filePath`, `exported`, `body` |
| `"jsmodule"` | JsModule | `filePath`, `name`, `isBarrel` |

### How results are ranked (BM25)

FalkorDB scores results by BM25 across indexed fields with weights:
- **name**: 10x — most discriminative (method/class name)
- **javadoc** / **path** / **id**: 3-8x — documentation, endpoint path, Pinia id
- **body**: 1x — source code text (catches terms not in the name)

### Return format (compact — no full bodies)
```json
{"type": "method", "fqn": "com.example.AuthService#login(String)", "name": "login", "file": "src/.../AuthService.java"}
```

### Worked examples
```
# Find a specific class by name
onelens_search("UserService", node_type="class", graph="myapp")
→ [{"type":"class","fqn":"com.example.UserService","name":"UserService","file":"src/.../UserService.java"}]

# Find all auth-related methods (prefix wildcard)
onelens_search("auth*", graph="myapp")
→ [{"type":"method","fqn":"...#authenticate()","name":"authenticate","file":"..."},
   {"type":"method","fqn":"...#setAuthenticationType()","name":"setAuthenticationType","file":"..."}]

# Find methods whose body mentions "password" AND "encryption" (intersection)
onelens_search("password encryption", graph="myapp")
→ [{"type":"method","fqn":"...#encryptApiFieldPassword()","name":"encryptApiFieldPassword","file":"..."}]

# Find Vue components related to tickets
onelens_search("ticket*", node_type="component", graph="myapp")
→ [{"type":"component","fqn":"src/views/TicketList.vue::TicketList","name":"TicketList","file":"src/views/TicketList.vue"}]

# Find all Pinia stores (wildcard)
onelens_search("*", node_type="store", graph="myapp")
```
</search_tool>

<query_tool>
## onelens_query — Cypher for graph traversal

### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cypher` | string | YES | — | Cypher query |
| `graph` | string | no | `"onelens"` | Graph name |
| `limit` | int | no | `100` | Max rows |

### FalkorDB Cypher rules (READ BEFORE WRITING QUERIES)

FalkorDB is NOT Neo4j. These differences cause errors:

- **No `=~` regex.** Use `CONTAINS`, `STARTS WITH`, `ENDS WITH`, `toLower(x) CONTAINS 'y'`.
- **No `[:REL*1..3]` variable-length paths.** Use explicit hops:
  `MATCH (a)-[:CALLS]->(b)-[:CALLS]->(c)`.
- **Property names are camelCase**: `fqn`, `filePath`, `classFqn`, `returnType`.
- **Always include `LIMIT`** — unbounded MATCH on 200K nodes hangs.
- **External stubs exist** — filter with `WHERE n.external IS NULL` to get only
  project code (not JDK/library methods).
- **If a query errors, rewrite and retry 2-3 times** before falling back to Grep.

### Graph schema — nodes

**Java / Spring:**
| Label | Properties |
|-------|-----------|
| Class | `fqn`, `name`, `kind` (CLASS/INTERFACE/ENUM/ABSTRACT_CLASS/RECORD), `filePath`, `superClass`, `packageName` |
| Method | `fqn` (`com.example.Foo#bar(String)`), `name`, `classFqn`, `returnType`, `body`, `javadoc`, `visibility`, `isStatic`, `isConstructor`, `isAbstract`, `external` |
| Field | `fqn` (`com.example.Foo#bar`), `name`, `classFqn`, `type` |
| Endpoint | `id`, `path`, `httpMethod`, `consumes`, `produces` |
| SpringBean | `name`, `classFqn`, `scope`, `primary` |
| Module | `name` |
| Package | `name`, `parentId` |
| Annotation | `fqn`, `name` |

**Vue 3:**
| Label | Properties |
|-------|-----------|
| Component | `fqn` (`src/views/X.vue::X`), `name`, `filePath`, `props`, `emits`, `body`, `isTest` |
| Store | `fqn`, `name`, `id`, `state`, `getters`, `actions`, `isTest` |
| Composable | `fqn`, `name`, `body`, `isTest` |
| Route | `name`, `path`, `fullPath`, `componentRef` |
| ApiCall | `fqn`, `method`, `path`, `callerFqn` |
| JsFunction | `fqn`, `name`, `filePath`, `exported`, `body` |
| JsModule | `filePath`, `name`, `isBarrel` |

### Graph schema — edges (relationships)

**Structural:**
| Edge | From → To | Meaning |
|------|-----------|---------|
| `HAS_METHOD` | Class → Method | Class declares method |
| `HAS_FIELD` | Class → Field | Class declares field |
| `CONTAINS` | Package → Class/Package | Package nesting |
| `EXTENDS` | Class → Class | Inheritance (`extends`) |
| `IMPLEMENTS` | Class → Class | Interface implementation |
| `OVERRIDES` | Method → Method | Method overrides parent |

**Code flow:**
| Edge | From → To | Meaning |
|------|-----------|---------|
| `CALLS` | Method → Method | Method A calls method B (**the big one — 600K+ edges**) |
| `READS_FIELD` | Method → Field | Field read access |
| `WRITES_FIELD` | Method → Field | Field write access |
| `INSTANTIATES` | Method → Class | `new Foo()` |
| `RETURNS` | Method → Class | Return type |
| `THROWS` | Method → Class | Throws exception |
| `HAS_PARAMETER` | Method → Class | Method parameter type |

**Spring:**
| Edge | From → To | Meaning |
|------|-----------|---------|
| `HANDLES` | Class → Endpoint | @RestController maps to endpoint |
| `INJECTS` | Class → SpringBean | @Autowired/constructor injection |
| `REGISTERED_AS` | Class → SpringBean | @Service/@Component/@Repository |
| `ANNOTATED_WITH` | Class/Method → Annotation | Annotation usage |

**Vue 3:**
| Edge | From → To | Meaning |
|------|-----------|---------|
| `USES_STORE` | Component/Composable → Store | Component uses Pinia store |
| `USES_COMPOSABLE` | Component/Composable → Composable | Component uses composable |
| `CALLS_API` | Component/Composable/JsFunction → ApiCall | Frontend calls HTTP API |
| `DISPATCHES` | Route → Component | Route renders component |
| `HAS_FUNCTION` | JsModule → JsFunction | Module exports function |
| `IMPORTS` | JsModule/Component/Store → JsModule/JsFunction | ES6 import |

**Cross-stack (the killer feature):**
| Edge | From → To | Meaning |
|------|-----------|---------|
| `HITS` | ApiCall → Endpoint | Vue API call matches Spring endpoint (normalized HTTP path) |

### Copy-paste Cypher recipes

**IMPACT ANALYSIS — "What breaks if I change UserService?"**
```cypher
MATCH (caller:Method)-[:CALLS]->(target:Method)
WHERE target.classFqn STARTS WITH 'com.example.UserService'
RETURN DISTINCT caller.classFqn AS affected_class, caller.name AS caller_method
ORDER BY affected_class LIMIT 50
```

**BLAST RADIUS (2 hops) — "Full impact of changing this specific method"**
```cypher
MATCH (caller:Method)-[:CALLS]->(mid:Method)-[:CALLS]->(target:Method)
WHERE target.fqn = 'com.example.UserService#findById(Long)'
RETURN DISTINCT caller.fqn AS blast_radius LIMIT 100
```

**EXECUTION TRACE — "Trace /api/users endpoint through the call chain"**
```cypher
MATCH (e:Endpoint {path: '/api/users'})<-[:HANDLES]-(controller:Class)
MATCH (controller)-[:HAS_METHOD]->(handler:Method)
MATCH (handler)-[:CALLS]->(callee:Method)
WHERE callee.external IS NULL
RETURN handler.name AS entry_point, callee.name AS calls, callee.classFqn AS in_class LIMIT 50
```

**ALL REST ENDPOINTS**
```cypher
MATCH (e:Endpoint) RETURN e.httpMethod AS method, e.path AS path ORDER BY path LIMIT 100
```

**SPRING DEPENDENCY CHAIN — "Who injects AuthService?"**
```cypher
MATCH (dependent:Class)-[:INJECTS]->(bean:SpringBean)
WHERE bean.classFqn CONTAINS 'AuthService'
RETURN dependent.name AS dependent_class, bean.name AS bean_name
```

**DEAD CODE — "Which public methods have no callers?"**
```cypher
MATCH (m:Method)
WHERE m.external IS NULL AND m.visibility = 'public'
  AND NOT ()-[:CALLS]->(m)
RETURN m.fqn AS potentially_dead LIMIT 50
```
Note: before declaring dead, also check OVERRIDES (polymorphic dispatch),
ANNOTATED_WITH (@Scheduled/@EventListener/@PostConstruct), and reflection.

**INHERITANCE TREE — "What implements UserRepository?"**
```cypher
MATCH (impl:Class)-[:IMPLEMENTS]->(iface:Class)
WHERE iface.name CONTAINS 'UserRepository'
RETURN impl.fqn AS implementation
```

**ANNOTATION USAGE — "What classes use @Transactional?"**
```cypher
MATCH (c:Class)-[:ANNOTATED_WITH]->(a:Annotation)
WHERE a.fqn CONTAINS 'Transactional'
RETURN c.fqn AS transactional_class
```

**CROSS-STACK TRACE — "Which Vue components call which Spring endpoints?"**
```cypher
MATCH (c:Component)-[:CALLS_API]->(a:ApiCall)-[:HITS]->(e:Endpoint)
RETURN c.name AS vue_component, a.method AS http_method,
       a.path AS api_path, e.path AS spring_endpoint LIMIT 50
```

**VUE STORE USAGE — "Which components use the user store?"**
```cypher
MATCH (c:Component)-[:USES_STORE]->(s:Store)
WHERE s.name CONTAINS 'user' OR s.id CONTAINS 'user'
RETURN c.name AS component, s.name AS store_name
```

**FIND ALL CALLERS OF A METHOD**
```cypher
MATCH (caller:Method)-[:CALLS]->(target:Method)
WHERE target.name = 'findById' AND target.classFqn CONTAINS 'UserService'
RETURN caller.fqn AS called_from LIMIT 30
```

**TEST: exclude test doubles**
```cypher
MATCH (m:Method) WHERE m.external IS NULL
RETURN count(m) AS project_methods
-- or for Vue nodes:
MATCH (s:Store) WHERE NOT s.isTest RETURN s.name
```
</query_tool>

<retry_protocol>
## Retry when queries return empty

1. **Empty result, graph is populated?** Relax predicate:
   `name = 'X'` → `name CONTAINS 'X'` → `toLower(name) CONTAINS 'x'`.
2. **Wrong FQN format?** Method FQNs include params: `Foo#bar(String,int)`.
   Search by name first: `onelens_search("bar", node_type="method")`.
3. **Node type doesn't exist?** Check `onelens_status` — if no Vue data imported,
   `Component` nodes won't exist. Only query node types that appear in counts.
4. **FalkorDB dialect error?** Rewrite: remove `=~`, remove `*1..3`, add `LIMIT`.
5. **Overwhelming results?** Filter `WHERE n.external IS NULL` (project code only),
   add tighter `LIMIT`, add `WHERE` on `classFqn` or `name`.
6. **After 2-3 retries** still empty, fall back to Grep and tell the user.
</retry_protocol>

<anti_patterns>
## Common mistakes to AVOID

- Don't skip `onelens_status` — it tells you what's available.
- Don't invent graph names — parse `available_graphs` from status.
- Don't use snake_case in Cypher — properties are camelCase.
- Don't use variable-length paths (`[:CALLS*1..3]`) — use explicit hops.
- Don't query without `LIMIT` — graphs can have 200K+ nodes.
- Don't use `onelens_search` for impact/trace — that's `onelens_query`.
- Don't use `onelens_query` for name lookup — that's `onelens_search`.
- Don't search class names for cross-entity references — "Does Order link to
  Customer?" is answered by traversing edges, not by a class named "OrderCustomer".
- Don't treat "0 callers" as dead code without checking OVERRIDES,
  ANNOTATED_WITH (@Scheduled, @EventListener, @PostConstruct), and reflection.
- Don't stop at abstract declarations — `(caller)-[:CALLS]->(abstract_method)`
  means the real implementation lives on subclasses via OVERRIDES.
- Don't claim a bug from graph reachability alone — read the actual source
  code at `file:line` before asserting "off-by-one" or "dead branch".
</anti_patterns>

<reading_code>
## After finding code — read it

Both tools return `filePath` and `fqn` but NOT full source code. After finding
the relevant node:

1. Use the `Read` tool on the `file` / `filePath` value to see actual code.
2. Method FQNs include the method name + params — use to locate it in the file.
3. For Vue components, `filePath` is relative to the project root.

Pattern: **search → read**. Find candidates via graph, then read source for logic.
Graph tells you WHERE and WHAT CONNECTS. Source tells you HOW.
</reading_code>

<references_index>
## Reference files — load for advanced patterns

| File | Load when |
|------|-----------|
| `references/recipes.md` | First stop for complex multi-step queries (20+ real recipes) |
| `references/graph-schema.md` | Complete property list for every node + edge |
| `references/queries-code.md` | Advanced Java code patterns (polymorphism, generics) |
| `references/queries-sql.md` | SQL migration, table/column lineage, report impact |
| `references/queries-tests.md` | Test coverage queries |
| `references/jvm.md` | Spring/JPA deep patterns (@Qualifier, bean graph, @MappedSuperclass) |
| `references/vue3.md` | Vue 3 specific patterns |
| `references/capabilities.md` | What each capability flag means |
</references_index>
