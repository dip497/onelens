"""
vue_extractor.py — extract Vue/TS frontend structure into normalized OneLens JSON.

Emits the node/edge shape `GraphLoader` understands:
- `Component` nodes  — one per `.vue` single-file component.
- `HttpCall` nodes   — one per outbound `axios`/`fetch`/`api.*` call site, carrying
  the `(httpMethod, path)` contract that `cross_stack.link_http_calls` matches to
  backend `Endpoint` nodes.
- `USES_COMPONENT` edges — from imports of other `.vue` files.
- `MAKES_CALL` edges — component → its HttpCall sites (carried implicitly via
  each HttpCall's `componentFqn`).

This is a pragmatic text parser (no Node/TS toolchain dependency) — enough to
prove the cross-stack path and to test it. Production-grade Vue extraction will
use WebStorm's JS/TS + Vue PSI in the IntelliJ plugin, emitting this same JSON.

Usage:
    python -m onelens.extractors.vue_extractor <src_dir> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

LANG = "vue"

# `<ident>.<method>(<url>...)` — axios.get / api.post / http.put / this.$http.delete
_METHOD_CALL = re.compile(
    r"""[\w$.]+\.(get|post|put|patch|delete)\s*\(\s*(['"`])([^'"`]*)\2""",
    re.IGNORECASE,
)
# `fetch(<url> [, { ... method: 'X' ... }])`
_FETCH = re.compile(r"""fetch\s*\(\s*(['"`])([^'"`]*)\1""")
_FETCH_METHOD = re.compile(r"""method\s*:\s*['"](\w+)['"]""", re.IGNORECASE)
# `axios({ method: 'post', url: '/x' })` (order-independent)
_AXIOS_CONFIG = re.compile(r"""axios\s*\(\s*\{(?P<body>[^}]*)\}""", re.DOTALL)
_CFG_URL = re.compile(r"""url\s*:\s*['"`]([^'"`]*)['"`]""")
_CFG_METHOD = re.compile(r"""method\s*:\s*['"](\w+)['"]""", re.IGNORECASE)
# `import Foo from './path/Foo.vue'`
_IMPORT_VUE = re.compile(r"""import\s+\w+\s+from\s+['"]([^'"]+\.vue)['"]""")
# Strip line comments so commented-out calls aren't extracted.
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _line_of(text: str, idx: int) -> int:
    """1-based line number of character offset `idx`."""
    return text.count("\n", 0, idx) + 1


@dataclass
class VueFile:
    """Extraction result for one .vue file."""

    component: dict
    http_calls: list[dict] = field(default_factory=list)
    import_targets: list[str] = field(default_factory=list)  # raw relative .vue import paths


def extract_vue_source(rel_path: str, text: str) -> VueFile:
    """Parse one .vue file's text into a Component + its HttpCalls + imports.

    Pure function (no filesystem) so it is directly unit-testable. `rel_path` is
    the component's identity (posix, repo-relative); `text` is the file contents.
    """
    fqn = PurePosixPath(rel_path).as_posix()
    name = PurePosixPath(rel_path).stem
    total_lines = text.count("\n") + 1
    component = {
        "fqn": fqn,
        "name": name,
        "filePath": fqn,
        "lineStart": 1,
        "lineEnd": total_lines,
        "lang": LANG,
    }

    scrubbed = _LINE_COMMENT.sub("", text)
    calls: list[dict] = []

    def add_call(method: str, path: str, idx: int):
        path = path.strip()
        if not path:
            return
        line = _line_of(scrubbed, idx)
        calls.append({
            "id": f"{fqn}#http:{line}:{method.upper()}:{path}",
            "componentFqn": fqn,
            "httpMethod": method.upper(),
            "path": path,
            "filePath": fqn,
            "lineStart": line,
            "lang": LANG,
        })

    for m in _METHOD_CALL.finditer(scrubbed):
        add_call(m.group(1), m.group(3), m.start())

    for m in _FETCH.finditer(scrubbed):
        # Look for a method in the (optional) options object right after the URL.
        tail = scrubbed[m.end():m.end() + 200]
        mm = _FETCH_METHOD.search(tail)
        method = mm.group(1) if mm else "GET"
        add_call(method, m.group(2), m.start())

    for m in _AXIOS_CONFIG.finditer(scrubbed):
        body = m.group("body")
        url_m = _CFG_URL.search(body)
        if url_m:
            meth_m = _CFG_METHOD.search(body)
            add_call(meth_m.group(1) if meth_m else "GET", url_m.group(1), m.start())

    imports = [m.group(1) for m in _IMPORT_VUE.finditer(text)]

    # De-dupe identical call sites (same id) that overlapping patterns may emit.
    seen: set[str] = set()
    unique_calls = []
    for c in calls:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique_calls.append(c)

    return VueFile(component=component, http_calls=unique_calls, import_targets=imports)


def extract_dir(root: str | Path) -> dict:
    """Walk a directory of `.vue` files → normalized OneLens JSON dict.

    Resolves each `.vue` import to a component fqn (repo-relative posix path) to
    build `USES_COMPONENT` edges between components that actually exist.
    """
    root_path = Path(root).resolve()
    files = sorted(root_path.rglob("*.vue"))
    components: list[dict] = []
    http_calls: list[dict] = []
    parsed: dict[str, VueFile] = {}

    for f in files:
        rel = f.relative_to(root_path).as_posix()
        vf = extract_vue_source(rel, f.read_text(encoding="utf-8", errors="replace"))
        parsed[rel] = vf
        components.append(vf.component)
        http_calls.extend(vf.http_calls)

    known = set(parsed.keys())
    uses_component: list[dict] = []
    for rel, vf in parsed.items():
        importer_dir = PurePosixPath(rel).parent
        for raw in vf.import_targets:
            # Resolve relative import against the importer's directory.
            target = (importer_dir / raw).as_posix()
            target = _normpath(target)
            if target in known:
                uses_component.append({"src": rel, "dst": target})

    return {
        "header": {"lang": LANG, "kind": "full"},
        "components": components,
        "httpCalls": http_calls,
        "componentEdges": uses_component,
    }


def _normpath(posix_path: str) -> str:
    """Resolve `.`/`..` segments in a posix path without touching the filesystem."""
    parts: list[str] = []
    for seg in posix_path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m onelens.extractors.vue_extractor <src_dir> <out.json>",
              file=sys.stderr)
        return 2
    src_dir, out_path = argv
    data = extract_dir(src_dir)
    Path(out_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(
        f"vue-extract: {len(data['components'])} components, "
        f"{len(data['httpCalls'])} http calls, "
        f"{len(data['componentEdges'])} component edges → {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
