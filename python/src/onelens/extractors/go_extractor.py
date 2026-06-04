"""
go_extractor.py — extract Go backend structure into normalized OneLens JSON.

Primary cross-stack output is `Endpoint` nodes (so a Vue/TS `HttpCall` can link
to a Go handler). Recognizes the common router dialects:
- net/http:      `http.HandleFunc("/path", handler)` / `mux.HandleFunc(...)`
- gin/echo/chi:  `r.GET("/path", handler)` (GET/POST/PUT/DELETE/PATCH/...)

Also emits `Function`/`Method` nodes (top-level funcs and receiver methods) so the
graph has backend structure. This is a pragmatic text parser (no Go toolchain
dependency); production Go extraction will use GoLand's Go PSI in the IntelliJ
plugin, emitting this same JSON.

Usage:
    python -m onelens.extractors.go_extractor <src_dir> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LANG = "go"

_PACKAGE = re.compile(r"(?m)^\s*package\s+(\w+)")
# func [ (recv *Type) ] Name(
_FUNC = re.compile(r"(?m)^\s*func\s+(?:\(\s*\w+\s+\*?(\w+)\s*\)\s+)?(\w+)\s*\(")
# r.GET("/path", handler)  — gin/echo/chi style method routers
_ROUTE = re.compile(
    r"""\.\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(\s*"([^"]+)"\s*(?:,\s*([\w.]+))?""",
    re.IGNORECASE,
)
# http.HandleFunc("/path", handler) / mux.HandleFunc(...) — method unspecified
_HANDLEFUNC = re.compile(r"""\b\w+\.HandleFunc\s*\(\s*"([^"]+)"\s*(?:,\s*([\w.]+))?""")
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def extract_go_source(rel_path: str, text: str) -> dict:
    """Parse one .go file → {functions, endpoints} (pure, unit-testable)."""
    scrubbed = _LINE_COMMENT.sub("", text)
    pkg_m = _PACKAGE.search(scrubbed)
    pkg = pkg_m.group(1) if pkg_m else Path(rel_path).stem

    functions = []
    func_names: set[str] = set()
    for m in _FUNC.finditer(scrubbed):
        recv, name = m.group(1), m.group(2)
        container = f"{pkg}.{recv}" if recv else pkg
        fqn = f"{container}.{name}" if recv else f"{pkg}.{name}"
        func_names.add(name)
        functions.append({
            "fqn": fqn,
            "name": name,
            "classFqn": container if recv else "",
            "container": container,
            "simpleName": name,
            "filePath": rel_path,
            "lineStart": _line_of(scrubbed, m.start()),
            "lang": LANG,
        })

    endpoints = []
    seen: set[str] = set()

    def add_ep(method: str, path: str, handler: str | None):
        # net/http HandleFunc registers all methods; we record GET as the default
        # (cross-stack normalizes an unspecified method to GET as well).
        method = (method or "GET").upper()
        ep_id = f"{method}:{path}"
        if ep_id in seen:
            return
        seen.add(ep_id)
        handler_fqn = ""
        if handler:
            hname = handler.split(".")[-1]
            if hname in func_names:
                handler_fqn = f"{pkg}.{hname}"
        endpoints.append({
            "id": ep_id,
            "path": path,
            "httpMethod": method,
            "controllerFqn": "",
            "handlerMethodFqn": handler_fqn,
            "lang": LANG,
        })

    for m in _ROUTE.finditer(scrubbed):
        add_ep(m.group(1), m.group(2), m.group(3))
    for m in _HANDLEFUNC.finditer(scrubbed):
        add_ep("", m.group(1), m.group(2))   # net/http: method unspecified → GET

    return {"functions": functions, "endpoints": endpoints}


def extract_dir(root: str | Path) -> dict:
    root_path = Path(root).resolve()
    methods: list[dict] = []
    endpoints: list[dict] = []
    for f in sorted(root_path.rglob("*.go")):
        if f.name.endswith("_test.go"):
            continue
        rel = f.relative_to(root_path).as_posix()
        res = extract_go_source(rel, f.read_text(encoding="utf-8", errors="replace"))
        methods.extend(res["functions"])
        endpoints.extend(res["endpoints"])
    return {
        "header": {"lang": LANG, "kind": "full"},
        "methods": methods,
        "endpoints": endpoints,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m onelens.extractors.go_extractor <src_dir> <out.json>",
              file=sys.stderr)
        return 2
    data = extract_dir(argv[0])
    Path(argv[1]).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"go-extract: {len(data['methods'])} funcs, {len(data['endpoints'])} endpoints → {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
