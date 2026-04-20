# SQL surface — Cypher patterns

Gated by `onelens_status.capabilities.has_sql`. Powers:
- Flyway migration history → entity evolution
- Custom `.sql` reports → entity / column impact
- Column-level rename impact via `REFERENCES_COLUMN`

Node shape reminder (see `graph-schema.md`):
- `:Migration` — one per Flyway `V*__*.sql` (has `body`, `version`, `dbKind`)
- `:SqlQuery` — one per custom `.sql` file (has `filename`, `body`)
- `:SqlStatement` — one per `;`-separated statement inside a file
  (`opKind` ∈ SELECT / CREATE_TABLE / ALTER_TABLE / DROP_TABLE / UPDATE /
  INSERT / DELETE / OTHER)
- `:Class:JpaEntity` — `tableName`, `schema`
- `:Field:JpaColumn` — `columnName`, `nullable`, `unique`, `relation`

Edges:
- `(SqlQuery | Migration) -[:HAS_STATEMENT {index}]-> :SqlStatement`
- `:SqlStatement -[:QUERIES_TABLE]-> :JpaEntity` (SELECT / INSERT / UPDATE / DELETE)
- `:SqlStatement -[:CREATES_TABLE | :ALTERS_TABLE | :DROPS_TABLE]-> :JpaEntity`
- `:SqlStatement -[:REFERENCES_COLUMN]-> :JpaColumn` (column-level precision)

---

## Which migrations touched entity X?

```cypher
MATCH (m:Migration)-[:HAS_STATEMENT]->(s:SqlStatement)
     -[r:CREATES_TABLE|ALTERS_TABLE|DROPS_TABLE]->(:JpaEntity {tableName:$t})
RETURN m.version, m.description, s.opKind, type(r)
ORDER BY toInteger(m.version)
```

## Entity-rename impact — "which reports break if I rename column Y?"

```cypher
MATCH (q:SqlQuery)-[:HAS_STATEMENT]->(s:SqlStatement)
     -[:REFERENCES_COLUMN]->(c:JpaColumn {columnName:$col})
     <-[:HAS_COLUMN]-(e:JpaEntity {tableName:$table})
RETURN DISTINCT q.filename, s.opKind
```

For a whole-entity rename (no column filter):

```cypher
MATCH (q:SqlQuery)-[:HAS_STATEMENT]->(s:SqlStatement)
     -[:QUERIES_TABLE]->(:JpaEntity {tableName:$table})
RETURN DISTINCT q.filename
```

## Show the exact SELECT that touches X

```cypher
MATCH (q:SqlQuery)-[:HAS_STATEMENT]->(s:SqlStatement)
     -[:QUERIES_TABLE]->(:JpaEntity {tableName:$table})
RETURN q.filename, s.sql LIMIT 5
```

## Full file body (when user wants to read the whole script)

```cypher
MATCH (q:SqlQuery {filename:$filename}) RETURN q.body
```

## Column popularity — which columns get queried the most

```cypher
MATCH (:SqlStatement)-[:REFERENCES_COLUMN]->(c:JpaColumn)
      <-[:HAS_COLUMN]-(e:JpaEntity)
RETURN e.tableName, c.columnName, count(*) AS hits
ORDER BY hits DESC LIMIT 20
```

## Entities per report (coupling — refactor candidates)

```cypher
MATCH (q:SqlQuery)-[:HAS_STATEMENT]->(s:SqlStatement)
     -[:QUERIES_TABLE]->(e:JpaEntity)
RETURN q.filename, count(DISTINCT e) AS entities
ORDER BY entities DESC LIMIT 10
```

## Migration timeline for a table

```cypher
MATCH (m:Migration)-[:HAS_STATEMENT]->(:SqlStatement)
     -[r]->(:JpaEntity {tableName:$table})
WHERE type(r) STARTS WITH 'CREATES_' OR type(r) STARTS WITH 'ALTERS_' OR type(r) STARTS WITH 'DROPS_'
RETURN m.version, m.description, m.dbKind, type(r) AS op
ORDER BY toInteger(m.version)
```

## Repository → entity + derived queries

```cypher
MATCH (r:JpaRepository {classFqn:$repoFqn})-[:REPOSITORY_FOR]->(e:JpaEntity)
OPTIONAL MATCH (r)-[:QUERIES]->(m:Method)
RETURN e.tableName, collect(m.fqn) AS derivedQueries
```

## Entity relations (foreign-key-style `RELATES_TO`)

```cypher
MATCH (e:JpaEntity {tableName:$table})-[r:RELATES_TO]->(other:JpaEntity)
RETURN r.relation, r.field, other.tableName
```

## Java field ↔ DB column side-by-side

Because `JpaColumn` is dual-labelled with `Field`, a single node carries
both views:

```cypher
MATCH (e:JpaEntity {tableName:$table})-[:HAS_COLUMN]->(c:Field:JpaColumn)
RETURN c.name AS javaField, c.columnName AS dbColumn,
       c.nullable, c.relation, c.targetEntityFqn
```

---

## Matching semantics (read once, internalise)

- Table names are compared **case-insensitively** at import time — writing
  `MATCH (e:JpaEntity {tableName:$t})` expects the user's `$t` in the
  same case the DB uses (usually PascalCase or snake_case).
- `REFERENCES_COLUMN` resolves columns via an **inheritance-aware walk**
  (depth 6): if `Request` extends `TicketBase`, `priorityId` declared on
  TicketBase is still resolved correctly for SQL against the flat `Request`
  table. So `c.columnName = 'priorityId'` matches either side.
- Unqualified columns in multi-FROM SQL statements are **not** bound (we'd
  have to guess which table). Expect ~80% of column refs to resolve on
  typical codebases.
- DDL column-level tracking (CREATES_COLUMN / ALTERS_COLUMN) is NOT yet
  emitted — only table-level. Deferred to a future phase.

---

## When the pattern returns empty

1. Confirm `onelens_status.capabilities.has_sql = true` — if false, no SQL
   is indexed for this graph; say so plainly.
2. Confirm the user's table / column casing matches the DB schema.
3. Check the SQL file actually parsed — the statement might be an opaque
   DO block or PG-specific function (`opKind: OTHER`) with no extracted
   tables.
