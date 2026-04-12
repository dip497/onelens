"""Delta (incremental) import into any Cypher-compatible graph DB."""

import json
import logging
from pathlib import Path

from onelens.graph.db import GraphDB

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class DeltaLoader:
    def __init__(self, db: GraphDB):
        self.db = db

    def apply_delta(self, delta_path: Path) -> dict:
        """Apply a delta export to an existing graph.

        Strategy:
        1. Delete old nodes by FQN (cascade removes edges)
        2. Upsert new nodes + external stubs (batched)
        3. Upsert new edges (batched)
        """
        with open(delta_path) as f:
            data = json.load(f)

        deleted = data.get("deleted", {})
        upserted = data.get("upserted", {})

        # 1. Delete classes (DETACH DELETE cascades edges)
        deleted_classes = [fqn for fqn in deleted.get("classes", []) if fqn]
        for batch in self._chunks(deleted_classes, BATCH_SIZE):
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (c:Class {fqn: fqn}) DETACH DELETE c",
                {"batch": batch}
            )
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (m:Method {classFqn: fqn}) DETACH DELETE m",
                {"batch": batch}
            )
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (f:Field {classFqn: fqn}) DETACH DELETE f",
                {"batch": batch}
            )
        logger.info(f"Deleted {len(deleted_classes)} classes")

        # 2. Upsert classes (batched)
        classes = upserted.get("classes", [])
        for batch in self._chunks(classes, BATCH_SIZE):
            items = [{
                "fqn": c["fqn"], "name": c.get("name", ""),
                "kind": c.get("kind", "CLASS"), "filePath": c.get("filePath", ""),
                "packageName": c.get("packageName", ""), "superClass": c.get("superClass", ""),
                "lineStart": c.get("lineStart", 0), "lineEnd": c.get("lineEnd", 0),
            } for c in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (c:Class {fqn: item.fqn})
                SET c.name = item.name, c.kind = item.kind, c.filePath = item.filePath,
                    c.packageName = item.packageName, c.superClass = item.superClass,
                    c.lineStart = item.lineStart, c.lineEnd = item.lineEnd
            """, {"batch": items})

        # 3. Upsert methods (batched)
        methods = upserted.get("methods", [])
        for batch in self._chunks(methods, BATCH_SIZE):
            items = [{
                "fqn": m["fqn"], "name": m.get("name", ""),
                "classFqn": m.get("classFqn", ""), "returnType": m.get("returnType", ""),
                "isConstructor": m.get("isConstructor", False),
                "filePath": m.get("filePath", ""), "lineStart": m.get("lineStart", 0),
                "lineEnd": m.get("lineEnd", 0),
            } for m in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (m:Method {fqn: item.fqn})
                SET m.name = item.name, m.classFqn = item.classFqn, m.returnType = item.returnType,
                    m.isConstructor = item.isConstructor, m.filePath = item.filePath,
                    m.lineStart = item.lineStart, m.lineEnd = item.lineEnd
            """, {"batch": items})

        # HAS_METHOD edges for upserted methods
        has_method = [{"src": m.get("classFqn", ""), "dst": m["fqn"]} for m in methods if m.get("classFqn")]
        for batch in self._chunks(has_method, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (m:Method {fqn: edge.dst})
                MERGE (c)-[:HAS_METHOD]->(m)
            """, {"batch": batch})

        # 4. Upsert fields (batched)
        fields = upserted.get("fields", [])
        for batch in self._chunks(fields, BATCH_SIZE):
            items = [{
                "fqn": f["fqn"], "name": f.get("name", ""),
                "classFqn": f.get("classFqn", ""), "type": f.get("type", ""),
                "filePath": f.get("filePath", ""),
            } for f in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (f:Field {fqn: item.fqn})
                SET f.name = item.name, f.classFqn = item.classFqn, f.type = item.type,
                    f.filePath = item.filePath
            """, {"batch": items})

        has_field = [{"src": f.get("classFqn", ""), "dst": f["fqn"]} for f in fields if f.get("classFqn")]
        for batch in self._chunks(has_field, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (f:Field {fqn: edge.dst})
                MERGE (c)-[:HAS_FIELD]->(f)
            """, {"batch": batch})

        # 5. Create external stub nodes for call targets not in graph
        upserted_class_fqns = {c["fqn"] for c in classes}
        upserted_method_fqns = {m["fqn"] for m in methods}

        ext_class_fqns = set()
        ext_method_fqns = set()

        for call in upserted.get("callGraph", []):
            callee = call.get("calleeFqn", "")
            if callee and callee not in upserted_method_fqns:
                ext_method_fqns.add(callee)
                if "#" in callee:
                    ext_class_fqns.add(callee.split("#")[0])

        for edge in upserted.get("inheritance", []):
            parent = edge.get("parentFqn", "")
            if parent and parent not in upserted_class_fqns:
                ext_class_fqns.add(parent)

        for ov in upserted.get("methodOverrides", []):
            parent = ov.get("overridesFqn", "")
            if parent and parent not in upserted_method_fqns:
                ext_method_fqns.add(parent)
                if "#" in parent:
                    ext_class_fqns.add(parent.split("#")[0])

        # Batch create external class stubs
        ext_class_items = []
        for fqn in ext_class_fqns:
            name = fqn.split(".")[-1] if "." in fqn else fqn
            pkg = fqn.rsplit(".", 1)[0] if "." in fqn else ""
            ext_class_items.append({"fqn": fqn, "name": name, "pkg": pkg})

        for batch in self._chunks(ext_class_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (c:Class {fqn: item.fqn})
                ON CREATE SET c.name = item.name, c.kind = 'CLASS',
                    c.packageName = item.pkg, c.external = true,
                    c.filePath = '', c.lineStart = 0, c.lineEnd = 0
            """, {"batch": batch})

        # Batch create external method stubs
        ext_method_items = []
        ext_has_method = []
        for fqn in ext_method_fqns:
            class_fqn = fqn.split("#")[0] if "#" in fqn else ""
            name = fqn.split("#")[1].split("(")[0] if "#" in fqn else fqn
            class_simple = class_fqn.split(".")[-1] if class_fqn else ""
            if "$" in class_simple:
                class_simple = class_simple.split("$")[-1]
            is_constructor = (name == class_simple) if class_fqn else False
            ext_method_items.append({
                "fqn": fqn, "name": name, "classFqn": class_fqn,
                "isCtor": is_constructor,
            })
            if class_fqn:
                ext_has_method.append({"src": class_fqn, "dst": fqn})

        for batch in self._chunks(ext_method_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (m:Method {fqn: item.fqn})
                ON CREATE SET m.name = item.name, m.classFqn = item.classFqn,
                    m.isConstructor = item.isCtor, m.external = true,
                    m.returnType = '', m.filePath = '', m.lineStart = 0, m.lineEnd = 0
            """, {"batch": batch})

        for batch in self._chunks(ext_has_method, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (m:Method {fqn: edge.dst})
                MERGE (c)-[:HAS_METHOD]->(m)
            """, {"batch": batch})

        # 6. Upsert call edges (delete old calls from affected methods first)
        affected_callers = list({call["callerFqn"] for call in upserted.get("callGraph", [])})
        for batch in self._chunks(affected_callers, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS fqn
                MATCH (m:Method {fqn: fqn})-[r:CALLS]->()
                DELETE r
            """, {"batch": batch})

        call_edges = [{"src": c["callerFqn"], "dst": c["calleeFqn"], "line": c.get("line", 0)}
                      for c in upserted.get("callGraph", [])]
        for batch in self._chunks(call_edges, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:Method {fqn: edge.src}), (b:Method {fqn: edge.dst})
                MERGE (a)-[:CALLS {line: edge.line}]->(b)
            """, {"batch": batch})

        # 7. Upsert inheritance edges (batched per type)
        for rel_type in ("EXTENDS", "IMPLEMENTS"):
            edges = [{"src": e["childFqn"], "dst": e["parentFqn"]}
                     for e in upserted.get("inheritance", []) if e.get("relationType") == rel_type]
            for batch in self._chunks(edges, BATCH_SIZE):
                self.db.execute(f"""
                    UNWIND $batch AS edge
                    MATCH (a:Class {{fqn: edge.src}}), (b:Class {{fqn: edge.dst}})
                    MERGE (a)-[:{rel_type}]->(b)
                """, {"batch": batch})

        # 8. Upsert override edges (batched)
        overrides = [{"src": o["methodFqn"], "dst": o["overridesFqn"]}
                     for o in upserted.get("methodOverrides", [])]
        for batch in self._chunks(overrides, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:Method {fqn: edge.src}), (b:Method {fqn: edge.dst})
                MERGE (a)-[:OVERRIDES]->(b)
            """, {"batch": batch})

        # 9. Ensure full-text search indexes exist (idempotent)
        from onelens.importer.schema import FULLTEXT_SCHEMA
        for ddl in FULLTEXT_SCHEMA.values():
            try:
                self.db.execute(ddl)
            except Exception:
                pass

        stats = data.get("stats", {})
        logger.info(f"Delta applied: {stats}")
        return stats

    @staticmethod
    def _chunks(lst: list, size: int):
        """Yield successive chunks from list."""
        for i in range(0, len(lst), size):
            yield lst[i:i + size]
