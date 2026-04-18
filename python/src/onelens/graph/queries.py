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


# --- Semantic Search ---

def _escape_fts_term(term: str) -> str:
    """Escape single quotes in search terms for FalkorDB CALL procedures.

    FalkorDB CALL procedures take string literals, not $param placeholders.
    """
    return term.replace("\\", "\\\\").replace("'", "\\'")


def search(term: str, node_type: str = "") -> tuple[str, dict]:
    """Full-text search for a single node type.

    FalkorDB CALL procedures don't support $param — must embed term as literal.
    Call this once per node type; use search_code() in analysis.py for multi-type.

    Supports prefix (User*), fuzzy (%auth%1), and exact matching.
    """
    safe_term = _escape_fts_term(term)

    if node_type == "class":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Class', '{safe_term}') YIELD node
            RETURN 'Class' AS type, node.fqn AS fqn, node.name AS name,
                   node.filePath AS file, node.kind AS kind
        """
    elif node_type == "method":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Method', '{safe_term}') YIELD node
            WHERE node.external IS NULL
            RETURN 'Method' AS type, node.fqn AS fqn, node.name AS name,
                   node.filePath AS file, '' AS kind
        """
    elif node_type == "endpoint":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Endpoint', '{safe_term}') YIELD node
            RETURN 'Endpoint' AS type, node.id AS fqn, node.path AS name,
                   node.httpMethod AS file, '' AS kind
        """
    elif node_type == "component":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Component', '{safe_term}') YIELD node
            RETURN 'Component' AS type, ('component:' + node.filePath) AS fqn,
                   node.name AS name, node.filePath AS file, '' AS kind
        """
    elif node_type == "composable":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Composable', '{safe_term}') YIELD node
            RETURN 'Composable' AS type, ('composable:' + node.fqn) AS fqn,
                   node.name AS name, node.filePath AS file, '' AS kind
        """
    elif node_type == "store":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Store', '{safe_term}') YIELD node
            RETURN 'Store' AS type, ('store:' + node.id) AS fqn,
                   node.name AS name, node.filePath AS file, '' AS kind
        """
    elif node_type == "route":
        # Prefix matches ChromaDB drawer-id convention (`<type>:<key>`) so
        # retrieval._fetch_locations_batch's prefix-partition lookup resolves
        # FTS hits. Without the prefix, location + snippet both drop silently.
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Route', '{safe_term}') YIELD node
            RETURN 'Route' AS type, ('route:' + node.name) AS fqn,
                   node.path AS name, node.filePath AS file, '' AS kind
        """
    elif node_type == "apicall":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('ApiCall', '{safe_term}') YIELD node
            RETURN 'ApiCall' AS type, ('apicall:' + node.fqn) AS fqn,
                   node.path AS name, node.filePath AS file,
                   node.method AS kind
        """
    elif node_type == "jsmodule":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('JsModule', '{safe_term}') YIELD node
            RETURN 'JsModule' AS type, ('jsmodule:' + node.filePath) AS fqn,
                   node.filePath AS name, node.filePath AS file, '' AS kind
        """
    elif node_type == "jsfunction":
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('JsFunction', '{safe_term}') YIELD node
            RETURN 'JsFunction' AS type, ('jsfunction:' + node.fqn) AS fqn,
                   node.name AS name, node.filePath AS file, '' AS kind
        """
    else:
        # Default: search classes (caller should loop for multi-type)
        cypher = f"""
            CALL db.idx.fulltext.queryNodes('Class', '{safe_term}') YIELD node
            RETURN 'Class' AS type, node.fqn AS fqn, node.name AS name,
                   node.filePath AS file, node.kind AS kind
        """

    return cypher, {}


# --- Execution Flow Tracing ---

def list_entry_points() -> tuple[str, dict]:
    """List all entry points: REST endpoints, @Scheduled methods, main() methods."""
    cypher = """
        MATCH (handler:Method)-[:HANDLES]->(e:Endpoint)
        RETURN 'ENDPOINT' AS type, e.httpMethod + ' ' + e.path AS entry, handler.fqn AS methodFqn
        UNION
        MATCH (m:Method)-[:ANNOTATED_WITH]->(a:Annotation)
        WHERE a.fqn IN ['org.springframework.scheduling.annotation.Scheduled',
                         'javax.annotation.PostConstruct',
                         'jakarta.annotation.PostConstruct']
        RETURN 'SCHEDULED' AS type, a.name + ' ' + m.name AS entry, m.fqn AS methodFqn
        UNION
        MATCH (m:Method {name: 'main'})
        WHERE m.external IS NULL
        RETURN 'MAIN' AS type, m.classFqn AS entry, m.fqn AS methodFqn
    """
    return cypher, {}


def trace_flow(method_fqn: str, depth: int = 5) -> tuple[str, dict]:
    """Trace execution flow from a method through CALLS edges (explicit multi-hop)."""
    depth = min(depth, 5)
    parts = []
    for d in range(1, depth + 1):
        chain = "".join(f"-[:CALLS]->(c{i}:Method)" for i in range(1, d + 1))
        last = f"c{d}"
        parts.append(
            f"MATCH (root:Method {{fqn: $fqn}}){chain}\n"
            f"RETURN DISTINCT {last}.fqn AS fqn, {last}.classFqn AS className, "
            f"{last}.name AS method, {last}.filePath AS file, "
            f"{last}.lineStart AS line, {last}.external AS external, "
            f"{d} AS depth, '' AS endpoint"
        )
    cypher = "\nUNION\n".join(parts)
    return cypher, {"fqn": method_fqn}


def trace_endpoint_flow(path: str, http_method: str = "", depth: int = 5) -> tuple[str, dict]:
    """Trace from a REST endpoint through handler into the full call chain."""
    depth = min(depth, 5)

    if http_method:
        match_ep = "MATCH (e:Endpoint {path: $path, httpMethod: $httpMethod})"
        params = {"path": path, "httpMethod": http_method}
    else:
        match_ep = "MATCH (e:Endpoint) WHERE e.path CONTAINS $path"
        params = {"path": path}

    # Depth 0: the handler — include endpoint info (HTTP method + path)
    parts = [
        f"{match_ep}\n"
        f"MATCH (handler:Method)-[:HANDLES]->(e)\n"
        f"RETURN DISTINCT handler.fqn AS fqn, handler.classFqn AS className, "
        f"handler.name AS method, handler.filePath AS file, "
        f"handler.lineStart AS line, handler.external AS external, "
        f"0 AS depth, e.httpMethod + ' ' + e.path AS endpoint"
    ]

    # Depths 1..N from handler
    for d in range(1, depth + 1):
        chain = "".join(f"-[:CALLS]->(c{i}:Method)" for i in range(1, d + 1))
        last = f"c{d}"
        parts.append(
            f"{match_ep}\n"
            f"MATCH (handler:Method)-[:HANDLES]->(e)\n"
            f"MATCH (handler){chain}\n"
            f"RETURN DISTINCT {last}.fqn AS fqn, {last}.classFqn AS className, "
            f"{last}.name AS method, {last}.filePath AS file, "
            f"{last}.lineStart AS line, {last}.external AS external, "
            f"{d} AS depth, '' AS endpoint"
        )

    cypher = "\nUNION\n".join(parts)
    return cypher, params


def reverse_trace(method_fqn: str, depth: int = 5) -> tuple[str, dict]:
    """Reverse trace: from a method, trace UP through callers to find entry points.

    Returns callers at each depth AND any endpoints they handle.
    This answers: "if I change this method, which API endpoints are affected?"
    """
    depth = min(depth, 5)
    parts = []
    for d in range(1, depth + 1):
        # Build reverse chain: (cN)-[:CALLS]->...-[:CALLS]->(target)
        chain = "".join(f"(c{i}:Method)-[:CALLS]->" for i in range(d, 0, -1))
        first = f"c{d}"
        parts.append(
            f"MATCH {chain}(target:Method {{fqn: $fqn}})\n"
            f"OPTIONAL MATCH ({first})-[:HANDLES]->(e:Endpoint)\n"
            f"RETURN DISTINCT {first}.fqn AS fqn, {first}.classFqn AS className, "
            f"{first}.name AS method, {first}.filePath AS file, "
            f"{first}.lineStart AS line, {first}.external AS external, "
            f"{d} AS depth, "
            f"CASE WHEN e IS NOT NULL THEN e.httpMethod + ' ' + e.path ELSE '' END AS endpoint"
        )
    cypher = "\nUNION\n".join(parts)
    return cypher, {"fqn": method_fqn}


def impact_endpoints(method_fqn: str, depth: int = 5) -> tuple[str, dict]:
    """Find all REST endpoints that eventually call a method.

    This is the key AI agent query: "which user-facing APIs break if I change this?"
    Only returns methods that are endpoint handlers — skips intermediate callers.
    """
    depth = min(depth, 5)
    parts = []
    for d in range(1, depth + 1):
        chain = "".join(f"(c{i}:Method)-[:CALLS]->" for i in range(d, 0, -1))
        first = f"c{d}"
        parts.append(
            f"MATCH {chain}(target:Method {{fqn: $fqn}})\n"
            f"MATCH ({first})-[:HANDLES]->(e:Endpoint)\n"
            f"RETURN DISTINCT e.httpMethod + ' ' + e.path AS endpoint, "
            f"{first}.classFqn AS controller, {first}.name AS handler, "
            f"{first}.filePath AS file, {first}.lineStart AS line, {d} AS hops"
        )
    cypher = "\nUNION\n".join(parts)
    return cypher, {"fqn": method_fqn}
