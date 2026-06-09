"""JpaLoader — owns both the full and delta JPA import paths.

Extracted from loader.py (inline jpa: node block ~221-280 + edge block ~522-580)
and delta_loader.py (_replace_jpa) so the two paths cannot drift (the
:JpaEntity label-demotion bug that prompted this extraction).
"""

import logging

from onelens.importer.loaders.base import SubdocLoader

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class JpaLoader(SubdocLoader):
    json_key = "jpa"

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """Phase JPA — dual-label :JpaEntity/:JpaColumn/:JpaRepository nodes
        followed immediately by HAS_COLUMN/RELATES_TO/REPOSITORY_FOR/QUERIES edges.

        Both blocks are combined into one method so nodes exist before edges are
        wired. Call site is at the NODE-block location (~221) — after
        Class/Method/Field nodes, before _load_sql (which reads :JpaEntity).
        """
        jpa = data.get("jpa")
        if not jpa:
            return

        entities = [dict(e, wing=wing) for e in jpa.get("entities", [])]
        if entities:
            # Dual-label: a JpaEntity IS a Class. Tag the existing Class
            # node with :JpaEntity + the JPA-specific props. Avoids a
            # duplicate node per @Entity class (was 748 extra nodes on
            # myapp) and lets queries use either label.
            writer.batch_add_label(
                progress, "JPA Entities", entities,
                base_label="Class", base_pk="fqn",
                pk_field="classFqn",
                add_label="JpaEntity",
                props=["tableName", "schema", "wing"],
            )
            # Flatten columns into their own nodes so Cypher can query by
            # column name / nullability / relation. ID format:
            #   column:<entity-fqn>#<field-name>
            # Dedupe on fieldFqn in case the collector ever re-emits a
            # parent's column via inheritance (belt-and-suspenders — the
            # JpaCollector now uses `psiClass.fields` not `allFields`).
            columns = []
            seen_cols = set()
            for e in entities:
                for col in e.get("columns", []):
                    key = col.get("fieldFqn", "")
                    if not key or key in seen_cols:
                        continue
                    seen_cols.add(key)
                    columns.append({
                        "fieldFqn": col["fieldFqn"],
                        "columnName": col.get("columnName", ""),
                        "nullable": bool(col.get("nullable", True)),
                        "unique": bool(col.get("unique", False)),
                        "relation": col.get("relation") or "",
                        "targetEntityFqn": col.get("targetEntityFqn") or "",
                        "wing": wing,
                    })
            if columns:
                # Dual-label: a JpaColumn IS a Field. MemberCollector
                # already emits the Field node with the same fqn.
                writer.batch_add_label(
                    progress, "JPA Columns", columns,
                    base_label="Field", base_pk="fqn",
                    pk_field="fieldFqn",
                    add_label="JpaColumn",
                    props=["columnName", "nullable", "unique",
                           "relation", "targetEntityFqn", "wing"],
                )

        repos = [dict(r, wing=wing) for r in jpa.get("repositories", [])]
        if repos:
            # Dual-label: a JpaRepository IS a Class (interface).
            writer.batch_add_label(
                progress, "JPA Repositories", repos,
                base_label="Class", base_pk="fqn",
                pk_field="classFqn",
                add_label="JpaRepository",
                props=["entityFqn", "wing"],
            )

        # --- EDGES ---

        # HAS_COLUMN: JpaEntity → JpaColumn. Edge source = entity classFqn,
        # target = column fieldFqn (already unique by entity + field).
        has_column = []
        seen_hc = set()
        for e in jpa.get("entities", []):
            for col in e.get("columns", []):
                key = (e["classFqn"], col.get("fieldFqn", ""))
                if not key[1] or key in seen_hc:
                    continue
                seen_hc.add(key)
                has_column.append({"src": e["classFqn"], "dst": col["fieldFqn"]})
        if has_column:
            # After dual-labeling, JpaEntity nodes are Class nodes keyed by
            # `fqn` and JpaColumn nodes are Field nodes keyed by `fqn`.
            writer.batch_edges(
                progress, "HAS_COLUMN", has_column,
                "JpaEntity", "fqn", "JpaColumn", "fqn",
            )

        # RELATES_TO: JpaEntity → JpaEntity with relation type on the edge.
        relates = []
        for e in jpa.get("entities", []):
            for col in e.get("columns", []):
                target = col.get("targetEntityFqn")
                rel = col.get("relation")
                if target and rel:
                    relates.append({
                        "src": e["classFqn"], "dst": target,
                        "relation": rel,
                        "field": col["fieldFqn"].split("#", 1)[-1] if "#" in col["fieldFqn"] else "",
                    })
        if relates:
            writer.batch_edges_with_props(
                progress, "RELATES_TO", relates,
                "JpaEntity", "fqn",
                "JpaEntity", "fqn",
                ["relation", "field"],
            )

        # REPOSITORY_FOR: JpaRepository → JpaEntity
        repo_for = [{"src": r["classFqn"], "dst": r["entityFqn"]}
                    for r in jpa.get("repositories", [])
                    if r.get("entityFqn")]
        if repo_for:
            writer.batch_edges(
                progress, "REPOSITORY_FOR", repo_for,
                "JpaRepository", "fqn",
                "JpaEntity", "fqn",
            )

        # QUERIES: JpaRepository → Method (derived-query methods). The Method
        # node already exists from MemberCollector — we just wire the edge.
        queries = []
        for r in jpa.get("repositories", []):
            for q in r.get("derivedQueries", []):
                queries.append({
                    "src": r["classFqn"], "dst": q["methodFqn"],
                    "methodName": q.get("methodName", ""),
                    "kind": q.get("kind", "derived"),
                })
        if queries:
            writer.batch_edges_with_props(
                progress, "QUERIES", queries,
                "JpaRepository", "fqn",
                "Method", "fqn",
                ["methodName", "kind"],
            )

    def apply_delta(self, writer, data: dict, wing: str) -> None:
        """Strip + re-apply JPA dual-labels and edges (parity with loader.py).

        A modified @Entity is DETACH-deleted then re-MERGEd as a plain :Class,
        losing its :JpaEntity label + tableName/schema. The whole JPA layer is
        cross-class (RELATES_TO between entities, REPOSITORY_FOR), so we strip
        every JPA label + edge globally and re-derive from the full re-scan —
        cheap (JPA layer is small) and guarantees parity.
        """
        jpa = data.get("jpa")
        if not jpa:
            return

        # 1. Strip labels + JPA edges. REMOVE keeps the underlying Class/Field
        # node (and its structural edges); only the JPA overlay is rebuilt.
        writer.db.execute("MATCH (n:JpaEntity) REMOVE n:JpaEntity")
        writer.db.execute("MATCH (n:JpaColumn) REMOVE n:JpaColumn")
        writer.db.execute("MATCH (n:JpaRepository) REMOVE n:JpaRepository")
        writer.db.execute("MATCH ()-[r:HAS_COLUMN|RELATES_TO|REPOSITORY_FOR|QUERIES]->() DELETE r")

        entities = jpa.get("entities", []) or []
        # JpaEntity dual-label on the existing Class node.
        ent_items = [{
            "fqn": e["classFqn"], "tableName": e.get("tableName", ""),
            "schema": e.get("schema", ""), "wing": wing,
        } for e in entities if e.get("classFqn")]
        for batch in _chunks(ent_items, _CHUNK_SIZE):
            writer.db.execute("""
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
        for batch in _chunks(col_items, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS item
                MATCH (f:Field {fqn: item.fqn})
                SET f:JpaColumn, f.columnName = item.columnName,
                    f.nullable = item.nullable, f.unique = item.unique,
                    f.relation = item.relation,
                    f.targetEntityFqn = item.targetEntityFqn, f.wing = item.wing
            """, {"batch": batch})
        for batch in _chunks(has_col, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:JpaEntity {fqn: edge.src}), (f:JpaColumn {fqn: edge.dst})
                MERGE (c)-[:HAS_COLUMN]->(f)
            """, {"batch": batch})
        for batch in _chunks(relates, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:JpaEntity {fqn: edge.src}), (b:JpaEntity {fqn: edge.dst})
                MERGE (a)-[:RELATES_TO {relation: edge.relation, field: edge.field}]->(b)
            """, {"batch": batch})

        # JpaRepository dual-label + REPOSITORY_FOR + QUERIES.
        repos = jpa.get("repositories", []) or []
        repo_items = [{"fqn": r["classFqn"], "entityFqn": r.get("entityFqn", ""), "wing": wing}
                      for r in repos if r.get("classFqn")]
        for batch in _chunks(repo_items, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS item
                MATCH (c:Class {fqn: item.fqn})
                SET c:JpaRepository, c.entityFqn = item.entityFqn, c.wing = item.wing
            """, {"batch": batch})
        repo_for = [{"src": r["classFqn"], "dst": r["entityFqn"]}
                    for r in repos if r.get("entityFqn") and r.get("classFqn")]
        for batch in _chunks(repo_for, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (r:JpaRepository {fqn: edge.src}), (e:JpaEntity {fqn: edge.dst})
                MERGE (r)-[:REPOSITORY_FOR]->(e)
            """, {"batch": batch})
        queries = []
        for r in repos:
            for q in r.get("derivedQueries", []):
                queries.append({"src": r["classFqn"], "dst": q.get("methodFqn", ""),
                                "methodName": q.get("methodName", ""), "kind": q.get("kind", "derived")})
        for batch in _chunks([q for q in queries if q["dst"]], _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (r:JpaRepository {fqn: edge.src}), (m:Method {fqn: edge.dst})
                MERGE (r)-[:QUERIES {methodName: edge.methodName, kind: edge.kind}]->(m)
            """, {"batch": batch})
        logger.info("JPA replaced: %d entities, %d repos (wing=%s)",
                    len(ent_items), len(repo_items), wing)
