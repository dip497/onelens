"""
kotlin_extractor.py — extract Kotlin/Android backend structure into normalized JSON.

Phase 1 reference extractor. Primary cross-stack output is `Endpoint` nodes:
- Spring (Kotlin):  class `@RequestMapping("/base")` + method `@GetMapping("/{id}")`
                    → `/base/{id}` (GetMapping/PostMapping/PutMapping/Delete/Patch).
- Ktor:             `get("/path") { ... }` route DSL (get/post/put/delete/patch).

Also emits `Class`/`Method` nodes (class/object/interface, fun). NOTE: Kotlin is a
JVM/IntelliJ-Platform language — production extraction will reuse the existing
IntelliJ plugin via Kotlin PSI + UAST (one collector for Java *and* Kotlin),
emitting this same JSON. This standalone parser is the reference + test oracle.

Usage:
    python -m onelens.extractors.kotlin_extractor <src_dir> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LANG = "kotlin"

_PACKAGE = re.compile(r"(?m)^\s*package\s+([\w.]+)")
_CLASS = re.compile(
    r"(?m)^\s*(?:@\w+(?:\([^)]*\))?\s+)*"  # leading annotations, with or without args
    r"(?:public|internal|open|final|abstract|sealed|data|annotation|\s)*"
    r"\b(?:class|object|interface)\s+(\w+)"
)
# `fun name(` — non-anchored: `fun` is a keyword, so this reliably marks a
# declaration even when an inline annotation precedes it (`@GetMapping(...) fun x(`).
_FUN = re.compile(r"\bfun\s+(\w+)\s*\(")
_REQUEST_MAPPING = re.compile(r'@RequestMapping\(\s*(?:value\s*=\s*)?(?:\[\s*)?"([^"]*)"')
_METHOD_MAPPING = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping(?:\(\s*(?:value\s*=\s*)?(?:\[\s*)?"([^"]*)")?'
)
# Ktor route DSL: bare `get("/path") {` not preceded by a dot/identifier char.
_KTOR = re.compile(r"""(?m)(?<![\w.])(get|post|put|delete|patch)\s*\(\s*"([^"]+)"\s*\)\s*\{""")
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _combine(base: str, leaf: str) -> str:
    # Spring semantics: a method mapping is ALWAYS relative to the class
    # @RequestMapping — a leading '/' on the method path does NOT make it
    # absolute (unlike ASP.NET attribute routing). So always concatenate.
    if base and leaf:
        full = base.rstrip("/") + "/" + leaf.lstrip("/")
    else:
        full = base or leaf
    if not full:
        return ""
    if not full.startswith("/"):
        full = "/" + full
    return re.sub(r"//+", "/", full)


def extract_kotlin_source(rel_path: str, text: str) -> dict:
    """Parse one .kt file → {classes, methods, endpoints} (pure, unit-testable)."""
    scrubbed = _LINE_COMMENT.sub("", text)
    lines = scrubbed.splitlines()
    pkg_m = _PACKAGE.search(scrubbed)
    pkg = pkg_m.group(1) if pkg_m else ""

    classes: list[dict] = []
    methods: list[dict] = []
    endpoints: list[dict] = []
    seen_ep: set[str] = set()

    cur_class = ""
    cur_class_fqn = ""
    class_route = ""
    pending_request_mapping = ""
    pending_http: tuple[str, str] | None = None

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
        rm = _REQUEST_MAPPING.search(line)
        if rm:
            pending_request_mapping = rm.group(1)

        cm = _CLASS.search(line)
        if cm:
            cur_class = cm.group(1)
            cur_class_fqn = f"{pkg}.{cur_class}" if pkg else cur_class
            class_route = pending_request_mapping
            pending_request_mapping = ""
            pending_http = None
            classes.append({
                "fqn": cur_class_fqn, "name": cur_class, "kind": "CLASS",
                "packageName": pkg, "filePath": rel_path,
                "lineStart": i + 1, "lang": LANG,
            })
            # NOTE: no `continue` — Kotlin allows the whole class body inline
            # (`class C { @GetMapping("/x") fun f() {...} }`), so the same line may
            # still carry a mapping + fun that must be parsed below.

        # A mapping annotation and its `fun` may share one line — set the pending
        # mapping but fall through so the same line's `fun` is still processed.
        mm = _METHOD_MAPPING.search(line)
        if mm:
            pending_http = (mm.group(1).upper(), mm.group(2) or "")

        fm = _FUN.search(line)
        if fm:
            fname = fm.group(1)
            container = cur_class_fqn or pkg
            ffqn = f"{cur_class_fqn}#{fname}" if cur_class_fqn else f"{pkg}#{fname}" if pkg else fname
            methods.append({
                "fqn": ffqn, "name": fname, "classFqn": cur_class_fqn,
                "container": container, "simpleName": fname,
                "filePath": rel_path, "lineStart": i + 1, "lang": LANG,
            })
            if pending_http is not None:
                method, leaf = pending_http
                add_endpoint(method, _combine(class_route, leaf), ffqn)
                pending_http = None

    # Ktor route DSL (handler is an inline lambda — no named method to link).
    for m in _KTOR.finditer(scrubbed):
        add_endpoint(m.group(1).upper(), m.group(2), "")

    return {"classes": classes, "methods": methods, "endpoints": endpoints}


def extract_dir(root: str | Path) -> dict:
    root_path = Path(root).resolve()
    classes: list[dict] = []
    methods: list[dict] = []
    endpoints: list[dict] = []
    for f in sorted(root_path.rglob("*.kt")):
        rel = f.relative_to(root_path).as_posix()
        res = extract_kotlin_source(rel, f.read_text(encoding="utf-8", errors="replace"))
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
        print("usage: python -m onelens.extractors.kotlin_extractor <src_dir> <out.json>",
              file=sys.stderr)
        return 2
    data = extract_dir(argv[0])
    Path(argv[1]).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"kotlin-extract: {len(data['classes'])} classes, {len(data['methods'])} funs, "
          f"{len(data['endpoints'])} endpoints → {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
