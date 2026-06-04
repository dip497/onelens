"""
python_extractor.py — extract Python backend structure into normalized OneLens JSON.

Uses the stdlib `ast` module (100% accurate parse, no third-party dependency).
Primary cross-stack output is `Endpoint` nodes for the common web frameworks:
- FastAPI / APIRouter:  `@app.get("/path")`, `@router.post("/path")`, ...
- Flask:                `@app.route("/path", methods=["GET", "POST"])`
- Django:               `path("route/", view)` / `re_path(...)` in urls.py

Also emits `Function`/`Method` and `Class` nodes. Production Python extraction will
use PyCharm's Python PSI in the IntelliJ plugin, emitting this same JSON.

Usage:
    python -m onelens.extractors.python_extractor <src_dir> <out.json>
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

LANG = "python"
_HTTP_DECORATOR_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _module_name(rel_path: str) -> str:
    p = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    parts = [s for s in p.split("/") if s and s != "__init__"]
    return ".".join(parts)


def _str_arg(node) -> str | None:
    """Return a string-literal argument's value, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorator_endpoint(dec) -> list[tuple[str, str]]:
    """Map one decorator to [(method, path)] if it's a route decorator."""
    if not isinstance(dec, ast.Call) or not dec.args:
        return []
    path = _str_arg(dec.args[0])
    if path is None:
        return []
    func = dec.func
    # @app.get(...) / @router.post(...)  → attribute name is the method
    if isinstance(func, ast.Attribute):
        attr = func.attr.lower()
        if attr in _HTTP_DECORATOR_METHODS:
            return [(attr.upper(), path)]
        if attr == "route":  # Flask: methods kwarg, default GET
            methods = ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    got = [_str_arg(e) for e in kw.value.elts]
                    methods = [m.upper() for m in got if m]
            return [(m, path) for m in methods]
    return []


def extract_python_source(rel_path: str, text: str) -> dict:
    """Parse one .py file → {classes, functions, endpoints} (pure, unit-testable)."""
    module = _module_name(rel_path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"classes": [], "functions": [], "endpoints": []}

    classes: list[dict] = []
    functions: list[dict] = []
    endpoints: list[dict] = []
    seen_ep: set[str] = set()

    def add_endpoint(method: str, path: str, handler_fqn: str):
        ep_id = f"{method}:{path}"
        if ep_id in seen_ep:
            return
        seen_ep.add(ep_id)
        endpoints.append({
            "id": ep_id, "path": path, "httpMethod": method,
            "controllerFqn": "", "handlerMethodFqn": handler_fqn, "lang": LANG,
        })

    def visit_function(fn, container: str, container_fqn: str):
        name = fn.name
        fqn = f"{container_fqn}:{name}" if container_fqn else f"{module}:{name}"
        is_ctor = name == "__init__"
        functions.append({
            "fqn": fqn, "name": name, "classFqn": container,
            "container": container_fqn or module, "simpleName": name,
            "isConstructor": is_ctor,
            "filePath": rel_path, "lineStart": fn.lineno, "lang": LANG,
        })
        for dec in fn.decorator_list:
            for method, path in _decorator_endpoint(dec):
                add_endpoint(method, path, fqn)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            cfqn = f"{module}.{node.name}"
            classes.append({
                "fqn": cfqn, "name": node.name, "kind": "CLASS",
                "packageName": module, "filePath": rel_path,
                "lineStart": node.lineno, "lang": LANG,
            })
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit_function(item, cfqn, cfqn)

    # Module-level functions (not nested in a class).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit_function(node, "", module)
        # Django urls: path("route/", view) / re_path(r"^route$", view)
        elif isinstance(node, ast.Expr):
            pass
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("path", "re_path") and node.args:
            route = _str_arg(node.args[0])
            if route is not None:
                add_endpoint("GET", "/" + route.lstrip("^/").rstrip("$"), "")

    return {"classes": classes, "functions": functions, "endpoints": endpoints}


def extract_dir(root: str | Path) -> dict:
    root_path = Path(root).resolve()
    classes: list[dict] = []
    methods: list[dict] = []
    endpoints: list[dict] = []
    for f in sorted(root_path.rglob("*.py")):
        rel = f.relative_to(root_path).as_posix()
        res = extract_python_source(rel, f.read_text(encoding="utf-8", errors="replace"))
        classes.extend(res["classes"])
        methods.extend(res["functions"])
        endpoints.extend(res["endpoints"])
    return {
        "header": {"lang": LANG, "kind": "full"},
        "classes": classes,
        "methods": methods,
        "endpoints": endpoints,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m onelens.extractors.python_extractor <src_dir> <out.json>",
              file=sys.stderr)
        return 2
    data = extract_dir(argv[0])
    Path(argv[1]).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"py-extract: {len(data['classes'])} classes, {len(data['methods'])} funcs, "
          f"{len(data['endpoints'])} endpoints → {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
