"""End-to-end cross-stack data path WITHOUT a database:

    .vue source ──(vue_extractor)──► HttpCall nodes
                                          │
                                          ▼ (cross_stack.link_http_calls)
    Java/Spring endpoints ───────────► CALLS_ENDPOINT edges

This proves the headline capability — a Vue component's call resolves to the
backend endpoint that serves it — using only the pure, infra-free core. The
graph storage/query layer is a thin wrapper tested separately (test_cross_stack).
"""

from onelens.extractors.vue_extractor import extract_vue_source
from onelens.importer.cross_stack import link_http_calls


# A Vue component that talks to three backend routes.
VUE_SRC = """
<script setup>
import axios from 'axios'
const list   = () => axios.get('/api/users')
const update = (id, b) => axios.patch(`/api/users/${id}`, b)
const remove = (id) => axios.delete(`/api/users/${id}`)
const oops   = () => axios.get('/api/typo-not-on-backend')
</script>
"""

# Backend endpoints as the loader would have them from spring.endpoints
# (id = "<METHOD>:<path>", path uses Spring's {id} template). The gateway adds a
# /api prefix the backend declares without — exercising the suffix tier.
SPRING_ENDPOINTS = [
    {"id": "GET:/users",        "httpMethod": "GET",    "path": "/users"},
    {"id": "PATCH:/users/{id}", "httpMethod": "PATCH",  "path": "/users/{id}"},
    {"id": "DELETE:/users/{id}","httpMethod": "DELETE", "path": "/users/{id}"},
]


def test_vue_calls_resolve_to_spring_endpoints():
    vf = extract_vue_source("views/UserAdmin.vue", VUE_SRC)
    result = link_http_calls(vf.http_calls, SPRING_ENDPOINTS)

    # Map each linked frontend call to the backend endpoint id it reached.
    call_by_id = {c["id"]: c for c in vf.http_calls}
    linked = {
        (call_by_id[e["src"]]["httpMethod"], call_by_id[e["src"]]["path"]): e["dst"]
        for e in result.edges
    }

    assert linked[("GET", "/api/users")] == "GET:/users"
    assert linked[("PATCH", "/api/users/${id}")] == "PATCH:/users/{id}"
    assert linked[("DELETE", "/api/users/${id}")] == "DELETE:/users/{id}"

    # All three matched via the suffix tier (frontend carries the /api prefix).
    assert result.stats["fuzzy"] == 3
    assert result.stats["exact"] == 0

    # The typo'd call is surfaced as unmatched — a real finding, never dropped.
    assert result.stats["unmatched"] == 1
    assert result.unmatched[0]["path"] == "/api/typo-not-on-backend"


def test_exact_match_when_no_gateway_prefix():
    """Same backend mounted without the /api prefix → exact (confidence 1.0)."""
    eps = [{"id": "GET:/api/users", "httpMethod": "GET", "path": "/api/users"}]
    vf = extract_vue_source("v.vue", "<script>axios.get('/api/users')</script>")
    result = link_http_calls(vf.http_calls, eps)
    assert result.stats["exact"] == 1
    assert result.edges[0]["confidence"] == 1.0
