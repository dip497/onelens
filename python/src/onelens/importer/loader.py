"""Full JSON import into any Cypher-compatible graph DB using batch UNWIND."""

import json
import logging
import time
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from onelens.graph.db import GraphDB
from onelens.importer.schema import NODE_SCHEMA, FULLTEXT_SCHEMA

logger = logging.getLogger(__name__)

NODE_BATCH = 1000
EDGE_BATCH = 500


class GraphLoader:
    def __init__(self, db: GraphDB):
        self.db = db

    def clear(self):
        """Drop all data from the graph."""
        self.db.clear()

    def load_full(self, export_path: Path) -> dict:
        """Load a full export JSON into the graph DB using batch UNWIND queries."""
        start = time.time()

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
        ) as progress:

            # Parse JSON
            task = progress.add_task("Loading JSON...", total=1)
            with open(export_path) as f:
                data = json.load(f)
            progress.update(task, completed=1)

            # Create indexes (idempotent)
            task = progress.add_task("Creating indexes...", total=len(NODE_SCHEMA))
            for i, (name, ddl) in enumerate(NODE_SCHEMA.items()):
                try:
                    self.db.execute(ddl)
                except Exception:
                    pass  # Index already exists
                progress.update(task, completed=i + 1)

            # Create full-text search indexes (idempotent)
            task = progress.add_task("Creating full-text indexes...", total=len(FULLTEXT_SCHEMA))
            for i, (name, ddl) in enumerate(FULLTEXT_SCHEMA.items()):
                try:
                    self.db.execute(ddl)
                except Exception:
                    pass  # Index already exists
                progress.update(task, completed=i + 1)

            # --- NODES ---

            classes = data.get("classes", [])
            self._batch_nodes(progress, "Classes", classes, "Class", "fqn", [
                "name", "kind", "filePath", "lineStart", "lineEnd",
                "packageName", "enclosingClass", "superClass",
            ])

            methods = data.get("methods", [])
            self._batch_nodes(progress, "Methods", methods, "Method", "fqn", [
                "name", "classFqn", "returnType", "isConstructor",
                "filePath", "lineStart", "lineEnd",
                "body", "javadoc",
            ])

            fields = data.get("fields", [])
            self._batch_nodes(progress, "Fields", fields, "Field", "fqn", [
                "name", "classFqn", "type", "filePath", "lineStart",
            ])

            # EnumConstant nodes — semantic payload for enum-as-config registries.
            # `args` is a JSON-serialized blob kept for forensic inspection; `argList`
            # is a flat string array usable in `IN` predicates. Both ship because
            # FalkorDB stores arrays natively — no per-token explosion needed. Absent
            # in pre-1.1 exports; `data.get` returns [] so older graphs no-op.
            enum_constants = data.get("enumConstants", [])
            self._batch_nodes(progress, "Enum Constants", enum_constants,
                              "EnumConstant", "fqn", [
                                  "name", "ordinal", "enumFqn",
                                  "args", "argList", "argTypes",
                                  "filePath", "lineStart",
                              ])

            modules = data.get("modules", [])
            self._batch_nodes(progress, "Modules", modules, "Module", "name", ["type"])

            # Deduplicate annotations
            ann_fqns = set()
            for a in data.get("annotations", []):
                ann_fqns.add(a.get("annotationFqn", ""))
            for cls in classes:
                for a in cls.get("annotations", []):
                    ann_fqns.add(a.get("fqn", ""))
            ann_fqns.discard("")
            ann_nodes = [{"fqn": fqn, "name": fqn.split(".")[-1]} for fqn in ann_fqns]
            self._batch_nodes(progress, "Annotations", ann_nodes, "Annotation", "fqn", ["name"])

            # Spring nodes. Every node is stamped with `wing = graph_name` so the
            # cross-wing bridge pass (bridge_http.compute_hits) can filter Spring
            # Endpoints against Vue ApiCalls that live in a different wing on the
            # same FalkorDB instance. Without `wing` on Endpoint the bridge
            # query's `e.wing IS NOT NULL` check is always false and zero HITS
            # edges are emitted.
            graph_wing = data.get("project", {}).get("name", "") or "default"
            spring = data.get("spring")
            if spring:
                beans = [dict(b, wing=graph_wing) for b in spring.get("beans", [])]
                self._batch_nodes(progress, "Spring Beans", beans, "SpringBean", "name", [
                    "classFqn", "scope", "profile", "type", "wing",
                ])
                endpoints = spring.get("endpoints", [])
                for ep in endpoints:
                    if "id" not in ep:
                        ep["id"] = f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"
                    ep["wing"] = graph_wing
                self._batch_nodes(progress, "Endpoints", endpoints, "Endpoint", "id", [
                    "path", "httpMethod", "controllerFqn", "handlerMethodFqn", "wing",
                ])

            # --- EXTERNAL STUB NODES ---
            # Create stub nodes for external (library) classes/methods referenced in edges.
            # The plugin already resolves calls to library methods — we just need nodes for them.
            project_class_fqns = {c["fqn"] for c in classes}
            project_method_fqns = {m["fqn"] for m in methods}

            ext_class_fqns = set()
            ext_method_fqns = set()

            # From call graph: callee methods not in project
            for c in data.get("callGraph", []):
                callee = c.get("calleeFqn", "")
                if callee and callee not in project_method_fqns:
                    ext_method_fqns.add(callee)
                    # Extract class FQN from method FQN (before #)
                    if "#" in callee:
                        ext_class_fqns.add(callee.split("#")[0])

            # From inheritance: parent classes not in project
            for e in data.get("inheritance", []):
                parent = e.get("parentFqn", "")
                if parent and parent not in project_class_fqns:
                    ext_class_fqns.add(parent)

            # From overrides: parent methods not in project
            for o in data.get("methodOverrides", []):
                parent = o.get("overridesFqn", "")
                if parent and parent not in project_method_fqns:
                    ext_method_fqns.add(parent)
                    if "#" in parent:
                        ext_class_fqns.add(parent.split("#")[0])

            # Remove any external classes that are actually project classes
            ext_class_fqns -= project_class_fqns

            # Create external class stubs
            ext_class_nodes = []
            for fqn in ext_class_fqns:
                name = fqn.split(".")[-1] if "." in fqn else fqn
                pkg = fqn.rsplit(".", 1)[0] if "." in fqn else ""
                ext_class_nodes.append({
                    "fqn": fqn, "name": name, "kind": "CLASS",
                    "filePath": "", "lineStart": 0, "lineEnd": 0,
                    "packageName": pkg, "enclosingClass": "", "superClass": "",
                    "external": True,
                })
            self._batch_nodes(progress, "External Classes", ext_class_nodes, "Class", "fqn", [
                "name", "kind", "filePath", "lineStart", "lineEnd",
                "packageName", "enclosingClass", "superClass", "external",
            ])

            # Split method stubs into truly external vs project implicit constructors.
            # Project classes may have implicit default constructors that PSI doesn't export
            # but are referenced in call edges — these should NOT be marked external.
            ext_method_nodes = []
            implicit_method_nodes = []
            for fqn in ext_method_fqns:
                class_fqn = fqn.split("#")[0] if "#" in fqn else ""
                name = fqn.split("#")[1].split("(")[0] if "#" in fqn else fqn
                # Handle inner classes: com.example.Outer$Inner → constructor name is "Inner"
                class_simple = class_fqn.split(".")[-1] if class_fqn else ""
                if "$" in class_simple:
                    class_simple = class_simple.split("$")[-1]
                is_constructor = (name == class_simple) if class_fqn else False
                is_project_class = class_fqn in project_class_fqns
                node = {
                    "fqn": fqn, "name": name, "classFqn": class_fqn,
                    "returnType": "", "isConstructor": is_constructor,
                    "filePath": "", "lineStart": 0, "lineEnd": 0,
                    "external": not is_project_class,
                }
                if is_project_class:
                    implicit_method_nodes.append(node)
                else:
                    ext_method_nodes.append(node)

            self._batch_nodes(progress, "External Methods", ext_method_nodes, "Method", "fqn", [
                "name", "classFqn", "returnType", "isConstructor",
                "filePath", "lineStart", "lineEnd", "external",
            ])
            if implicit_method_nodes:
                self._batch_nodes(progress, "Implicit Methods", implicit_method_nodes, "Method", "fqn", [
                    "name", "classFqn", "returnType", "isConstructor",
                    "filePath", "lineStart", "lineEnd", "external",
                ])

            # HAS_METHOD for external + implicit methods → their classes
            ext_has_method = [{"src": m["classFqn"], "dst": m["fqn"]}
                              for m in ext_method_nodes + implicit_method_nodes if m["classFqn"]]

            # --- EDGES ---

            # HAS_METHOD (Class → Method)
            has_method = [{"src": m["classFqn"], "dst": m["fqn"]} for m in methods]
            has_method.extend(ext_has_method)
            self._batch_edges(progress, "HAS_METHOD", has_method, "Class", "fqn", "Method", "fqn")

            # HAS_FIELD (Class → Field)
            has_field = [{"src": f["classFqn"], "dst": f["fqn"]} for f in fields]
            self._batch_edges(progress, "HAS_FIELD", has_field, "Class", "fqn", "Field", "fqn")

            # HAS_ENUM_CONSTANT (Class → EnumConstant). Skipped when `enumConstants`
            # is empty (pre-1.1 exports / non-Java adapters).
            has_enum_const = [{"src": e["enumFqn"], "dst": e["fqn"]} for e in enum_constants]
            self._batch_edges(progress, "HAS_ENUM_CONSTANT", has_enum_const,
                              "Class", "fqn", "EnumConstant", "fqn")

            # EXTENDS
            extends = [{"src": e["childFqn"], "dst": e["parentFqn"]}
                       for e in data.get("inheritance", []) if e.get("relationType") == "EXTENDS"]
            self._batch_edges(progress, "EXTENDS", extends, "Class", "fqn", "Class", "fqn")

            # IMPLEMENTS
            implements = [{"src": e["childFqn"], "dst": e["parentFqn"]}
                          for e in data.get("inheritance", []) if e.get("relationType") == "IMPLEMENTS"]
            self._batch_edges(progress, "IMPLEMENTS", implements, "Class", "fqn", "Class", "fqn")

            # CALLS (Method → Method) — the big one
            calls = [{"src": c["callerFqn"], "dst": c["calleeFqn"], "line": c.get("line", 0)}
                     for c in data.get("callGraph", [])]
            self._batch_edges_with_props(progress, "CALLS", calls, "Method", "fqn", "Method", "fqn", ["line"])

            # OVERRIDES (Method → Method)
            overrides = [{"src": o["methodFqn"], "dst": o["overridesFqn"]}
                         for o in data.get("methodOverrides", [])]
            self._batch_edges(progress, "OVERRIDES", overrides, "Method", "fqn", "Method", "fqn")

            # ANNOTATED_WITH — edges carry the `attributes` JSON blob (resolved
            # values; `{}` for pre-1.1 exports). Group by target label since each
            # label has its own primary-key column.
            ann_groups = {"Class": [], "Method": [], "Field": []}
            for a in data.get("annotations", []):
                kind = a.get("targetKind", "CLASS")
                label = "Class" if kind == "CLASS" else "Method" if kind == "METHOD" else "Field"
                ann_groups[label].append({
                    "src": a["targetFqn"],
                    "dst": a["annotationFqn"],
                    "attributes": a.get("attributes", "{}"),
                })
            for label, edges in ann_groups.items():
                if edges:
                    self._batch_edges_with_props(
                        progress, f"ANNOTATED_WITH ({label})", edges,
                        label, "fqn", "Annotation", "fqn",
                        prop_names=["attributes"], rel_type="ANNOTATED_WITH",
                    )

            # Spring edges
            if spring:
                handles = [{"src": ep["handlerMethodFqn"],
                            "dst": f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"}
                           for ep in spring.get("endpoints", [])]
                self._batch_edges(progress, "HANDLES", handles, "Method", "fqn", "Endpoint", "id")

                injects = [{"src": inj["targetClassFqn"], "dst": inj["injectedClassFqn"],
                            "field": inj.get("targetFieldOrParam", ""), "type": inj.get("injectionType", "")}
                           for inj in spring.get("injections", [])]
                self._batch_edges_with_props(progress, "INJECTS", injects,
                                             "SpringBean", "classFqn", "SpringBean", "classFqn",
                                             ["field", "type"])

            # Vue 3 — load the frontend subdoc if present. Kept inside the
            # `with Progress(...)` context so `progress.add_task` has a live
            # context (Rich raises on a stopped progress). Java-only exports
            # pass through unchanged: `data.get("vue3")` is None.
            vue3 = data.get("vue3")
            if vue3:
                self._load_vue3(progress, vue3, graph_name=data.get("project", {}).get("name", ""))

        # Post-import phase: compute PageRank on the call graph and write
        # it back as Method.pagerank + Class.pagerank. One-time cost (~5-15s
        # for 80K methods). Enables "important methods" queries via
        # `ORDER BY pagerank DESC` with no runtime traversal.
        stats = data.get("stats", {})
        try:
            from onelens.importer import pagerank as _pr

            pr_stats = _pr.run(self.db)
            stats["pagerank"] = pr_stats
            if pr_stats.get("methods_scored"):
                print(
                    f"PageRank: {pr_stats['methods_scored']} methods, "
                    f"{pr_stats['classes_scored']} classes "
                    f"({pr_stats['total_ms']} ms)"
                )
        except Exception as e:
            logger.warning("PageRank computation failed: %s", e)
            stats["pagerank"] = {"error": str(e)}

        elapsed = time.time() - start
        stats["importDurationSec"] = round(elapsed, 1)
        print(f"\nImport complete in {elapsed:.1f}s")
        return stats

    def _load_vue3(self, progress, vue3: dict, graph_name: str):
        """Load the Vue 3 subdoc into the same graph wing as the Java/Spring nodes.

        Every Vue node is tagged with `wing = graph_name` so the bridge pass
        (`bridge_http.py`) can match cross-wing ApiCall ↔ Endpoint pairs when
        multiple repos share one FalkorDB graph.
        """
        wing = graph_name or "default"

        # Components — primary key = filePath (unique per repo).
        components = [dict(c, wing=wing) for c in vue3.get("components", [])]
        for c in components:
            # Props list is a list of small dicts; flatten to a comma-separated name
            # string for the FTS index. The full prop detail lives as separate fields.
            props = c.get("props", []) or []
            c["propNames"] = ",".join(p.get("name", "") for p in props)
            c["emits"] = ",".join(c.get("emits", []) or [])
            c["exposes"] = ",".join(c.get("exposes", []) or [])
        self._batch_nodes(progress, "Vue Components", components, "Component", "filePath", [
            "name", "scriptSetup", "propNames", "emits", "exposes", "body", "wing",
        ])

        # Composables
        composables = [dict(c, wing=wing) for c in vue3.get("composables", [])]
        self._batch_nodes(progress, "Vue Composables", composables, "Composable", "fqn", [
            "name", "filePath", "body", "wing",
        ])

        # Stores
        stores = [dict(s, wing=wing) for s in vue3.get("stores", [])]
        for s in stores:
            s["state"] = ",".join(s.get("state", []) or [])
            s["getters"] = ",".join(s.get("getters", []) or [])
            s["actions"] = ",".join(s.get("actions", []) or [])
        self._batch_nodes(progress, "Vue Stores", stores, "Store", "id", [
            "name", "filePath", "style", "state", "getters", "actions", "body", "wing",
        ])

        # Routes
        routes = [dict(r, wing=wing) for r in vue3.get("routes", [])]
        for r in routes:
            r["meta"] = ",".join(f"{k}={v}" for k, v in (r.get("meta") or {}).items())
        self._batch_nodes(progress, "Vue Routes", routes, "Route", "name", [
            "path", "componentRef", "meta", "parentName", "filePath", "wing",
        ])

        # ApiCalls — fqn synthesized to be unique even across repeated callers.
        api_calls = vue3.get("apiCalls", []) or []
        for a in api_calls:
            a["fqn"] = f"{a.get('method', '')}:{a.get('path', '')}:{a.get('callerFqn', '')}"
            a["wing"] = wing
        self._batch_nodes(progress, "Vue ApiCalls", api_calls, "ApiCall", "fqn", [
            "method", "path", "parametric", "binding", "callerFqn", "filePath", "wing",
        ])

        # Edges — caller match is a 3-way OR because collectors emit
        # `callerFqn` in three shapes:
        #   Component-scoped call   -> "<filePath>::<ComponentName>"   (CallThroughResolver)
        #   Function-scoped call    -> "<filePath>::<fnName>"           (ApiCallCollector)
        #   Module-top-level call   -> "<filePath>::<module>"
        # Component nodes are keyed on `filePath` (no `::name` suffix), so a
        # literal equality check misses most component-sourced edges. We
        # additionally accept any caller whose string starts with
        # `c.filePath + '::'` — which matches Component rows without
        # double-counting Composable rows whose `fqn` already equals the full
        # caller string.
        uses_store = [
            {"caller": e.get("callerFqn", ""), "store": e.get("storeId", ""),
             "indirect": bool(e.get("indirect", False)), "via": e.get("via", "") or ""}
            for e in vue3.get("usesStore", [])
        ]
        self._batch_edges_simple(
            progress, "USES_STORE", uses_store,
            "MATCH (c {wing: $wing}) "
            "WHERE (c:Component OR c:Composable) AND ("
            "    c.fqn = e.caller OR c.filePath = e.caller "
            " OR (c.filePath IS NOT NULL AND e.caller STARTS WITH (c.filePath + '::'))"
            ")",
            "MATCH (s:Store {wing: $wing, id: e.store})",
            "MERGE (c)-[r:USES_STORE]->(s) SET r.indirect = e.indirect, r.via = e.via",
            wing=wing,
        )

        uses_comp = [
            {"caller": e.get("callerFqn", ""), "comp": e.get("composableFqn", "")}
            for e in vue3.get("usesComposable", [])
        ]
        self._batch_edges_simple(
            progress, "USES_COMPOSABLE", uses_comp,
            "MATCH (c {wing: $wing}) "
            "WHERE (c:Component OR c:Composable) AND ("
            "    c.fqn = e.caller OR c.filePath = e.caller "
            " OR (c.filePath IS NOT NULL AND e.caller STARTS WITH (c.filePath + '::'))"
            ")",
            "MATCH (co:Composable {wing: $wing, fqn: e.comp})",
            "MERGE (c)-[:USES_COMPOSABLE]->(co)",
            wing=wing,
        )

        # DISPATCHES: route.componentRef is as-typed in source ('./views/X.vue'),
        # Component.filePath is project-relative ('src/modules/ticket/views/X.vue').
        # Resolve the relative ref against the route file's directory so the
        # match is exact — ENDS WITH alone overmatches every component whose
        # filename happens to appear multiple places in the tree.
        import os.path as _osp
        routes_by_name = {r.get("name", ""): r for r in vue3.get("routes", []) if r.get("name")}

        def _resolve_comp(route_name: str, ref: str) -> str:
            if not ref:
                return ""
            cleaned = ref
            # Resolve relative path against the route file's directory.
            rt = routes_by_name.get(route_name)
            if rt and rt.get("filePath") and (cleaned.startswith("./") or cleaned.startswith("../") or not cleaned.startswith("/")):
                base_dir = _osp.dirname(rt["filePath"])
                cleaned = _osp.normpath(_osp.join(base_dir, cleaned)).replace("\\", "/")
            else:
                while cleaned.startswith("./") or cleaned.startswith("../"):
                    cleaned = cleaned[cleaned.index("/") + 1:]
            return cleaned

        dispatches = [
            {"route": e.get("routeName", ""),
             "comp": _resolve_comp(e.get("routeName", ""), e.get("componentRef", ""))}
            for e in vue3.get("dispatches", [])
            if e.get("componentRef")
        ]
        self._batch_edges_simple(
            progress, "DISPATCHES", dispatches,
            "MATCH (r:Route {wing: $wing, name: e.route})",
            "MATCH (co:Component {wing: $wing, filePath: e.comp})",
            "MERGE (r)-[:DISPATCHES]->(co)",
            wing=wing,
            src_var="r",
        )

        calls_api = [
            {"caller": e.get("callerFqn", ""), "api": e.get("apiCallFqn", "")}
            for e in vue3.get("callsApi", [])
        ]
        # Restrict the caller MATCH to Component or Composable — an untyped match
        # also picks up ApiCall / Route nodes (they carry filePath) and pairs
        # every such match with every target ApiCall in the batch, which over-
        # produces edges by a factor of ~20 on a 1500-component repo.
        self._batch_edges_simple(
            progress, "CALLS_API", calls_api,
            "MATCH (c {wing: $wing}) "
            "WHERE (c:Component OR c:Composable) AND ("
            "    c.fqn = e.caller OR c.filePath = e.caller "
            " OR (c.filePath IS NOT NULL AND e.caller STARTS WITH (c.filePath + '::'))"
            ")",
            "MATCH (a:ApiCall {wing: $wing, fqn: e.api})",
            "MERGE (c)-[:CALLS_API]->(a)",
            wing=wing,
        )

        # Bridge pass — emit cross-wing HITS edges between Vue ApiCall and Spring Endpoint.
        try:
            from onelens.importer import bridge_http

            bridge_stats = bridge_http.compute_hits(self.db, graph_name=wing)
            logger.info("Vue 3 bridge pass: %s", bridge_stats)
        except Exception as e:
            logger.warning("Vue 3 bridge pass failed: %s", e)

    def _batch_edges_simple(self, progress, desc: str, edges: list,
                             src_match: str, dst_match: str, tail: str, wing: str,
                             src_var: str = "c"):
        """UNWIND-based batched edge creation with caller-provided MATCH/MERGE fragments.

        `src_var` names the Cypher variable bound by `src_match`. We carry that
        variable (alongside `e`) through the `WITH` clause into `dst_match`. A
        previous version hard-coded `WITH e, c` which silently broke the
        DISPATCHES batch (src bound as `r`, not `c`) — the batch would throw
        `c is undefined` and every DISPATCHES edge would be swallowed by the
        generic except below.

        Used only for the Vue 3 edges which do not fit the tidy (label,key)-based
        `_batch_edges`. Keeping it separate avoids polluting the Java code path.
        """
        if not edges:
            return
        query = (
            "UNWIND $batch AS e "
            f"{src_match} WITH e, {src_var} "
            f"{dst_match} "
            f"{tail}"
        )
        task = progress.add_task(f"{desc}...", total=len(edges))
        for i in range(0, len(edges), EDGE_BATCH):
            batch = edges[i:i + EDGE_BATCH]
            try:
                self.db.execute(query, {"batch": batch, "wing": wing})
            except Exception as e:
                logger.warning("Edge batch %s failed: %s", desc, e)
            progress.update(task, advance=len(batch))

    def _batch_nodes(self, progress, desc: str, items: list, label: str, pk: str, props: list[str]):
        """Create nodes using UNWIND in batches."""
        if not items:
            return

        all_props = [pk] + props
        set_clause = ", ".join(f"n.{p} = item.{p}" for p in props)
        query = f"UNWIND $batch AS item CREATE (n:{label} {{{pk}: item.{pk}}}) SET {set_clause}"

        task = progress.add_task(f"{desc}...", total=len(items))
        for i in range(0, len(items), NODE_BATCH):
            batch = items[i:i + NODE_BATCH]
            # Sanitize: ensure all props exist in each item
            clean = []
            for item in batch:
                row = {}
                for p in all_props:
                    val = item.get(p)
                    if val is None:
                        row[p] = "" if isinstance(item.get(p, ""), str) else 0
                    else:
                        row[p] = val
                clean.append(row)

            try:
                self.db.execute(query, {"batch": clean})
            except Exception as e:
                logger.warning(f"Batch {label} failed, falling back to individual: {e}")
                for item in clean:
                    try:
                        self.db.execute(
                            f"CREATE (n:{label} {{{pk}: $pk_val}}) SET " +
                            ", ".join(f"n.{p} = ${p}" for p in props),
                            {"pk_val": item[pk], **{p: item[p] for p in props}}
                        )
                    except Exception:
                        pass

            progress.update(task, advance=len(batch))

    def _batch_edges(self, progress, desc: str, edges: list,
                     src_label: str, src_key: str, dst_label: str, dst_key: str,
                     rel_type: str | None = None):
        """Create edges using UNWIND in batches."""
        if not edges:
            return

        rt = rel_type or desc.split(" ")[0]  # Use desc as rel type if not specified
        query = f"""
            UNWIND $batch AS edge
            MATCH (a:{src_label} {{{src_key}: edge.src}})
            MATCH (b:{dst_label} {{{dst_key}: edge.dst}})
            CREATE (a)-[:{rt}]->(b)
        """

        failed_count = 0
        task = progress.add_task(f"{desc}...", total=len(edges))
        for i in range(0, len(edges), EDGE_BATCH):
            batch = edges[i:i + EDGE_BATCH]
            try:
                self.db.execute(query, {"batch": batch})
            except Exception as e:
                logger.warning(f"Batch {desc} failed, retrying individually: {e}")
                for edge in batch:
                    try:
                        single_q = f"""
                            MATCH (a:{src_label} {{{src_key}: $src}})
                            MATCH (b:{dst_label} {{{dst_key}: $dst}})
                            CREATE (a)-[:{rt}]->(b)
                        """
                        self.db.execute(single_q, {"src": edge["src"], "dst": edge["dst"]})
                    except Exception:
                        failed_count += 1
            progress.update(task, advance=len(batch))
        if failed_count > 0:
            logger.warning(f"{desc}: {failed_count} edges failed (missing nodes)")

    def _batch_edges_with_props(self, progress, desc: str, edges: list,
                                src_label: str, src_key: str, dst_label: str, dst_key: str,
                                prop_names: list[str], rel_type: str | None = None):
        """Create edges with properties using UNWIND in batches."""
        if not edges:
            return

        rt = rel_type or desc
        prop_clause = ", ".join(f"{p}: edge.{p}" for p in prop_names)
        query = f"""
            UNWIND $batch AS edge
            MATCH (a:{src_label} {{{src_key}: edge.src}})
            MATCH (b:{dst_label} {{{dst_key}: edge.dst}})
            CREATE (a)-[:{rt} {{{prop_clause}}}]->(b)
        """

        failed_count = 0
        task = progress.add_task(f"{desc}...", total=len(edges))
        for i in range(0, len(edges), EDGE_BATCH):
            batch = edges[i:i + EDGE_BATCH]
            try:
                self.db.execute(query, {"batch": batch})
            except Exception as e:
                logger.warning(f"Batch {desc} failed, retrying individually: {e}")
                for edge in batch:
                    try:
                        props_set = ", ".join(f"{p}: ${p}" for p in prop_names)
                        single_q = f"""
                            MATCH (a:{src_label} {{{src_key}: $src}})
                            MATCH (b:{dst_label} {{{dst_key}: $dst}})
                            CREATE (a)-[:{rt} {{{props_set}}}]->(b)
                        """
                        self.db.execute(single_q, {"src": edge["src"], "dst": edge["dst"],
                                                    **{p: edge.get(p, "") for p in prop_names}})
                    except Exception:
                        failed_count += 1
            progress.update(task, advance=len(batch))
        if failed_count > 0:
            logger.warning(f"{desc}: {failed_count} edges failed (missing nodes)")
