"""Shared graph-write primitives extracted from loader.py (E5 Stage 1).

Contains module-level constants / helpers and the GraphWriter class that
encapsulates the six UNWIND-based batch helper methods previously living
on GraphLoader. loader.py re-exports everything so existing call sites are
unchanged.
"""

import logging

logger = logging.getLogger(__name__)

NODE_BATCH = 1000
EDGE_BATCH = 500

# Java primitives + void — never get a Class node (no FQN, not a reference type).
_PRIMITIVES = frozenset({
    "void", "boolean", "byte", "char", "short", "int", "long", "float", "double",
})

# Annotation simple-names that flip a Method boolean prop. Matched on the
# trailing segment so `org.springframework.transaction.annotation.Transactional`
# and a re-exported `Transactional` both hit.
_TXN_ANNOS = frozenset({"Transactional"})
_ASYNC_ANNOS = frozenset({"Async"})
_DEPRECATED_ANNOS = frozenset({"Deprecated"})


def _normalize_type(t: str) -> str:
    """Reduce a Java type string to a Class FQN, or '' if it isn't one.

    Strips generics (`List<Foo>` → `List`), array suffixes (`Foo[]` → `Foo`),
    varargs (`Foo...` → `Foo`), and rejects primitives/void. Used to turn
    declared return / param / throws types into edges to Class nodes.
    """
    if not t:
        return ""
    t = t.strip()
    # Strip generic args first — the outermost <...> and everything after.
    lt = t.find("<")
    if lt != -1:
        t = t[:lt]
    t = t.replace("[]", "").replace("...", "").strip()
    if not t or t in _PRIMITIVES:
        return ""
    # Bare type var (e.g. `T`, `E`) or unqualified name with no package — keep
    # only fully-qualified reference types so edges resolve against real nodes.
    if "." not in t:
        return ""
    return t


def _anno_simple_names(method: dict) -> set[str]:
    """Trailing-segment names of every annotation on a method dict."""
    out: set[str] = set()
    for a in method.get("annotations", []) or []:
        fqn = a.get("fqn") or a.get("annotationFqn") or ""
        if fqn:
            out.add(fqn.rsplit(".", 1)[-1])
    return out


def _enrich_method(m: dict) -> None:
    """Add derived structural props to a method dict in place (Tier-0 enrich).

    All inputs already ship in the export (modifiers / parameters /
    annotations) — the full loader previously dropped them. 100% PSI-accurate,
    so these power exact queries: public dead code, deprecated-still-called,
    non-transactional write paths, async boundaries.
    """
    mods = m.get("modifiers", []) or []
    mods_set = set(mods)
    if "public" in mods_set:
        vis = "public"
    elif "private" in mods_set:
        vis = "private"
    elif "protected" in mods_set:
        vis = "protected"
    else:
        vis = "package"
    m["visibility"] = vis
    m["isStatic"] = "static" in mods_set
    m["isAbstract"] = "abstract" in mods_set
    m["paramCount"] = len(m.get("parameters", []) or [])
    annos = _anno_simple_names(m)
    m["isDeprecated"] = bool(annos & _DEPRECATED_ANNOS)
    m["isTransactional"] = bool(annos & _TXN_ANNOS)
    m["isAsync"] = bool(annos & _ASYNC_ANNOS)


class GraphWriter:
    def __init__(self, db, node_batch=NODE_BATCH, edge_batch=EDGE_BATCH):
        self.db = db
        self.node_batch = node_batch
        self.edge_batch = edge_batch

    def batch_edges_simple(self, progress, desc: str, edges: list,
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
        task = progress.add_task(f"{desc}...", total=len(edges)) if progress is not None else None
        for i in range(0, len(edges), self.edge_batch):
            batch = edges[i:i + self.edge_batch]
            try:
                self.db.execute(query, {"batch": batch, "wing": wing})
            except Exception as e:
                logger.warning("Edge batch %s failed: %s", desc, e)
            if progress is not None:
                progress.update(task, advance=len(batch))

    def batch_add_label(self, progress, desc: str, items: list,
                        base_label: str, base_pk: str, pk_field: str,
                        add_label: str, props: list[str]):
        """
        Dual-label upsert. Collapses "JpaColumn IS a Field", "JpaEntity IS a
        Class", "EnumConstant IS a Field", etc. into one node per underlying
        concept.

        Resolves the node by `(:base_label {base_pk: item.pk_field})` (MERGE —
        creates if absent so the loader is order-independent), then `SET` tags
        the extra label and writes the label-specific props. Existing
        `:base_label` props (name, type, modifiers, ...) are preserved.

        Existing edges that matched on the add_label + pk_field keep working
        because FalkorDB's label matching is "has any of these labels" — the
        node still carries the extra label we just SET. Edges that matched on
        a property name the add_label layer owned (e.g. `fieldFqn` on
        JpaColumn) should move to the base_label's primary key (`fqn` on
        Field); rewire the edge batch separately.
        """
        if not items:
            return
        set_clause = ", ".join(f"n.{p} = item.{p}" for p in props)
        query = (
            f"UNWIND $batch AS item "
            f"MERGE (n:{base_label} {{{base_pk}: item.{pk_field}}}) "
            f"SET n:{add_label}"
        )
        if set_clause:
            query += f", {set_clause}"

        task = progress.add_task(f"{desc}...", total=len(items)) if progress is not None else None
        for i in range(0, len(items), self.node_batch):
            batch = items[i:i + self.node_batch]
            clean = []
            for item in batch:
                row = {pk_field: item.get(pk_field, "")}
                for p in props:
                    v = item.get(p)
                    if v is None:
                        row[p] = "" if isinstance(item.get(p, ""), str) else 0
                    else:
                        row[p] = v
                clean.append(row)
            try:
                self.db.execute(query, {"batch": clean})
            except Exception as e:
                logger.warning(f"Dual-label {add_label} batch failed: {e}")
            if progress is not None:
                progress.update(task, advance=len(batch))

    def batch_nodes(self, progress, desc: str, items: list, label: str, pk: str, props: list[str]):
        """Create nodes using UNWIND in batches."""
        if not items:
            return

        all_props = [pk] + props
        set_clause = ", ".join(f"n.{p} = item.{p}" for p in props)
        # MERGE (not CREATE) so duplicate primary keys within a single export
        # or across re-imports upsert instead of failing the whole batch.
        # Duplicates surface legitimately in multi-module / multi-repo workspaces
        # (plugin-style forks of `Constants`, shared common classes, etc.).
        query = f"UNWIND $batch AS item MERGE (n:{label} {{{pk}: item.{pk}}}) SET {set_clause}"

        task = progress.add_task(f"{desc}...", total=len(items)) if progress is not None else None
        for i in range(0, len(items), self.node_batch):
            batch = items[i:i + self.node_batch]
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
                            f"MERGE (n:{label} {{{pk}: $pk_val}}) SET " +
                            ", ".join(f"n.{p} = ${p}" for p in props),
                            {"pk_val": item[pk], **{p: item[p] for p in props}}
                        )
                    except Exception:
                        pass

            if progress is not None:
                progress.update(task, advance=len(batch))

    def batch_edges(self, progress, desc: str, edges: list,
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
        task = progress.add_task(f"{desc}...", total=len(edges)) if progress is not None else None
        for i in range(0, len(edges), self.edge_batch):
            batch = edges[i:i + self.edge_batch]
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
            if progress is not None:
                progress.update(task, advance=len(batch))
        if failed_count > 0:
            logger.warning(f"{desc}: {failed_count} edges failed (missing nodes)")

    def batch_edges_with_props(self, progress, desc: str, edges: list,
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
        task = progress.add_task(f"{desc}...", total=len(edges)) if progress is not None else None
        for i in range(0, len(edges), self.edge_batch):
            batch = edges[i:i + self.edge_batch]
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
            if progress is not None:
                progress.update(task, advance=len(batch))
        if failed_count > 0:
            logger.warning(f"{desc}: {failed_count} edges failed (missing nodes)")

    def batch_annotation_edges(self, progress, label: str, edges: list):
        """Specialized batcher for ANNOTATED_WITH edges with dynamic
        `attr_<key>` properties on top of the `attributes` JSON blob.

        `_batch_edges_with_props` requires fixed prop names declared up
        front; annotations have per-row variable keys (`@RequestMapping`
        carries `attr_value` + `attr_method`, `@Qualifier` carries only
        `attr_value`, etc.) so we use Cypher `SET r += $map` to write
        the per-row map onto the relationship in the same UNWIND pass.

        FalkorDB supports `SET r += map` per openCypher; behaviour:
        existing keys overwritten, new keys added, missing keys left
        alone. Empty `attr_props` is a no-op.
        """
        if not edges:
            return

        query = f"""
            UNWIND $batch AS edge
            MATCH (a:{label} {{fqn: edge.src}})
            MATCH (b:Annotation {{fqn: edge.dst}})
            CREATE (a)-[r:ANNOTATED_WITH {{attributes: edge.attributes}}]->(b)
            SET r += edge.attr_props
        """

        failed_count = 0
        desc = f"ANNOTATED_WITH ({label})"
        task = progress.add_task(f"{desc}...", total=len(edges)) if progress is not None else None
        for i in range(0, len(edges), self.edge_batch):
            batch = edges[i:i + self.edge_batch]
            try:
                self.db.execute(query, {"batch": batch})
            except Exception as e:
                logger.warning(f"Batch {desc} failed, retrying individually: {e}")
                for edge in batch:
                    try:
                        single_q = f"""
                            MATCH (a:{label} {{fqn: $src}})
                            MATCH (b:Annotation {{fqn: $dst}})
                            CREATE (a)-[r:ANNOTATED_WITH {{attributes: $attributes}}]->(b)
                            SET r += $attr_props
                        """
                        self.db.execute(single_q, {
                            "src": edge["src"], "dst": edge["dst"],
                            "attributes": edge.get("attributes", "{}"),
                            "attr_props": edge.get("attr_props", {}),
                        })
                    except Exception:
                        failed_count += 1
            if progress is not None:
                progress.update(task, advance=len(batch))
        if failed_count > 0:
            logger.warning(f"{desc}: {failed_count} edges failed (missing nodes)")
