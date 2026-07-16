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
from onelens.importer.loaders.enums import EnumLoader
from onelens.importer.loaders.jpa import JpaLoader
from onelens.importer.loaders.spring import SpringLoader
from onelens.importer.loaders.tests import TestLoader
from onelens.importer.loaders.type_flow import TypeFlowLoader
from onelens.importer.loaders.data_flow import DataFlowLoader

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

        # 4b. Upsert enum constants (delegated to EnumLoader).
        EnumLoader().apply_delta(self.writer, data, "")

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
        upserted_method_fqn_list = [m["fqn"] for m in methods]
        TypeFlowLoader().apply_delta(self.writer, methods)

        # 6c. Tier-1 data-flow edges (READS_FIELD / WRITES_FIELD / INSTANTIATES)
        # parity with the full loader. Delete from every upserted method, then
        # re-create. Field targets MATCH existing Field nodes (external field
        # access drops — project data-flow only). INSTANTIATES MERGEs the
        # target Class stub like the type-flow edges above.
        DataFlowLoader().apply_delta(self.writer, upserted)

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
            SpringLoader().apply_delta(self.writer, data, graph_wing)

        modules = data.get("modules")
        if modules is not None:
            self._replace_modules(modules)

        # JPA + tests: full re-scan + replace-all (same rationale as Spring).
        # MUST run after _replace_spring (MOCKS/SPIES target SpringBean) and
        # after the CALLS upsert above (TESTS derives from direct CALLS).
        jpa = data.get("jpa")
        if jpa is not None:
            JpaLoader().apply_delta(self.writer, data, graph_wing)

        if "tests" in data or "mockBeans" in data or "spyBeans" in data:
            TestLoader().apply_delta(self.writer, data, graph_wing)

        # Next.js: the Kotlin side re-collects the WHOLE Next subgraph on every
        # delta (~3s, ~500 nodes), so we replace it wholesale — no per-file
        # cascade bookkeeping. Fixes stale ReactComponent/Route/etc. that used
        # to survive a delta and force a --clear.
        nextjs = data.get("nextjs")
        if nextjs:
            self._replace_nextjs(nextjs, graph_wing, adapters=data.get("adapters") or [])

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

                # Next.js drawers: same wholesale-replace strategy as the graph.
                # This collection is per-wing (context_path derives from
                # graph_name), so a prefix purge IS a wing purge — delete every
                # Next drawer, then re-mine the fresh Next section.
                nextjs = data.get("nextjs")
                if nextjs:
                    try:
                        miner._ensure_collection()
                        for prefix in ("reactcomponent:", "page:", "serveraction:", "customhook:"):
                            miner.delete_by_ids(list(miner._get_existing_ids(prefix)))
                        miner._mine_next_components(nextjs)
                        miner._mine_next_pages(nextjs)
                        miner._mine_server_actions(nextjs)
                        miner._mine_custom_hooks(nextjs)
                    except Exception as e:
                        logger.warning("Next.js delta context mining failed: %s", e)
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

    # Next-exclusive labels — safe to wing-delete wholesale, they belong to
    # nobody but the Next collector.
    _NEXT_EXCLUSIVE_LABELS = (
        "Route", "Page", "Layout", "SpecialFile", "ReactComponent",
        "ServerAction", "RouteHandler", "CustomHook", "Hook",
        "ContextProvider", "Middleware",
    )
    # Shared with the Vue collector — only safe to delete when the graph is
    # Next-only.
    _NEXT_SHARED_LABELS = ("JsModule", "JsFunction", "ApiCall")

    def _replace_nextjs(self, nextjs: dict, wing: str, adapters: list) -> None:
        """Replace the entire Next.js subgraph for this wing, then re-insert.

        The delta's `nextjs` section is a FULL re-collect (the Kotlin side
        does this deliberately — Next collection is cheap). So we delete the
        Next-owned nodes for this wing and re-run the existing full mapping.
        No per-file cascade logic — staleness is fixed by wholesale replace.
        """
        labels = list(self._NEXT_EXCLUSIVE_LABELS)

        next_only = "nextjs" in adapters and "vue3" not in adapters
        if next_only:
            labels += list(self._NEXT_SHARED_LABELS)
        else:
            # ponytail: mixed Vue+Next graph — we don't distinguish which
            # JsModule/JsFunction/ApiCall came from which collector, so we
            # can't safely wing-delete the shared labels (would nuke Vue's).
            # We MERGE-upsert them instead; genuinely-removed shared JS nodes
            # linger until a --clear. Upgrade path: stamp a `source` prop on
            # shared JS nodes and scope the delete by it.
            logger.warning(
                "Next.js delta on a mixed Vue+Next graph (wing=%s): stale "
                "JsModule/JsFunction/ApiCall nodes may linger; run a full "
                "--clear import to purge them.", wing
            )

        for label in labels:
            self.db.execute(
                f"MATCH (n:{label}) WHERE n.wing = $wing DETACH DELETE n",
                {"wing": wing},
            )

        # Re-insert via the EXISTING full mapping. GraphLoader._load_nextjs
        # stamps every node with wing=graph_name and its _batch_* helpers
        # guard `progress is not None`, so pass None (no progress bar).
        from onelens.importer.loader import GraphLoader

        GraphLoader(self.db)._load_nextjs(None, nextjs, graph_name=wing)
        logger.info("Next.js subgraph replaced for wing=%s", wing)

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
