"""Pre-built Cypher queries for impact analysis.

All property names use camelCase to match the JSON export schema:
  - classFqn, filePath, lineStart, lineEnd, httpMethod, handlerMethodFqn, etc.

FalkorDB does NOT support variable-length paths ([:CALLS*1..N]).
Use explicit multi-hop OPTIONAL MATCH instead.
"""


def find_callers(method_fqn: str, depth: int = 2) -> tuple[str, dict]:
    """Find all methods that call the given method (transitive, up to 3 hops).

    Returns (cypher, params) tuple for parameterized execution.
    """
    # FalkorDB can't do *1..N, so use explicit hops with UNION
    if depth >= 3:
        cypher = """
            MATCH (c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c1.fqn AS caller, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
            UNION
            MATCH (c2:Method)-[:CALLS]->(c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c2.fqn AS caller, c2.classFqn AS className, c2.filePath AS file, 2 AS depth
            UNION
            MATCH (c3:Method)-[:CALLS]->(c2:Method)-[:CALLS]->(c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c3.fqn AS caller, c3.classFqn AS className, c3.filePath AS file, 3 AS depth
        """
    elif depth == 2:
        cypher = """
            MATCH (c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c1.fqn AS caller, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
            UNION
            MATCH (c2:Method)-[:CALLS]->(c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c2.fqn AS caller, c2.classFqn AS className, c2.filePath AS file, 2 AS depth
        """
    else:
        cypher = """
            MATCH (c1:Method)-[:CALLS]->(target:Method {fqn: $fqn})
            RETURN DISTINCT c1.fqn AS caller, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
        """
    return cypher, {"fqn": method_fqn}


def find_callees(method_fqn: str, depth: int = 2) -> tuple[str, dict]:
    """Find all methods called by the given method (transitive, up to 3 hops)."""
    if depth >= 3:
        cypher = """
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)
            RETURN DISTINCT c1.fqn AS callee, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
            UNION
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)-[:CALLS]->(c2:Method)
            RETURN DISTINCT c2.fqn AS callee, c2.classFqn AS className, c2.filePath AS file, 2 AS depth
            UNION
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)-[:CALLS]->(c2:Method)-[:CALLS]->(c3:Method)
            RETURN DISTINCT c3.fqn AS callee, c3.classFqn AS className, c3.filePath AS file, 3 AS depth
        """
    elif depth == 2:
        cypher = """
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)
            RETURN DISTINCT c1.fqn AS callee, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
            UNION
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)-[:CALLS]->(c2:Method)
            RETURN DISTINCT c2.fqn AS callee, c2.classFqn AS className, c2.filePath AS file, 2 AS depth
        """
    else:
        cypher = """
            MATCH (source:Method {fqn: $fqn})-[:CALLS]->(c1:Method)
            RETURN DISTINCT c1.fqn AS callee, c1.classFqn AS className, c1.filePath AS file, 1 AS depth
        """
    return cypher, {"fqn": method_fqn}


def blast_radius(file_path: str) -> tuple[str, dict]:
    """Find all code affected by changes to a file (2-hop callers)."""
    cypher = """
        MATCH (m:Method {filePath: $filePath})
        MATCH (c1:Method)-[:CALLS]->(m)
        RETURN DISTINCT c1.fqn AS affectedMethod, c1.classFqn AS className, c1.filePath AS file
        UNION
        MATCH (m:Method {filePath: $filePath})
        MATCH (c2:Method)-[:CALLS]->(c1:Method)-[:CALLS]->(m)
        RETURN DISTINCT c2.fqn AS affectedMethod, c2.classFqn AS className, c2.filePath AS file
    """
    return cypher, {"filePath": file_path}


def endpoint_trace(path: str) -> tuple[str, dict]:
    """Trace HTTP endpoint -> controller -> service -> repository."""
    cypher = """
        MATCH (e:Endpoint) WHERE e.path CONTAINS $path
        MATCH (handler:Method)-[:HANDLES]->(e)
        RETURN e.path AS endpoint, e.httpMethod AS method, handler.fqn AS handler
        UNION
        MATCH (e:Endpoint) WHERE e.path CONTAINS $path
        MATCH (handler:Method)-[:HANDLES]->(e)
        MATCH (handler)-[:CALLS]->(d1:Method)
        RETURN e.path AS endpoint, e.httpMethod AS method, d1.fqn AS handler
        UNION
        MATCH (e:Endpoint) WHERE e.path CONTAINS $path
        MATCH (handler:Method)-[:HANDLES]->(e)
        MATCH (handler)-[:CALLS]->(d1:Method)-[:CALLS]->(d2:Method)
        RETURN e.path AS endpoint, e.httpMethod AS method, d2.fqn AS handler
    """
    return cypher, {"path": path}


def find_class(name: str) -> tuple[str, dict]:
    """Search for classes by name pattern."""
    cypher = """
        MATCH (c:Class) WHERE c.name CONTAINS $name
        RETURN c.fqn, c.kind, c.filePath LIMIT 20
    """
    return cypher, {"name": name}


def unused_methods() -> tuple[str, dict]:
    """List methods that are never called."""
    cypher = """
        MATCH (m:Method)
        WHERE NOT EXISTS { MATCH ()-[:CALLS]->(m) }
        AND m.name <> '<init>'
        AND (m.external IS NULL OR m.external = false)
        RETURN m.fqn, m.classFqn, m.filePath LIMIT 50
    """
    return cypher, {}
