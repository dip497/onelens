"""High-level impact analysis functions."""

from onelens.graph.db import GraphDB
from onelens.graph import queries


def get_blast_radius(db: GraphDB, file_path: str) -> list[dict]:
    """Get all code affected by changes to a file."""
    cypher, params = queries.blast_radius(file_path)
    return db.query(cypher, params)


def get_callers(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callers of a method."""
    cypher, params = queries.find_callers(method_fqn, depth)
    return db.query(cypher, params)


def get_callees(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callees of a method."""
    cypher, params = queries.find_callees(method_fqn, depth)
    return db.query(cypher, params)


def search_code(db: GraphDB, term: str, node_type: str = "") -> list[dict]:
    """Full-text search across the knowledge graph.

    Runs separate queries per node type and merges results,
    because FalkorDB may not support UNION with CALL...YIELD.
    """
    results = []
    types_to_search = [node_type] if node_type else ["class", "method", "endpoint"]

    for nt in types_to_search:
        cypher, params = queries.search(term, nt)
        try:
            results.extend(db.query(cypher, params))
        except Exception:
            pass  # FTS index may not exist for this type yet
    return results


def get_entry_points(db: GraphDB) -> list[dict]:
    """List all entry points in the codebase."""
    cypher, params = queries.list_entry_points()
    return db.query(cypher, params)


def _is_trivial_accessor(method_name: str, fqn: str) -> bool:
    """Check if method is a simple getter/setter (0-1 params, name starts with get/set/is)."""
    if not (method_name.startswith("get") or method_name.startswith("set") or method_name.startswith("is")):
        return False
    # Count params from FQN: Class#method(P1,P2) — count commas inside parens
    if "#" in fqn and "(" in fqn:
        params_str = fqn.split("(", 1)[1].rstrip(")")
        param_count = 0 if not params_str else params_str.count(",") + 1
        return param_count <= 1
    return True


def _compact_trace(results: list[dict], include_external: bool = False) -> list[dict]:
    """Deduplicate, filter externals and trivial accessors, and compact trace results."""
    seen = set()
    out = []
    for r in sorted(results, key=lambda x: (x.get("depth", 0), x.get("className", ""))):
        fqn = r.get("fqn", "")
        depth = r.get("depth", 0)
        key = (fqn, depth)
        if key in seen:
            continue
        seen.add(key)

        # Skip external library methods unless requested
        if not include_external and r.get("external") is True:
            continue

        # Skip trivial getters/setters at depth 2+ (reduce noise)
        method_name = r.get("method", "")
        if depth >= 2 and _is_trivial_accessor(method_name, fqn):
            continue

        # Compact: short class name, short param types, just filename
        class_fqn = r.get("className", "")
        short_class = class_fqn.rsplit(".", 1)[-1] if "." in class_fqn else class_fqn

        method_name = r.get("method", "")
        # Shorten param types: com.example.Foo → Foo
        if "(" in fqn and "#" in fqn:
            raw_sig = fqn.split("#", 1)[1]
            name_part = raw_sig.split("(")[0]
            params_part = raw_sig.split("(", 1)[1].rstrip(")")
            short_params = ",".join(p.rsplit(".", 1)[-1] for p in params_part.split(",") if p)
            method_name = f"{name_part}({short_params})"

        file_path = r.get("file", "")
        short_file = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

        line = r.get("line", 0) or 0
        endpoint = r.get("endpoint", "")
        loc = f"{short_file}:{line}" if line else short_file

        entry = {
            "depth": depth,
            "class": short_class,
            "method": method_name,
            "location": loc,
            "fqn": fqn,
        }
        if endpoint:
            entry["endpoint"] = endpoint
        out.append(entry)
    return out


def get_flow_trace(db: GraphDB, method_fqn: str, depth: int = 5,
                   include_external: bool = False) -> list[dict]:
    """Trace execution flow from a method through call chain."""
    cypher, params = queries.trace_flow(method_fqn, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def get_endpoint_flow(db: GraphDB, path: str, http_method: str = "", depth: int = 5,
                      include_external: bool = False) -> list[dict]:
    """Trace execution flow from a REST endpoint."""
    cypher, params = queries.trace_endpoint_flow(path, http_method, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def get_reverse_trace(db: GraphDB, method_fqn: str, depth: int = 5,
                      include_external: bool = False) -> list[dict]:
    """Reverse trace: from a method, trace UP to find callers and their endpoints."""
    cypher, params = queries.reverse_trace(method_fqn, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def get_impacted_endpoints(db: GraphDB, method_fqn: str, depth: int = 5) -> list[dict]:
    """Find all REST endpoints that eventually call this method.

    Returns only endpoint handlers — the key "what breaks" answer.
    """
    cypher, params = queries.impact_endpoints(method_fqn, depth)
    results = db.query(cypher, params)
    # Deduplicate and compact controller names
    seen = set()
    out = []
    for r in sorted(results, key=lambda x: x.get("endpoint", "")):
        ep = r.get("endpoint", "")
        if ep in seen:
            continue
        seen.add(ep)
        ctrl = r.get("controller", "")
        short_ctrl = ctrl.rsplit(".", 1)[-1] if "." in ctrl else ctrl
        handler = r.get("handler", "")
        file_path = r.get("file", "")
        short_file = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        line = r.get("line", 0) or 0
        loc = f"{short_file}:{line}" if line else short_file
        out.append({
            "endpoint": ep,
            "controller": short_ctrl,
            "handler": handler,
            "location": loc,
            "hops": r.get("hops", 0),
        })
    return out
