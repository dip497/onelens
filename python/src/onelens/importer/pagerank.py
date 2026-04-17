"""
Compute personalized PageRank on the call graph and write scores back as
Method.pagerank / Class.pagerank properties.

Why PageRank over raw fan-in? Naked fan-in ranks utility pollinators
(`Logger.info`, `String.equals`) above real business-critical methods.
PageRank propagates importance — a method called BY important methods
scores high; a method called by a tight loop of low-importance helpers
does not. Personalization seeds mass at REST endpoints (and other entry
points) so importance flows downstream from user-facing traffic.

One-time cost at import: ~5-15s for 80K methods / 600K edges on NetworkX.
Read-side benefit: "show core services" becomes `ORDER BY pagerank DESC`
— O(1) via range index.
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    import networkx as nx
except ImportError:  # soft dep — importer still works without it
    nx = None  # type: ignore

logger = logging.getLogger(__name__)

# Seed mass. Entry points receive higher personalization weight so
# importance flows downstream from user-facing traffic rather than
# accumulating at library-like utilities with many callers.
_ENTRY_POINT_SEED = 10.0
_DEFAULT_SEED = 1.0

# NetworkX pagerank parameters.
_DAMPING = 0.85       # Google's canonical damping
_MAX_ITER = 100
_TOL = 1e-6


def compute_method_pagerank(db, graph_name: str | None = None) -> dict[str, float]:
    """Build the CALLS graph in-memory, run personalized PageRank, return fqn→score.

    PageRank follows CALLS edges: a call `caller → callee` pushes importance
    from caller to callee. We personalize endpoint handlers and scheduled
    methods so the canonical "important" leaves are those reachable from
    real traffic.

    Returns empty dict if NetworkX isn't installed or the graph has no
    method nodes.
    """
    if nx is None:
        logger.warning("NetworkX not installed; skipping PageRank")
        return {}

    t0 = time.time()

    # All CALLS edges in the graph. One round trip.
    rows = db.query(
        "MATCH (c:Method)-[:CALLS]->(m:Method) RETURN c.fqn AS src, m.fqn AS dst"
    )
    if not rows:
        logger.info("No CALLS edges — skipping PageRank")
        return {}

    G: Any = nx.DiGraph()
    for r in rows:
        src = r.get("src")
        dst = r.get("dst")
        if src and dst:
            G.add_edge(src, dst)

    # Entry points: REST endpoint handlers + @Scheduled + main(). These seed
    # the personalization vector so importance "flows down" from traffic.
    ep_rows = db.query(
        "MATCH (m:Method)-[:HANDLES]->(e:Endpoint) RETURN DISTINCT m.fqn AS fqn"
    )
    scheduled_rows = db.query(
        "MATCH (m:Method)-[:ANNOTATED_WITH]->(a:Annotation) "
        "WHERE a.name IN ['Scheduled', 'PostConstruct', 'EventListener', 'KafkaListener'] "
        "RETURN DISTINCT m.fqn AS fqn"
    )
    entry_points = {r["fqn"] for r in (ep_rows + scheduled_rows) if r.get("fqn")}

    # Ensure entry points are in the graph even if they have no outbound calls.
    for fqn in entry_points:
        if fqn not in G:
            G.add_node(fqn)

    personalization: dict[str, float] = {}
    for node in G.nodes():
        personalization[node] = _ENTRY_POINT_SEED if node in entry_points else _DEFAULT_SEED

    try:
        ranks = nx.pagerank(
            G,
            alpha=_DAMPING,
            personalization=personalization,
            max_iter=_MAX_ITER,
            tol=_TOL,
        )
    except nx.PowerIterationFailedConvergence:
        # Graph has structural issues (dangling clusters, bad weights).
        # Fall back to un-personalized — still better than nothing.
        logger.warning("PageRank did not converge with personalization; retrying plain")
        ranks = nx.pagerank(G, alpha=_DAMPING, max_iter=_MAX_ITER, tol=_TOL)

    dt = time.time() - t0
    logger.info(
        "PageRank: %d nodes, %d edges, %d entry-points, took %.1fs",
        G.number_of_nodes(),
        G.number_of_edges(),
        len(entry_points),
        dt,
    )
    return ranks


def write_pagerank(db, scores: dict[str, float], batch_size: int = 5000) -> int:
    """Write pagerank scores back onto Method nodes via batched UNWIND."""
    if not scores:
        return 0

    items = [{"fqn": fqn, "pr": float(pr)} for fqn, pr in scores.items()]
    written = 0
    for i in range(0, len(items), batch_size):
        chunk = items[i : i + batch_size]
        db.query(
            "UNWIND $items AS row "
            "MATCH (m:Method {fqn: row.fqn}) "
            "SET m.pagerank = row.pr",
            {"items": chunk},
        )
        written += len(chunk)
    return written


def compute_class_pagerank(db, method_scores: dict[str, float]) -> dict[str, float]:
    """Roll method scores up to owning Class — a class's PR = sum of its methods'.

    This is cheap (one query + dict sum) and makes class-level ranking
    ("core services") a direct `ORDER BY Class.pagerank` query.
    """
    if not method_scores:
        return {}

    rows = db.query(
        "MATCH (c:Class)-[:HAS_METHOD]->(m:Method) RETURN c.fqn AS cls, m.fqn AS mfqn"
    )
    class_scores: dict[str, float] = {}
    for r in rows:
        cls = r.get("cls")
        mfqn = r.get("mfqn")
        if not cls or not mfqn:
            continue
        class_scores[cls] = class_scores.get(cls, 0.0) + method_scores.get(mfqn, 0.0)
    return class_scores


def write_class_pagerank(db, scores: dict[str, float], batch_size: int = 2000) -> int:
    if not scores:
        return 0
    items = [{"fqn": fqn, "pr": float(pr)} for fqn, pr in scores.items()]
    written = 0
    for i in range(0, len(items), batch_size):
        chunk = items[i : i + batch_size]
        db.query(
            "UNWIND $items AS row "
            "MATCH (c:Class {fqn: row.fqn}) "
            "SET c.pagerank = row.pr",
            {"items": chunk},
        )
        written += len(chunk)
    return written


def run(db, graph_name: str | None = None) -> dict:
    """Full pipeline: compute + write for methods and classes. Returns stats."""
    t0 = time.time()
    method_scores = compute_method_pagerank(db, graph_name)
    if not method_scores:
        return {"pagerank": "skipped"}

    n_methods = write_pagerank(db, method_scores)
    class_scores = compute_class_pagerank(db, method_scores)
    n_classes = write_class_pagerank(db, class_scores)

    return {
        "methods_scored": n_methods,
        "classes_scored": n_classes,
        "top_method": max(method_scores, key=method_scores.get) if method_scores else None,
        "top_class": max(class_scores, key=class_scores.get) if class_scores else None,
        "total_ms": int((time.time() - t0) * 1000),
    }
