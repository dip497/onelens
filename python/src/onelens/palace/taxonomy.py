"""Wing / room / hall readers. Pulls from ChromaDB metadata (MemPalace-style)."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from . import store

# 30 s taxonomy cache to amortize metadata scans.
_CACHE: dict[str, Any] = {"ts": 0.0, "wings": {}, "rooms": {}, "halls": {}}
_CACHE_TTL = 30.0

HALLS = ("hall_code", "hall_signature", "hall_doc", "hall_event", "hall_fact")


def _scan() -> dict[str, Any]:
    """Walk every wing's Chroma collection once; emit counts keyed by wing/room/hall."""
    now = time.monotonic()
    if now - _CACHE["ts"] < _CACHE_TTL and _CACHE["wings"]:
        return _CACHE

    wing_counts: dict[str, int] = defaultdict(int)
    room_counts: dict[tuple[str, str], int] = defaultdict(int)
    hall_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    last_touched: dict[str, str] = {}
    fqn_samples: dict[tuple[str, str], list[str]] = defaultdict(list)

    for wing in store.all_wings(include_agents=True):
        try:
            col = store.get_chroma_collection(wing)
        except Exception:
            continue
        try:
            rows = col.get(include=["metadatas"])
        except Exception:
            continue
        for meta in rows.get("metadatas", []) or []:
            if not meta:
                continue
            w = meta.get("wing", wing) or wing
            r = meta.get("room", "unknown") or "unknown"
            h = meta.get("hall", "hall_code") or "hall_code"
            wing_counts[w] += 1
            room_counts[(w, r)] += 1
            hall_counts[(w, r, h)] += 1
            filed = meta.get("filed_at")
            if filed and (w not in last_touched or filed > last_touched[w]):
                last_touched[w] = filed
            fqn = meta.get("fqn")
            if fqn and len(fqn_samples[(w, r)]) < 5:
                fqn_samples[(w, r)].append(fqn)

    _CACHE.update(
        ts=now,
        wings=dict(wing_counts),
        rooms=dict(room_counts),
        halls=dict(hall_counts),
        last_touched=last_touched,
        fqn_samples=dict(fqn_samples),
    )
    return _CACHE


def invalidate() -> None:
    _CACHE["ts"] = 0.0


def wing_counts() -> dict[str, int]:
    return _scan()["wings"]


def room_counts(wing: str | None = None) -> dict[str, int]:
    rooms = _scan()["rooms"]
    if wing:
        return {r: c for (w, r), c in rooms.items() if w == wing}
    flat: dict[str, int] = defaultdict(int)
    for (_w, r), c in rooms.items():
        flat[r] += c
    return dict(flat)


def taxonomy_tree() -> dict[str, dict[str, dict[str, int]]]:
    """Nested {wing: {room: {hall: count}}}."""
    tree: dict[str, dict[str, dict[str, int]]] = {}
    for (w, r, h), c in _scan()["halls"].items():
        tree.setdefault(w, {}).setdefault(r, {})[h] = c
    return tree


def last_touched() -> dict[str, str]:
    return _scan().get("last_touched", {})


def fqn_samples() -> dict[tuple[str, str], list[str]]:
    return _scan().get("fqn_samples", {})
