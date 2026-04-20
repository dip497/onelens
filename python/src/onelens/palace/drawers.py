"""Drawer operations: add, delete, search, check_duplicate. Canonical metadata preserved."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from . import store, taxonomy, wal
from .paths import CONTEXT_BASE


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _drawer_id(wing: str, content: str) -> str:
    h = hashlib.sha1(content.encode("utf-8")).hexdigest()[:12]
    return f"note:{wing}:{h}"


def _ensure_wing_collection(wing: str):
    """Create Chroma collection on demand for new wings (user notes / diaries)."""
    from onelens.context.palace import get_collection

    path = CONTEXT_BASE / wing
    path.mkdir(parents=True, exist_ok=True)
    col = get_collection(str(path), create=True)
    store._STATE["chroma_cache"][wing] = col
    return col


def check_duplicate(
    content: str,
    threshold: float = 0.9,
    *,
    wing: str | None = None,
    hall: str | None = None,
) -> dict:
    """Chroma semantic similarity query. similarity = 1 - distance."""
    matches: list[dict] = []
    wings = [wing] if wing else store.all_wings(include_agents=True)
    where: dict = {}
    if hall:
        where = {"hall": hall}

    for w in wings:
        try:
            col = store.get_chroma_collection(w)
        except Exception:
            continue
        try:
            kwargs = {
                "query_texts": [content],
                "n_results": 5,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            res = col.query(**kwargs)
        except Exception:
            continue
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for did, doc, meta, dist in zip(ids, docs, metas, dists):
            sim = round(max(0.0, 1.0 - float(dist)), 4)
            if sim >= threshold:
                matches.append(
                    {
                        "id": did,
                        "wing": (meta or {}).get("wing", w),
                        "room": (meta or {}).get("room", ""),
                        "similarity": sim,
                        "content": (doc or "")[:240],
                    }
                )
    matches.sort(key=lambda m: -m["similarity"])
    return {"is_duplicate": len(matches) > 0, "matches": matches}


def add_drawer(
    wing: str,
    room: str,
    content: str,
    source_file: str | None = None,
    added_by: str = "mcp",
    *,
    hall: str = "hall_fact",
    kind: str = "note",
    importance: float = 1.0,
    fqn: str | None = None,
    force: bool = False,
) -> dict:
    dup_threshold = float(os.environ.get("ONELENS_PALACE_DEDUP_COSINE", "0.95"))
    if not force:
        dup = check_duplicate(content, dup_threshold, wing=wing, hall=hall)
        if dup["is_duplicate"]:
            result = {
                "success": False,
                "wing": wing,
                "room": room,
                "drawer_id": dup["matches"][0]["id"],
                "reason": "already_exists",
                "matches": dup["matches"],
            }
            wal.log("palace_add_drawer", {"wing": wing, "room": room, "hall": hall}, result)
            return result

    col = _ensure_wing_collection(wing)
    did = _drawer_id(wing, content)
    ts = _utc_iso()
    metadata = {
        "wing": wing,
        "room": room,
        "hall": hall,
        "fqn": fqn or "",
        "type": kind,
        "importance": float(importance),
        "filed_at": ts,
        "source_file": source_file or "",
        "added_by": added_by,
    }
    try:
        col.upsert(ids=[did], documents=[content], metadatas=[metadata])
    except AttributeError:
        col.add(ids=[did], documents=[content], metadatas=[metadata])

    taxonomy.invalidate()
    result = {
        "success": True,
        "wing": wing,
        "room": room,
        "drawer_id": did,
        "timestamp": ts,
    }
    wal.log("palace_add_drawer", {"wing": wing, "room": room, "hall": hall, "kind": kind}, result)
    return result


def delete_drawer(drawer_id: str) -> dict:
    """Deletes from whichever wing collection holds the id."""
    deleted = 0
    for wing in store.all_wings(include_agents=True):
        try:
            col = store.get_chroma_collection(wing)
        except Exception:
            continue
        try:
            col.delete(ids=[drawer_id])
            deleted += 1
        except Exception:
            continue
    taxonomy.invalidate()
    result = {"success": deleted > 0, "drawer_id": drawer_id, "deleted": deleted}
    wal.log("palace_delete_drawer", {"drawer_id": drawer_id}, result)
    return result


def search(
    query: str,
    limit: int = 5,
    wing: str | None = None,
    room: str | None = None,
    context: str | None = None,  # noqa: ARG001 — MemPalace parity param, unused for embedding
    *,
    hall: str | None = None,
    kind: str | None = None,
    rerank: bool = True,
) -> dict:
    """Cross-wing Chroma search with optional cross-encoder rerank."""
    from onelens.context.searcher import build_where_filter

    where = build_where_filter(wing=wing, room=room, entity_type=kind)
    if hall:
        if where:
            conds = where.get("$and", [where])
            conds.append({"hall": hall})
            where = {"$and": conds}
        else:
            where = {"hall": hall}

    wings = [wing] if wing else store.all_wings(include_agents=False)
    hits: list[dict] = []
    for w in wings:
        try:
            col = store.get_chroma_collection(w)
        except Exception:
            continue
        kwargs = {
            "query_texts": [query],
            "n_results": max(limit * 3, 10),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        try:
            res = col.query(**kwargs)
        except Exception:
            continue
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for did, doc, meta, dist in zip(ids, docs, metas, dists):
            meta = meta or {}
            hits.append(
                {
                    "drawer_id": did,
                    "wing": meta.get("wing", w),
                    "room": meta.get("room", ""),
                    "hall": meta.get("hall"),
                    "fqn": meta.get("fqn"),
                    "snippet": (doc or "")[:240],
                    "score": round(max(0.0, 1.0 - float(dist)), 4),
                    "source": "main",
                }
            )

    hits.sort(key=lambda h: -h["score"])
    hits = hits[: max(limit * 3, limit)]

    if rerank and hits:
        try:
            reranker = store.get_reranker()
            scores = reranker.score(query, [h["snippet"] for h in hits])
            for h, s in zip(hits, scores):
                h["score"] = round(float(s), 4)
            hits.sort(key=lambda h: -h["score"])
        except Exception:
            pass

    return {"query": query, "total": len(hits), "results": hits[:limit]}
