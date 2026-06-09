"""Full JSON import into any Cypher-compatible graph DB using batch UNWIND."""

import logging
import time
from pathlib import Path

# orjson parses the 500 MB+ a 500 MB export in ~2 s vs ~10 s with stdlib json.
# Falls back cleanly if the dep ever goes missing.
try:
    import orjson as _json  # type: ignore[import-not-found]
    _USE_ORJSON = True
except ImportError:  # pragma: no cover
    import json as _json  # type: ignore[no-redef]
    _USE_ORJSON = False

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from onelens.graph.db import GraphDB
from onelens.importer.schema import NODE_SCHEMA, FULLTEXT_SCHEMA

logger = logging.getLogger(__name__)

from onelens.importer.graph_writer import (
    GraphWriter,
    NODE_BATCH,
    EDGE_BATCH,
    _PRIMITIVES,
    _TXN_ANNOS,
    _ASYNC_ANNOS,
    _DEPRECATED_ANNOS,
    _normalize_type,
    _anno_simple_names,
    _enrich_method,
)
from onelens.importer.loaders.annotations import AnnotationLoader
from onelens.importer.loaders.enums import EnumLoader
from onelens.importer.loaders.jpa import JpaLoader
from onelens.importer.loaders.spring import SpringLoader
from onelens.importer.loaders.tests import TestLoader
from onelens.importer.loaders.type_flow import TypeFlowLoader
from onelens.importer.loaders.data_flow import DataFlowLoader


class GraphLoader:
    def __init__(self, db: GraphDB):
        self.db = db
        self.writer = GraphWriter(db)

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

            # Parse JSON — orjson.loads takes bytes + returns dict; stdlib
            # json.load takes a text stream. Normalize by reading bytes once.
            task = progress.add_task("Loading JSON...", total=1)
            t_json = time.time()
            with open(export_path, "rb") as f:
                raw = f.read()
            if _USE_ORJSON:
                data = _json.loads(raw)
            else:
                # stdlib json needs str not bytes on 3.10+; decode.
                data = _json.loads(raw.decode("utf-8"))
            logger.info(
                "JSON parse: %.2fs (%s, %.1f MB)",
                time.time() - t_json,
                "orjson" if _USE_ORJSON else "stdlib",
                len(raw) / 1024 / 1024,
            )
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
            # Tier-0 enrichment: derive visibility/static/abstract/deprecated/
            # paramCount/transactional/async from already-exported modifiers +
            # annotations. The full loader used to discard all of this.
            for _m in methods:
                _enrich_method(_m)
            self._batch_nodes(progress, "Methods", methods, "Method", "fqn", [
                "name", "classFqn", "returnType", "isConstructor",
                "filePath", "lineStart", "lineEnd",
                "body", "javadoc",
                "visibility", "isStatic", "isAbstract", "isDeprecated",
                "paramCount", "isTransactional", "isAsync",
            ])

            fields = data.get("fields", [])
            self._batch_nodes(progress, "Fields", fields, "Field", "fqn", [
                "name", "classFqn", "type", "filePath", "lineStart",
            ])

            modules = data.get("modules", [])
            self._batch_nodes(progress, "Modules", modules, "Module", "name", ["type"])

            # Annotation nodes + ANNOTATED_WITH edges are written by AnnotationLoader.load_full
            # (called below at the edge-block site, after base Class/Method/Field nodes exist).

            # Spring nodes. Every node is stamped with `wing = graph_name` so the
            # cross-wing bridge pass (bridge_http.compute_hits) can filter Spring
            # Endpoints against Vue ApiCalls that live in a different wing on the
            # same FalkorDB instance. Without `wing` on Endpoint the bridge
            # query's `e.wing IS NOT NULL` check is always false and zero HITS
            # edges are emitted.
            # Phase C: prefer the workspace header's graphId so multi-repo exports
            # tagged with a user-chosen graph id stamp the right wing. Falls back
            # to project.name for pre-workspace exports.
            workspace_header = data.get("workspace") or {}
            graph_wing = (
                workspace_header.get("graphId")
                or data.get("project", {}).get("name", "")
                or "default"
            )
            dup_policy = workspace_header.get("duplicateFqnPolicy", "merge")
            if dup_policy != "merge":
                # MERGE is the only policy wired today — warn/error/suffix are
                # tracked in Phase C PROGRESS; keep the log loud so adopters see it.
                print(
                    f"[onelens] workspace duplicateFqnPolicy='{dup_policy}' is not yet"
                    f" enforced — falling back to MERGE (duplicates upsert silently).",
                    flush=True,
                )
            SpringLoader().load_full(self.writer, progress, data, graph_wing)

            # --- APPS + PACKAGES (Phase C2) ---
            # Apps = one per @SpringBootApplication / Vue root. Packages mirror the
            # Java package hierarchy (Spring) or `src/<segment>` folders (Vue3).
            # Emitted before class-level edges so CONTAINS can wire in one pass.
            apps = [dict(a, wing=graph_wing) for a in data.get("apps", [])]
            if apps:
                self._batch_nodes(progress, "Apps", apps, "App", "id", [
                    "name", "type", "rootFqn", "rootPath", "scanPackages",
                    "moduleNames", "wing",
                ])

            packages = [dict(p, wing=graph_wing) for p in data.get("packages", [])]
            if packages:
                self._batch_nodes(progress, "Packages", packages, "Package", "id", [
                    "name", "parentId", "appId", "wing",
                ])

            # EnumConstant nodes + HAS_ENUM_CONSTANT edges — semantic payload for
            # enum-as-config registries. Absent in pre-1.1 exports; no-ops safely.
            # Runs after Field nodes (which back the dual-label) and after graph_wing
            # is resolved. Combines the former dual-label block (~131) and edge block
            # (~322) into a single call.
            EnumLoader().load_full(self.writer, progress, data, graph_wing)

            JpaLoader().load_full(self.writer, progress, data, graph_wing)

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

            # Tier-0 type-flow: declared return / param / throws types become
            # edges to Class nodes. Collect their FQNs so external types (JDK,
            # libraries) get stubs and the edges below resolve via MATCH.
            for m in methods:
                rt = _normalize_type(m.get("returnType", ""))
                if rt and rt not in project_class_fqns:
                    ext_class_fqns.add(rt)
                for p in m.get("parameters", []) or []:
                    pt = _normalize_type(p.get("type", ""))
                    if pt and pt not in project_class_fqns:
                        ext_class_fqns.add(pt)
                for tt in m.get("throwsTypes", []) or []:
                    et = _normalize_type(tt)
                    if et and et not in project_class_fqns:
                        ext_class_fqns.add(et)

            # INSTANTIATES targets (Tier-1) — `new ArrayList()` etc. need a Class
            # stub so the edge resolves. Most already arrive via constructor
            # CALLS, but collect defensively.
            _dataflow = data.get("dataFlow") or {}
            for inst in _dataflow.get("instantiations", []) or []:
                ic = inst.get("classFqn", "")
                if ic and ic not in project_class_fqns:
                    ext_class_fqns.add(ic)

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

            # Tier-0 type-flow edges (Method → Class). Powers "what produces a
            # User" (RETURNS), "what consumes a UserDto" (HAS_PARAMETER), and
            # "what can throw PaymentDeclined" (THROWS). Reference types only —
            # primitives/void/type-vars filtered by _normalize_type.
            TypeFlowLoader().load_full(self.writer, progress, methods)

            # Tier-1 data-flow edges: READS_FIELD / WRITES_FIELD (Method→Field)
            # + INSTANTIATES (Method→Class). Field targets resolve against
            # existing Field nodes (external/library field access silently
            # drops — we only model project data-flow). The read/write split
            # answers "who mutates order.status" vs "who reads the cache".
            DataFlowLoader().load_full(self.writer, progress, data)

            # ANNOTATED_WITH — Annotation nodes + ANNOTATED_WITH edges (nodes + edges
            # in one call so nodes exist before edges). Runs here, after base
            # Class/Method/Field nodes exist, to preserve edge-resolution ordering.
            AnnotationLoader().load_full(self.writer, progress, data, graph_wing)

            # --- APP / PACKAGE EDGES (Phase C2) ---
            if packages:
                parent_edges = [{"src": p["parentId"], "dst": p["id"]}
                                for p in packages if p.get("parentId")]
                if parent_edges:
                    self._batch_edges(progress, "PARENT_OF", parent_edges,
                                      "Package", "id", "Package", "id")

            if apps and packages:
                # App → Package for every package whose scan prefix matches the app.
                # Materialising at every package (not only scan roots) so one-hop
                # queries like `MATCH (a:App)-[:CONTAINS]->(p:Package) WHERE p.name =~
                # 'com.acme.order.*'` just work. For 10-app / 500-package projects
                # this stays well under 5000 edges.
                app_contains_pkg = [{"src": p["appId"], "dst": p["id"]}
                                    for p in packages if p.get("appId")]
                if app_contains_pkg:
                    self._batch_edges(progress, "CONTAINS (App→Package)",
                                      app_contains_pkg,
                                      "App", "id", "Package", "id",
                                      rel_type="CONTAINS")

            if packages and classes:
                pkg_ids = {p["id"] for p in packages}
                pkg_contains_class = [{"src": c["packageName"], "dst": c["fqn"]}
                                      for c in classes
                                      if c.get("packageName") in pkg_ids]
                if pkg_contains_class:
                    self._batch_edges(progress, "CONTAINS (Package→Class)",
                                      pkg_contains_class,
                                      "Package", "id", "Class", "fqn",
                                      rel_type="CONTAINS")

            # Vue 3 — load the frontend subdoc if present. Kept inside the
            # `with Progress(...)` context so `progress.add_task` has a live
            # context (Rich raises on a stopped progress). Java-only exports
            # pass through unchanged: `data.get("vue3")` is None.
            # Tests (Phase Q.code) — dual-label :Method:TestCase + MOCKS/SPIES
            # edges + derived :TESTS edges from direct CALLS.
            TestLoader().load_full(self.writer, progress, data, graph_wing)

            # SQL surface (Phase C6) — migrations + custom queries. Opt-in via
            # `sql:` section of onelens.workspace.yaml (auto-detected Flyway is
            # the default). Reads the yaml directly from disk because the plugin
            # only forwards its *effective* fields; keeping the SQL config
            # loader-side lets us extend without rebuilding the plugin.
            self._load_sql(progress, workspace_header, graph_wing)

            vue3 = data.get("vue3")
            if vue3:
                self._load_vue3(progress, vue3, graph_name=graph_wing)

                # Package → Vue member CONTAINS edges (Phase C2). Packages carry
                # `id = vue:<rootName>:<segment>`, `name = segment`. A member
                # whose relative filePath starts with `<segment>/` (or `src/<segment>/`)
                # belongs to that package. The segment-only match can fire for
                # multi-root workspaces that share a segment name — accepted
                # trade-off until per-member appId lands in C2.1.
                vue_pkgs = [p for p in packages if p.get("id", "").startswith("vue:")]
                if vue_pkgs:
                    def _top(fp: str) -> str:
                        p = fp.lstrip("/").removeprefix("src/")
                        return p.split("/", 1)[0] if "/" in p else ""

                    pkg_by_name = {p["name"]: p["id"] for p in vue_pkgs}

                    def _emit(label, items, key):
                        edges = []
                        seen = set()
                        for it in items:
                            fp = it.get("filePath", "")
                            seg = _top(fp)
                            pid = pkg_by_name.get(seg)
                            if not pid or not it.get(key):
                                continue
                            dedup = (pid, it[key])
                            if dedup in seen:
                                continue
                            seen.add(dedup)
                            edges.append({"src": pid, "dst": it[key]})
                        if edges:
                            self._batch_edges(progress, f"CONTAINS (Package→{label})",
                                              edges, "Package", "id", label, key,
                                              rel_type="CONTAINS")

                    _emit("Component", vue3.get("components", []), "filePath")
                    _emit("Composable", vue3.get("composables", []), "fqn")
                    _emit("Store", vue3.get("stores", []), "id")
                    _emit("JsModule", vue3.get("modules", []), "filePath")

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

        # Full-path concatenation — walk parent chain and join segments so
        # queries like `WHERE r.fullPath CONTAINS '/ticket'` work. The raw
        # `path` is relative-only in vue-router nested configs (`:id`,
        # `create`, `${config.prefix}`); without a rolled-up path every
        # nested route appears detached from its domain.
        by_name = {r["name"]: r for r in routes if r.get("name")}

        def _full_path(r: dict, seen: set[str] | None = None) -> str:
            seen = seen or set()
            if not r or r.get("name") in seen:
                return r.get("path", "") if r else ""
            seen.add(r.get("name", ""))
            own = (r.get("path") or "").strip()
            parent = by_name.get(r.get("parentName") or "")
            if parent is None:
                return own if own.startswith("/") else f"/{own}" if own else ""
            pref = _full_path(parent, seen)
            # Absolute child path overrides parent prefix (vue-router semantics).
            if own.startswith("/"):
                return own
            joined = f"{pref.rstrip('/')}/{own}" if own else pref
            return joined or "/"

        for r in routes:
            r["fullPath"] = _full_path(r)

        self._batch_nodes(progress, "Vue Routes", routes, "Route", "name", [
            "path", "fullPath", "componentRef", "meta", "parentName", "filePath", "wing",
        ])

        # ApiCalls — fqn synthesized to be unique even across repeated callers.
        api_calls = vue3.get("apiCalls", []) or []
        for a in api_calls:
            a["fqn"] = f"{a.get('method', '')}:{a.get('path', '')}:{a.get('callerFqn', '')}"
            a["wing"] = wing
        self._batch_nodes(progress, "Vue ApiCalls", api_calls, "ApiCall", "fqn", [
            "method", "path", "parametric", "binding", "callerFqn", "filePath", "wing",
        ])

        # Phase B2 — JS business-logic layer. `JsModule` per file (always),
        # `JsFunction` per exported top-level fn. Both carry `wing` so
        # cross-repo graphs can filter.
        modules = [dict(m, wing=wing) for m in vue3.get("modules", [])]
        # Derive a display `name` from the filePath basename (e.g.
        # `resource-list-title.vue` → `resource-list-title`). The
        # collector only emits filePath; without a name the FalkorDB
        # browser shows only the numeric node id because there's no
        # human-readable label to render.
        import os.path as _osp
        for _m in modules:
            fp = _m.get("filePath", "")
            base = _osp.basename(fp)
            # Strip extension if present (vue / js / ts / mjs).
            stem = base.rsplit(".", 1)[0] if "." in base else base
            _m.setdefault("name", stem or fp)
        self._batch_nodes(progress, "JS Modules", modules, "JsModule", "filePath", [
            "name", "fileKind", "isBarrel", "wing",
        ])

        functions = [dict(f, wing=wing) for f in vue3.get("functions", [])]
        self._batch_nodes(progress, "JS Functions", functions, "JsFunction", "fqn", [
            "name", "filePath", "exported", "isDefault", "isAsync",
            "lineStart", "lineEnd", "body", "wing",
        ])

        # HAS_FUNCTION: JsModule -> JsFunction by shared filePath. Without
        # this, cross-stack traversal (Component -[IMPORTS]-> JsModule ->
        # JsFunction -[CALLS_API]-> ApiCall) requires a filePath join in
        # Cypher, which is slow and breaks agent-style multi-hop queries.
        has_fn = [
            {"fp": f["filePath"], "fqn": f["fqn"]}
            for f in functions if f.get("filePath") and f.get("fqn")
        ]
        if has_fn:
            self._batch_edges_simple(
                progress, "HAS_FUNCTION", has_fn,
                "MATCH (m:JsModule {wing: $wing, filePath: e.fp})",
                "MATCH (f:JsFunction {wing: $wing, fqn: e.fqn})",
                "MERGE (m)-[:HAS_FUNCTION]->(f)",
                wing=wing,
                src_var="m",
            )

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
        # JsFunction carries an `fqn` that exactly equals `callerFqn` for api-
        # wrapper functions (e.g. `src/modules/x/x-api.js::fooApi`). Without
        # JsFunction in the label set, every CALLS_API edge from a plain-JS
        # api wrapper drops — the dogfood shipped 0 CALLS_API edges before
        # this was widened. Component / Composable stay included for callers
        # declared inline inside `.vue` / composable files.
        # Caller match rules per label:
        #   - Component / Composable: filePath == caller OR caller STARTS WITH
        #     (filePath + '::'). These nodes are keyed on the file itself, so
        #     the STARTS_WITH lets a `src/x/Foo.vue::fn` caller fqn still hit
        #     the `src/x/Foo.vue` component row.
        #   - JsFunction: exact fqn match only. JsFunction nodes all share
        #     `filePath` with their siblings; the STARTS_WITH fallback would
        #     match every function in the file, amplifying CALLS_API 15-20x
        #     (dogfooded — 22974 edges instead of 1404 before this split).
        self._batch_edges_simple(
            progress, "CALLS_API", calls_api,
            "MATCH (c {wing: $wing}) "
            "WHERE ("
            "  ((c:Component OR c:Composable) AND ("
            "       c.fqn = e.caller OR c.filePath = e.caller "
            "    OR (c.filePath IS NOT NULL AND e.caller STARTS WITH (c.filePath + '::'))"
            "  ))"
            "  OR (c:JsFunction AND c.fqn = e.caller)"
            ")",
            "MATCH (a:ApiCall {wing: $wing, fqn: e.api})",
            "MERGE (c)-[:CALLS_API]->(a)",
            wing=wing,
        )

        # IMPORTS edges — JsModule / Component / Composable / Store → JsFunction (or JsModule).
        # The source side can be any of those four labels, keyed on filePath.
        # Target side: when targetFqn is set, match a JsFunction by fqn;
        # otherwise fall back to a JsModule by filePath.
        imports_resolved = [
            {"src": e.get("sourceModule", ""), "tgt_fqn": e.get("targetFqn") or "",
             "name": e.get("importedName", ""),
             "alias": e.get("localAlias") or "",
             "isDefault": bool(e.get("isDefault", False)),
             "isNamespace": bool(e.get("isNamespace", False))}
            for e in vue3.get("imports", []) if e.get("targetFqn")
        ]
        # Split per source label so FalkorDB can use the `filePath` RANGE
        # index on each label individually. A single label-less match
        # forces a full-node scan (22k+ rows × N batches = minutes of
        # wall-clock). Extensions pick the correct label by the source
        # filePath extension, so each row lands on exactly one pass.
        # Source nodes can wear multiple labels at the same filePath:
        # a composable file also has a JsModule row; a `.vue` component file
        # only has a Component row. We route to the label that owns the
        # richer semantic payload — Composable / Store over JsModule so the
        # traversal `Composable -[IMPORTS]-> JsModule` is actually populated.
        composable_paths = {c["filePath"] for c in composables if c.get("filePath")}
        store_paths = {s["filePath"] for s in stores if s.get("filePath")}

        def _split_by_src_ext(rows: list[dict]) -> dict[str, list[dict]]:
            buckets: dict[str, list[dict]] = {
                "JsModule": [], "Component": [], "Composable": [], "Store": [],
            }
            for r in rows:
                s = r.get("src", "")
                if s.endswith(".vue"):
                    buckets["Component"].append(r)
                elif s in store_paths:
                    buckets["Store"].append(r)
                elif s in composable_paths:
                    buckets["Composable"].append(r)
                else:
                    buckets["JsModule"].append(r)
            return buckets

        if imports_resolved:
            for label, rows in _split_by_src_ext(imports_resolved).items():
                if not rows:
                    continue
                self._batch_edges_simple(
                    progress, f"IMPORTS (resolved · {label})", rows,
                    f"MATCH (src:{label} {{wing: $wing, filePath: e.src}})",
                    "MATCH (tgt:JsFunction {wing: $wing, fqn: e.tgt_fqn})",
                    "MERGE (src)-[r:IMPORTS]->(tgt) "
                    "SET r.importedName = e.name, r.alias = e.alias, "
                    "    r.isDefault = e.isDefault, r.isNamespace = e.isNamespace",
                    wing=wing,
                    src_var="src",
                )

        imports_modulelevel = [
            {"src": e.get("sourceModule", ""), "tgt": e.get("targetModule", ""),
             "name": e.get("importedName", ""),
             "alias": e.get("localAlias") or "",
             "unresolved": bool(e.get("unresolved", False))}
            for e in vue3.get("imports", []) if not e.get("targetFqn")
        ]
        # ES6 module resolution: `import './config'` resolves to `./config.js`
        # or `./config/index.js`. Collector emits the bare specifier; the
        # loader expands candidate filePaths so the match hits. Without
        # this, every extensionless import (thousands in a typical Vue 3
        # repo) silently drops at the JsModule join.
        expanded_imports: list[dict] = []
        module_paths: set[str] = {m["filePath"] for m in modules}
        for e in imports_modulelevel:
            tgt = e["tgt"]
            candidates = [tgt]
            if not tgt.endswith((".js", ".ts", ".mjs", ".vue")):
                candidates += [f"{tgt}.js", f"{tgt}.ts", f"{tgt}/index.js", f"{tgt}/index.ts"]
            resolved = next((c for c in candidates if c in module_paths), tgt)
            expanded_imports.append({**e, "tgt": resolved})
        if expanded_imports:
            for label, rows in _split_by_src_ext(expanded_imports).items():
                if not rows:
                    continue
                self._batch_edges_simple(
                    progress, f"IMPORTS (module · {label})", rows,
                    f"MATCH (src:{label} {{wing: $wing, filePath: e.src}})",
                    "MATCH (tgt:JsModule {wing: $wing, filePath: e.tgt})",
                    "MERGE (src)-[r:IMPORTS]->(tgt) "
                    "SET r.importedName = e.name, r.alias = e.alias, r.unresolved = e.unresolved",
                    wing=wing,
                    src_var="src",
                )

        # IMPORTS_FN bridge — the Kotlin PSI resolve step hits empty
        # `importedBindings` / `importSpecifiers` on stub-backed files, so
        # every `import { fooApi } from './x-api'` lands as a module-level
        # IMPORTS edge without a JsFunction target. We re-derive the
        # function-level edge in Python using data already in the graph:
        # for every IMPORTS edge with `importedName`, if a JsFunction with
        # that name exists at the target module's filePath, emit
        # IMPORTS_FN. Deterministic, cheap, and bypasses the stub
        # limitation entirely.
        fn_bridge_rows = [
            {"src": e["src"], "tgt": e["tgt"], "name": e["name"]}
            for e in expanded_imports
            if e.get("name") and e["name"] not in ("", "*", "default")
        ]
        if fn_bridge_rows:
            for label, rows in _split_by_src_ext(fn_bridge_rows).items():
                if not rows:
                    continue
                self._batch_edges_simple(
                    progress, f"IMPORTS_FN ({label})", rows,
                    f"MATCH (src:{label} {{wing: $wing, filePath: e.src}})",
                    "MATCH (fn:JsFunction {wing: $wing, name: e.name, filePath: e.tgt})",
                    "MERGE (src)-[:IMPORTS_FN]->(fn)",
                    wing=wing,
                    src_var="src",
                )

        # Bridge pass — emit cross-wing HITS edges between Vue ApiCall and Spring Endpoint.
        try:
            from onelens.importer import bridge_http

            bridge_stats = bridge_http.compute_hits(self.db, graph_name=wing)
            logger.info("Vue 3 bridge pass: %s", bridge_stats)
        except Exception as e:
            logger.warning("Vue 3 bridge pass failed: %s", e)

    def _load_sql(self, progress, workspace_header: dict, graph_wing: str):
        """
        Phase C6 — emit :SqlQuery / :Migration / :SqlStatement + QUERIES_TABLE /
        CREATES_TABLE / ALTERS_TABLE / DROPS_TABLE edges.

        Config source: `sql:` block inside `onelens.workspace.yaml` (path is in
        `workspace_header.configFile`). Default: auto-detect Flyway, no custom
        queries. Yaml missing? Falls back to Flyway-only auto-detect.

        Safe to call unconditionally — if no SQL sources resolve, the method
        is a no-op.
        """
        from pathlib import Path

        try:
            from onelens.miners import sql_miner
            from onelens.miners import flyway_detector
        except Exception as e:
            logger.warning("SQL miner imports failed: %s — skipping SQL phase", e)
            return

        roots_raw = workspace_header.get("roots") or []
        roots = [Path(r) for r in roots_raw if r]
        if not roots:
            return

        # --- Read `sql:` block from yaml, if present ---
        sql_cfg: dict = {}
        cfg_file = workspace_header.get("configFile")
        if cfg_file:
            try:
                import yaml
                parsed = yaml.safe_load(Path(cfg_file).read_text(encoding="utf-8")) or {}
                sql_cfg = parsed.get("sql") or {}
            except Exception as e:
                logger.debug("workspace.yaml sql read failed: %s", e)

        flyway_cfg = sql_cfg.get("flyway") or {}
        auto_detect = bool(flyway_cfg.get("autoDetect", True))
        extra_locations = flyway_cfg.get("extraLocations") or []
        query_globs = sql_cfg.get("queries") or []

        # --- Resolve Flyway migration directories ---
        locations: list[str] = []
        if auto_detect:
            locations.extend(flyway_detector.detect_flyway_locations(roots))
        locations.extend(extra_locations)
        # Dedup preserving order
        seen_loc: set[str] = set()
        locations = [l for l in locations if not (l in seen_loc or seen_loc.add(l))]

        migration_dirs = [d for _, d in flyway_detector.resolve_classpath_globs(locations, roots)]

        if not migration_dirs and not query_globs:
            return  # Nothing to do — no flyway detected, no custom queries configured

        logger.info(
            "SQL phase: %d migration dirs, %d query globs",
            len(migration_dirs), len(query_globs),
        )

        # --- Mine ---
        files = sql_miner.mine(
            roots=roots,
            migration_dirs=migration_dirs,
            query_globs=query_globs,
        )
        if not files:
            return

        # --- Emit nodes ---
        migration_files = [f for f in files if f.kind == "migration"]
        query_files = [f for f in files if f.kind == "query"]

        if migration_files:
            nodes = [
                {
                    "id": f"migration:{f.path}",
                    "filename": f.filename,
                    "filePath": f.path,
                    "body": f.body,
                    "version": f.version or "",
                    "description": f.description or "",
                    "dbKind": f.dbKind or "",
                    "statementCount": len(f.statements),
                    "wing": graph_wing,
                }
                for f in migration_files
            ]
            self._batch_nodes(
                progress, "SQL Migrations", nodes, "Migration", "id",
                ["filename", "filePath", "body", "version", "description",
                 "dbKind", "statementCount", "wing"],
            )

        if query_files:
            nodes = [
                {
                    "id": f"query:{f.path}",
                    "filename": f.filename,
                    "filePath": f.path,
                    "body": f.body,
                    "statementCount": len(f.statements),
                    "wing": graph_wing,
                }
                for f in query_files
            ]
            self._batch_nodes(
                progress, "SQL Queries", nodes, "SqlQuery", "id",
                ["filename", "filePath", "body", "statementCount", "wing"],
            )

        # --- Statement nodes + parent-to-statement edges + table edges ---
        statement_nodes = []
        parent_edges = []      # (fileId)-[:HAS_STATEMENT {index}]->(stmtId)
        queries_table = []     # (stmtId)-[:QUERIES_TABLE]->(JpaEntity fqn)
        ddl_edges = {          # per-op edges from stmt → JpaEntity
            "CREATES_TABLE": [],
            "ALTERS_TABLE": [],
            "DROPS_TABLE": [],
        }
        references_column = []  # (stmtId)-[:REFERENCES_COLUMN]->(JpaColumn fqn)

        # Build tableName → Entity fqn lookup + (table,column) → Column fqn lookup
        # from in-graph state. db.execute() returns None (writes); db.query()
        # returns list[dict].
        table_to_fqn: dict[str, str] = {}
        col_to_fqn: dict[tuple[str, str], str] = {}
        try:
            rows = self.db.query(
                "MATCH (e:JpaEntity) RETURN toLower(e.tableName) AS tn, e.fqn AS fqn"
            )
            for row in rows or []:
                tn = row.get("tn") if isinstance(row, dict) else None
                fqn = row.get("fqn") if isinstance(row, dict) else None
                if tn and fqn:
                    table_to_fqn[str(tn).lower()] = str(fqn)
        except Exception as e:
            logger.warning("JpaEntity lookup for SQL edges failed: %s", e)

        # Inheritance-aware column map: `Request` inherits `priorityId` from
        # TicketBase via `@Inheritance(SINGLE_TABLE)` or MappedSuperclass, so
        # SQL reads the flat row — we need the walk up the :Class EXTENDS chain.
        # Depth cap 6 covers all cases seen in practice (Request→TicketBase→MultiTenantOrder→
        # FlotoBase→FlotoSingleBase→FlotoEntity).
        try:
            rows = self.db.query(
                "MATCH (e:JpaEntity)-[:EXTENDS*0..6]->(p:Class)-[:HAS_COLUMN]->(c:JpaColumn) "
                "RETURN toLower(e.tableName) AS tn, toLower(c.columnName) AS cn, c.fqn AS fqn"
            )
            for row in rows or []:
                tn = row.get("tn") if isinstance(row, dict) else None
                cn = row.get("cn") if isinstance(row, dict) else None
                fqn = row.get("fqn") if isinstance(row, dict) else None
                if tn and cn and fqn:
                    col_to_fqn[(str(tn).lower(), str(cn).lower())] = str(fqn)
        except Exception as e:
            logger.warning("JpaColumn lookup for SQL edges failed: %s", e)

        logger.info(
            "SQL phase: %d tables, %d columns cached for edge matching",
            len(table_to_fqn), len(col_to_fqn),
        )

        def _file_id(f):
            return f"migration:{f.path}" if f.kind == "migration" else f"query:{f.path}"

        for f in files:
            fid = _file_id(f)
            for s in f.statements:
                sid = f"{fid}#{s.index}"
                statement_nodes.append({
                    "id": sid,
                    "sql": s.sql,
                    "opKind": s.opKind,
                    "statementIndex": s.index,
                    "wing": graph_wing,
                })
                parent_edges.append({"src": fid, "dst": sid, "index": s.index})

                # Route edges by opKind. SELECT/INSERT/UPDATE/DELETE → QUERIES_TABLE;
                # CREATE_TABLE / ALTER_TABLE / DROP_TABLE → specific DDL edge.
                for tbl in s.tableNames:
                    fqn = table_to_fqn.get(tbl)
                    if not fqn:
                        continue
                    edge = {"src": sid, "dst": fqn}
                    if s.opKind in ("CREATE_TABLE",):
                        ddl_edges["CREATES_TABLE"].append(edge)
                    elif s.opKind in ("ALTER_TABLE",):
                        ddl_edges["ALTERS_TABLE"].append(edge)
                    elif s.opKind in ("DROP_TABLE", "DROP"):
                        ddl_edges["DROPS_TABLE"].append(edge)
                    else:
                        queries_table.append(edge)

                # Column references — only meaningful for SELECT/UPDATE/DELETE/
                # INSERT. DDL (CREATE/ALTER) column tracking is a separate feature.
                if s.opKind in ("SELECT", "UPDATE", "INSERT", "DELETE") and getattr(s, "columnRefs", None):
                    seen_col: set[str] = set()
                    for (tbl, col) in s.columnRefs:
                        cfqn = col_to_fqn.get((tbl, col))
                        if not cfqn or cfqn in seen_col:
                            continue
                        seen_col.add(cfqn)
                        references_column.append({"src": sid, "dst": cfqn})

        if statement_nodes:
            self._batch_nodes(
                progress, "SQL Statements", statement_nodes,
                "SqlStatement", "id",
                ["sql", "opKind", "statementIndex", "wing"],
            )

        if parent_edges:
            # HAS_STATEMENT has two possible parent labels (Migration OR SqlQuery);
            # emit twice, once per label, and let the unmatched half drop silently.
            self._batch_edges_with_props(
                progress, "HAS_STATEMENT (Migration)", parent_edges,
                "Migration", "id", "SqlStatement", "id", ["index"],
                rel_type="HAS_STATEMENT",
            )
            self._batch_edges_with_props(
                progress, "HAS_STATEMENT (SqlQuery)", parent_edges,
                "SqlQuery", "id", "SqlStatement", "id", ["index"],
                rel_type="HAS_STATEMENT",
            )

        if queries_table:
            self._batch_edges(
                progress, "QUERIES_TABLE", queries_table,
                "SqlStatement", "id", "JpaEntity", "fqn",
            )
        for rel, edges in ddl_edges.items():
            if not edges:
                continue
            self._batch_edges(
                progress, rel, edges,
                "SqlStatement", "id", "JpaEntity", "fqn",
            )
        if references_column:
            self._batch_edges(
                progress, "REFERENCES_COLUMN", references_column,
                "SqlStatement", "id", "JpaColumn", "fqn",
            )

    def _batch_edges_simple(self, *a, **k):
        return self.writer.batch_edges_simple(*a, **k)

    def _batch_add_label(self, *a, **k):
        return self.writer.batch_add_label(*a, **k)

    def _batch_nodes(self, *a, **k):
        return self.writer.batch_nodes(*a, **k)

    def _batch_edges(self, *a, **k):
        return self.writer.batch_edges(*a, **k)

    def _batch_edges_with_props(self, *a, **k):
        return self.writer.batch_edges_with_props(*a, **k)

    def _batch_annotation_edges(self, *a, **k):
        return self.writer.batch_annotation_edges(*a, **k)
