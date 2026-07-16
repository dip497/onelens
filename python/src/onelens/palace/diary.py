"""Per-agent diary — Chroma-backed under wing=agent:<name>."""

from __future__ import annotations

from . import drawers, store


def _agent_wing(agent_name: str) -> str:
    return f"agent:{agent_name}"


def write(agent_name: str, entry: str, topic: str = "general", *, importance: float = 1.0) -> dict:
    return drawers.add_drawer(
        wing=_agent_wing(agent_name),
        room=f"diary-{topic}",
        content=entry,
        added_by=f"agent:{agent_name}",
        hall="hall_event",
        kind="diary",
        importance=importance,
        force=True,  # diaries are append-only; no dedup
    )


def read(
    agent_name: str,
    last_n: int = 10,
    *,
    topic: str | None = None,
    since: str | None = None,
) -> list[dict]:
    wing = _agent_wing(agent_name)
    try:
        col = store.get_chroma_collection(wing)
    except Exception:
        return []

    where: dict = {"$and": [{"wing": wing}, {"hall": "hall_event"}]}
    if topic:
        where["$and"].append({"room": f"diary-{topic}"})
    try:
        rows = col.get(where=where, include=["documents", "metadatas"])
    except Exception:
        return []

    docs = rows.get("documents", []) or []
    metas = rows.get("metadatas", []) or []
    entries: list[dict] = []
    for doc, meta in zip(docs, metas):
        meta = meta or {}
        ts = meta.get("filed_at", "")
        if since and ts < since:
            continue
        entries.append({
            "ts": ts,
            "topic": (meta.get("room", "") or "").removeprefix("diary-") or "general",
            "entry": doc or "",
            "importance": float(meta.get("importance", 1.0) or 1.0),
        })
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries[:last_n]
