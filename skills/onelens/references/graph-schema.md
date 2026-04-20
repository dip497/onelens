# Graph schema — nodes + edges vocabulary

Labels and edges the agent can query via `onelens_query`. A given graph has
a subset — check `onelens_status.capabilities` first.

## Node labels

### Core (JVM)
| Label | Primary key | Notes |
|---|---|---|
| `Class` | `fqn` | Classes + interfaces. `packageName` / `filePath` / `external` props |
| `Method` | `fqn` | Format: `<classFqn>#<name>(<paramTypes>)`. `returnType`, `modifiers`, `pagerank` |
| `Field` | `fqn` | Format: `<classFqn>#<name>`. Dual-labelled `:Field:JpaColumn` / `:Field:EnumConstant` when applicable |
| `EnumConstant` | `fqn` | Dual-labelled with `:Field`. `argList` prop for enum-as-config |
| `Annotation` | `fqn` | One per distinct annotation type |
| `Module` | `name` | Maven / Gradle module |
| `App` | `id` | One per `@SpringBootApplication`. `scanPackages`, `rootFqn` |
| `Package` | `id` | Java package. Part of App via `[:CONTAINS]` |

### Spring
| Label | Primary key | Notes |
|---|---|---|
| `SpringBean` | `name` | `type`: SERVICE / COMPONENT / REPOSITORY / etc. `primary`, `source`, `factoryMethodFqn` |
| `Endpoint` | `id` (`<method>:<path>`) | `httpMethod`, `path`, `controllerFqn`, `handlerMethodFqn` |
| `SpringAutoConfig` | `classFqn` | Discovered from `spring.factories` / `AutoConfiguration.imports` |

### JPA (dual-labelled with `:Class` / `:Field`)
| Label | Primary key | Notes |
|---|---|---|
| `:Class:JpaEntity` | `fqn` | `tableName`, `schema` |
| `:Field:JpaColumn` | `fqn` | `columnName`, `nullable`, `unique`, `relation`, `targetEntityFqn` |
| `:Class:JpaRepository` | `fqn` | `entityFqn` — target entity type |

### SQL surface
| Label | Primary key | Notes |
|---|---|---|
| `Migration` | `id` | Flyway `V*__*.sql`. `version`, `description`, `dbKind`, `body` |
| `SqlQuery` | `id` | Custom SELECTs / reports. `filename`, `body` |
| `SqlStatement` | `id` | One per `;`-separated stmt. `opKind`, `sql`, `statementIndex` |

### Tests (dual-labelled with `:Method`)
| Label | Primary key | Notes |
|---|---|---|
| `:Method:TestCase` | `fqn` | `testKind` ∈ {unit, unit-mocked, integration, slice-jpa, slice-web, slice-json, slice-rest-client, slice-other, bdd, unknown}; `tags`, `activeProfiles`, `usesMockito`, `disabled` |

### Vue 3
| Label | Primary key | Notes |
|---|---|---|
| `Component` | `filePath` | `.vue` file |
| `Composable` | `fqn` | `module::function` |
| `Store` | `id` | Pinia `defineStore` first arg |
| `Route` | `name` | vue-router route |
| `ApiCall` | `apiCallFqn` | `method`, `path` (templated), `callerFqn` |
| `JsModule` | `filePath` | Every `.js` / `.ts` / `.vue` |
| `JsFunction` | `fqn` | Named function / exported arrow |

### Memory (palace graph — separate graph usually `onelens_palace_kg`)
| Label | Primary key | Notes |
|---|---|---|
| `Wing` | `name` | Scope container |
| `Room` | `id` | Domain slug within a wing |
| `Hall` | `id` | Namespace within a room |
| `Drawer` | `id` | Stored note / memory item |
| `Concept` | `id` | KG subject/object |

## Edges

### Code structural
`EXTENDS` · `IMPLEMENTS` · `HAS_METHOD` · `HAS_FIELD` · `HAS_ENUM_CONSTANT`
· `CALLS` · `OVERRIDES` · `ANNOTATED_WITH { attributes }`

### Spring / JPA
`HANDLES` (Method → Endpoint) · `INJECTS { field, type, qualifier }`
(SpringBean → SpringBean) · `REGISTERED_AS` (Class → SpringBean) ·
`HAS_COLUMN` (JpaEntity → JpaColumn) · `RELATES_TO { relation, field }`
(JpaEntity → JpaEntity) · `REPOSITORY_FOR` (JpaRepository → JpaEntity) ·
`QUERIES { methodName, kind }` (JpaRepository → Method)

### SQL surface
`HAS_STATEMENT { index }` (Migration / SqlQuery → SqlStatement) ·
`QUERIES_TABLE` (SqlStatement → JpaEntity) · `CREATES_TABLE` /
`ALTERS_TABLE` / `DROPS_TABLE` (SqlStatement → JpaEntity) ·
`REFERENCES_COLUMN` (SqlStatement → JpaColumn)

### Tests
`TESTS` (TestCase → Method) · `MOCKS` (Class → SpringBean) ·
`SPIES` (Class → SpringBean)

### App / Package hierarchy
`PARENT_OF` (Package → Package) · `CONTAINS` (App → Package,
Package → Class, App → Component, Package → Component)

### Vue 3
`USES_STORE { indirect }` · `USES_COMPOSABLE` · `DISPATCHES` ·
`CALLS_API` · `IMPORTS`

### Cross-stack (when JVM + Vue3 graphs co-exist)
`HITS` (ApiCall → Endpoint) — emitted when `(method, path)` normalizes
identically on both sides

## Quick introspection

```cypher
CALL db.labels()                 // every label in this graph
CALL db.relationshipTypes()      // every edge type
CALL db.propertyKeys()           // every property name ever stored
```
