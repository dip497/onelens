"""Temporal KG over FalkorDB — Entity + ASSERTS subgraph in graph 'onelens_palace_kg'.

Divergence from MemPalace (which uses SQLite): co-locating with FalkorDB lets
kg_query cross-reference code Class/Method nodes by shared `fqn` via structural
projection. See docs/DECISIONS.md ADR-P1.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from . import store, wal

_SCHEMA_READY = False

_STRUCTURAL_EDGE_MAP = {
    "CALLS": "calls",
    "EXTENDS": "extends",
    "IMPLEMENTS": "implements",
    "HAS_METHOD": "has_method",
    "HAS_FIELD": "has_field",
    "OVERRIDES": "overrides",
    "ANNOTATED_WITH": "annotated_with",
    "HANDLES": "handles",
    "INJECTS": "injects",
    "HAS_ENUM_CONSTANT": "has_enum_constant",
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _triple_id(s: str, p: str, o: str, vf: str) -> str:
    h = hashlib.sha1(f"{s}|{p}|{o}|{vf}".encode()).hexdigest()[:16]
    return f"triple:{h}"


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    db = store.get_kg_db()
    for ddl in (
        "CREATE INDEX FOR (e:Entity) ON (e.name)",
        "CREATE INDEX FOR ()-[a:ASSERTS]-() ON (a.predicate)",
        "CREATE INDEX FOR ()-[a:ASSERTS]-() ON (a.validFrom)",
    ):
        try:
            db.execute(ddl)
        except Exception:
            pass  # idempotent
    _SCHEMA_READY = True


def _infer_object_kind(value: str) -> str:
    if value.startswith('"') or value.isdigit() or value.lower() in ("true", "false"):
        return "literal"
    return "entity"


def add(
    subject: str,
    predicate: str,
    object: str,
    valid_from: str | None = None,
    confidence: float = 1.0,
    source_closet: str | None = None,
    *,
    ended: str | None = None,
    wing: str = "global",
) -> dict:
    _ensure_schema()
    db = store.get_kg_db()
    now = _utc_iso()
    vf = valid_from or now
    tid = _triple_id(subject, predicate, object, vf)
    okind = _infer_object_kind(object)

    # INSERT OR IGNORE semantics: abort if tripleId already exists.
    existing = db.query(
        "MATCH ()-[a:ASSERTS {tripleId:$tid}]->() RETURN a.tripleId AS id LIMIT 1",
        {"tid": tid},
    )
    if existing:
        result = {
            "triple_id": tid,
            "created": False,
            "valid_from": vf,
            "valid_to": ended,
        }
        wal.log("palace_kg_add", {"subject": subject, "predicate": predicate, "object": object}, result)
        return result

    db.execute(
        """
        MERGE (s:Entity {name:$s}) ON CREATE SET s.firstSeen=$now, s.kind='entity'
        MERGE (o:Entity {name:$o}) ON CREATE SET o.firstSeen=$now, o.kind=$okind
        WITH s,o
        CREATE (s)-[a:ASSERTS {
          predicate:$p, validFrom:$vf, validTo:$vt,
          confidence:$c, sourceCloset:$src, wing:$wing, tripleId:$tid
        }]->(o)
        """,
        {
            "s": subject, "o": object, "p": predicate,
            "vf": vf, "vt": ended,
            "c": float(confidence),
            "src": source_closet, "wing": wing,
            "now": now, "okind": okind, "tid": tid,
        },
    )
    result = {"triple_id": tid, "created": True, "valid_from": vf, "valid_to": ended}
    wal.log("palace_kg_add", {"subject": subject, "predicate": predicate, "object": object, "wing": wing}, result)
    return result


def query(
    entity: str,
    as_of: str | None = None,
    direction: str = "both",
    *,
    predicate: str | None = None,
    include_structural: bool = True,
    depth: int = 1,  # noqa: ARG001 — depth>1 requires Python-side hop unroll, v1 ignores.
) -> list[dict]:
    _ensure_schema()
    db = store.get_kg_db()
    results: list[dict] = []

    clauses: list[str] = []
    params: dict = {"entity": entity, "asOf": as_of, "predicate": predicate}
    if as_of:
        clauses.append(
            "(a.validFrom IS NULL OR a.validFrom <= $asOf) AND "
            "(a.validTo IS NULL OR a.validTo >= $asOf)"
        )
    if predicate:
        clauses.append("a.predicate = $predicate")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    if direction in ("both", "out"):
        rows = db.query(
            f"MATCH (s:Entity {{name:$entity}})-[a:ASSERTS]->(o:Entity){where} "
            "RETURN s.name AS s, a.predicate AS p, o.name AS o, "
            "a.validFrom AS vf, a.validTo AS vt, a.confidence AS c, a.wing AS w",
            params,
        )
        for r in rows or []:
            results.append({
                "subject": r["s"], "predicate": r["p"], "object": r["o"],
                "valid_from": r["vf"], "valid_to": r["vt"],
                "confidence": r["c"] or 1.0,
                "source": "sidecar", "wing": r.get("w"),
            })

    if direction in ("both", "in"):
        rows = db.query(
            f"MATCH (s:Entity)-[a:ASSERTS]->(o:Entity {{name:$entity}}){where} "
            "RETURN s.name AS s, a.predicate AS p, o.name AS o, "
            "a.validFrom AS vf, a.validTo AS vt, a.confidence AS c, a.wing AS w",
            params,
        )
        for r in rows or []:
            results.append({
                "subject": r["s"], "predicate": r["p"], "object": r["o"],
                "valid_from": r["vf"], "valid_to": r["vt"],
                "confidence": r["c"] or 1.0,
                "source": "sidecar", "wing": r.get("w"),
            })

    if include_structural:
        results.extend(_project_structural(entity, direction))

    return results


def _project_structural(entity: str, direction: str) -> list[dict]:
    """Union structural edges from every code wing where a node matches `entity` by fqn."""
    hits: list[dict] = []
    for wing in store.all_wings():
        try:
            db = store.get_graph_db(wing)
        except Exception:
            continue
        pairs = []
        if direction in ("both", "out"):
            pairs.append(("(n)-[r]->(m)", "out"))
        if direction in ("both", "in"):
            pairs.append(("(m)-[r]->(n)", "in"))
        for pattern, dir_tag in pairs:
            try:
                rows = db.query(
                    f"MATCH (n) WHERE n.fqn=$fqn MATCH {pattern} "
                    "RETURN n.fqn AS nf, type(r) AS t, coalesce(m.fqn, m.name) AS mf",
                    {"fqn": entity},
                )
            except Exception:
                continue
            for row in rows or []:
                t = row["t"]
                pred = _STRUCTURAL_EDGE_MAP.get(t, t.lower())
                if dir_tag == "out":
                    s, o = row["nf"], row["mf"]
                else:
                    s, o = row["mf"], row["nf"]
                hits.append(
                    {
                        "subject": s, "predicate": pred, "object": o,
                        "valid_from": None, "valid_to": None, "confidence": 1.0,
                        "source": "structural", "wing": wing,
                    }
                )
    return hits


def invalidate(subject: str, predicate: str, object: str, ended: str | None = None) -> dict:
    _ensure_schema()
    db = store.get_kg_db()
    ts = ended or _utc_iso()
    rows = db.query(
        """
        MATCH (s:Entity {name:$s})-[a:ASSERTS {predicate:$p}]->(o:Entity {name:$o})
        WHERE a.validTo IS NULL
        SET a.validTo = $ts
        RETURN count(a) AS n
        """,
        {"s": subject, "p": predicate, "o": object, "ts": ts},
    )
    n = rows[0]["n"] if rows else 0
    result = {"invalidated": int(n), "ended": ts}
    wal.log("palace_kg_invalidate", {"subject": subject, "predicate": predicate, "object": object}, result)
    return result


def timeline(
    entity: str | None = None,
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> list[dict]:
    _ensure_schema()
    db = store.get_kg_db()
    where: list[str] = []
    params: dict = {"entity": entity, "since": since, "until": until}
    if entity:
        where.append("(s.name = $entity OR o.name = $entity)")
    if since:
        where.append("(a.validFrom IS NULL OR a.validFrom >= $since)")
    if until:
        where.append("(a.validFrom IS NULL OR a.validFrom <= $until)")
    where_clause = (" WHERE " + " AND ".join(where)) if where else ""

    rows = db.query(
        f"MATCH (s:Entity)-[a:ASSERTS]->(o:Entity){where_clause} "
        "RETURN s.name AS s, a.predicate AS p, o.name AS o, "
        "a.validFrom AS vf, a.validTo AS vt, a.wing AS w "
        "ORDER BY a.validFrom ASC",
        params,
    ) or []

    events: list[dict] = []
    for r in rows:
        if r["vf"]:
            events.append({
                "ts": r["vf"], "event": "asserted",
                "subject": r["s"], "predicate": r["p"], "object": r["o"],
                "wing": r.get("w"), "source": "kg",
            })
        if r["vt"]:
            events.append({
                "ts": r["vt"], "event": "ended",
                "subject": r["s"], "predicate": r["p"], "object": r["o"],
                "wing": r.get("w"), "source": "kg",
            })
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def stats() -> dict:
    _ensure_schema()
    db = store.get_kg_db()
    try:
        ent = db.query("MATCH (e:Entity) RETURN count(e) AS n")
        triples = db.query("MATCH ()-[a:ASSERTS]->() RETURN count(a) AS n")
        open_ = db.query("MATCH ()-[a:ASSERTS]->() WHERE a.validTo IS NULL RETURN count(a) AS n")
        preds = db.query("MATCH ()-[a:ASSERTS]->() RETURN a.predicate AS p, count(*) AS n")
        per_wing = db.query("MATCH ()-[a:ASSERTS]->() RETURN a.wing AS w, count(*) AS n")
        literals = db.query("MATCH (e:Entity {kind:'literal'}) RETURN count(e) AS n")
    except Exception as exc:  # pragma: no cover
        return {"error": f"kg stats unavailable: {exc}"}

    total = triples[0]["n"] if triples else 0
    opn = open_[0]["n"] if open_ else 0
    return {
        "entities": (ent[0]["n"] if ent else 0),
        "triples_total": total,
        "open_triples": opn,
        "closed_triples": max(0, total - opn),
        "predicates": {row["p"]: row["n"] for row in (preds or [])},
        "per_wing": {row["w"] or "global": row["n"] for row in (per_wing or [])},
        "literal_entities": (literals[0]["n"] if literals else 0),
    }
