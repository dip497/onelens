"""Delta (incremental) import into any Cypher-compatible graph DB."""

import json
import logging
from pathlib import Path

from onelens.graph.db import GraphDB

logger = logging.getLogger(__name__)


class DeltaLoader:
    def __init__(self, db: GraphDB):
        self.db = db

    def apply_delta(self, delta_path: Path) -> dict:
        """Apply a delta export to an existing graph.

        Delta JSON has two sections:
        - deleted: FQNs of classes/methods/fields to remove (cascade removes edges)
        - upserted: new/updated classes/methods/fields/edges to add

        Strategy:
        1. Delete old nodes by FQN (edges cascade)
        2. Insert new nodes
        3. Insert new edges
        """
        with open(delta_path) as f:
            data = json.load(f)

        deleted = data.get("deleted", {})
        upserted = data.get("upserted", {})

        # 1. Delete classes (cascade: removes HAS_METHOD, HAS_FIELD, CALLS, etc.)
        deleted_classes = deleted.get("classes", [])
        for fqn in deleted_classes:
            self.db.execute("MATCH (c:Class {fqn: $fqn}) DETACH DELETE c", {"fqn": fqn})
            # Also delete orphaned methods and fields of this class
            self.db.execute("MATCH (m:Method {classFqn: $fqn}) DETACH DELETE m", {"fqn": fqn})
            self.db.execute("MATCH (f:Field {classFqn: $fqn}) DETACH DELETE f", {"fqn": fqn})

        logger.info(f"Deleted {len(deleted_classes)} classes")

        # 2. Upsert classes
        for cls in upserted.get("classes", []):
            self.db.execute("""
                MERGE (c:Class {fqn: $fqn})
                SET c.name = $name, c.kind = $kind, c.filePath = $filePath,
                    c.packageName = $packageName, c.superClass = $superClass
            """, {
                "fqn": cls["fqn"], "name": cls.get("name", ""),
                "kind": cls.get("kind", "CLASS"), "filePath": cls.get("filePath", ""),
                "packageName": cls.get("packageName", ""),
                "superClass": cls.get("superClass", ""),
            })

        # 3. Upsert methods
        for m in upserted.get("methods", []):
            self.db.execute("""
                MERGE (m:Method {fqn: $fqn})
                SET m.name = $name, m.classFqn = $classFqn, m.returnType = $returnType,
                    m.isConstructor = $isConstructor, m.filePath = $filePath,
                    m.lineStart = $lineStart
            """, {
                "fqn": m["fqn"], "name": m.get("name", ""),
                "classFqn": m.get("classFqn", ""), "returnType": m.get("returnType", ""),
                "isConstructor": m.get("isConstructor", False),
                "filePath": m.get("filePath", ""), "lineStart": m.get("lineStart", 0),
            })

            # Re-create HAS_METHOD edge
            self.db.execute("""
                MATCH (c:Class {fqn: $classFqn}), (m:Method {fqn: $methodFqn})
                MERGE (c)-[:HAS_METHOD]->(m)
            """, {"classFqn": m.get("classFqn", ""), "methodFqn": m["fqn"]})

        # 4. Upsert fields
        for f in upserted.get("fields", []):
            self.db.execute("""
                MERGE (f:Field {fqn: $fqn})
                SET f.name = $name, f.classFqn = $classFqn, f.type = $type,
                    f.filePath = $filePath
            """, {
                "fqn": f["fqn"], "name": f.get("name", ""),
                "classFqn": f.get("classFqn", ""), "type": f.get("type", ""),
                "filePath": f.get("filePath", ""),
            })

            self.db.execute("""
                MATCH (c:Class {fqn: $classFqn}), (f:Field {fqn: $fieldFqn})
                MERGE (c)-[:HAS_FIELD]->(f)
            """, {"classFqn": f.get("classFqn", ""), "fieldFqn": f["fqn"]})

        # 5. Upsert call edges (delete old calls from affected methods first)
        affected_callers = set()
        for call in upserted.get("callGraph", []):
            affected_callers.add(call["callerFqn"])

        for caller_fqn in affected_callers:
            self.db.execute("""
                MATCH (m:Method {fqn: $fqn})-[r:CALLS]->()
                DELETE r
            """, {"fqn": caller_fqn})

        for call in upserted.get("callGraph", []):
            self.db.execute("""
                MATCH (a:Method {fqn: $caller}), (b:Method {fqn: $callee})
                MERGE (a)-[:CALLS {line: $line}]->(b)
            """, {
                "caller": call["callerFqn"],
                "callee": call["calleeFqn"],
                "line": call.get("line", 0),
            })

        # 6. Upsert inheritance edges
        for edge in upserted.get("inheritance", []):
            rel = edge["relationType"]
            self.db.execute(f"""
                MATCH (a:Class {{fqn: $child}}), (b:Class {{fqn: $parent}})
                MERGE (a)-[:{rel}]->(b)
            """, {"child": edge["childFqn"], "parent": edge["parentFqn"]})

        # 7. Upsert override edges
        for ov in upserted.get("methodOverrides", []):
            self.db.execute("""
                MATCH (a:Method {fqn: $method}), (b:Method {fqn: $overrides})
                MERGE (a)-[:OVERRIDES]->(b)
            """, {"method": ov["methodFqn"], "overrides": ov["overridesFqn"]})

        stats = data.get("stats", {})
        logger.info(f"Delta applied: {stats}")
        return stats
