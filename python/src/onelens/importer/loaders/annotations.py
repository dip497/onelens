"""AnnotationLoader — owns both the full and delta annotation import paths.

Extracted from loader.py (full path, lines ~145-153 + ~494-525) and
delta_loader.py (8b block, lines ~429-490) so they cannot drift.
"""

from onelens.importer.loaders.base import SubdocLoader

# Target-kind → graph label mapping, shared by both paths.
_LABEL_BY_KIND = {"CLASS": "Class", "METHOD": "Method", "FIELD": "Field"}


def _label_for(a: dict) -> str:
    return _LABEL_BY_KIND.get(a.get("targetKind", "CLASS"), "Field")


def _attr_props(a: dict) -> dict:
    """Promote attrValues → attr_<key> flat properties, skipping empty/dynamic."""
    out: dict = {}
    for k, v in (a.get("attrValues") or {}).items():
        if not v or v == "<dynamic>":
            continue
        out[f"attr_{k}"] = v
    return out


def _edge(a: dict) -> dict:
    return {
        "src": a["targetFqn"],
        "dst": a["annotationFqn"],
        "attributes": a.get("attributes", "{}"),
        "attr_props": _attr_props(a),
    }


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


_CHUNK_SIZE = 500


class AnnotationLoader(SubdocLoader):
    json_key = "annotations"

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """Replicate loader.py full-import behavior exactly.

        1. Dedup Annotation node fqns from data["annotations"] (key annotationFqn)
           PLUS class-level annotations (data["classes"][*]["annotations"][*]["fqn"]).
        2. Write Annotation nodes via writer.batch_nodes.
        3. Group ANNOTATED_WITH edges by target label, write via writer.batch_annotation_edges.
        """
        classes = data.get("classes", [])

        # Deduplicate annotation FQNs — same logic as loader.py lines 145-153.
        ann_fqns: set = set()
        for a in data.get("annotations", []):
            ann_fqns.add(a.get("annotationFqn", ""))
        for cls in classes:
            for a in cls.get("annotations", []):
                ann_fqns.add(a.get("fqn", ""))
        ann_fqns.discard("")
        ann_nodes = [{"fqn": fqn, "name": fqn.split(".")[-1]} for fqn in ann_fqns]
        writer.batch_nodes(progress, "Annotations", ann_nodes, "Annotation", "fqn", ["name"])

        # Group edges by target label — mirrors loader.py lines 505-525.
        ann_groups: dict[str, list] = {"Class": [], "Method": [], "Field": []}
        for a in data.get("annotations", []):
            label = _label_for(a)
            ann_groups[label].append(_edge(a))
        for label, edges in ann_groups.items():
            if edges:
                writer.batch_annotation_edges(progress, label, edges)

    def apply_delta(self, writer, upserted: dict, wing: str) -> None:
        """Replicate delta_loader.py 8b block exactly.

        1. MERGE Annotation nodes (dedup on annotationFqn).
        2. Per label, DELETE existing ANNOTATED_WITH on upserted targets.
        3. Per label, CREATE fresh edges with SET r += edge.attr_props.
        """
        annotations = upserted.get("annotations", [])
        if not annotations:
            return

        # MERGE target Annotation nodes (dedup on fqn).
        ann_fqns = sorted({a["annotationFqn"] for a in annotations if a.get("annotationFqn")})
        for batch in _chunks(ann_fqns, _CHUNK_SIZE):
            writer.db.execute(
                "UNWIND $batch AS fqn MERGE (a:Annotation {fqn: fqn}) "
                "ON CREATE SET a.name = split(fqn, '.')[-1]",
                {"batch": batch},
            )

        # Drop old edges per target label.
        by_label: dict[str, list] = {"Class": [], "Method": [], "Field": []}
        for a in annotations:
            by_label[_label_for(a)].append(a["targetFqn"])
        for label, fqns in by_label.items():
            unique = sorted(set(fqns))
            for batch in _chunks(unique, _CHUNK_SIZE):
                writer.db.execute(
                    f"UNWIND $batch AS fqn "
                    f"MATCH (n:{label} {{fqn: fqn}})-[r:ANNOTATED_WITH]->() DELETE r",
                    {"batch": batch},
                )

        # Create fresh edges.
        edges_by_label: dict[str, list] = {"Class": [], "Method": [], "Field": []}
        for a in annotations:
            edges_by_label[_label_for(a)].append(_edge(a))
        for label, edges in edges_by_label.items():
            for batch in _chunks(edges, _CHUNK_SIZE):
                writer.db.execute(
                    f"UNWIND $batch AS edge "
                    f"MATCH (n:{label} {{fqn: edge.src}}), (a:Annotation {{fqn: edge.dst}}) "
                    f"CREATE (n)-[r:ANNOTATED_WITH {{attributes: edge.attributes}}]->(a) "
                    f"SET r += edge.attr_props",
                    {"batch": batch},
                )
