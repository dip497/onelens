"""Full JSON import into any Cypher-compatible graph DB using batch UNWIND."""

import json
import logging
import time
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from onelens.graph.db import GraphDB
from onelens.importer.schema import NODE_SCHEMA

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
                endpoints = spring.get("endpoints", [])
                for ep in endpoints:
                    if "id" not in ep:
                        ep["id"] = f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"
                self._batch_nodes(progress, "Endpoints", endpoints, "Endpoint", "id", [
                    "path", "httpMethod", "controllerFqn", "handlerMethodFqn",
                ])

            # --- EDGES ---

            # HAS_METHOD (Class → Method)
            has_method = [{"src": m["classFqn"], "dst": m["fqn"]} for m in methods]
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

            # ANNOTATED_WITH
            ann_edges = []
            for a in data.get("annotations", []):
                kind = a.get("targetKind", "CLASS")
                label = "Class" if kind == "CLASS" else "Method" if kind == "METHOD" else "Field"
                ann_edges.append({"src": a["targetFqn"], "dst": a["annotationFqn"], "label": label})
            # Group by source label for correct MATCH
            for label in ["Class", "Method", "Field"]:
                group = [e for e in ann_edges if e["label"] == label]
                if group:
                    edges = [{"src": e["src"], "dst": e["dst"]} for e in group]
                    self._batch_edges(progress, f"ANNOTATED_WITH ({label})", edges, label, "fqn", "Annotation", "fqn",
                                      rel_type="ANNOTATED_WITH")

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

        elapsed = time.time() - start
        stats = data.get("stats", {})
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

        task = progress.add_task(f"{desc}...", total=len(edges))
        for i in range(0, len(edges), EDGE_BATCH):
            batch = edges[i:i + EDGE_BATCH]
            try:
                self.db.execute(query, {"batch": batch})
            except Exception as e:
                logger.warning(f"Batch {desc} failed: {e}")
            progress.update(task, advance=len(batch))

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

        task = progress.add_task(f"{desc}...", total=len(edges))
        for i in range(0, len(edges), EDGE_BATCH):
            batch = edges[i:i + EDGE_BATCH]
            try:
                self.db.execute(query, {"batch": batch})
            except Exception as e:
                logger.warning(f"Batch {desc} failed: {e}")
            progress.update(task, advance=len(batch))
