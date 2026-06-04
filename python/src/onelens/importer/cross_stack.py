"""
cross_stack.py — link frontend HTTP call sites to backend REST endpoints.

This is the headline cross-stack capability: after a graph contains both backend
`Endpoint` nodes (Java/.NET/Go/Python handlers) and frontend `HttpCall` nodes
(Vue/TS `axios`/`fetch` sites), this pass connects them with `CALLS_ENDPOINT`
edges so a single trace crosses the stack — "which Vue components break if I
change `PATCH:/users/{id}`" and "trace this button to its DB write".

Design:
- `normalize_path` canonicalizes the many path-template dialects to one form so
  Spring `/users/{id}`, vue-router `/users/:id`, and a JS template literal
  `` `/users/${id}` `` all compare equal as `/users/{}`.
- `link_http_calls` is a PURE function over two node lists → match edges. It is
  exhaustively unit-tested without any database. Exact `(method, path)` matches
  score 1.0; base-path/suffix matches score lower and are flagged; unmatched
  calls are returned (never silently dropped — an unmatched call is a real
  finding: a dead endpoint, a typo'd path, or a proxy rewrite).
- `apply_cross_stack_links` is the thin DB wrapper: read nodes, call the pure
  function, write edges.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# A path segment that is a parameter placeholder in *some* framework dialect:
#   {id}            Spring / FastAPI / ASP.NET
#   :id             vue-router / Express
#   ${expr}         JS template literal (expr may contain dots/calls)
#   <id> / <int:id> Flask
# Any such segment canonicalizes to the single token "{}".
_PARAM_SEGMENT = re.compile(r"^(\{.*\}|:.+|\$\{.*\}|<.*>)$")
# A template-literal interpolation embedded *within* a segment, e.g. "user-${id}".
_TEMPLATE_INTERP = re.compile(r"\$\{[^}]*\}")
_SCHEME_HOST = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+")

CANON_PARAM = "{}"


def normalize_path(raw: str) -> str:
    """Canonicalize a URL path template for cross-dialect comparison.

    Strips scheme+host and query string, normalizes every parameter placeholder
    to ``{}``, and removes the trailing slash. Returns ``""`` for empty input.

    >>> normalize_path("https://api.x.com/users/{id}/posts?sort=asc")
    '/users/{}/posts'
    >>> normalize_path("/users/:id")
    '/users/{}'
    >>> normalize_path("`/users/${userId}`")
    '/users/{}'

    Path comparison is case-insensitive: URL routing is conventionally
    case-insensitive (and ASP.NET's `[controller]` token yields PascalCase while
    a frontend usually calls lowercase), so `/api/Users` and `/api/users` match.
    """
    if not raw:
        return ""
    p = raw.strip().strip("`").strip('"').strip("'")
    # Drop scheme://host if a full URL was captured.
    p = _SCHEME_HOST.sub("", p)
    # Drop query string and fragment.
    p = p.split("?", 1)[0].split("#", 1)[0]
    if not p:
        return ""
    # Collapse any in-segment template interpolation first (e.g. "u-${id}" → "u-{}"),
    # then normalize whole-segment placeholders.
    segments = []
    for seg in p.split("/"):
        if seg == "":
            continue
        if _PARAM_SEGMENT.match(seg):
            segments.append(CANON_PARAM)
        elif "${" in seg:
            segments.append(_TEMPLATE_INTERP.sub(CANON_PARAM, seg))
        else:
            segments.append(seg)
    canon = "/" + "/".join(segments) if segments else "/"
    return canon.lower()


def _method(raw: str) -> str:
    """Normalize an HTTP method; empty/unknown defaults to GET (axios/fetch default)."""
    m = (raw or "").strip().upper()
    return m if m else "GET"


@dataclass
class CrossStackResult:
    """Outcome of linking: edges to write + unmatched calls (a real finding)."""

    edges: list[dict] = field(default_factory=list)        # {src, dst, confidence, match}
    unmatched: list[dict] = field(default_factory=list)    # http-call dicts with no endpoint

    @property
    def stats(self) -> dict:
        exact = sum(1 for e in self.edges if e["match"] == "exact")
        fuzzy = len(self.edges) - exact
        return {
            "linked": len(self.edges),
            "exact": exact,
            "fuzzy": fuzzy,
            "unmatched": len(self.unmatched),
        }


def link_http_calls(http_calls: list[dict], endpoints: list[dict]) -> CrossStackResult:
    """Match frontend `http_calls` to backend `endpoints` by (method, path).

    Each input dict needs an identity plus a method/path:
      http_call : {"id": str, "httpMethod": str, "path": str}
      endpoint  : {"id": str, "httpMethod": str, "path": str}

    Matching tiers (first hit wins, highest confidence):
      1. exact  — identical (method, normalized path).            confidence 1.0
      2. suffix — endpoint path is a suffix of the call path (or
                  vice-versa) under the same method. Covers a base
                  prefix like `/api` or `/v1` on one side only.    confidence 0.6

    Unmatched calls are returned in `result.unmatched`, never dropped.
    """
    # Index endpoints by (method, canonical-path) and by method→[(canon, ep)] for suffix.
    exact_index: dict[tuple[str, str], dict] = {}
    by_method: dict[str, list[tuple[str, dict]]] = {}
    for ep in endpoints:
        canon = normalize_path(ep.get("path", ""))
        meth = _method(ep.get("httpMethod", ""))
        if not canon:
            continue
        exact_index.setdefault((meth, canon), ep)
        by_method.setdefault(meth, []).append((canon, ep))

    result = CrossStackResult()
    for call in http_calls:
        cid = call.get("id")
        if not cid:
            continue
        canon = normalize_path(call.get("path", ""))
        meth = _method(call.get("httpMethod", ""))
        if not canon:
            result.unmatched.append(call)
            continue

        ep = exact_index.get((meth, canon))
        if ep is not None:
            result.edges.append(
                {"src": cid, "dst": ep["id"], "confidence": 1.0, "match": "exact"}
            )
            continue

        # Suffix fallback: one side carries a base prefix the other omits.
        match = _best_suffix_match(canon, by_method.get(meth, []))
        if match is not None:
            result.edges.append(
                {"src": cid, "dst": match["id"], "confidence": 0.6, "match": "suffix"}
            )
        else:
            result.unmatched.append(call)

    return result


def _best_suffix_match(canon: str, candidates: list[tuple[str, dict]]) -> dict | None:
    """Return the endpoint whose path is the longest suffix-compatible match.

    "Suffix-compatible" = the shorter path is a trailing path-segment suffix of
    the longer one (so `/api/v1/users/{}` matches `/users/{}`). Longest overlap
    wins to avoid matching an over-broad `/{}` against everything.
    """
    best: dict | None = None
    best_len = -1
    call_segs = canon.strip("/").split("/")
    for ep_canon, ep in candidates:
        ep_segs = ep_canon.strip("/").split("/")
        short, long = sorted((call_segs, ep_segs), key=len)
        if not short:
            continue
        if long[-len(short):] == short:
            overlap = len(short)
            # Require at least one concrete (non-param) segment to avoid `/{}`
            # matching unrelated single-segment paths.
            if overlap > best_len and any(s != CANON_PARAM for s in short):
                best, best_len = ep, overlap
    return best


# ── DB wrapper ────────────────────────────────────────────────────────────────


def apply_cross_stack_links(db) -> dict:
    """Read HttpCall + Endpoint nodes, link them, write CALLS_ENDPOINT edges.

    Idempotent-ish: existing CALLS_ENDPOINT edges for a call are cleared first so
    re-running after a delta re-links cleanly. Returns stats (and logs unmatched
    count — unmatched calls are surfaced, not hidden).
    """
    calls = db.query(
        "MATCH (h:HttpCall) RETURN h.id AS id, h.httpMethod AS httpMethod, h.path AS path"
    )
    if not calls:
        return {"cross_stack": "no HttpCall nodes"}
    endpoints = db.query(
        "MATCH (e:Endpoint) RETURN e.id AS id, e.httpMethod AS httpMethod, e.path AS path"
    )
    if not endpoints:
        return {"cross_stack": "no Endpoint nodes"}

    result = link_http_calls(calls, endpoints)

    # Clear stale links, then write fresh ones.
    db.execute("MATCH (:HttpCall)-[r:CALLS_ENDPOINT]->(:Endpoint) DELETE r")
    BATCH = 500
    edges = result.edges
    for i in range(0, len(edges), BATCH):
        chunk = edges[i : i + BATCH]
        db.execute(
            """
            UNWIND $batch AS edge
            MATCH (h:HttpCall {id: edge.src})
            MATCH (e:Endpoint {id: edge.dst})
            CREATE (h)-[:CALLS_ENDPOINT {confidence: edge.confidence, match: edge.match}]->(e)
            """,
            {"batch": chunk},
        )

    stats = result.stats
    if stats["unmatched"]:
        logger.warning(
            "cross-stack: %d frontend calls matched no endpoint "
            "(dead endpoint, typo'd path, or proxy rewrite) — first few: %s",
            stats["unmatched"],
            [c.get("path") for c in result.unmatched[:5]],
        )
    return {"cross_stack": stats}
