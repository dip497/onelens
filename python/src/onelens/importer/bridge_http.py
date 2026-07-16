"""Cross-wing HTTP bridge pass.

Runs after any import that touches Vue `ApiCall` or Spring `Endpoint` nodes. Emits a
`HITS` edge whenever a Vue ApiCall's normalized path matches a Spring Endpoint's
normalized path AND their HTTP methods agree.

Normalization (single canonical form for both sides):
  1. Strip query string and fragment.
  2. Strip a known axios `baseURL` prefix (when the project config exposes one).
  3. Lowercase.
  4. Collapse every path-param placeholder to the literal `{}`:
        Spring:   /users/{id}            ->  /users/{}
        Vue:      /users/${id}           ->  /users/{}
        Vue:      /users/{userId}        ->  /users/{}
  5. Trim leading/trailing slashes, re-prepend `/`.

The matcher only emits cross-wing edges (`a.wing <> e.wing`). Same-wing matches are
skipped — within a project that's almost always accidental regex overlap.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)

# Matches both `${foo}` (Vue template literal) and `{foo}` (Spring path variable).
_PARAM_PLACEHOLDER = re.compile(r"\$?\{[^}]+\}")


def normalize_path(path: str, base_url_prefix: str = "") -> str:
    """Canonicalize an HTTP path so Vue and Spring forms compare equal."""
    if not path:
        return "/"
    p = path
    if base_url_prefix and p.startswith(base_url_prefix):
        p = p[len(base_url_prefix):]
    # Strip query and fragment.
    p = p.split("?", 1)[0].split("#", 1)[0]
    # Lowercase for robustness against inconsistent casing.
    p = p.lower()
    # Collapse path params.
    p = _PARAM_PLACEHOLDER.sub("{}", p)
    # Normalize leading / trailing slashes.
    p = "/" + p.strip("/")
    # Collapse double slashes that sometimes appear in interpolated templates.
    while "//" in p[1:]:
        p = p[0] + p[1:].replace("//", "/")
    return p


def compute_hits(db, graph_name: str, base_url_prefix: str = "") -> dict:
    """Emit `HITS` edges. Returns a stats dict; never raises on empty graphs."""
    # 1. Precompute normalizedPath on every ApiCall and Endpoint node. Cheap — just a
    #    property write, idempotent via SET.
    _precompute(db, graph_name, base_url_prefix)

    # 2. Emit HITS edges. MERGE is idempotent so re-running the pass is safe.
    created = db.execute(
        """
        MATCH (a:ApiCall), (e:Endpoint)
        WHERE a.wing IS NOT NULL AND e.wing IS NOT NULL
          AND a.wing <> e.wing
          AND toLower(a.method) = toLower(e.httpMethod)
          AND a.normalizedPath = e.normalizedPath
        MERGE (a)-[:HITS]->(e)
        RETURN count(*) AS edges
        """
    )
    edges = _first_scalar(created, default=0)
    logger.info("bridge_http: emitted %s HITS edges across wings", edges)
    return {"hits_edges": int(edges or 0)}


def _precompute(db, graph_name: str, base_url_prefix: str) -> None:
    """Set ApiCall.normalizedPath and Endpoint.normalizedPath properties."""
    # ApiCall normalization is pure Cypher replace over known placeholder shapes.
    # We also replicate the regex locally so the Python code has a single definition.
    # FalkorDB lacks regex-based property compute, so we fall back to Python iteration.
    api_rows = db.execute(
        "MATCH (a:ApiCall) WHERE a.path IS NOT NULL RETURN id(a) AS id, a.path AS path"
    ) or []
    for row in _rows(api_rows):
        nid, p = row[0], row[1]
        np = normalize_path(p, base_url_prefix)
        db.execute(
            "MATCH (a:ApiCall) WHERE id(a) = $id SET a.normalizedPath = $np",
            {"id": nid, "np": np},
        )

    endpoint_rows = db.execute(
        "MATCH (e:Endpoint) WHERE e.path IS NOT NULL RETURN id(e) AS id, e.path AS path"
    ) or []
    for row in _rows(endpoint_rows):
        nid, p = row[0], row[1]
        np = normalize_path(p)  # Spring paths never carry a client baseURL
        db.execute(
            "MATCH (e:Endpoint) WHERE id(e) = $id SET e.normalizedPath = $np",
            {"id": nid, "np": np},
        )


def _rows(result) -> Iterable:
    """Flatten assorted backend result shapes (FalkorDB/Neo4j) into row tuples."""
    if result is None:
        return ()
    # Most of our GraphDB backends return objects with a `.result_set` iterable;
    # fall back to treating the result as already-iterable.
    rs = getattr(result, "result_set", None)
    return rs if rs is not None else result


def _first_scalar(result, default=None):
    for row in _rows(result):
        if not row:
            continue
        return row[0]
    return default
