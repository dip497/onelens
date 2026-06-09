"""DataFlowLoader — READS_FIELD / WRITES_FIELD / INSTANTIATES edges.

Shared edge-list builder (_build) extracted from loader.py and delta_loader.py
so the two paths cannot drift. The WRITES legitimately differ and stay
path-specific: full uses writer.batch_edges_with_props (MATCH; stubs pre-exist
from the core ext-stub pass); delta uses MATCH for field edges and MERGE-inline
for INSTANTIATES (self-creates the stub).
"""

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _build(dataflow: dict):
    """Shared builder. dataflow = the 'dataFlow' subdoc. Returns
    (reads, writes, instantiations) edge dicts — the previously-duplicated logic."""
    reads, writes = [], []
    for fa in dataflow.get("fieldAccesses", []) or []:
        e = {"src": fa.get("accessorFqn", ""), "dst": fa.get("fieldFqn", ""),
             "line": fa.get("line", 0)}
        if not e["src"] or not e["dst"]:
            continue
        (writes if fa.get("mode") == "write" else reads).append(e)
    instantiations = [{"src": i.get("methodFqn", ""), "dst": i.get("classFqn", ""),
                       "line": i.get("line", 0)}
                      for i in dataflow.get("instantiations", []) or []
                      if i.get("methodFqn") and i.get("classFqn")]
    return reads, writes, instantiations


class DataFlowLoader:
    def load_full(self, writer, progress, data):
        """Full-import write path: MATCH against pre-existing stubs via batch_edges_with_props."""
        reads, writes, instantiations = _build(data.get("dataFlow") or {})
        writer.batch_edges_with_props(progress, "READS_FIELD", reads,
                                      "Method", "fqn", "Field", "fqn", ["line"])
        writer.batch_edges_with_props(progress, "WRITES_FIELD", writes,
                                      "Method", "fqn", "Field", "fqn", ["line"])
        writer.batch_edges_with_props(progress, "INSTANTIATES", instantiations,
                                      "Method", "fqn", "Class", "fqn", ["line"])

    def apply_delta(self, writer, upserted, batch_size=500):
        """Delta write path: DELETE old edges, then re-create.
        Field edges MATCH existing Field nodes (external field access drops — project
        data-flow only). INSTANTIATES MERGEs the target Class stub inline."""
        upserted_method_fqn_list = [m["fqn"] for m in upserted.get("methods", [])]
        for batch in _chunks(upserted_method_fqn_list, batch_size):
            writer.db.execute(
                "UNWIND $batch AS fqn MATCH (m:Method {fqn: fqn})"
                "-[r:READS_FIELD|WRITES_FIELD|INSTANTIATES]->() DELETE r",
                {"batch": batch}
            )
        reads, writes, instantiations = _build(upserted.get("dataFlow") or {})
        for rel, edges in (("READS_FIELD", reads), ("WRITES_FIELD", writes)):
            for batch in _chunks(edges, batch_size):
                writer.db.execute(
                    f"UNWIND $batch AS edge "
                    f"MATCH (m:Method {{fqn: edge.src}}), (f:Field {{fqn: edge.dst}}) "
                    f"MERGE (m)-[:{rel} {{line: edge.line}}]->(f)",
                    {"batch": batch}
                )
        for batch in _chunks(instantiations, batch_size):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:INSTANTIATES {line: edge.line}]->(c)
            """, {"batch": batch})
