"""
searcher.py — Semantic search over OneLens context drawers.

Returns structured results with FQN, type, importance, and similarity.
Integrates query_sanitizer to mitigate prompt injection from AI agents.
"""

import logging

from .config import DEFAULT_COLLECTION_NAME
from .palace import get_collection
from .query_sanitizer import sanitize_query

logger = logging.getLogger(__name__)


def build_where_filter(
    wing: str = None,
    room: str = None,
    entity_type: str = None,
) -> dict:
    """Build ChromaDB where filter for wing/room/type filtering."""
    conditions = []
    if wing:
        conditions.append({"wing": wing})
    if room:
        conditions.append({"room": room})
    if entity_type:
        conditions.append({"type": entity_type})

    if len(conditions) > 1:
        return {"$and": conditions}
    elif len(conditions) == 1:
        return conditions[0]
    return {}


def search_context(
    query: str,
    context_path: str,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    wing: str = None,
    room: str = None,
    entity_type: str = None,
    n_results: int = 10,
    max_distance: float = 0.0,
) -> dict:
    """
    Semantic search over code context. Returns structured results.

    Args:
        query: Natural language search query.
        context_path: Path to the ChromaDB context directory.
        wing: Optional graph name filter.
        room: Optional package filter.
        entity_type: Optional "method" | "class" | "endpoint" filter.
        n_results: Max results to return.
        max_distance: Max cosine distance (0.0 disables). Range 0.3-1.0 typical.

    Returns:
        Dict with query, filters, and results list.
    """
    # Sanitize query to strip prompt injection
    sanitized = sanitize_query(query)
    clean_query = sanitized["clean_query"]
    if not clean_query.strip():
        return {"query": query, "filters": {}, "results": [], "error": "empty query"}

    try:
        col = get_collection(context_path, collection_name, create=False)
    except Exception as e:
        logger.error("No context found at %s: %s", context_path, e)
        return {
            "error": "No context found",
            "hint": "Run: onelens import <json> --graph <name> --context",
        }

    where = build_where_filter(wing, room, entity_type)

    kwargs = {
        "query_texts": [clean_query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = col.query(**kwargs)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        if max_distance > 0.0 and dist > max_distance:
            continue
        hits.append({
            "text": doc,
            "fqn": meta.get("fqn", ""),
            "type": meta.get("type", ""),
            "wing": meta.get("wing", ""),
            "room": meta.get("room", ""),
            "importance": meta.get("importance", 0.0),
            "similarity": round(max(0.0, 1 - dist), 3),
            "distance": round(dist, 4),
        })

    return {
        "query": query,
        "clean_query": clean_query,
        "was_sanitized": sanitized["was_sanitized"],
        "filters": {"wing": wing, "room": room, "type": entity_type},
        "total": len(docs),
        "results": hits,
    }
