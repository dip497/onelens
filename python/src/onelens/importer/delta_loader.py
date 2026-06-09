"""Delta (incremental) import into any Cypher-compatible graph DB."""

import logging
from pathlib import Path

try:
    import orjson as _json  # type: ignore[import-not-found]
    _USE_ORJSON = True
except ImportError:  # pragma: no cover
    import json as _json  # type: ignore[no-redef]
    _USE_ORJSON = False

from onelens.graph.db import GraphDB
from onelens.importer.graph_writer import GraphWriter
from onelens.importer.loaders.annotations import AnnotationLoader

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class DeltaLoader:
    def __init__(self, db: GraphDB):
        self.db = db
        self.writer = GraphWriter(db)

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
        with open(delta_path, "rb") as f:
            raw = f.read()
        data = _json.loads(raw) if _USE_ORJSON else _json.loads(raw.decode("utf-8"))

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
                # enclosingClass parity with full loader (loader.py:87-90) — a
                # modified inner class would otherwise lose this prop on delta.
                "enclosingClass": c.get("enclosingClass", ""),
                "lineStart": c.get("lineStart", 0), "lineEnd": c.get("lineEnd", 0),
            } for c in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (c:Class {fqn: item.fqn})
                SET c.name = item.name, c.kind = item.kind, c.filePath = item.filePath,
                    c.packageName = item.packageName, c.superClass = item.superClass,
                    c.enclosingClass = item.enclosingClass,
                    c.lineStart = item.lineStart, c.lineEnd = item.lineEnd
            """, {"batch": items})

        # 3. Upsert methods (batched)
        methods = upserted.get("methods", [])
        # Tier-0 enrichment parity with the full loader — derive
        # visibility/static/abstract/deprecated/paramCount/transactional/async
        # so delta-upserted methods carry the same props as a full import.
        from onelens.importer.graph_writer import _enrich_method
        for _m in methods:
            _enrich_method(_m)
        for batch in self._chunks(methods, BATCH_SIZE):
            items = [{
                "fqn": m["fqn"], "name": m.get("name", ""),
                "classFqn": m.get("classFqn", ""), "returnType": m.get("returnType", ""),
                "isConstructor": m.get("isConstructor", False),
                "filePath": m.get("filePath", ""), "lineStart": m.get("lineStart", 0),
                "lineEnd": m.get("lineEnd", 0),
                "body": m.get("body") or "", "javadoc": m.get("javadoc") or "",
                "visibility": m.get("visibility", "package"),
                "isStatic": m.get("isStatic", False),
                "isAbstract": m.get("isAbstract", False),
                "isDeprecated": m.get("isDeprecated", False),
                "paramCount": m.get("paramCount", 0),
                "isTransactional": m.get("isTransactional", False),
                "isAsync": m.get("isAsync", False),
            } for m in batch]
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (m:Method {fqn: item.fqn})
                SET m.name = item.name, m.classFqn = item.classFqn, m.returnType = item.returnType,
                    m.isConstructor = item.isConstructor, m.filePath = item.filePath,
                    m.lineStart = item.lineStart, m.lineEnd = item.lineEnd,
                    m.body = item.body, m.javadoc = item.javadoc,
                    m.visibility = item.visibility, m.isStatic = item.isStatic,
                    m.isAbstract = item.isAbstract, m.isDeprecated = item.isDeprecated,
                    m.paramCount = item.paramCount,
                    m.isTransactional = item.isTransactional, m.isAsync = item.isAsync
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
        # Strip the :EnumConstant label (not DETACH DELETE) from constants
        # under upserted classes. Full import models an enum constant as a
        # DUAL-LABEL on the Field node (loader.py:104-121) — one node carrying
        # :Field:EnumConstant. DETACH-deleting by enumFqn here would destroy
        # the shared Field node (and its HAS_FIELD edge) that step 4 just
        # re-created, then the re-insert below would split it into two nodes
        # (bug #9). REMOVE clears stale enum-ness while preserving the Field.
        upserted_class_fqn_list = [c["fqn"] for c in classes]
        for batch in self._chunks(upserted_class_fqn_list, BATCH_SIZE):
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (e:EnumConstant {enumFqn: fqn}) "
                "REMOVE e:EnumConstant "
                "SET e.ordinal = null, e.enumFqn = null, e.args = null, "
                "    e.argList = null, e.argTypes = null",
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
            # Dual-label on the existing Field node (created in step 4), NOT a
            # standalone :EnumConstant node — matches full import's single
            # :Field:EnumConstant node so `MATCH (:Field:EnumConstant)` and
            # HAS_FIELD→constant queries work identically on full and delta.
            self.db.execute("""
                UNWIND $batch AS item
                MERGE (e:Field {fqn: item.fqn})
                SET e:EnumConstant,
                    e.name = item.name, e.ordinal = item.ordinal,
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

        # 6. Upsert call edges (delete old outbound calls first).
        # Delete from EVERY upserted method, not just those that appear as a
        # callerFqn in the delta (bug #6). A method whose body changed so it
        # no longer calls anything drops out of `callGraph` entirely — if we
        # only cleared `affected_callers` its stale outbound CALLS would
        # survive forever (phantom edges full-import never has). Union the
        # upserted-method set with the delta's callers so a method that
        # stopped calling still gets its old edges purged.
        affected_callers = list(
            {m["fqn"] for m in methods}
            | {call["callerFqn"] for call in upserted.get("callGraph", [])}
        )
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

        # 6b. Tier-0 type-flow edges (RETURNS / THROWS / HAS_PARAMETER) parity
        # with the full loader. Delete old ones from every upserted method then
        # re-create, MERGE-ing target Class stubs so external types (JDK,
        # libraries) resolve without a separate stub pass.
        from onelens.importer.graph_writer import _normalize_type
        upserted_method_fqn_list = [m["fqn"] for m in methods]
        for batch in self._chunks(upserted_method_fqn_list, BATCH_SIZE):
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (m:Method {fqn: fqn})"
                "-[r:RETURNS|THROWS|HAS_PARAMETER]->() DELETE r",
                {"batch": batch}
            )
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
        for batch in self._chunks(returns, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:RETURNS]->(c)
            """, {"batch": batch})
        for batch in self._chunks(throws, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:THROWS]->(c)
            """, {"batch": batch})
        for batch in self._chunks(has_param, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:HAS_PARAMETER {position: edge.position, name: edge.name}]->(c)
            """, {"batch": batch})

        # 6c. Tier-1 data-flow edges (READS_FIELD / WRITES_FIELD / INSTANTIATES)
        # parity with the full loader. Delete from every upserted method, then
        # re-create. Field targets MATCH existing Field nodes (external field
        # access drops — project data-flow only). INSTANTIATES MERGEs the
        # target Class stub like the type-flow edges above.
        for batch in self._chunks(upserted_method_fqn_list, BATCH_SIZE):
            self.db.execute(
                "UNWIND $batch AS fqn MATCH (m:Method {fqn: fqn})"
                "-[r:READS_FIELD|WRITES_FIELD|INSTANTIATES]->() DELETE r",
                {"batch": batch}
            )
        dataflow = upserted.get("dataFlow") or {}
        df_reads, df_writes = [], []
        for fa in dataflow.get("fieldAccesses", []) or []:
            e = {"src": fa.get("accessorFqn", ""), "dst": fa.get("fieldFqn", ""),
                 "line": fa.get("line", 0)}
            if not e["src"] or not e["dst"]:
                continue
            (df_writes if fa.get("mode") == "write" else df_reads).append(e)
        for rel, edges in (("READS_FIELD", df_reads), ("WRITES_FIELD", df_writes)):
            for batch in self._chunks(edges, BATCH_SIZE):
                self.db.execute(
                    f"UNWIND $batch AS edge "
                    f"MATCH (m:Method {{fqn: edge.src}}), (f:Field {{fqn: edge.dst}}) "
                    f"MERGE (m)-[:{rel} {{line: edge.line}}]->(f)",
                    {"batch": batch}
                )
        df_inst = [{"src": i.get("methodFqn", ""), "dst": i.get("classFqn", ""),
                    "line": i.get("line", 0)}
                   for i in dataflow.get("instantiations", []) or []
                   if i.get("methodFqn") and i.get("classFqn")]
        for batch in self._chunks(df_inst, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src})
                MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true,
                    c.name = split(edge.dst, '.')[-1], c.kind = 'CLASS'
                MERGE (m)-[:INSTANTIATES {line: edge.line}]->(c)
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

        # 8b. Replace ANNOTATED_WITH edges on upserted targets (delegated to AnnotationLoader).
        # graph_wing is derived below at step 9b; pass graph_name here since the
        # AnnotationLoader only needs upserted, not the wing value.
        AnnotationLoader().apply_delta(self.writer, upserted, graph_name or "")

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
        # Resolve the wing the same way the full loader does (loader.py:146-151)
        # so Spring nodes get the same `wing` stamp — the Vue↔Spring HTTP
        # bridge filters `Endpoint.wing IS NOT NULL`, so an unstamped delta
        # silently zeroes the cross-stack HITS edges (bug #5).
        workspace_header = data.get("workspace") or {}
        graph_wing = (
            workspace_header.get("graphId")
            or graph_name
            or data.get("project", {}).get("name", "")
            or "default"
        )

        spring = data.get("spring")
        if spring is not None:
            self._replace_spring(spring, wing=graph_wing)

        modules = data.get("modules")
        if modules is not None:
            self._replace_modules(modules)

        # JPA + tests: full re-scan + replace-all (same rationale as Spring).
        # MUST run after _replace_spring (MOCKS/SPIES target SpringBean) and
        # after the CALLS upsert above (TESTS derives from direct CALLS).
        jpa = data.get("jpa")
        if jpa is not None:
            self._replace_jpa(jpa, wing=graph_wing)

        if "tests" in data or "mockBeans" in data or "spyBeans" in data:
            self._replace_tests(data, wing=graph_wing)

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

    def _replace_spring(self, spring: dict, wing: str = "default") -> None:
        """Drop all SpringBean/Endpoint/AutoConfig/HANDLES/INJECTS/REGISTERED_AS,
        then re-insert with full-loader parity (props + wing + edges).

        Spring data is small (~2K beans on a 10K-class project) so a
        full replace is simpler and more correct than per-class diff —
        injections reference types on other classes, bean names can be
        renamed, and annotations can be added/removed without the
        annotated file showing up as "changed" if only a supertype
        changed.

        `wing` MUST match the full loader's stamp (loader.py:161-184): the
        Vue↔Spring HTTP bridge filters `Endpoint.wing IS NOT NULL`, so an
        unstamped Endpoint silently emits zero cross-stack HITS edges.
        """
        self.db.execute("MATCH (b:SpringBean) DETACH DELETE b")
        self.db.execute("MATCH (e:Endpoint) DETACH DELETE e")
        self.db.execute("MATCH (a:SpringAutoConfig) DETACH DELETE a")

        beans = spring.get("beans", []) or []
        bean_items = [{
            "name": b.get("name", ""), "classFqn": b.get("classFqn", ""),
            "type": b.get("type", ""), "scope": b.get("scope", ""),
            "profile": b.get("profile", ""), "wing": wing,
            "primary": bool(b.get("primary", False)),
            "source": b.get("source") or "annotation",
            "factoryMethodFqn": b.get("factoryMethodFqn") or "",
            "activeProfiles": ",".join(b.get("activeProfiles") or []),
        } for b in beans if b.get("name")]
        for batch in self._chunks(bean_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (b:SpringBean {name: item.name})
                SET b.classFqn = item.classFqn, b.type = item.type,
                    b.scope = item.scope, b.profile = item.profile,
                    b.wing = item.wing, b.primary = item.primary,
                    b.source = item.source,
                    b.factoryMethodFqn = item.factoryMethodFqn,
                    b.activeProfiles = item.activeProfiles
            """, {"batch": batch})

        # REGISTERED_AS (Class → SpringBean) — parity with loader.py:446-451.
        reg_as = [{"src": b["classFqn"], "dst": b["name"]}
                  for b in bean_items if b.get("classFqn") and b.get("name")]
        for batch in self._chunks(reg_as, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (b:SpringBean {name: edge.dst})
                MERGE (c)-[:REGISTERED_AS]->(b)
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
                "wing": wing,
            })
            if ep.get("handlerMethodFqn"):
                handles.append({"src": ep["handlerMethodFqn"], "dst": ep_id})

        for batch in self._chunks(ep_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (e:Endpoint {id: item.id})
                SET e.path = item.path, e.httpMethod = item.httpMethod,
                    e.controllerFqn = item.controllerFqn,
                    e.handlerMethodFqn = item.handlerMethodFqn,
                    e.wing = item.wing
            """, {"batch": batch})

        for batch in self._chunks(handles, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src}), (e:Endpoint {id: edge.dst})
                MERGE (m)-[:HANDLES]->(e)
            """, {"batch": batch})

        # SpringAutoConfig nodes — parity with loader.py:186-190.
        autoconfigs = [{
            "classFqn": ac.get("classFqn", ""), "source": ac.get("source", ""),
            "sourceFile": ac.get("sourceFile", ""), "wing": wing,
        } for ac in (spring.get("autoConfigs", []) or []) if ac.get("classFqn")]
        for batch in self._chunks(autoconfigs, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                CREATE (a:SpringAutoConfig {classFqn: item.classFqn})
                SET a.source = item.source, a.sourceFile = item.sourceFile,
                    a.wing = item.wing
            """, {"batch": batch})

        # INJECTS edges live between SpringBean nodes keyed by classFqn.
        # DETACH DELETE above already dropped them; re-insert from the delta.
        # `qualifier` parity with loader.py:431-438.
        injections = spring.get("injections", []) or []
        inj_items = [{
            "src": inj.get("targetClassFqn", ""),
            "dst": inj.get("injectedClassFqn", ""),
            "field": inj.get("targetFieldOrParam", ""),
            "type": inj.get("injectionType", ""),
            "qualifier": inj.get("qualifier") or "",
        } for inj in injections if inj.get("targetClassFqn") and inj.get("injectedClassFqn")]
        for batch in self._chunks(inj_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:SpringBean {classFqn: edge.src}),
                      (b:SpringBean {classFqn: edge.dst})
                MERGE (a)-[:INJECTS {field: edge.field, type: edge.type,
                                     qualifier: edge.qualifier}]->(b)
            """, {"batch": batch})

        logger.info(
            "Spring replaced: %d beans, %d endpoints, %d injections, %d autoconfigs (wing=%s)",
            len(bean_items), len(ep_items), len(inj_items), len(autoconfigs), wing,
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

    def _replace_jpa(self, jpa: dict, wing: str = "default") -> None:
        """Strip + re-apply JPA dual-labels and edges (parity with loader.py).

        A modified @Entity is DETACH-deleted then re-MERGEd as a plain :Class,
        losing its :JpaEntity label + tableName/schema. The whole JPA layer is
        cross-class (RELATES_TO between entities, REPOSITORY_FOR), so we strip
        every JPA label + edge globally and re-derive from the full re-scan —
        cheap (JPA layer is small) and guarantees parity.
        """
        # 1. Strip labels + JPA edges. REMOVE keeps the underlying Class/Field
        # node (and its structural edges); only the JPA overlay is rebuilt.
        self.db.execute("MATCH (n:JpaEntity) REMOVE n:JpaEntity")
        self.db.execute("MATCH (n:JpaColumn) REMOVE n:JpaColumn")
        self.db.execute("MATCH (n:JpaRepository) REMOVE n:JpaRepository")
        self.db.execute("MATCH ()-[r:HAS_COLUMN|RELATES_TO|REPOSITORY_FOR|QUERIES]->() DELETE r")

        entities = jpa.get("entities", []) or []
        # JpaEntity dual-label on the existing Class node.
        ent_items = [{
            "fqn": e["classFqn"], "tableName": e.get("tableName", ""),
            "schema": e.get("schema", ""), "wing": wing,
        } for e in entities if e.get("classFqn")]
        for batch in self._chunks(ent_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                MATCH (c:Class {fqn: item.fqn})
                SET c:JpaEntity, c.tableName = item.tableName,
                    c.schema = item.schema, c.wing = item.wing
            """, {"batch": batch})

        # JpaColumn dual-label on the existing Field node + HAS_COLUMN edge.
        col_items, has_col, relates = [], [], []
        seen_col = set()
        for e in entities:
            for col in e.get("columns", []):
                key = col.get("fieldFqn", "")
                if key and key not in seen_col:
                    seen_col.add(key)
                    col_items.append({
                        "fqn": key, "columnName": col.get("columnName", ""),
                        "nullable": bool(col.get("nullable", True)),
                        "unique": bool(col.get("unique", False)),
                        "relation": col.get("relation") or "",
                        "targetEntityFqn": col.get("targetEntityFqn") or "",
                        "wing": wing,
                    })
                    has_col.append({"src": e["classFqn"], "dst": key})
                tgt, rel = col.get("targetEntityFqn"), col.get("relation")
                if tgt and rel:
                    relates.append({
                        "src": e["classFqn"], "dst": tgt, "relation": rel,
                        "field": col["fieldFqn"].split("#", 1)[-1] if "#" in col.get("fieldFqn", "") else "",
                    })
        for batch in self._chunks(col_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                MATCH (f:Field {fqn: item.fqn})
                SET f:JpaColumn, f.columnName = item.columnName,
                    f.nullable = item.nullable, f.unique = item.unique,
                    f.relation = item.relation,
                    f.targetEntityFqn = item.targetEntityFqn, f.wing = item.wing
            """, {"batch": batch})
        for batch in self._chunks(has_col, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:JpaEntity {fqn: edge.src}), (f:JpaColumn {fqn: edge.dst})
                MERGE (c)-[:HAS_COLUMN]->(f)
            """, {"batch": batch})
        for batch in self._chunks(relates, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:JpaEntity {fqn: edge.src}), (b:JpaEntity {fqn: edge.dst})
                MERGE (a)-[:RELATES_TO {relation: edge.relation, field: edge.field}]->(b)
            """, {"batch": batch})

        # JpaRepository dual-label + REPOSITORY_FOR + QUERIES.
        repos = jpa.get("repositories", []) or []
        repo_items = [{"fqn": r["classFqn"], "entityFqn": r.get("entityFqn", ""), "wing": wing}
                      for r in repos if r.get("classFqn")]
        for batch in self._chunks(repo_items, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS item
                MATCH (c:Class {fqn: item.fqn})
                SET c:JpaRepository, c.entityFqn = item.entityFqn, c.wing = item.wing
            """, {"batch": batch})
        repo_for = [{"src": r["classFqn"], "dst": r["entityFqn"]}
                    for r in repos if r.get("entityFqn") and r.get("classFqn")]
        for batch in self._chunks(repo_for, BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (r:JpaRepository {fqn: edge.src}), (e:JpaEntity {fqn: edge.dst})
                MERGE (r)-[:REPOSITORY_FOR]->(e)
            """, {"batch": batch})
        queries = []
        for r in repos:
            for q in r.get("derivedQueries", []):
                queries.append({"src": r["classFqn"], "dst": q.get("methodFqn", ""),
                                "methodName": q.get("methodName", ""), "kind": q.get("kind", "derived")})
        for batch in self._chunks([q for q in queries if q["dst"]], BATCH_SIZE):
            self.db.execute("""
                UNWIND $batch AS edge
                MATCH (r:JpaRepository {fqn: edge.src}), (m:Method {fqn: edge.dst})
                MERGE (r)-[:QUERIES {methodName: edge.methodName, kind: edge.kind}]->(m)
            """, {"batch": batch})
        logger.info("JPA replaced: %d entities, %d repos (wing=%s)",
                    len(ent_items), len(repo_items), wing)

    def _replace_tests(self, data: dict, wing: str = "default") -> None:
        """Strip + re-apply :TestCase dual-label + MOCKS/SPIES/TESTS edges.

        Parity with loader.py::_load_tests. A modified test class DETACH-deletes
        and re-MERGEs as a plain :Method, losing :TestCase + every test edge;
        and _replace_spring wipes SpringBeans, destroying MOCKS/SPIES targets.
        Full strip + re-derive guarantees parity. Must run after Spring replace
        (MOCKS→SpringBean) and the CALLS upsert (TESTS derives from CALLS).
        """
        tests = data.get("tests", []) or []
        mock_beans = data.get("mockBeans", []) or []
        spy_beans = data.get("spyBeans", []) or []

        self.db.execute("MATCH (m:TestCase) REMOVE m:TestCase")
        self.db.execute("MATCH ()-[r:MOCKS|SPIES|TESTS]->() DELETE r")

        if tests:
            prepped = [{
                "methodFqn": t.get("methodFqn", ""), "testClass": t.get("testClass", ""),
                "testKind": t.get("testKind", "unknown"),
                "testFramework": t.get("testFramework", "unknown"),
                "tags": ",".join(t.get("tags") or []),
                "disabled": bool(t.get("disabled", False)),
                "activeProfiles": ",".join(t.get("activeProfiles") or []),
                "springBootApp": t.get("springBootApp") or "",
                "usesMockito": bool(t.get("usesMockito", False)),
                "usesTestcontainers": bool(t.get("usesTestcontainers", False)),
                "displayName": t.get("displayName") or "", "wing": wing,
            } for t in tests if t.get("methodFqn")]
            for batch in self._chunks(prepped, BATCH_SIZE):
                self.db.execute("""
                    UNWIND $batch AS item
                    MATCH (m:Method {fqn: item.methodFqn})
                    SET m:TestCase, m.testClass = item.testClass,
                        m.testKind = item.testKind, m.testFramework = item.testFramework,
                        m.tags = item.tags, m.disabled = item.disabled,
                        m.activeProfiles = item.activeProfiles,
                        m.springBootApp = item.springBootApp,
                        m.usesMockito = item.usesMockito,
                        m.usesTestcontainers = item.usesTestcontainers,
                        m.displayName = item.displayName, m.wing = item.wing
                """, {"batch": batch})

        for rel, bindings in (("MOCKS", mock_beans), ("SPIES", spy_beans)):
            items = [{"src": b["testClassFqn"], "dst": b["beanClassFqn"],
                      "field": b.get("fieldName", "")}
                     for b in bindings if b.get("testClassFqn") and b.get("beanClassFqn")]
            for batch in self._chunks(items, BATCH_SIZE):
                self.db.execute(
                    f"UNWIND $batch AS edge "
                    f"MATCH (c:Class {{fqn: edge.src}}), (b:SpringBean {{classFqn: edge.dst}}) "
                    f"MERGE (c)-[:{rel} {{field: edge.field}}]->(b)",
                    {"batch": batch}
                )

        if tests:
            try:
                self.db.execute(
                    "MATCH (t:TestCase)-[:CALLS]->(m:Method) "
                    "WHERE NOT m:TestCase MERGE (t)-[:TESTS]->(m)"
                )
            except Exception as e:
                logger.warning("Delta derived :TESTS pass failed: %s", e)
        logger.info("Tests replaced: %d test methods (wing=%s)", len(tests), wing)

    @staticmethod
    def _chunks(lst: list, size: int):
        """Yield successive chunks from list."""
        for i in range(0, len(lst), size):
            yield lst[i:i + size]
