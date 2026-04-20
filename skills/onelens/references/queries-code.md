# Structural Cypher patterns

All patterns run via `onelens_query`. Replaces the old `onelens_impact` /
`onelens_trace` / `onelens_entry_points` tools — those were thin Cypher
wrappers; the patterns below are the source of truth.

Substitute `$fqn` / `$path` / `$name` with the user's input. Default
`LIMIT 20–30` unless the question wants a count.

---

## Impact — "if I change method X, what endpoints break?"

```cypher
MATCH (m:Method {fqn: $fqn})
OPTIONAL MATCH (m)<-[:OVERRIDES*0..]-(impl:Method)
WITH m, collect(DISTINCT impl) + [m] AS targets
UNWIND targets AS t
MATCH (t)<-[:CALLS*1..5]-()<-[:HANDLES]-(ep:Endpoint)
RETURN DISTINCT ep.httpMethod + ' ' + ep.path AS endpoint,
                ep.controllerFqn, ep.handlerMethodFqn
ORDER BY endpoint
```

Notes:
- `OVERRIDES*0..` picks up polymorphic dispatch (interface implementations,
  abstract method overrides).
- `CALLS*1..5` — depth-5 is usually enough. Raise to `*1..8` for
  long-chain libraries.
- For bean-type-filtered impact (narrow to controllers with a field of the
  target's type), add:
  `WHERE EXISTS { MATCH (ep.controllerFqn)<-[:HAS_FIELD]-(f:Field) WHERE f.type = $target_type }`

## Trace — endpoint → methods

```cypher
MATCH p = (:Endpoint {path:$path, httpMethod:$method})
         -[:HANDLES]-()-[:CALLS*1..3]->(m:Method)
RETURN p LIMIT 50
```

Depth 3 is the sweet spot. Bump to 5 for deep service chains.

## Trace — method → methods (forward)

```cypher
MATCH p = (:Method {fqn:$fqn})-[:CALLS*1..4]->(m:Method)
WHERE NOT m.external
RETURN p LIMIT 50
```

## Entry points — every method reachable from the outside world

```cypher
// REST endpoints
MATCH (m:Method)-[:HANDLES]->(:Endpoint) RETURN m.fqn AS entry, 'endpoint' AS kind
UNION
// @Scheduled / @PostConstruct / @EventListener (framework-driven)
MATCH (m:Method)-[:ANNOTATED_WITH]->(a:Annotation)
WHERE a.fqn IN [
  'org.springframework.scheduling.annotation.Scheduled',
  'jakarta.annotation.PostConstruct',
  'javax.annotation.PostConstruct',
  'org.springframework.context.event.EventListener'
]
RETURN m.fqn AS entry, split(a.fqn, '.')[-1] AS kind
UNION
// public static main(String[])
MATCH (m:Method {name:'main'})<-[:HAS_METHOD]-(:Class)
WHERE 'public' IN m.modifiers AND 'static' IN m.modifiers
RETURN m.fqn AS entry, 'main' AS kind
```

## Class inheritance chain

```cypher
MATCH p = (c:Class {fqn:$fqn})-[:EXTENDS*1..6]->(anc:Class)
RETURN [n IN nodes(p) | n.fqn] AS chain
```

## Callers of a method (reverse impact, 1 hop)

```cypher
MATCH (caller:Method)-[:CALLS]->(m:Method {fqn:$fqn})
RETURN caller.fqn, caller.classFqn
LIMIT 50
```

## Callers up to N hops (blast radius estimate)

```cypher
MATCH (caller:Method)-[:CALLS*1..5]->(m:Method {fqn:$fqn})
RETURN DISTINCT caller.fqn, caller.classFqn
LIMIT 100
```

## List apps / modules / packages (was `list_*` tools)

```cypher
MATCH (a:App) RETURN a.id, a.name, a.rootFqn, a.scanPackages ORDER BY a.name
MATCH (m:Module) RETURN m.name, m.type ORDER BY m.name
MATCH (p:Package) RETURN p.id, p.appId ORDER BY p.id
```

## Class → its Spring bean (and back)

```cypher
// Class → SpringBean
MATCH (c:Class {fqn:$fqn})-[:REGISTERED_AS]->(sb:SpringBean)
RETURN sb.name, sb.type, sb.primary, sb.source

// SpringBean → Class
MATCH (sb:SpringBean {name:$beanName})<-[:REGISTERED_AS]-(c:Class)
RETURN c.fqn
```

## Bean injection graph

```cypher
// What does bean X inject?
MATCH (sb:SpringBean {name:$beanName})-[i:INJECTS]->(target:SpringBean)
RETURN target.name, target.classFqn, i.field, i.qualifier

// Who injects bean X?
MATCH (user:SpringBean)-[i:INJECTS]->(:SpringBean {name:$beanName})
RETURN user.name, user.classFqn, i.field
```

## Full-stack trace (cross-stack — requires both JVM + Vue3 graphs in one FalkorDB)

```cypher
MATCH (r:Route)-[:DISPATCHES]->(comp:Component)-[:CALLS_API]->(a:ApiCall)
      -[:HITS]->(e:Endpoint)<-[:HANDLES]-(m:Method)
WHERE r.path CONTAINS $pathFragment
RETURN r.path AS route, comp.name AS component,
       a.method + ' ' + a.path AS api,
       m.fqn AS handler
LIMIT 20
```

## Orphan endpoints (no frontend call hits them)

```cypher
MATCH (e:Endpoint)
WHERE NOT (e)<-[:HITS]-()
RETURN e.httpMethod + ' ' + e.path AS unused, e.handlerMethodFqn
ORDER BY e.path LIMIT 50
```

Only meaningful when the frontend graph is also indexed.

---

## Tips

- `m.external = true` marks stub nodes for library / JDK calls — filter them
  unless you're specifically asking about external deps.
- `name` matching is usually enough; reach for `fqn` only when the user pasted one.
- For polymorphism, combine `OVERRIDES*0..` with a concrete method target.
- Impact depth: start at `*1..3`, bump only if the user needs deeper reach.
