"""Cross-stack linking — path normalization, matching tiers, unmatched handling,
and the apply_cross_stack_links DB orchestration (via a fake graph)."""

from onelens.importer.cross_stack import (
    normalize_path,
    link_http_calls,
    apply_cross_stack_links,
)


# ── normalize_path ─────────────────────────────────────────────────────────────

def test_normalize_dialects_converge():
    assert normalize_path("/users/{id}") == "/users/{}"
    assert normalize_path("/users/:id") == "/users/{}"
    assert normalize_path("`/users/${userId}`") == "/users/{}"
    assert normalize_path("/users/<int:id>") == "/users/{}"

def test_normalize_strips_host_and_query():
    assert normalize_path("https://api.x.com/users/{id}/posts?sort=asc") == "/users/{}/posts"
    assert normalize_path("http://localhost:8080/health") == "/health"

def test_normalize_trailing_slash_and_empty():
    assert normalize_path("/users/") == "/users"
    assert normalize_path("") == ""
    assert normalize_path("/") == "/"

def test_normalize_in_segment_interpolation():
    assert normalize_path("/files/file-${name}.json") == "/files/file-{}.json"


# ── link_http_calls ────────────────────────────────────────────────────────────

def _call(i, method, path):
    return {"id": f"c{i}", "httpMethod": method, "path": path}

def _ep(method, path):
    return {"id": f"{method}:{path}", "httpMethod": method, "path": path}


def test_exact_match():
    calls = [_call(1, "PATCH", "/users/${id}")]
    eps = [_ep("PATCH", "/users/{id}")]
    res = link_http_calls(calls, eps)
    assert res.stats == {"linked": 1, "exact": 1, "fuzzy": 0, "unmatched": 0}
    assert res.edges[0]["dst"] == "PATCH:/users/{id}"
    assert res.edges[0]["confidence"] == 1.0

def test_method_mismatch_is_unmatched():
    calls = [_call(1, "DELETE", "/users/1")]   # concrete id but DELETE
    eps = [_ep("GET", "/users/{id}")]
    res = link_http_calls(calls, eps)
    # "/users/1" normalizes to "/users/1" (concrete) which won't equal "/users/{}",
    # and method differs → unmatched.
    assert res.stats["unmatched"] == 1

def test_suffix_match_with_base_prefix():
    # Frontend hits the gateway path /api/v1/orders; backend declares /orders.
    calls = [_call(1, "GET", "/api/v1/orders/${oid}")]
    eps = [_ep("GET", "/orders/{id}")]
    res = link_http_calls(calls, eps)
    assert res.stats["exact"] == 0
    assert res.stats["fuzzy"] == 1
    assert res.edges[0]["match"] == "suffix"
    assert res.edges[0]["confidence"] == 0.6

def test_unmatched_is_surfaced_not_dropped():
    calls = [_call(1, "GET", "/nonexistent/path")]
    eps = [_ep("GET", "/orders/{id}")]
    res = link_http_calls(calls, eps)
    assert res.edges == []
    assert len(res.unmatched) == 1
    assert res.unmatched[0]["id"] == "c1"

def test_default_method_is_get():
    calls = [_call(1, "", "/health")]   # axios('/health') → GET
    eps = [_ep("GET", "/health")]
    res = link_http_calls(calls, eps)
    assert res.stats["exact"] == 1

def test_bare_param_path_does_not_overmatch():
    # A call to "/{}" alone must not greedily match a concrete endpoint.
    calls = [_call(1, "GET", "/${x}")]
    eps = [_ep("GET", "/orders/{id}")]
    res = link_http_calls(calls, eps)
    assert res.stats["unmatched"] == 1


# ── apply_cross_stack_links (DB orchestration via a fake graph) ────────────────

class _FakeDB:
    """Minimal GraphDB stand-in: canned reads for the two MATCH queries used by
    apply_cross_stack_links; records execute() calls for assertions."""

    def __init__(self, calls, endpoints):
        self._calls = calls
        self._endpoints = endpoints
        self.executed = []

    def query(self, cypher, params=None):
        if "HttpCall" in cypher and "Endpoint" not in cypher:
            return self._calls
        if "Endpoint" in cypher:
            return self._endpoints
        return []

    def execute(self, cypher, params=None):
        self.executed.append((cypher, params))


def test_apply_writes_edges_and_clears_stale():
    calls = [{"id": "c1", "httpMethod": "GET", "path": "/users/${id}"}]
    eps = [{"id": "GET:/users/{id}", "httpMethod": "GET", "path": "/users/{id}"}]
    db = _FakeDB(calls, eps)

    stats = apply_cross_stack_links(db)

    assert stats["cross_stack"]["linked"] == 1
    # First execute clears stale edges; a later execute writes the new batch.
    assert any("DELETE r" in c for c, _ in db.executed)
    insert = [(c, p) for c, p in db.executed if "CREATE (h)" in c]
    assert insert, "expected a CALLS_ENDPOINT insert"
    batch = insert[0][1]["batch"]
    assert batch[0]["src"] == "c1"
    assert batch[0]["dst"] == "GET:/users/{id}"

def test_apply_noops_without_nodes():
    assert apply_cross_stack_links(_FakeDB([], []))["cross_stack"] == "no HttpCall nodes"
