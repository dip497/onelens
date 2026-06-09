"""TypeFlowLoader — RETURNS / THROWS / HAS_PARAMETER edges.

Shared edge-list builder (_build) extracted from loader.py and delta_loader.py
so the two paths cannot drift. The WRITES legitimately differ and stay
path-specific: full uses writer.batch_edges (MATCH; stubs pre-exist from the
core ext-stub pass); delta uses MERGE-inline (self-creates the stub).
"""

from onelens.importer.graph_writer import _normalize_type

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _build(methods):
    """Shared edge-list builder — the previously-duplicated logic.
    Returns (returns, throws, has_param) edge dicts."""
    returns, throws, has_param = [], [], []
    for m in methods:
        rt = _normalize_type(m.get("returnType", ""))
        if rt:
            returns.append({"src": m["fqn"], "dst": rt})
        for tt in m.get("throwsTypes", []) or []:
            et = _normalize_type(tt)
            if et:
                throws.append({"src": m["fqn"], "dst": et})
        for i, p in enumerate(m.get("parameters", []) or []):
            pt = _normalize_type(p.get("type", ""))
            if pt:
                has_param.append({"src": m["fqn"], "dst": pt,
                                  "position": i, "name": p.get("name", "")})
    return returns, throws, has_param


class TypeFlowLoader:
    def load_full(self, writer, progress, methods):
        """Full-import write path: MATCH against pre-existing stubs via batch_edges."""
        returns, throws, has_param = _build(methods)
        writer.batch_edges(progress, "RETURNS", returns, "Method", "fqn", "Class", "fqn")
        writer.batch_edges(progress, "THROWS", throws, "Method", "fqn", "Class", "fqn")
        writer.batch_edges_with_props(progress, "HAS_PARAMETER", has_param,
                                      "Method", "fqn", "Class", "fqn",
                                      ["position", "name"])

    def apply_delta(self, writer, methods, batch_size=500):
        """Delta write path: DELETE old edges, then MERGE-inline (self-creates stubs)."""
        fqn_list = [m["fqn"] for m in methods]
        for batch in _chunks(fqn_list, batch_size):
            writer.db.execute(
                "UNWIND $batch AS fqn MATCH (m:Method {fqn: fqn})"
                "-[r:RETURNS|THROWS|HAS_PARAMETER]->() DELETE r",
                {"batch": batch}
            )
        returns, throws, has_param = _build(methods)
        for batch in _chunks(returns, batch_size):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:RETURNS]->(c)
            """, {"batch": batch})
        for batch in _chunks(throws, batch_size):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:THROWS]->(c)
            """, {"batch": batch})
        for batch in _chunks(has_param, batch_size):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:HAS_PARAMETER {position: edge.position, name: edge.name}]->(c)
            """, {"batch": batch})
