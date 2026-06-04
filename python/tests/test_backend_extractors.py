"""Per-language backend extractors — endpoint detection + structure across
Go, Python, .NET/C#, and Kotlin/Android."""

from onelens.extractors.go_extractor import extract_go_source
from onelens.extractors.python_extractor import extract_python_source
from onelens.extractors.csharp_extractor import extract_csharp_source
from onelens.extractors.kotlin_extractor import extract_kotlin_source


def _eps(res):
    return {(e["httpMethod"], e["path"]) for e in res["endpoints"]}


# ── Go ─────────────────────────────────────────────────────────────────────────

GO_SRC = """
package handlers

func ListUsers(w http.ResponseWriter, r *http.Request) {}
func (s *Server) GetUser(w http.ResponseWriter, r *http.Request) {}

func register(r *gin.Engine) {
    r.GET("/users", ListUsers)
    r.POST("/users", createUser)
    r.DELETE("/users/:id", deleteUser)
    http.HandleFunc("/health", ListUsers)
}
"""


def test_go_router_and_handlefunc_endpoints():
    res = extract_go_source("handlers/users.go", GO_SRC)
    eps = _eps(res)
    assert ("GET", "/users") in eps
    assert ("POST", "/users") in eps
    assert ("DELETE", "/users/:id") in eps
    assert ("GET", "/health") in eps   # HandleFunc → method unspecified → GET

def test_go_funcs_and_methods():
    res = extract_go_source("handlers/users.go", GO_SRC)
    names = {f["name"] for f in res["functions"]}
    assert {"ListUsers", "GetUser", "register"} <= names
    # GetUser has a receiver → it's a method with a container.
    getuser = next(f for f in res["functions"] if f["name"] == "GetUser")
    assert getuser["classFqn"].endswith(".Server")

def test_go_handler_links_to_known_func():
    res = extract_go_source("handlers/users.go", GO_SRC)
    get_users = next(e for e in res["endpoints"] if e["path"] == "/users" and e["httpMethod"] == "GET")
    assert get_users["handlerMethodFqn"].endswith(".ListUsers")


# ── Python ─────────────────────────────────────────────────────────────────────

PY_FASTAPI = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/users")
async def list_users():
    return []

@router.patch("/users/{id}")
async def update_user(id: int):
    return {}

class Service:
    def __init__(self):
        pass
    def compute(self):
        return 1
'''

PY_FLASK = '''
@app.route("/login", methods=["POST"])
def login():
    return ""
'''


def test_python_fastapi_endpoints():
    res = extract_python_source("api/users.py", PY_FASTAPI)
    eps = _eps(res)
    assert ("GET", "/users") in eps
    assert ("PATCH", "/users/{id}") in eps

def test_python_flask_route_methods():
    res = extract_python_source("api/auth.py", PY_FLASK)
    assert ("POST", "/login") in _eps(res)

def test_python_classes_and_constructor():
    res = extract_python_source("api/users.py", PY_FASTAPI)
    assert any(c["name"] == "Service" for c in res["classes"])
    init = next(f for f in res["functions"] if f["name"] == "__init__")
    assert init["isConstructor"] is True


# ── C# / .NET ──────────────────────────────────────────────────────────────────

CS_CONTROLLER = '''
namespace Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    [HttpGet]
    public IActionResult List() { return Ok(); }

    [HttpGet("{id}")]
    public IActionResult Get(int id) { return Ok(); }

    [HttpPost]
    public IActionResult Create() { return Ok(); }
}
'''

CS_MINIMAL = '''
var app = builder.Build();
app.MapGet("/health", () => "ok");
app.MapDelete("/items/{id}", DeleteItem);
'''


def test_csharp_attribute_routing_combines_prefix():
    res = extract_csharp_source("Controllers/UsersController.cs", CS_CONTROLLER)
    eps = _eps(res)
    # [controller] → "Users"; combined with [Route("api/[controller]")].
    assert ("GET", "/api/Users") in eps
    assert ("GET", "/api/Users/{id}") in eps
    assert ("POST", "/api/Users") in eps

def test_csharp_handler_and_controller_fqn():
    res = extract_csharp_source("Controllers/UsersController.cs", CS_CONTROLLER)
    get_id = next(e for e in res["endpoints"] if e["path"] == "/api/Users/{id}")
    assert get_id["handlerMethodFqn"] == "Api.Controllers.UsersController.Get"

def test_csharp_minimal_apis():
    res = extract_csharp_source("Program.cs", CS_MINIMAL)
    eps = _eps(res)
    assert ("GET", "/health") in eps
    assert ("DELETE", "/items/{id}") in eps


# ── Kotlin / Android ───────────────────────────────────────────────────────────

KT_SPRING = '''
package com.example.web

@RestController
@RequestMapping("/api/users")
class UserController(val svc: UserService) {

    @GetMapping("/{id}")
    fun getUser(@PathVariable id: Long): User {
        return svc.find(id)
    }

    @PostMapping
    fun create(@RequestBody u: User): User {
        return svc.save(u)
    }
}
'''

KT_KTOR = '''
package com.example

fun Application.routes() {
    routing {
        get("/ping") { call.respondText("pong") }
        post("/echo") { call.respond(Unit) }
    }
}
'''


def test_kotlin_spring_combines_class_and_method_mapping():
    res = extract_kotlin_source("web/UserController.kt", KT_SPRING)
    eps = _eps(res)
    assert ("GET", "/api/users/{id}") in eps
    assert ("POST", "/api/users") in eps

def test_kotlin_spring_handler_fqn_and_lang():
    res = extract_kotlin_source("web/UserController.kt", KT_SPRING)
    get = next(e for e in res["endpoints"] if e["httpMethod"] == "GET")
    assert get["handlerMethodFqn"].endswith("#getUser")
    assert all(m["lang"] == "kotlin" for m in res["methods"])

def test_kotlin_inline_class_body_on_one_line():
    # Whole class + mapping + fun on a single physical line.
    src = ('package a\n'
           '@RequestMapping("/api/orders") class OrderController '
           '{ @GetMapping("/{id}") fun get(): Order { return s.f() } }')
    res = extract_kotlin_source("O.kt", src)
    assert ("GET", "/api/orders/{id}") in _eps(res)


def test_kotlin_ktor_dsl_routes():
    res = extract_kotlin_source("Routes.kt", KT_KTOR)
    eps = _eps(res)
    assert ("GET", "/ping") in eps
    assert ("POST", "/echo") in eps
