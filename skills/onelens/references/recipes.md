# OneLens Recipes — canonical multi-step queries for common intents

Load this when the user's question matches one of the patterns below.
Each recipe assumes you've already run `onelens_status` and confirmed the
relevant `capabilities.*` flags.

Every Cypher snippet is written for FalkorDB dialect (no `=~`, no
variable-length paths, camelCase properties). Adjust the `--graph` and
placeholder tokens in `<angle brackets>` for the user's project.

---

## 1. "Find X entity / table / endpoint / service"

**Goal:** locate the canonical node(s) for a user-named thing.

```cypher
// Prefer CONTAINS over exact match when the user gave a short name.
// Strip test-class noise unless the user is asking about tests.
MATCH (n) WHERE n.name CONTAINS '<token>' AND NOT n.external
  AND NOT (n:Class AND (n.fqn CONTAINS 'Test' OR n.fqn CONTAINS '.test.'))
  AND NOT (n:Method AND n:TestCase)
RETURN labels(n) AS labels, n.name AS name, n.fqn AS fqn, n.filePath AS path
LIMIT 20
```

If label filter narrows correctly:
```cypher
MATCH (e:JpaEntity) WHERE toLower(e.name) CONTAINS '<token>'
RETURN e.name, e.table, e.fqn LIMIT 10
```

---

## 2. "Impact of changing method X"

**Flag:** `has_structural`.

```cypher
// Step 1 — resolve the method.
MATCH (m:Method)
WHERE m.fqn CONTAINS '<FQN-fragment>' OR m.name = '<methodName>'
RETURN m.fqn LIMIT 5

// Step 2 — callers (one hop, explicit; no variable-length).
MATCH (caller:Method)-[:CALLS]->(target:Method)
WHERE target.fqn = '<exact-fqn-from-step-1>'
RETURN caller.fqn, caller.classFqn LIMIT 30

// Step 3 — reach REST endpoints (two hops explicit).
MATCH (h:Method)-[:HANDLES]-(e:Endpoint)
WHERE EXISTS {
  MATCH (h)-[:CALLS]->(mid:Method)-[:CALLS]->(tgt:Method)
  WHERE tgt.fqn = '<exact-fqn>'
}
RETURN e.method, e.path, h.fqn LIMIT 20
```

---

## 3. "What REST endpoints touch a column / table?"

**Flags:** `has_sql` + `has_jpa` + `has_structural`.

```cypher
// Columns referenced by a table.
MATCH (q:SqlQuery)-[:REFERENCES_TABLE]->(t:JpaEntity {table: '<table>'})
MATCH (q)<-[:DECLARES_QUERY]-(repo:JpaRepository)-[:HAS_METHOD]->(rm:Method)
MATCH (handler:Method)-[:CALLS]->(rm)
MATCH (handler)-[:HANDLES]-(ep:Endpoint)
RETURN ep.method, ep.path, handler.fqn, q.sql LIMIT 30
```
If `has_jpa=false`: drop the SqlQuery leg, grep migrations.

---

## 4. "Which tests cover method / endpoint X?"

**Flag:** `has_tests`.

```cypher
// TestCase ∪ Method dual-label; filter by :TESTS edge.
MATCH (t:TestCase)-[:TESTS]->(m:Method)
WHERE m.fqn CONTAINS '<FQN-fragment>'
RETURN t.classFqn, t.name, t.testKind LIMIT 20

// Or by endpoint path:
MATCH (t:TestCase)-[:TESTS]->(m:Method)-[:HANDLES]-(e:Endpoint {path: '<path>'})
RETURN t.classFqn, t.name LIMIT 20
```

---

## 5. "Spring bean graph for service X"

**Flag:** `has_spring`.

```cypher
// Injection fan-in.
MATCH (b:SpringBean)-[:INJECTS]->(target:SpringBean)
WHERE target.name CONTAINS '<service>'
RETURN b.name, b.scope, b.primary LIMIT 30

// Qualifier disambiguation.
MATCH (b:SpringBean)-[r:INJECTS]->(t:SpringBean)
WHERE r.qualifier IS NOT NULL
RETURN b.name, r.qualifier, t.name LIMIT 20
```

---

## 6. "Which migrations created / altered table X?"

**Flag:** `has_sql`.

```cypher
MATCH (m:Migration)-[:CONTAINS]->(s:SqlStatement)
WHERE s.opKind IN ['CREATE_TABLE','ALTER_TABLE']
  AND any(t IN s.tableNames WHERE toLower(t) = toLower('<table>'))
RETURN m.name, s.opKind, s.sql
ORDER BY m.name LIMIT 30
```

---

## 7. "How does feature Y work?" (conceptual)

**Flag:** `has_semantic` — ONLY then.

```bash
onelens call-tool onelens_retrieve --query "<3-10 word phrase>" --graph <name>
```
If `has_semantic=false`: use `onelens_search` with several tokens + read
top-3 source snippets. Don't reinvent via Cypher for conceptual asks.

---

## 8. "Dead code / unused public methods"

**Flag:** `has_structural`.

```cypher
MATCH (m:Method) WHERE NOT m.external
  AND NOT EXISTS { MATCH ()-[:CALLS]->(m) }
  AND NOT EXISTS { MATCH (m)-[:HANDLES]-(:Endpoint) }
  AND NOT EXISTS { MATCH (m)<-[:OVERRIDES]-() }
  AND m.visibility = 'public'
RETURN m.fqn, m.classFqn, m.pagerank
ORDER BY m.pagerank DESC LIMIT 30
```

---

## 9. "Cross-stack: Vue component → backend endpoint"

**Flags:** `has_vue3` + `has_structural` (single combined graph).

```cypher
MATCH (c:Component)-[:USES]->(api:ApiCall)-[:HITS]->(ep:Endpoint)
WHERE c.name CONTAINS '<component>'
RETURN c.name, api.path, ep.method, ep.path LIMIT 30
```

---

## 10. "Annotations with specific attribute"

```cypher
// e.g. all @RequestMapping with method=GET
MATCH (m:Method)-[r:ANNOTATED_WITH]->(a:Annotation)
WHERE a.name = 'RequestMapping' AND r.attributes CONTAINS '"GET"'
RETURN m.fqn, r.attributes LIMIT 20
```

Use `CONTAINS` on the `attributes` JSON — it's a string map, substring
match works for most filters.

---

## 11. "JPA entity → actual SQL table / column name"

**Why:** when writing raw SQL against JPA-mapped tables, you must know the
physical name. `@Table(name=…)` overrides; otherwise Hibernate's
naming-strategy transforms (PascalCase entity → snake_case table, by
default `SpringPhysicalNamingStrategy`).

```cypher
// Explicit @Table annotation value.
MATCH (e:JpaEntity {name: '<Entity>'})-[r:ANNOTATED_WITH]->(a:Annotation {name: 'Table'})
RETURN r.attributes LIMIT 1

// Explicit @Column on fields (physical column name override).
MATCH (e:JpaEntity {name: '<Entity>'})-[:HAS_FIELD]->(f:Field)
       -[r:ANNOTATED_WITH]->(a:Annotation {name: 'Column'})
RETURN f.name AS javaField, r.attributes LIMIT 30
```

If no `@Table` / `@Column`, physical name = snake_case of Java name under
default Spring naming strategy. Confirm by grepping the user's
`application.properties` for `spring.jpa.hibernate.naming.physical-strategy`
— custom strategies change the mapping.

**When `JpaEntity.tableName` comes back `NULL`** (collector couldn't resolve
it at import time): walk the inheritance chain — `@Table` often sits on an
abstract base.

```cypher
MATCH (e:JpaEntity {name: '<Entity>'})-[:EXTENDS*1..5]->(parent:Class)
       -[r:ANNOTATED_WITH]->(a:Annotation {name: 'Table'})
RETURN parent.name, r.attributes LIMIT 1
```

If still unresolved, read the entity's source file (`e.filePath:1`) — the
annotation value is right there. Do not silently assume `toLower(name)`
on enterprise projects; they often have abbreviations (`ReqEntity`
→ `request`, not `req_entity`).

## 12. "Does entity A reference / link to concept B?"

**The reference rarely lives in a class name.** Scan six places — run the
likely one, or all six when unsure which layer carries the link:

```cypher
// a) FK column (most common on JPA projects)
MATCH (e:JpaEntity)-[:HAS_COLUMN]->(c:JpaColumn)
WHERE toLower(c.name) CONTAINS '<b>' OR toLower(c.columnName) CONTAINS '<b>'
RETURN e.name, c.name, c.columnName LIMIT 30

// b) Java field type (POJO / DTO composition)
MATCH (e:Class)-[:HAS_FIELD]->(f:Field)
WHERE f.typeFqn CONTAINS '<B>' AND NOT e.external
RETURN e.name, f.name, f.typeFqn LIMIT 30

// c) Method signature (param / return / throws)
MATCH (m:Method)
WHERE m.returnType CONTAINS '<B>'
   OR any(p IN m.parameterTypes WHERE p CONTAINS '<B>')
RETURN m.fqn, m.parameterTypes, m.returnType LIMIT 30

// d) Annotation attribute — JPQL, path vars, config refs hide here
MATCH (n)-[r:ANNOTATED_WITH]->(:Annotation)
WHERE toLower(r.attributes) CONTAINS '<b>'
RETURN labels(n)[0] AS kind, n.name, r.attributes LIMIT 30

// e) Raw SQL / migration body (only if has_sql=true)
MATCH (s:SqlStatement) WHERE toLower(s.sql) CONTAINS '<b>'
RETURN s.opKind, s.sql LIMIT 20

// f) Enum-as-config registry (args list)
MATCH (ec:EnumConstant) WHERE any(a IN ec.argList WHERE toLower(a) CONTAINS '<b>')
RETURN ec.classFqn, ec.name, ec.argList LIMIT 30
```

If all six come back empty, the reference genuinely isn't in the graph —
then grep source / config / YAML.

## 13. "What runs on startup / schedule / on event?"

Entry points are NOT just REST endpoints. Union these:

```cypher
// Lifecycle + scheduled + event-driven + app runners
MATCH (m:Method)-[r:ANNOTATED_WITH]->(a:Annotation)
WHERE a.name IN ['PostConstruct','PreDestroy','EventListener',
                 'Scheduled','ApplicationRunner','CommandLineRunner',
                 'KafkaListener','RabbitListener','JmsListener']
RETURN a.name AS trigger, m.fqn, r.attributes
ORDER BY trigger LIMIT 80

// REST handlers
MATCH (m:Method)-[:HANDLES]-(e:Endpoint) RETURN e.method, e.path, m.fqn LIMIT 50

// Factory-method beans (init-style)
MATCH (sb:SpringBean) WHERE sb.factoryMethodFqn IS NOT NULL
RETURN sb.name, sb.factoryMethodFqn LIMIT 30
```

## 14. "Is method X really dead code? (0 CALLS callers)"

Before declaring dead, rule out four invisible-caller classes:

```cypher
// 1 — REST handler?
MATCH (m:Method {fqn:'<fqn>'})-[:HANDLES]-(e:Endpoint) RETURN e.method, e.path
// 2 — framework-invoked (lifecycle/scheduled/event/listener)?
MATCH (m:Method {fqn:'<fqn>'})-[:ANNOTATED_WITH]->(a:Annotation)
WHERE a.name IN ['PostConstruct','PreDestroy','Scheduled','EventListener',
                 'ApplicationRunner','CommandLineRunner',
                 'KafkaListener','RabbitListener','JmsListener','Async']
RETURN a.name
// 3 — polymorphic dispatch (someone calls the abstract parent)?
MATCH (m:Method {fqn:'<fqn>'})-[:OVERRIDES]->(parent:Method)
MATCH (caller:Method)-[:CALLS]->(parent) WHERE caller <> m
RETURN caller.fqn LIMIT 20
// 4 — override direction (callers of children reach you through super)?
MATCH (m:Method {fqn:'<fqn>'})<-[:OVERRIDES]-(child:Method)
RETURN child.fqn LIMIT 20
```

Then grep source for reflection: `Class.forName`, `getBean(`, `.invoke(`,
`MethodHandle`, `ApplicationContext.getBean`. Only after all five
signals come back empty → genuinely dead.

## 15. Schema exploration — "what's in this graph?"

Prefer `onelens_status` first — it already ships `counts` (per label) and
`edge_counts` (per type). Use these only for property-key discovery or
when touching an unfamiliar graph:

```cypher
CALL db.labels()
CALL db.relationshipTypes()
CALL db.propertyKeys()
```

Then probe a single node's properties:

```cypher
MATCH (n:<Label>) RETURN keys(n) AS props, n LIMIT 1
```

## 16. "Diff two release snapshots" (API churn, regression hunt)

Assumes both `<graph>@<tag-a>` and `<graph>@<tag-b>` are installed locally
(via `onelens_snapshots_pull` or a manual restore). FalkorDB Lite holds
one graph per query, so the pattern is: run same Cypher against both,
set-diff client-side.

### Endpoint surface diff (removed in b, added in b)

```cypher
// Run on `<graph>@<tag-a>` (old)
MATCH (e:Endpoint) RETURN e.method + ':' + e.path AS id
// Run on `<graph>@<tag-b>` (new) — compare result sets client-side.
```

### Method signature drift (same FQN, different return/param types)

```cypher
// On each snapshot, independently:
MATCH (m:Method) WHERE NOT m.external
RETURN m.fqn AS fqn, m.returnType AS ret, m.parameterTypes AS params
// Join the two payloads client-side on fqn; flag rows where ret/params differ.
```

### Dead-code delta (methods present in a, absent in b)

```cypher
MATCH (m:Method) WHERE NOT m.external RETURN m.fqn
// Difference of the two result sets is the removed-method set.
```

### SQL migration inventory between tags

```cypher
MATCH (mig:Migration) RETURN mig.name
ORDER BY mig.name
// Migrations present in b but not a = delta applied between releases.
```

**Important:** FalkorDB can't `UNION` across graphs in one query. Invoke
`onelens_query` twice (once per graph) and compute the set-diff in your
answer. Keep `LIMIT` discipline — even at 2k endpoints, two calls + a
client-side diff costs nothing.

## Answer-synthesis checklist

After the final query lands:

1. Cite specific nodes: `ClassName#method(ArgType)` with `file:line`.
2. State the edge that proves the claim — don't assert behavior from
   reachability alone. (Structural → "is called from", not "runs at
   runtime" — verify predicates before claiming execution.)
3. If the result is empty and predicates look right, say "no match in
   the graph" — don't invent synonyms indefinitely.
