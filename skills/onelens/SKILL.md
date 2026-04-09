---
name: onelens
description: >
  Query the OneLens code knowledge graph to understand a Java/Spring Boot codebase.
  Use this skill whenever the user asks about code impact, dependencies, call chains,
  blast radius, Spring bean wiring, REST endpoint tracing, inheritance hierarchies,
  or "what calls/uses this class/method". Also use when the user asks "what breaks if
  I change X", "who depends on X", "trace this endpoint", or any question about code
  relationships. Even if the user doesn't mention OneLens or graphs — if the question
  is about understanding relationships between classes, methods, services, or endpoints
  in the codebase, use this skill.
---

# OneLens: Code Knowledge Graph

You have access to a knowledge graph of a Java/Spring Boot codebase stored in FalkorDB.
It contains 100% accurate type-resolved data exported from IntelliJ's PSI engine.

## How to Query

Run Cypher queries via the CLI:

```bash
~/.onelens/venv/bin/onelens query "<CYPHER>" --graph <project-name>
```

To find available graphs: `~/.onelens/venv/bin/onelens stats --graph <name>`

## Graph Schema

### Nodes

| Label | Key Properties | Description |
|-------|---------------|-------------|
| Class | fqn, name, kind, filePath, packageName, superClass | Classes, interfaces, enums, records |
| Method | fqn, name, classFqn, returnType, isConstructor, filePath, lineStart | Methods and constructors |
| Field | fqn, name, classFqn, type, filePath | Fields |
| SpringBean | name, classFqn, scope, type | Spring-managed beans (SERVICE, COMPONENT, REPOSITORY, REST_CONTROLLER) |
| Endpoint | id, path, httpMethod, handlerMethodFqn | REST API endpoints |
| Module | name, type, sourceRoots | Maven/Gradle modules |
| Annotation | fqn, name | Java annotations |

### Edges

| Type | From → To | Meaning |
|------|-----------|---------|
| CALLS | Method → Method | Method A calls method B |
| EXTENDS | Class → Class | Class inheritance |
| IMPLEMENTS | Class → Class | Interface implementation |
| HAS_METHOD | Class → Method | Class declares this method |
| HAS_FIELD | Class → Field | Class declares this field |
| OVERRIDES | Method → Method | Method overrides parent method |
| ANNOTATED_WITH | Class/Method/Field → Annotation | Has this annotation |
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

## Approach

1. Identify the question type from the patterns above
2. Extract the class/method/endpoint name from the question
3. Build and run the Cypher query
4. Present results clearly — summarize key findings
5. Follow up if results suggest deeper questions

For broad questions like "tell me about X", combine multiple queries: class info + methods + callers + inheritance + Spring wiring.

## Tips

- Use `name` for matching, not `fqn` (unless user provides full path)
- Use `CONTAINS` for fuzzy matching with partial names
- Exclude self-calls: `WHERE caller.classFqn <> c.fqn`
- LIMIT results to 20-30 by default
- FalkorDB variable-length paths (`[:EXTENDS*1..3]`) can be slow — use explicit multi-hop MATCH instead
