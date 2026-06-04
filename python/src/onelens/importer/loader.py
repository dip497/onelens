"""Full JSON import into any Cypher-compatible graph DB using batch UNWIND."""

import json
import logging
import time
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from onelens.graph.db import GraphDB
from onelens.importer.schema import NODE_SCHEMA, FULLTEXT_SCHEMA
from onelens.lang import identity

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
                "packageName", "enclosingClass", "superClass", "lang",
            ])

            methods = data.get("methods", [])
            self._batch_nodes(progress, "Methods", methods, "Method", "fqn", [
                "name", "classFqn", "returnType", "isConstructor",
                "filePath", "lineStart", "lineEnd",
                "body", "javadoc", "lang",
            ])

            fields = data.get("fields", [])
            self._batch_nodes(progress, "Fields", fields, "Field", "fqn", [
                "name", "classFqn", "type", "filePath", "lineStart",
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

            # Spring nodes
            spring = data.get("spring")
            if spring:
                beans = spring.get("beans", [])
                self._batch_nodes(progress, "Spring Beans", beans, "SpringBean", "name", [
                    "classFqn", "scope", "profile", "type",
                ])

            # Endpoints — language-neutral. Spring emits them under `spring.endpoints`;
            # other backends (Go/Python/.NET/Ktor extractors) emit a top-level
            # `endpoints` list of the same shape. Both feed the same Endpoint nodes
            # so cross-stack linking works regardless of backend framework.
            endpoints = list((spring or {}).get("endpoints", [])) + list(data.get("endpoints", []))
            if endpoints:
                for ep in endpoints:
                    if "id" not in ep:
                        ep["id"] = f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"
                self._batch_nodes(progress, "Endpoints", endpoints, "Endpoint", "id", [
                    "path", "httpMethod", "controllerFqn", "handlerMethodFqn",
                ])

            # --- EXTERNAL STUB NODES ---
            # Create stub nodes for external (library) classes/methods referenced in edges.
            # The plugin already resolves calls to library methods — we just need nodes for them.
            project_class_fqns = {c["fqn"] for c in classes}
            project_method_fqns = {m["fqn"] for m in methods}

            ext_class_fqns = set()
            ext_method_fqns = set()

            # From call graph: callee methods not in project. The owning
            # container comes from identity (Java: text before '#'), so the
            # parsing rule is language-driven, not hardcoded here.
            for c in data.get("callGraph", []):
                callee = c.get("calleeFqn", "")
                if callee and callee not in project_method_fqns:
                    ext_method_fqns.add(callee)
                    cont = identity.container_fqn(callee)
                    if cont and cont != callee:
                        ext_class_fqns.add(cont)

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
                    cont = identity.container_fqn(parent)
                    if cont and cont != parent:
                        ext_class_fqns.add(cont)

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
                cont = identity.container_fqn(fqn)
                has_container = bool(cont) and cont != fqn
                class_fqn = cont if has_container else ""
                name = identity.simple_name(fqn) if has_container else fqn
                # Constructor detection (incl. Java inner-class `Outer$Inner`) is
                # centralized in identity and driven by the language profile.
                is_constructor = identity.is_constructor(fqn) if class_fqn else False
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

            # ANNOTATED_WITH — group by source label in single pass
            ann_groups = {"Class": [], "Method": [], "Field": []}
            for a in data.get("annotations", []):
                kind = a.get("targetKind", "CLASS")
                label = "Class" if kind == "CLASS" else "Method" if kind == "METHOD" else "Field"
                ann_groups[label].append({"src": a["targetFqn"], "dst": a["annotationFqn"]})
            for label, edges in ann_groups.items():
                if edges:
                    self._batch_edges(progress, f"ANNOTATED_WITH ({label})", edges, label, "fqn", "Annotation", "fqn",
                                      rel_type="ANNOTATED_WITH")

            # HANDLES (Method → Endpoint) — language-neutral, from every endpoint
            # that names a handler method (Spring or any other backend extractor).
            handles = [{"src": ep["handlerMethodFqn"],
                        "dst": ep.get("id") or f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"}
                       for ep in endpoints if ep.get("handlerMethodFqn")]
            self._batch_edges(progress, "HANDLES", handles, "Method", "fqn", "Endpoint", "id")

            # Spring-only edges
            if spring:
                injects = [{"src": inj["targetClassFqn"], "dst": inj["injectedClassFqn"],
                            "field": inj.get("targetFieldOrParam", ""), "type": inj.get("injectionType", "")}
                           for inj in spring.get("injections", [])]
                self._batch_edges_with_props(progress, "INJECTS", injects,
                                             "SpringBean", "classFqn", "SpringBean", "classFqn",
                                             ["field", "type"])

            # --- CROSS-STACK (frontend) NODES + EDGES ---
            # Vue/TS extractors contribute Component + HttpCall nodes. These can
            # arrive in the same import (full multi-stack export) or be merged in
            # from a separate frontend extractor run sharing the graph name.
            components = data.get("components", [])
            self._batch_nodes(progress, "Components", components, "Component", "fqn", [
                "name", "filePath", "lineStart", "lineEnd", "lang",
            ])

            http_calls = data.get("httpCalls", [])
            self._batch_nodes(progress, "HTTP Calls", http_calls, "HttpCall", "id", [
                "componentFqn", "httpMethod", "path", "filePath", "lineStart", "lang",
            ])

            # MAKES_CALL (Component → HttpCall) — derived from each call's owner.
            makes_call = [{"src": h["componentFqn"], "dst": h["id"]}
                          for h in http_calls if h.get("componentFqn")]
            self._batch_edges(progress, "MAKES_CALL", makes_call,
                              "Component", "fqn", "HttpCall", "id", rel_type="MAKES_CALL")

            # USES_COMPONENT (Component → Component)
            uses = data.get("componentEdges", [])
            self._batch_edges(progress, "USES_COMPONENT", uses,
                              "Component", "fqn", "Component", "fqn", rel_type="USES_COMPONENT")

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

        # Cross-stack phase: link frontend HttpCall sites to backend Endpoints
        # via CALLS_ENDPOINT. No-op (cheap) when the graph has no HttpCall nodes.
        try:
            from onelens.importer import cross_stack as _cs

            cs_stats = _cs.apply_cross_stack_links(self.db)
            stats.update(cs_stats)
            cs = cs_stats.get("cross_stack")
            if isinstance(cs, dict) and cs.get("linked"):
                print(
                    f"Cross-stack: {cs['linked']} frontend→endpoint links "
                    f"({cs['exact']} exact, {cs['fuzzy']} fuzzy, {cs['unmatched']} unmatched)"
                )
        except Exception as e:
            logger.warning("Cross-stack linking failed: %s", e)
            stats["cross_stack"] = {"error": str(e)}

        elapsed = time.time() - start
        stats["importDurationSec"] = round(elapsed, 1)
        print(f"\nImport complete in {elapsed:.1f}s")
        return stats

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
