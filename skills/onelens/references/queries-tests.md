# Test surface — Cypher patterns

Gated by `onelens_status.capabilities.has_tests`. OneLens dual-labels every
test method as `:Method:TestCase` with a structured classification.

`testKind` vocabulary (fixed across projects for portable queries):

| Kind | Detected via |
|---|---|
| `unit` | `@Test` with no Spring annotation in the class hierarchy |
| `unit-mocked` | `@ExtendWith(MockitoExtension.class)` anywhere in chain |
| `integration` | `@SpringBootTest` anywhere in chain (**superclass or meta-annotation** — resolved via IntelliJ's `AnnotationUtil.CHECK_HIERARCHY`) |
| `slice-jpa` | `@DataJpaTest` |
| `slice-web` | `@WebMvcTest` |
| `slice-json` | `@JsonTest` |
| `slice-rest-client` | `@RestClientTest` |
| `slice-other` | other `@AutoConfigureXxx` slices |
| `bdd` | Cucumber step def (`@Given` / `@When` / `@Then` / `@And`) |
| `unknown` | has `@Test` but classification failed |

Properties worth querying: `tags` (comma-joined `@Tag` values),
`activeProfiles`, `disabled`, `usesMockito`, `usesTestcontainers`,
`displayName`, `testClass`, `springBootApp`.

Edges:
- `:TestCase -[:TESTS]-> :Method` — derived from direct CALLS where target
  isn't a test (depth 1)
- `:Class -[:MOCKS]-> :SpringBean` — from `@MockBean` fields on the test class
- `:Class -[:SPIES]-> :SpringBean` — from `@SpyBean` fields

---

## Split — how many of each kind?

```cypher
MATCH (t:TestCase) RETURN t.testKind, count(t) AS n
ORDER BY n DESC
```

## Tests exercising a production method

```cypher
MATCH (t:TestCase)-[:TESTS]->(m:Method {fqn:$fqn})
RETURN t.fqn, t.testKind, t.disabled
```

## Tests covering a JPA entity

```cypher
MATCH (t:TestCase)-[:TESTS]->(m:Method)<-[:HAS_METHOD]-(c:Class:JpaEntity {tableName:$table})
RETURN DISTINCT t.fqn, t.testKind
```

## Tests that mock a bean

```cypher
MATCH (testClass:Class)-[:MOCKS]->(sb:SpringBean {name:$beanName})
RETURN testClass.fqn
```

## Beans most-mocked (refactor candidates — high mock count often signals bad cohesion)

```cypher
MATCH (:Class)-[:MOCKS]->(sb:SpringBean)
RETURN sb.name, sb.classFqn, count(*) AS mockCount
ORDER BY mockCount DESC LIMIT 20
```

## Test classes that spy on a bean

```cypher
MATCH (testClass:Class)-[:SPIES]->(sb:SpringBean {name:$beanName})
RETURN testClass.fqn
```

## Disabled tests (tech debt)

```cypher
MATCH (t:TestCase {disabled:true})
RETURN t.testKind, count(t) AS n, collect(t.fqn)[0..10] AS sample
ORDER BY n DESC
```

## Tests tagged with X

```cypher
MATCH (t:TestCase) WHERE t.tags CONTAINS $tag
RETURN t.fqn, t.testKind LIMIT 50
```

## Tag taxonomy — what categories are in use?

```cypher
MATCH (t:TestCase) WHERE t.tags <> ''
UNWIND split(t.tags, ',') AS tag
RETURN trim(tag) AS tag, count(*) AS n
ORDER BY n DESC LIMIT 30
```

## Coverage gap — production classes with zero test reach

```cypher
MATCH (c:Class)
WHERE NOT c.external AND NOT c.fqn CONTAINS '.test.'
  AND NOT EXISTS { MATCH (c)-[:HAS_METHOD]->(:Method)<-[:TESTS]-(:TestCase) }
RETURN c.fqn ORDER BY c.fqn LIMIT 50
```

## Coverage — integration tests reaching the most production code

```cypher
MATCH (t:TestCase {testKind:'integration'})-[:TESTS]->(m:Method)
WHERE NOT m.external AND NOT m.fqn CONTAINS '.test.'
RETURN t.fqn AS test, count(DISTINCT m) AS reach
ORDER BY reach DESC LIMIT 20
```

## Integration tests not running the `test` profile (config smell)

```cypher
MATCH (t:TestCase {testKind:'integration'})
WHERE NOT t.activeProfiles CONTAINS 'test'
RETURN t.fqn, t.activeProfiles LIMIT 20
```

## Mockito unit tests per service class

```cypher
MATCH (t:TestCase {testKind:'unit-mocked'})-[:TESTS]->(m:Method)<-[:HAS_METHOD]-(c:Class)
WHERE NOT c.fqn CONTAINS '.test.'
RETURN c.fqn, count(DISTINCT t) AS tests
ORDER BY tests DESC LIMIT 20
```

## Find the `:TESTS` derivation if it's missing

The `:TESTS` edge is a one-Cypher post-import derivation from direct
`:CALLS`. If `MATCH (:TestCase)-[:TESTS]->()` returns empty but
`MATCH (:TestCase)-[:CALLS]->()` works, the derivation didn't run —
re-sync or call:

```cypher
MATCH (t:TestCase)-[:CALLS]->(m:Method)
WHERE NOT m:TestCase
MERGE (t)-[:TESTS]->(m)
```

---

## Edge cases to remember

- Integration tests that **hit endpoints via HTTP** (MockMvc) aren't wired
  to `:Endpoint` nodes — the endpoint URLs are often built dynamically and
  we deliberately skip the fragile matcher. Use the `:TESTS` edge into the
  controller's handler method instead; the transitive call graph still
  reaches everything the integration test exercises.
- `@MockBean` / `@SpyBean` edges emit from the **test class**, not
  individual test methods. A single test class typically has multiple
  test methods sharing the same mocks — reflects Spring's reality.
