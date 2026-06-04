"""
csharp_extractor.py — extract .NET/C# backend structure into normalized OneLens JSON.

Primary cross-stack output is `Endpoint` nodes for ASP.NET Core:
- Attribute routing:  `[Route("api/[controller]")]` on a controller + `[HttpGet("{id}")]`
                      on actions → combined path `/api/users/{id}`.
- Minimal APIs:       `app.MapGet("/path", handler)` (MapGet/MapPost/...).

Also emits `Class`/`Method` nodes. This is a pragmatic line/regex parser (no .NET
toolchain). NOTE: .NET is the one stack that is NOT an IntelliJ-Platform language —
production C# extraction will be a standalone Roslyn (`Microsoft.CodeAnalysis`)
`dotnet tool` emitting this same JSON, not an IDE plugin.

Usage:
    python -m onelens.extractors.csharp_extractor <src_dir> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LANG = "csharp"

_NAMESPACE = re.compile(r"(?m)^\s*namespace\s+([\w.]+)")
_CLASS = re.compile(r"(?m)^\s*(?:public|internal|sealed|abstract|partial|\s)*\bclass\s+(\w+)")
_ROUTE_ATTR = re.compile(r"""\[Route\(\s*"([^"]*)"\s*\)\]""")
_HTTP_ATTR = re.compile(r"""\[Http(Get|Post|Put|Delete|Patch|Head|Options)(?:\(\s*"([^"]*)"\s*\))?\]""")
_METHOD_SIG = re.compile(
    r"""^\s*(?:\[[^\]]*\]\s*)*"""  # optional leading attributes on the same line
    r"""(?:public|private|protected|internal|static|async|virtual|override|\s)+"""
    r"""[\w<>\[\],.?]+\s+(\w+)\s*\("""
)
_MINIMAL_API = re.compile(r"""\bapp\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"\s*(?:,\s*([\w.]+))?""")
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _combine(base: str, leaf: str, controller: str, action: str) -> str:
    """Combine a class route prefix and a method route into a canonical path."""
    def expand(s: str) -> str:
        return (s.replace("[controller]", controller)
                 .replace("[action]", action))
    base, leaf = expand(base), expand(leaf)
    if leaf.startswith("/"):
        full = leaf
    elif leaf:
        full = (base.rstrip("/") + "/" + leaf.lstrip("/")) if base else leaf
    else:
        full = base
    if not full:
        return ""
    if not full.startswith("/"):
        full = "/" + full
    return re.sub(r"//+", "/", full)


def extract_csharp_source(rel_path: str, text: str) -> dict:
    """Parse one .cs file → {classes, methods, endpoints} (pure, unit-testable)."""
    scrubbed = _LINE_COMMENT.sub("", text)
    lines = scrubbed.splitlines()

    ns_m = _NAMESPACE.search(scrubbed)
    namespace = ns_m.group(1) if ns_m else ""

    classes: list[dict] = []
    methods: list[dict] = []
    endpoints: list[dict] = []
    seen_ep: set[str] = set()

    cur_class = ""
    cur_class_fqn = ""
    cur_controller = ""    # class name minus trailing "Controller"
    class_route = ""
    pending_route = ""     # a [Route(...)] seen, awaiting its class
    pending_http: tuple[str, str] | None = None  # (method, leaf) awaiting its action

    def add_endpoint(method: str, path: str, handler_fqn: str):
        if not path:
            return
        ep_id = f"{method}:{path}"
        if ep_id in seen_ep:
            return
        seen_ep.add(ep_id)
        endpoints.append({
            "id": ep_id, "path": path, "httpMethod": method,
            "controllerFqn": cur_class_fqn, "handlerMethodFqn": handler_fqn, "lang": LANG,
        })

    for i, line in enumerate(lines):
        rm = _ROUTE_ATTR.search(line)
        if rm:
            pending_route = rm.group(1)

        cm = _CLASS.search(line)
        if cm:
            cur_class = cm.group(1)
            cur_class_fqn = f"{namespace}.{cur_class}" if namespace else cur_class
            cur_controller = cur_class[:-10] if cur_class.endswith("Controller") else cur_class
            class_route = pending_route
            pending_route = ""
            pending_http = None
            classes.append({
                "fqn": cur_class_fqn, "name": cur_class, "kind": "CLASS",
                "packageName": namespace, "filePath": rel_path,
                "lineStart": i + 1, "lang": LANG,
            })
            continue

        # The Http attribute and its method may share a line — set the pending
        # mapping but fall through so the same line's method signature is parsed.
        hm = _HTTP_ATTR.search(line)
        if hm:
            pending_http = (hm.group(1).upper(), hm.group(2) or "")

        sm = _METHOD_SIG.search(line)
        if sm and cur_class:
            mname = sm.group(1)
            mfqn = f"{cur_class_fqn}.{mname}"
            methods.append({
                "fqn": mfqn, "name": mname, "classFqn": cur_class_fqn,
                "container": cur_class_fqn, "simpleName": mname,
                "isConstructor": mname == cur_class,
                "filePath": rel_path, "lineStart": i + 1, "lang": LANG,
            })
            if pending_http is not None:
                method, leaf = pending_http
                path = _combine(class_route, leaf, cur_controller, mname)
                add_endpoint(method, path, mfqn)
                pending_http = None

    # Minimal APIs (top-level, outside controller classes).
    for m in _MINIMAL_API.finditer(scrubbed):
        method, path, handler = m.group(1).upper(), m.group(2), m.group(3)
        add_endpoint(method, path, handler or "")

    return {"classes": classes, "methods": methods, "endpoints": endpoints}


def extract_dir(root: str | Path) -> dict:
    root_path = Path(root).resolve()
    classes: list[dict] = []
    methods: list[dict] = []
    endpoints: list[dict] = []
    for f in sorted(root_path.rglob("*.cs")):
        rel = f.relative_to(root_path).as_posix()
        res = extract_csharp_source(rel, f.read_text(encoding="utf-8", errors="replace"))
        classes.extend(res["classes"])
        methods.extend(res["methods"])
        endpoints.extend(res["endpoints"])
    return {
        "header": {"lang": LANG, "kind": "full"},
        "classes": classes,
        "methods": methods,
        "endpoints": endpoints,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m onelens.extractors.csharp_extractor <src_dir> <out.json>",
              file=sys.stderr)
        return 2
    data = extract_dir(argv[0])
    Path(argv[1]).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"csharp-extract: {len(data['classes'])} classes, {len(data['methods'])} methods, "
          f"{len(data['endpoints'])} endpoints → {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
