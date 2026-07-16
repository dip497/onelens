"""Generic BFS traverse over code graphs (FalkorDB) + palace KG."""

from __future__ import annotations

from . import store


def _resolve_graph(start: str, wing: str | None):
    """Pick the wing whose graph contains the start node (by fqn). Fallback: first wing."""
    candidates = [wing] if wing else store.all_wings()
    for w in candidates:
        try:
            db = store.get_graph_db(w)
            rows = db.query(
                "MATCH (n) WHERE n.fqn=$s OR n.name=$s RETURN 1 LIMIT 1", {"s": start}
            )
        except Exception:
            continue
        if rows:
            return w, db
    return None, None


def traverse(
    start_room: str,
    max_hops: int = 2,
    *,
    wing: str | None = None,
    edge_kinds: list[str] | None = None,
    node_labels: list[str] | None = None,
    limit: int = 50,
) -> list[dict]:
    """BFS from start. `start_room` may be an fqn, node name, or room slug."""
    resolved_wing, db = _resolve_graph(start_room, wing)
    if db is None:
        return []

    hops = max(1, min(int(max_hops), 5))
    edge_pred = ""
    if edge_kinds:
        types = ",".join(f"'{t}'" for t in edge_kinds)
        edge_pred = f" WHERE all(r IN relationships(p) WHERE type(r) IN [{types}])"

    try:
        rows = db.query(
            f"MATCH p=(s)-[*1..{hops}]-(n) "
            "WHERE s.fqn=$start OR s.name=$start "
            f"{edge_pred} "
            "RETURN p LIMIT $limit",
            {"start": start_room, "limit": int(limit)},
        )
    except Exception:
        return []

    paths: list[dict] = []
    label_filter = set(node_labels or [])
    for row in rows or []:
        p = row.get("p")
        if not p:
            continue
        nodes_out: list[dict] = []
        edges_out: list[dict] = []
        for n in getattr(p, "nodes", []) or []:
            labels = list(getattr(n, "labels", []) or [])
            if label_filter and not (label_filter & set(labels)):
                break
            props = dict(getattr(n, "properties", {}) or {})
            nodes_out.append({
                "label": labels[0] if labels else "",
                "fqn": props.get("fqn"),
                "name": props.get("name"),
                "wing": resolved_wing,
            })
        else:
            for e in getattr(p, "edges", []) or []:
                edges_out.append({
                    "type": getattr(e, "relation", "") or getattr(e, "type", ""),
                    "props": dict(getattr(e, "properties", {}) or {}),
                })
            paths.append({"nodes": nodes_out, "edges": edges_out})
    return paths
