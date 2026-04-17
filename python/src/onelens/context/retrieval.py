"""
retrieval.py — Hybrid retrieval pipeline (FTS + semantic + RRF + snippets).

Design (2026 state of the art, see docs for sources):
- Parallel retrieval: FalkorDB FTS and ChromaDB semantic run concurrently.
- Reciprocal Rank Fusion (RRF, k=60): industry-standard rank fusion that
  rewards docs appearing in either list. Reference: Cormack et al. 2009.
- N>>K principle: retrieve `fanout` (default 50) per source, fuse to top-N.
- Code snippets: fetched from filePath[lineStart:lineEnd] so the LLM gets
  actual code, not just FQN pointers (matches Augment Context Engine UX).
- 1-hop expansion (optional): adds direct callers/callees for methods.

Typical latency on a warm cache: ~150-250ms for 10 hits with snippets.
"""

import concurrent.futures
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from .config import DEFAULT_COLLECTION_NAME
from .searcher import search_context

logger = logging.getLogger(__name__)

# RRF constant from Cormack et al. 2009; Elasticsearch/Redis default; don't tune.
RRF_K = 60
DEFAULT_FANOUT = 50
MAX_SNIPPET_LINES = 80

# PageRank boost: after fusion, multiply each hit's score by
# (1 + PAGERANK_WEIGHT * normalized_pr). PR is graph-topological — it
# measures how important a method is structurally. Applying it AFTER
# fusion (rather than as an RRF source) means PR only promotes hits
# that already matched the query — it can't leak irrelevant-but-central
# utilities into results. 0.3 is conservative: a method in top 10% of
# PR gets at most 30% score boost, not enough to push off-topic hits
# over on-topic ones, enough to break ties toward canonical impls.
PAGERANK_WEIGHT = 0.3

# Cross-encoder score below this → drop the hit. Empirically calibrated:
# gibberish queries produce rerank scores ≤ 0.005, real queries mostly ≥ 0.1,
# but short/broad queries like "/ticket" can have top hits around 0.03-0.07.
# The 0.02 floor kills gibberish without cutting legitimate weak matches.
# Override via env ONELENS_MIN_RERANK_SCORE.
DEFAULT_MIN_RERANK_SCORE = 0.02

# Query-shape boost multipliers (post-RRF, pre-rerank). Derived from
# code-review-graph's detect_query_kind_boost. Rationale: when the user types
# a literal class/method name or a URL path, we know which node type they
# want — boost hits of that type instead of treating all fused results equally.
_BOOST_CLASS = 1.5
_BOOST_METHOD = 1.5
_BOOST_ENDPOINT = 2.5
_BOOST_FQN_MATCH = 2.0


@dataclass
class RetrievalHit:
    """A single retrieval result with score, location, and optional snippet."""

    fqn: str
    type: str
    score: float
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
    context_text: str = ""
    rank_fts: Optional[int] = None
    rank_semantic: Optional[int] = None
    rerank_score: Optional[float] = None
    callers: list = field(default_factory=list)
    callees: list = field(default_factory=list)


_HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _detect_query_kind(query: str) -> dict:
    """Parse query shape → hint for which node types to boost.

    Returns a dict with keys:
        preferred_types: set of node types to boost (e.g., {"class"})
        boost_factor: multiplier for hits of preferred types
        fqn_substring: if query looks like a qualified name fragment
                       (contains '.' or '#'), boost hits whose fqn contains it
        is_route: True if query looks like a URL path or HTTP verb + path
    """
    q = query.strip()
    out = {
        "preferred_types": set(),
        "boost_factor": 1.0,
        "fqn_substring": "",
        "is_route": False,
    }

    # Route-shaped query: starts with '/', or HTTP_VERB + space + /path
    first_token = q.split(None, 1)[0] if q else ""
    if q.startswith("/") or first_token.upper() in _HTTP_VERBS:
        out["preferred_types"] = {"endpoint"}
        out["boost_factor"] = _BOOST_ENDPOINT
        out["is_route"] = True
        return out

    # Method/Field FQN: contains '#'
    if "#" in q:
        out["fqn_substring"] = q
        out["preferred_types"] = {"method"}
        out["boost_factor"] = _BOOST_FQN_MATCH
        return out

    # Qualified name: contains '.' and no spaces (user typed a.b.c fragment)
    if "." in q and " " not in q and len(q) > 3:
        out["fqn_substring"] = q
        out["boost_factor"] = _BOOST_FQN_MATCH
        return out

    # Single-token shape detection
    if " " not in q and q.isidentifier():
        if q[0].isupper() and any(c.islower() for c in q[1:]):
            # PascalCase → class name
            out["preferred_types"] = {"class"}
            out["boost_factor"] = _BOOST_CLASS
        elif q[0].islower() and (any(c.isupper() for c in q) or "_" in q):
            # camelCase or snake_case → method name
            out["preferred_types"] = {"method"}
            out["boost_factor"] = _BOOST_METHOD
    return out


def _apply_pagerank_boost(
    ranked: list[tuple[str, tuple[float, dict]]],
    locations: dict[str, dict],
    weight: float = PAGERANK_WEIGHT,
) -> list[tuple[str, tuple[float, dict]]]:
    """Multiply each ranked item's fused score by (1 + weight * normalized_pr).

    Normalization is min-max within the current candidate pool — prevents one
    absurdly high PR from dominating and keeps the boost bounded at `weight`.
    No-op if no candidate has a pagerank (graph imported before B1, or all
    hits are externals / non-method nodes).
    """
    if not ranked or weight <= 0:
        return ranked

    prs = [(locations.get(fqn) or {}).get("pagerank", 0.0) or 0.0 for fqn, _ in ranked]
    pr_max = max(prs)
    pr_min = min(prs)
    pr_range = pr_max - pr_min
    if pr_range <= 0:
        return ranked  # all same PR (likely all 0) → boost has no effect

    boosted: list[tuple[str, tuple[float, dict]]] = []
    for (fqn, (score, ranks)), pr in zip(ranked, prs):
        norm = (pr - pr_min) / pr_range  # [0, 1]
        mult = 1.0 + weight * norm
        boosted.append((fqn, (score * mult, ranks)))
    boosted.sort(key=lambda x: -x[1][0])
    return boosted


def _apply_kind_boost(
    ranked: list[tuple[str, tuple[float, dict]]],
    hint: dict,
    locations: dict[str, dict],
) -> list[tuple[str, tuple[float, dict]]]:
    """Multiply RRF scores by boost factor for hits matching the query-shape hint.

    Re-sorts after boosting. Safe no-op if hint is empty.
    """
    preferred = hint.get("preferred_types") or set()
    boost = hint.get("boost_factor", 1.0)
    substr = hint.get("fqn_substring", "")

    if boost <= 1.0 and not substr:
        return ranked

    boosted: list[tuple[str, tuple[float, dict]]] = []
    for fqn, (score, ranks) in ranked:
        mult = 1.0
        if preferred:
            ntype = (locations.get(fqn) or {}).get("type", "")
            if ntype in preferred:
                mult *= boost
        if substr and substr in fqn:
            mult *= _BOOST_FQN_MATCH
        boosted.append((fqn, (score * mult, ranks)))
    boosted.sort(key=lambda x: -x[1][0])
    return boosted


def _rrf_fuse(rankings: dict[str, list[str]], k: int = RRF_K) -> dict[str, tuple[float, dict]]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    Args:
        rankings: {source_name: [fqn, ...]} each list ordered best-first.
        k: RRF smoothing constant.

    Returns:
        {fqn: (fused_score, {source_name: rank})} sorted by score descending.
    """
    scores: dict[str, float] = {}
    ranks_by_fqn: dict[str, dict] = {}
    for source, ranking in rankings.items():
        for rank, fqn in enumerate(ranking):
            if not fqn:
                continue
            scores[fqn] = scores.get(fqn, 0.0) + 1.0 / (k + rank)
            ranks_by_fqn.setdefault(fqn, {})[source] = rank
    return {fqn: (score, ranks_by_fqn[fqn]) for fqn, score in scores.items()}


def _graph_direct(db, query: str, hint: dict, n: int) -> list[RetrievalHit]:
    """Fast-path: direct Cypher match for structural queries.

    Returns hits with score=1.0 for exact matches, 0.8 for CONTAINS.
    Skips the expensive FTS+semantic+RRF+rerank pipeline entirely.
    Returns empty list if query doesn't match a structural pattern.
    """
    q = query.strip()
    if not q:
        return []

    preferred = hint.get("preferred_types", set())
    is_route = hint.get("is_route", False)
    fqn_sub = hint.get("fqn_substring", "")

    results: list[dict] = []

    try:
        if is_route:
            # Extract path portion: "PATCH /vendor/{id}" → "/vendor/{id}"
            parts = q.split(None, 1)
            path = parts[1] if len(parts) > 1 and parts[0].upper() in _HTTP_VERBS else parts[0]
            http_method = parts[0].upper() if len(parts) > 1 and parts[0].upper() in _HTTP_VERBS else ""

            cypher = """
                MATCH (h:Method)-[:HANDLES]->(e:Endpoint)
                WHERE e.path CONTAINS $path
            """
            params: dict = {"path": path}
            if http_method:
                cypher += " AND e.httpMethod = $method"
                params["method"] = http_method
            # Use e.id (matches FTS / semantic output format "METHOD:/path").
            # Mixing formats here breaks RRF merging with other sources.
            cypher += """
                RETURN e.id AS fqn,
                       'endpoint' AS type,
                       h.filePath AS filePath,
                       h.lineStart AS lineStart,
                       h.lineEnd AS lineEnd,
                       1.0 AS score
                LIMIT $n
            """
            params["n"] = n
            results = db.query(cypher, params) or []

        elif fqn_sub:
            # FQN fragment: contains '#' or '.'
            for label in ("Method", "Class"):
                if len(results) >= n:
                    break
                rows = db.query(
                    f"MATCH (n:{label}) WHERE n.fqn CONTAINS $q "
                    f"RETURN n.fqn AS fqn, '{label.lower()}' AS type, "
                    f"n.filePath AS filePath, n.lineStart AS lineStart, "
                    f"n.lineEnd AS lineEnd, 0.9 AS score LIMIT $n",
                    {"q": fqn_sub, "n": n},
                ) or []
                results.extend(rows)

        elif "class" in preferred:
            # PascalCase → exact class name match first, then CONTAINS
            rows = db.query(
                "MATCH (c:Class {name: $q}) "
                "RETURN c.fqn AS fqn, 'class' AS type, c.filePath AS filePath, "
                "c.lineStart AS lineStart, c.lineEnd AS lineEnd, 1.0 AS score LIMIT $n",
                {"q": q, "n": n},
            ) or []
            results.extend(rows)
            if len(results) < n:
                more = db.query(
                    "MATCH (c:Class) WHERE c.name CONTAINS $q "
                    "RETURN c.fqn AS fqn, 'class' AS type, c.filePath AS filePath, "
                    "c.lineStart AS lineStart, c.lineEnd AS lineEnd, 0.8 AS score "
                    "ORDER BY c.name LIMIT $n",
                    {"q": q, "n": n - len(results)},
                ) or []
                results.extend(more)

        elif "method" in preferred:
            # camelCase/snake_case → method name match
            rows = db.query(
                "MATCH (m:Method) WHERE m.name = $q AND m.external IS NULL "
                "RETURN m.fqn AS fqn, 'method' AS type, m.filePath AS filePath, "
                "m.lineStart AS lineStart, m.lineEnd AS lineEnd, 1.0 AS score LIMIT $n",
                {"q": q, "n": n},
            ) or []
            results.extend(rows)
            if len(results) < n:
                more = db.query(
                    "MATCH (m:Method) WHERE m.name CONTAINS $q AND m.external IS NULL "
                    "RETURN m.fqn AS fqn, 'method' AS type, m.filePath AS filePath, "
                    "m.lineStart AS lineStart, m.lineEnd AS lineEnd, 0.8 AS score "
                    "ORDER BY m.name LIMIT $n",
                    {"q": q, "n": n - len(results)},
                ) or []
                results.extend(more)
        else:
            return []

    except Exception as e:
        logger.debug("Graph direct search failed: %s", e)
        return []

    # Deduplicate by fqn
    seen: set[str] = set()
    hits: list[RetrievalHit] = []
    for r in results:
        fqn = r.get("fqn", "")
        if not fqn or fqn in seen:
            continue
        seen.add(fqn)
        hits.append(RetrievalHit(
            fqn=fqn,
            type=r.get("type", "unknown"),
            score=float(r.get("score", 0.8)),
            file_path=r.get("filePath", "") or "",
            line_start=r.get("lineStart", 0) or 0,
            line_end=r.get("lineEnd", 0) or 0,
        ))
    return hits[:n]


def _fts_search(db, query: str, fanout: int) -> list[str]:
    """FalkorDB full-text search across all node types. Returns deduped FQN list."""
    from onelens.graph.analysis import search_code

    try:
        results = search_code(db, query, "")
    except Exception as e:
        logger.warning("FTS search failed: %s", e)
        return []

    seen: set[str] = set()
    ordered: list[str] = []
    for r in results:
        fqn = r.get("fqn", "")
        if fqn and fqn not in seen:
            seen.add(fqn)
            ordered.append(fqn)
            if len(ordered) >= fanout:
                break
    return ordered


def _semantic_search(
    query: str, context_path: str, wing: str, fanout: int
) -> tuple[list[str], dict[str, dict]]:
    """ChromaDB semantic search. Returns (fqn_list, {fqn: hit_metadata})."""
    try:
        result = search_context(query, context_path, wing=wing, n_results=fanout)
    except Exception as e:
        logger.warning("Semantic search failed: %s", e)
        return [], {}

    if "error" in result and not result.get("results"):
        logger.info("Semantic search unavailable: %s", result.get("error"))
        return [], {}

    hits = result.get("results", [])
    fqns: list[str] = []
    meta: dict[str, dict] = {}
    for h in hits:
        fqn = h.get("fqn", "")
        if fqn:
            fqns.append(fqn)
            meta[fqn] = h
    return fqns, meta


def _fetch_locations_batch(db, fqns: list[str]) -> dict[str, dict]:
    """Fetch {filePath, lineStart, lineEnd, type} for a list of FQNs in one pass.

    Probes Method, Class, and Endpoint labels in sequence — first match wins.
    One round-trip per label, regardless of how many FQNs.
    """
    locations: dict[str, dict] = {}
    remaining = set(fqns)
    if not remaining:
        return {}

    # Methods — also pull pagerank when present (populated at import time).
    # Missing pagerank is tolerated (pre-B1 graphs, external methods).
    try:
        rows = db.query(
            """
            UNWIND $fqns AS fqn
            MATCH (m:Method {fqn: fqn})
            RETURN m.fqn AS fqn, m.filePath AS filePath,
                   m.lineStart AS lineStart, m.lineEnd AS lineEnd,
                   m.pagerank AS pagerank
            """,
            {"fqns": list(remaining)},
        )
        for r in rows:
            fqn = r.get("fqn", "")
            if fqn:
                locations[fqn] = {
                    "type": "method",
                    "filePath": r.get("filePath", "") or "",
                    "lineStart": r.get("lineStart", 0) or 0,
                    "lineEnd": r.get("lineEnd", 0) or 0,
                    "pagerank": r.get("pagerank") or 0.0,
                }
                remaining.discard(fqn)
    except Exception as e:
        logger.debug("Method location lookup failed: %s", e)

    # Classes — pull pagerank too (Class.pagerank is sum of its methods' PRs).
    if remaining:
        try:
            rows = db.query(
                """
                UNWIND $fqns AS fqn
                MATCH (c:Class {fqn: fqn})
                RETURN c.fqn AS fqn, c.filePath AS filePath,
                       c.lineStart AS lineStart, c.lineEnd AS lineEnd,
                       c.pagerank AS pagerank
                """,
                {"fqns": list(remaining)},
            )
            for r in rows:
                fqn = r.get("fqn", "")
                if fqn:
                    locations[fqn] = {
                        "type": "class",
                        "filePath": r.get("filePath", "") or "",
                        "lineStart": r.get("lineStart", 0) or 0,
                        "lineEnd": r.get("lineEnd", 0) or 0,
                        "pagerank": r.get("pagerank") or 0.0,
                    }
                    remaining.discard(fqn)
        except Exception as e:
            logger.debug("Class location lookup failed: %s", e)

    # Endpoints (resolve via handler method)
    if remaining:
        try:
            rows = db.query(
                """
                UNWIND $fqns AS fqn
                MATCH (e:Endpoint {id: fqn})
                MATCH (h:Method)-[:HANDLES]->(e)
                RETURN e.id AS fqn, h.filePath AS filePath,
                       h.lineStart AS lineStart, h.lineEnd AS lineEnd
                """,
                {"fqns": list(remaining)},
            )
            for r in rows:
                fqn = r.get("fqn", "")
                if fqn:
                    locations[fqn] = {
                        "type": "endpoint",
                        "filePath": r.get("filePath", "") or "",
                        "lineStart": r.get("lineStart", 0) or 0,
                        "lineEnd": r.get("lineEnd", 0) or 0,
                    }
        except Exception as e:
            logger.debug("Endpoint location lookup failed: %s", e)

    return locations


def _read_snippet(
    file_path: str,
    line_start: int,
    line_end: int,
    project_root: str = "",
    max_lines: int = MAX_SNIPPET_LINES,
) -> str:
    """Read a source slice. filePath is project-relative; project_root resolves it."""
    if not file_path or not line_start:
        return ""

    full_path = file_path if os.path.isabs(file_path) else os.path.join(project_root or "", file_path)
    if not full_path or not os.path.isfile(full_path):
        return ""

    if line_end <= line_start:
        line_end = line_start + max_lines
    line_end = min(line_end, line_start + max_lines)

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        logger.debug("Could not read %s: %s", full_path, e)
        return ""

    return "".join(lines[line_start - 1 : line_end]).rstrip()


def _fetch_neighbors(db, fqn: str, limit: int = 5) -> tuple[list[str], list[str]]:
    """Direct callers and callees of a method (1-hop each)."""
    callers: list[str] = []
    callees: list[str] = []
    try:
        rows = db.query(
            "MATCH (c:Method)-[:CALLS]->(m:Method {fqn: $fqn}) RETURN DISTINCT c.fqn AS fqn LIMIT $lim",
            {"fqn": fqn, "lim": limit},
        )
        callers = [r.get("fqn", "") for r in rows if r.get("fqn")]
    except Exception:
        pass
    try:
        rows = db.query(
            "MATCH (m:Method {fqn: $fqn})-[:CALLS]->(c:Method) RETURN DISTINCT c.fqn AS fqn LIMIT $lim",
            {"fqn": fqn, "lim": limit},
        )
        callees = [r.get("fqn", "") for r in rows if r.get("fqn")]
    except Exception:
        pass
    return callers, callees


def hybrid_retrieve(
    query: str,
    graph: str,
    db,
    context_path: str,
    n_results: int = 10,
    fanout: int = DEFAULT_FANOUT,
    include_snippets: bool = True,
    include_neighbors: bool = False,
    rerank: bool = False,
    rerank_pool: int = 100,
    project_root: str = "",
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[RetrievalHit]:
    """Hybrid retrieval: parallel FTS + semantic → RRF → top-K with snippets.

    When rerank=True, fetches `rerank_pool` candidates (with snippets), scores
    each (query, snippet) pair with a cross-encoder, then keeps top n_results.

    Args:
        query: natural language query
        graph: graph name (wing)
        db: GraphDB instance (used for FTS + location + neighbors)
        context_path: ChromaDB context directory for this graph
        n_results: final top-K after fusion (and optional rerank)
        fanout: per-source retrieval depth before fusion (N>>K principle)
        include_snippets: read source at filePath:lineStart-lineEnd
        include_neighbors: include 1-hop callers/callees for methods
        rerank: apply cross-encoder reranking to top `rerank_pool` hits
        rerank_pool: how many candidates to rerank (usually 5-10x n_results)
        project_root: filesystem root to resolve relative filePaths

    Returns:
        List of RetrievalHit sorted by RRF score (or rerank score, if used).
    """
    if not query.strip():
        return []

    # Stage 0: query router — structural queries hit graph first. Graph hits
    # feed into RRF as a third source "graph". Only shortcircuit (skip
    # FTS+semantic+rerank entirely) when the query is a clear exact-symbol
    # match (PascalCase class name or FQN with '#'), where graph gives
    # canonical ground truth. Route queries and CONTAINS-style lookups fall
    # through to hybrid because they're too fuzzy to trust graph-only.
    hint = _detect_query_kind(query)
    _graph_fqns: list[str] = []
    _shortcircuit_ok = (
        bool(hint.get("fqn_substring"))
        or ("class" in hint.get("preferred_types", set()))
    )
    if hint.get("preferred_types") or hint.get("is_route") or hint.get("fqn_substring"):
        graph_hits = _graph_direct(db, query, hint, n_results)
        # Only shortcircuit when the TOP hit is a clean exact/prefix match
        # (score >= 1.0 means the exact-match branch fired in _graph_direct).
        if (
            _shortcircuit_ok
            and graph_hits
            and graph_hits[0].score >= 1.0
            and len(graph_hits) >= n_results
        ):
            if include_snippets:
                for h in graph_hits:
                    if h.file_path:
                        h.snippet = _read_snippet(h.file_path, h.line_start, h.line_end, project_root)
            if include_neighbors:
                for h in graph_hits:
                    if h.type == "method":
                        h.callers, h.callees = _fetch_neighbors(db, h.fqn)
            return graph_hits
        _graph_fqns = [h.fqn for h in graph_hits]

    # Stage 1: parallel retrieval
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fts_future = ex.submit(_fts_search, db, query, fanout)
        sem_future = ex.submit(_semantic_search, query, context_path, graph, fanout)
        fts_fqns = fts_future.result()
        sem_fqns, sem_meta = sem_future.result()

    if not fts_fqns and not sem_fqns:
        return []

    # Stage 2: RRF fusion (3 sources when graph-first returned partial results)
    sources = {"fts": fts_fqns, "semantic": sem_fqns}
    if _graph_fqns:
        sources["graph"] = _graph_fqns
    fused = _rrf_fuse(sources)

    # Pull a widened pool before truncation — kind-boost can promote items
    # outside the initial top-N into the final list. Over-fetch, then trim
    # after both RRF and kind-boost have run.
    pool_size = max(n_results, rerank_pool) if rerank else n_results
    wide_pool = min(len(fused), max(pool_size * 2, pool_size + 20))
    ranked = sorted(fused.items(), key=lambda x: -x[1][0])[:wide_pool]

    # Stage 2b: query-shape kind-boost + structural PageRank boost. Both
    # need node types/PR from location lookup, so fetch locations for the
    # wide pool first, apply both boosts, then trim.
    # (hint was already computed in stage 0 above)
    top_fqns = [fqn for fqn, _ in ranked]
    locations = _fetch_locations_batch(db, top_fqns)
    ranked = _apply_kind_boost(ranked, hint, locations)
    ranked = _apply_pagerank_boost(ranked, locations)[:pool_size]

    # Re-fetch locations only for the final pool (may differ if boost promoted
    # items from outside the first lookup — but _fetch_locations_batch already
    # covered the wider pool, so filter instead of re-querying).
    top_fqns = [fqn for fqn, _ in ranked]
    locations = {f: locations[f] for f in top_fqns if f in locations}
    need_locations = include_snippets or rerank or include_neighbors

    # Stage 4: build hits (+ snippets if requested or needed for rerank)
    need_snippets = include_snippets or rerank
    hits: list[RetrievalHit] = []
    for fqn, (score, ranks) in ranked:
        meta = sem_meta.get(fqn, {})
        loc = locations.get(fqn, {})

        hit = RetrievalHit(
            fqn=fqn,
            type=loc.get("type") or meta.get("type") or "unknown",
            score=round(score, 4),
            file_path=loc.get("filePath", ""),
            line_start=loc.get("lineStart", 0),
            line_end=loc.get("lineEnd", 0),
            context_text=meta.get("text", ""),
            rank_fts=ranks.get("fts"),
            rank_semantic=ranks.get("semantic"),
        )

        if need_snippets and hit.file_path:
            hit.snippet = _read_snippet(hit.file_path, hit.line_start, hit.line_end, project_root)

        hits.append(hit)

    # Stage 5: optional cross-encoder rerank on the pool, then truncate
    # Skip if no document text (reranker needs content; snippet or context_text)
    has_text = any((h.snippet or h.context_text) for h in hits)
    if rerank and hits and has_text:
        from .reranker import get_default_reranker

        try:
            reranker = get_default_reranker()
            hits = reranker.rerank(query, hits, top_k=n_results)
        except Exception as e:
            logger.warning("Rerank failed, returning RRF order: %s", e)
            hits = hits[:n_results]
    else:
        if rerank and not has_text:
            logger.info("Skipping rerank: no snippets or context text available")
        hits = hits[:n_results]

    # Stage 5b: precision filter — drop hits where the cross-encoder score
    # indicates no real semantic match. Protects against gibberish queries
    # (and off-topic retrieval) returning plausible-looking noise at the top.
    # Only applies when rerank ran (rerank_score is set).
    min_score = float(
        os.environ.get("ONELENS_MIN_RERANK_SCORE", DEFAULT_MIN_RERANK_SCORE)
    )
    if hits and hits[0].rerank_score is not None:
        hits = [h for h in hits if h.rerank_score is None or h.rerank_score >= min_score]

    # Stage 6: neighbors (only for final top-K, not the whole pool)
    if include_neighbors:
        for hit in hits:
            if hit.type == "method":
                hit.callers, hit.callees = _fetch_neighbors(db, hit.fqn)

    return hits
