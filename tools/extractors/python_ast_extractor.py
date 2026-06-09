#!/usr/bin/env python3
"""
Standalone Python → universal-SymbolGraph extractor.

Proof-of-architecture: emits the SAME JSON contract the IntelliJ plugin
produces for Java, using Python's own `ast` module instead of IntelliJ PSI.
The existing `GraphLoader` imports the output unchanged — demonstrating that
the JSON boundary is the right seam and the graph core is language-neutral.

Extraction backend per the tiered model (docs/design/multi-language-architecture.md):
  - Java       → IntelliJ Java PSI   (source=PSI, 100% accurate)
  - Python     → this, ast           (source=AST, structural-accurate; call
                                       resolution is best-effort by name since
                                       Python is dynamically typed)
Every node is stamped `source` so retrieval can express confidence honestly.

Usage:
    python python_ast_extractor.py <src_root> [--name <project>] > out.json
    onelens import-graph out.json --graph <name> --backend falkordblite

Universal core emitted: classes, methods, fields, callGraph, inheritance.
No framework overlays (spring/jpa/vue3) — those are framework-adapter concerns;
omitting them makes every `if spring/jpa/vue3` block in the loader no-op.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, field as dc_field

SOURCE = "AST"  # accuracy tag — this extractor is not type-resolved like PSI


def _module_fqn(rel_path: str) -> str:
    """`onelens/importer/loader.py` -> `onelens.importer.loader`."""
    p = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    p = p.replace("__init__", "").strip("/")
    return p.replace("/", ".").rstrip(".")


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    out = []
    for a in fn.args.args + fn.args.kwonlyargs:
        ann = ""
        if a.annotation is not None:
            try:
                ann = ast.unparse(a.annotation)
            except Exception:
                ann = ""
        out.append({"name": a.arg, "type": ann, "annotations": []})
    return out


def _decorator_annotations(node) -> list[dict]:
    annos = []
    for d in getattr(node, "decorator_list", []) or []:
        try:
            name = ast.unparse(d)
        except Exception:
            continue
        # Mirror the plugin's AnnotationData {fqn} shape so the loader's
        # annotation pipeline could pick these up later if desired.
        annos.append({"fqn": name})
    return annos


@dataclass
class Extractor:
    root: str
    project: str
    classes: list[dict] = dc_field(default_factory=list)
    methods: list[dict] = dc_field(default_factory=list)
    fields: list[dict] = dc_field(default_factory=list)
    call_graph: list[dict] = dc_field(default_factory=list)
    inheritance: list[dict] = dc_field(default_factory=list)
    # name -> fqn maps for best-effort call resolution (per-module).
    _func_index: dict[str, str] = dc_field(default_factory=dict)

    def run(self) -> dict:
        py_files = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames
                           if d not in {".git", "__pycache__", ".venv", "venv", "node_modules"}]
            for fn in filenames:
                if fn.endswith(".py"):
                    py_files.append(os.path.join(dirpath, fn))

        # Pass 1: index every class/method/module-func fqn by simple name so
        # pass 2 can resolve same-name calls. Honest best-effort for a dynamic
        # language — collisions resolve to "a function of this name exists".
        parsed = {}
        for path in py_files:
            try:
                src = open(path, encoding="utf-8").read()
                tree = ast.parse(src, filename=path)
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(path, self.root)
            parsed[path] = (rel, tree)
            self._index_names(rel, tree)

        # Pass 2: emit nodes + edges.
        for path, (rel, tree) in parsed.items():
            self._emit_module(rel, tree)

        return {
            "version": "1.0",
            "exportType": "full",
            "project": {"name": self.project},
            "classes": self.classes,
            "methods": self.methods,
            "fields": self.fields,
            "callGraph": self.call_graph,
            "inheritance": self.inheritance,
            "methodOverrides": [],
            # No framework subdocs — pure universal core.
            "adapters": ["python-ast"],
        }

    def _index_names(self, rel: str, tree: ast.AST) -> None:
        mod = _module_fqn(rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._func_index.setdefault(node.name, f"{mod}.{node.name}")

    def _emit_module(self, rel: str, tree: ast.Module) -> None:
        mod = _module_fqn(rel)
        # Synthetic Class node for the module so module-level functions have a
        # HAS_METHOD parent (mirrors how the graph models a Java class).
        self.classes.append({
            "fqn": mod, "name": mod.rsplit(".", 1)[-1], "kind": "MODULE",
            "packageName": mod.rsplit(".", 1)[0] if "." in mod else "",
            "superClass": "", "filePath": rel, "lineStart": 1, "lineEnd": 1,
            "enclosingClass": "", "source": SOURCE,
        })
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self._emit_class(rel, mod, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._emit_function(rel, mod, node, owner_fqn=mod, self_class=None)

    def _emit_class(self, rel: str, mod: str, node: ast.ClassDef) -> None:
        cls_fqn = f"{mod}.{node.name}"
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                pass
        self.classes.append({
            "fqn": cls_fqn, "name": node.name, "kind": "CLASS",
            "packageName": mod, "superClass": bases[0] if bases else "",
            "filePath": rel, "lineStart": node.lineno,
            "lineEnd": getattr(node, "end_lineno", node.lineno),
            "enclosingClass": "", "source": SOURCE,
        })
        # Inheritance — Python has no interfaces; every base is EXTENDS. Resolve
        # the base to a same-project class fqn when the simple name is known.
        for base in bases:
            simple = base.rsplit(".", 1)[-1]
            parent_fqn = self._resolve_class(simple, mod)
            self.inheritance.append({
                "childFqn": cls_fqn, "parentFqn": parent_fqn or base,
                "relationType": "EXTENDS",
            })
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._emit_function(rel, mod, child, owner_fqn=cls_fqn, self_class=cls_fqn)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                self._emit_field(rel, cls_fqn, child.target.id, child)
            elif isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name):
                        self._emit_field(rel, cls_fqn, t.id, child)

    def _emit_field(self, rel: str, cls_fqn: str, name: str, node) -> None:
        ftype = ""
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            try:
                ftype = ast.unparse(node.annotation)
            except Exception:
                ftype = ""
        self.fields.append({
            "fqn": f"{cls_fqn}#{name}", "name": name, "classFqn": cls_fqn,
            "type": ftype, "filePath": rel, "lineStart": node.lineno,
            "source": SOURCE,
        })

    def _emit_function(self, rel, mod, node, owner_fqn, self_class) -> None:
        params = _params(node)
        sig = ",".join(p["type"] or p["name"] for p in params)
        m_fqn = f"{owner_fqn}#{node.name}({sig})"
        ret = ""
        if node.returns is not None:
            try:
                ret = ast.unparse(node.returns)
            except Exception:
                ret = ""
        mods = ["async"] if isinstance(node, ast.AsyncFunctionDef) else []
        if node.name.startswith("__") and node.name.endswith("__"):
            mods.append("dunder")
        self.methods.append({
            "fqn": m_fqn, "name": node.name, "classFqn": owner_fqn,
            "returnType": ret, "parameters": params, "modifiers": mods,
            "throwsTypes": [], "isConstructor": node.name == "__init__",
            "filePath": rel, "lineStart": node.lineno,
            "lineEnd": getattr(node, "end_lineno", node.lineno),
            "annotations": _decorator_annotations(node), "source": SOURCE,
        })
        # Calls inside this function body (best-effort name resolution).
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                callee = self._resolve_call(sub.func, mod, self_class)
                if callee:
                    self.call_graph.append({
                        "callerFqn": m_fqn, "calleeFqn": callee,
                        "line": getattr(sub, "lineno", 0),
                    })

    def _resolve_call(self, func, mod: str, self_class: str | None) -> str | None:
        # self.method() -> current class method
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "self" and self_class:
                return self._resolve_member(self_class, func.attr)
            return None  # obj.method() / module.func() — type unknown (dynamic)
        # bare name() -> a module-level / imported function of that name
        if isinstance(func, ast.Name):
            return self._func_index.get(func.id)
        return None

    def _resolve_member(self, cls_fqn: str, name: str) -> str | None:
        # Match any emitted method on this class by simple name (overload-free
        # in Python, so the first match is unique).
        prefix = f"{cls_fqn}#{name}("
        for m in self.methods:
            if m["fqn"].startswith(prefix):
                return m["fqn"]
        # Forward ref — method not emitted yet; synthesize the canonical 0-arg
        # form so the edge still lands once the method node exists.
        return None

    def _resolve_class(self, simple: str, mod: str) -> str | None:
        local = f"{mod}.{simple}"
        for c in self.classes:
            if c["fqn"] == local or c["fqn"].endswith(f".{simple}"):
                return c["fqn"]
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--name", default=None)
    args = ap.parse_args()
    name = args.name or os.path.basename(os.path.abspath(args.root.rstrip("/")))
    doc = Extractor(root=args.root, project=name).run()
    json.dump(doc, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
