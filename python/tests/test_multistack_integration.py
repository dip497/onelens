"""Capstone: one Vue frontend resolves to endpoints across EVERY backend stack.

Proves the cross-stack linker is backend-agnostic — a Vue `axios` call links to a
Go, Python (FastAPI), .NET (ASP.NET), or Kotlin (Spring) endpoint identically,
because `normalize_path` collapses each framework's param dialect (`:id`, `{id}`)
to one canonical form. No database required.
"""

from onelens.extractors.vue_extractor import extract_vue_source
from onelens.extractors.go_extractor import extract_go_source
from onelens.extractors.python_extractor import extract_python_source
from onelens.extractors.csharp_extractor import extract_csharp_source
from onelens.extractors.kotlin_extractor import extract_kotlin_source
from onelens.importer.cross_stack import link_http_calls


VUE = """
<script setup>
import axios from 'axios'
const get    = (id) => axios.get(`/api/users/${id}`)
const create = (u)  => axios.post('/api/users', u)
</script>
"""

GO = """
package h
func reg(r *gin.Engine) {
    r.GET("/api/users/:id", getUser)
    r.POST("/api/users", createUser)
}
"""

PY = '''
@router.get("/api/users/{id}")
def get_user(id: int): ...
@router.post("/api/users")
def create_user(): ...
'''

CS = '''
namespace Api;
[Route("api/[controller]")]
public class UsersController : ControllerBase {
    [HttpGet("{id}")] public IActionResult Get(int id) { return Ok(); }
    [HttpPost] public IActionResult Create() { return Ok(); }
}
'''

KT = '''
package com.x
@RequestMapping("/api/users")
class UserController {
    @GetMapping("/{id}") fun get(): User { return svc.f() }
    @PostMapping fun create(): User { return svc.s() }
}
'''


def _link_vue_to(endpoints):
    vf = extract_vue_source("v/Users.vue", VUE)
    res = link_http_calls(vf.http_calls, endpoints)
    by_call = {c["id"]: (c["httpMethod"], c["path"]) for c in vf.http_calls}
    return {by_call[e["src"]]: e["dst"] for e in res.edges}, res


def test_vue_to_go():
    eps = extract_go_source("h.go", GO)["endpoints"]
    linked, res = _link_vue_to(eps)
    assert linked[("GET", "/api/users/${id}")] == "GET:/api/users/:id"
    assert linked[("POST", "/api/users")] == "POST:/api/users"
    assert res.stats["unmatched"] == 0


def test_vue_to_python_fastapi():
    eps = extract_python_source("api.py", PY)["endpoints"]
    linked, res = _link_vue_to(eps)
    assert linked[("GET", "/api/users/${id}")] == "GET:/api/users/{id}"
    assert linked[("POST", "/api/users")] == "POST:/api/users"
    assert res.stats["unmatched"] == 0


def test_vue_to_csharp_aspnet():
    eps = extract_csharp_source("U.cs", CS)["endpoints"]
    linked, res = _link_vue_to(eps)
    # [controller] expands to PascalCase "Users" → /api/Users/{id}; matches the
    # frontend's lowercase /api/users/${id} because path comparison is case-folded.
    # The linked endpoint id retains its original (Pascal) case.
    assert linked[("GET", "/api/users/${id}")] == "GET:/api/Users/{id}"
    assert linked[("POST", "/api/users")] == "POST:/api/Users"
    assert res.stats["unmatched"] == 0


def test_vue_to_kotlin_spring():
    eps = extract_kotlin_source("U.kt", KT)["endpoints"]
    linked, res = _link_vue_to(eps)
    assert linked[("GET", "/api/users/${id}")] == "GET:/api/users/{id}"
    assert linked[("POST", "/api/users")] == "POST:/api/users"
    assert res.stats["unmatched"] == 0


def test_all_backends_expose_same_canonical_contract():
    """Every backend extractor yields the same canonical (method, path) set for the
    same two routes — the contract the frontend links against."""
    from onelens.importer.cross_stack import normalize_path

    def canon(eps):
        return {(e["httpMethod"], normalize_path(e["path"])) for e in eps}

    go = canon(extract_go_source("h.go", GO)["endpoints"])
    py = canon(extract_python_source("api.py", PY)["endpoints"])
    kt = canon(extract_kotlin_source("U.kt", KT)["endpoints"])
    expected = {("GET", "/api/users/{}"), ("POST", "/api/users")}
    assert expected <= go
    assert expected <= py
    assert expected <= kt
