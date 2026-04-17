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

    def apply_delta(self, delta_path: Path, graph_name: str | None = None,
                    context: bool = False) -> dict:
        """Apply a delta export to an existing graph.

        Strategy:
        1. Delete old nodes by FQN (cascade removes edges)
        2. Upsert new nodes + external stubs (batched)
        3. Upsert new edges (batched)
        4. (Optional) update ChromaDB context: delete removed drawers, upsert
           changed methods/classes. Only when `context=True` and `graph_name`
           provided. Uses CodeMiner's deterministic IDs — incremental re-embed
           is O(changed methods), not full re-mine.
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
            # Cascade enum constants too — they're keyed by `enumFqn`, not
            # inherited from the class, so Cypher won't touch them via the
            # class DETACH DELETE above.
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (e:EnumConstant {enumFqn: fqn}) DETACH DELETE e",
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
                "body": m.get("body") or "", "javadoc": m.get("javadoc") or "",
            } for m in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (m:Method {fqn: item.fqn})
                SET m.name = item.name, m.classFqn = item.classFqn, m.returnType = item.returnType,
                    m.isConstructor = item.isConstructor, m.filePath = item.filePath,
                    m.lineStart = item.lineStart, m.lineEnd = item.lineEnd,
                    m.body = item.body, m.javadoc = item.javadoc
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

        # 4b. Upsert enum constants. Classes that changed may have added,
        # removed, or reordered constants — drop all EnumConstant nodes
        # under each upserted class first, then re-insert from the delta.
        # Keyed by enumFqn (not the enum class's node) so cascade works even
        # if the class node hasn't been DETACH-deleted (e.g. modified, not
        # removed). Delete-then-insert beats MERGE here because `ordinal`
        # and `argList` can both mutate.
        upserted_class_fqn_list = [c["fqn"] for c in classes]
        for batch in self._chunks(upserted_class_fqn_list, BATCH_SIZE):
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (e:EnumConstant {enumFqn: fqn}) DETACH DELETE e",
                {"batch": batch}
            )
        enum_consts = upserted.get("enumConstants", [])
        for batch in self._chunks(enum_consts, BATCH_SIZE):
            items = [{
                "fqn": e["fqn"], "name": e.get("name", ""),
                "ordinal": e.get("ordinal", 0), "enumFqn": e.get("enumFqn", ""),
                "args": e.get("args", "[]"),
                "argList": e.get("argList", []) or [],
                "argTypes": e.get("argTypes", []) or [],
                "filePath": e.get("filePath", ""),
                "lineStart": e.get("lineStart", 0),
            } for e in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (e:EnumConstant {fqn: item.fqn})
                SET e.name = item.name, e.ordinal = item.ordinal,
                    e.enumFqn = item.enumFqn, e.args = item.args,
                    e.argList = item.argList, e.argTypes = item.argTypes,
                    e.filePath = item.filePath, e.lineStart = item.lineStart
            """, {"batch": items})
        has_enum_const = [{"src": e.get("enumFqn", ""), "dst": e["fqn"]}
                          for e in enum_consts if e.get("enumFqn")]
        for batch in self._chunks(has_enum_const, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (e:EnumConstant {fqn: edge.dst})
                MERGE (c)-[:HAS_ENUM_CONSTANT]->(e)
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

        # 8b. Replace ANNOTATED_WITH edges on upserted targets. Pre-1.1 delta
        # flow skipped this — annotations added / removed on a modified class
        # never propagated to the graph (silent drift). Fix: for every target
        # in the delta's annotations block, drop its existing ANNOTATED_WITH
        # edges, then create fresh ones carrying the resolved `attributes`
        # JSON. Annotation nodes are MERGEd first so new FQNs auto-exist.
        annotations = upserted.get("annotations", [])
        if annotations:
            # MERGE target Annotation nodes (dedup on fqn).
            ann_fqns = sorted({a["annotationFqn"] for a in annotations if a.get("annotationFqn")})
            for batch in self._chunks(ann_fqns, BATCH_SIZE):
                self.db.execute(
                    "UNWIND $batch AS fqn MERGE (a:Annotation {fqn: fqn}) "
                    "ON CREATE SET a.name = split(fqn, '.')[-1]",
                    {"batch": batch}
                )

            # Drop old edges per target label. Use per-label batches keyed on
            # the label's primary-key column so we don't have to MATCH across
            # three labels in one query.
            by_label: dict[str, list[str]] = {"Class": [], "Method": [], "Field": []}
            for a in annotations:
                kind = a.get("targetKind", "CLASS")
                label = "Class" if kind == "CLASS" else "Method" if kind == "METHOD" else "Field"
                by_label[label].append(a["targetFqn"])
            for label, fqns in by_label.items():
                unique = sorted(set(fqns))
                for batch in self._chunks(unique, BATCH_SIZE):
                    self.db.execute(
                        f"UNWIND $batch AS fqn "
                        f"MATCH (n:{label} {{fqn: fqn}})-[r:ANNOTATED_WITH]->() DELETE r",
                        {"batch": batch}
                    )

            # Create fresh edges with attributes.
            edges_by_label: dict[str, list[dict]] = {"Class": [], "Method": [], "Field": []}
            for a in annotations:
                kind = a.get("targetKind", "CLASS")
                label = "Class" if kind == "CLASS" else "Method" if kind == "METHOD" else "Field"
                edges_by_label[label].append({
                    "src": a["targetFqn"],
                    "dst": a["annotationFqn"],
                    "attributes": a.get("attributes", "{}"),
                })
            for label, edges in edges_by_label.items():
                for batch in self._chunks(edges, BATCH_SIZE):
                    self.db.execute(
                        f"UNWIND $batch AS edge "
                        f"MATCH (n:{label} {{fqn: edge.src}}), (a:Annotation {{fqn: edge.dst}}) "
                        f"CREATE (n)-[:ANNOTATED_WITH {{attributes: edge.attributes}}]->(a)",
                        {"batch": batch}
                    )

        # 9. Ensure full-text search indexes exist (idempotent)
        from onelens.importer.schema import FULLTEXT_SCHEMA
        for ddl in FULLTEXT_SCHEMA.values():
            try:
                self.db.execute(ddl)
            except Exception:
                pass

        # 9b. Replace-all Spring layer (beans, endpoints, injections, HANDLES)
        # and Modules. Spring wiring is cross-class — per-class diff would miss
        # new bean types referenced from unchanged callers. Re-scan cost is
        # bounded (indexed), re-insert is cheap (~few K rows).
        spring = data.get("spring")
        if spring is not None:
            self._replace_spring(spring)

        modules = data.get("modules")
        if modules is not None:
            self._replace_modules(modules)

        stats = data.get("stats", {})

        # 10. Optional: propagate the delta into the ChromaDB semantic layer.
        # Deterministic drawer IDs (`method:<fqn>`, `class:<fqn>`) mean we can
        # upsert just the changed entities — full re-mine on every file save
        # would be unusable (20 min). Changed methods / classes re-embed;
        # deleted ones are purged by ID. External stubs are skipped (they
        # have no body to embed).
        if context and graph_name:
            try:
                from onelens.miners.code_miner import CodeMiner

                miner = CodeMiner(graph_name)

                # Purge drawers for deleted classes + cascade their methods.
                # Classes go by exact ID (`class:<fqn>`). Methods cascade via
                # metadata filter — each method drawer was written with its
                # owning `class` FQN, so one Chroma delete purges them all.
                del_class_fqns = [fqn for fqn in deleted.get("classes", []) if fqn]
                if del_class_fqns:
                    miner.delete_by_ids([f"class:{fqn}" for fqn in del_class_fqns])
                    miner.delete_methods_of_classes(del_class_fqns)

                # Upsert changed methods + classes from `upserted`.
                # Build a synthetic "mini export" shape CodeMiner accepts.
                mini = {
                    "classes": classes,
                    "methods": methods,
                    "callGraph": upserted.get("callGraph", []),
                }
                try:
                    ctx_stats = miner.mine_upserts(mini)
                    stats["context"] = ctx_stats
                except AttributeError:
                    logger.info(
                        "CodeMiner.mine_upserts not available; context layer "
                        "will drift until next full --context import"
                    )
                    stats["context"] = {"skipped": "mine_upserts not implemented"}
            except Exception as e:
                logger.warning("Delta context mining failed: %s", e)
                stats["context"] = {"error": str(e)}

        # 11. Recompute PageRank. Topology changed (new nodes / edges or
        # removed classes), so `Method.pagerank` / `Class.pagerank` are stale.
        # Retrieval's multiplicative boost reads these — without a refresh,
        # new endpoints / beans stay at pagerank=0 and rank below stale peers.
        # NetworkX + graph read takes ~5-15s on 80K methods; acceptable for
        # a delta that already paid for the graph round-trip.
        try:
            from onelens.importer import pagerank as _pr

            pr_stats = _pr.run(self.db)
            stats["pagerank"] = pr_stats
        except Exception as e:
            logger.warning("Delta PageRank refresh failed: %s", e)
            stats["pagerank"] = {"error": str(e)}

        logger.info(f"Delta applied: {stats}")
        return stats

    def _replace_spring(self, spring: dict) -> None:
        """Drop all SpringBean/Endpoint/HANDLES/INJECTS, then re-insert.

        Spring data is small (~2K beans on a 10K-class project) so a
        full replace is simpler and more correct than per-class diff —
        injections reference types on other classes, bean names can be
        renamed, and annotations can be added/removed without the
        annotated file showing up as "changed" if only a supertype
        changed.
        """
        self.db.execute("MATCH (b:SpringBean) DETACH DELETE b")
        self.db.execute("MATCH (e:Endpoint) DETACH DELETE e")

        beans = spring.get("beans", []) or []
        bean_items = [{
            "name": b.get("name", ""), "classFqn": b.get("classFqn", ""),
            "type": b.get("type", ""), "scope": b.get("scope", ""),
            "profile": b.get("profile", ""),
        } for b in beans if b.get("name")]
        for batch in self._chunks(bean_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (b:SpringBean {name: item.name})
                SET b.classFqn = item.classFqn, b.type = item.type,
                    b.scope = item.scope, b.profile = item.profile
            """, {"batch": batch})

        endpoints = spring.get("endpoints", []) or []
        ep_items = []
        handles = []
        for ep in endpoints:
            method = ep.get("httpMethod", "GET")
            path = ep.get("path", "/")
            ep_id = ep.get("id") or f"{method}:{path}"
            ep_items.append({
                "id": ep_id, "path": path, "httpMethod": method,
                "controllerFqn": ep.get("controllerFqn", ""),
                "handlerMethodFqn": ep.get("handlerMethodFqn", ""),
            })
            if ep.get("handlerMethodFqn"):
                handles.append({"src": ep["handlerMethodFqn"], "dst": ep_id})

        for batch in self._chunks(ep_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (e:Endpoint {id: item.id})
                SET e.path = item.path, e.httpMethod = item.httpMethod,
                    e.controllerFqn = item.controllerFqn,
                    e.handlerMethodFqn = item.handlerMethodFqn
            """, {"batch": batch})

        for batch in self._chunks(handles, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src}), (e:Endpoint {id: edge.dst})
                MERGE (m)-[:HANDLES]->(e)
            """, {"batch": batch})

        # INJECTS edges live between SpringBean nodes keyed by classFqn.
        # DETACH DELETE above already dropped them; re-insert from the delta.
        injections = spring.get("injections", []) or []
        inj_items = [{
            "src": inj.get("targetClassFqn", ""),
            "dst": inj.get("injectedClassFqn", ""),
            "field": inj.get("targetFieldOrParam", ""),
            "type": inj.get("injectionType", ""),
        } for inj in injections if inj.get("targetClassFqn") and inj.get("injectedClassFqn")]
        for batch in self._chunks(inj_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:SpringBean {classFqn: edge.src}),
                      (b:SpringBean {classFqn: edge.dst})
                MERGE (a)-[:INJECTS {field: edge.field, type: edge.type}]->(b)
            """, {"batch": batch})

        logger.info(
            "Spring replaced: %d beans, %d endpoints, %d injections",
            len(bean_items), len(ep_items), len(inj_items),
        )

    def _replace_modules(self, modules: list) -> None:
        """Drop all Module nodes, then re-insert."""
        self.db.execute("MATCH (m:Module) DETACH DELETE m")
        items = [{"name": m.get("name", ""), "type": m.get("type", "")}
                 for m in modules if m.get("name")]
        for batch in self._chunks(items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (m:Module {name: item.name}) SET m.type = item.type
            """, {"batch": batch})
        logger.info("Modules replaced: %d", len(items))

    @staticmethod
    def _chunks(lst: list, size: int):
        """Yield successive chunks from list."""
        for i in range(0, len(lst), size):
            yield lst[i:i + size]
