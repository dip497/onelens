"""Python -> OneLens graph JSON, with calls resolved by Jedi.

Declarations come from the stdlib `ast`; every call, base class and import is
resolved with Jedi (the engine behind python-lsp-server), which follows imports
and infers the type of `obj` in `obj.method()`. The output is the same JSON the
IntelliJ plugin writes for Java, and `onelens import-graph` reads it unchanged.

Python -> graph:

    module                 -> Class {kind: MODULE}   (owner of its top-level functions)
    class                  -> Class {kind: CLASS}
    class attribute        -> Field
    def                    -> Method
    call                   -> CALLS to the definition Jedi resolves; `Cls()` lands on
                              `Cls.__init__` when the project defines one
    base class             -> EXTENDS
    same-named method      -> OVERRIDES the nearest base-class method

Python is dynamic, so a call Jedi cannot infer is left out rather than guessed;
every node is tagged `source: LSP`.

Usage:
    python python_extractor.py <src_root> [--name <graph>] [--source-root Unix/src ...] > out.json

Source roots are where imports start (`from foundation.constants import X` means
the folder holding `foundation/`). They are found from the imports themselves
unless given.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import Counter

import jedi

SOURCE = "LSP"
SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "build", "dist", ".tox"}


def python_files(root: str) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        found += [os.path.join(dirpath, f) for f in sorted(filenames) if f.endswith(".py")]
    return found


def imported_top_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def find_source_roots(root: str, trees: dict[str, ast.AST]) -> list[str]:
    """Folders that hold a package or module the code imports by absolute name."""
    wanted = set()
    for tree in trees.values():
        wanted |= imported_top_names(tree)
    roots = {root}
    for path in trees:
        parent = os.path.dirname(os.path.dirname(path))
        pkg = os.path.basename(os.path.dirname(path))
        if pkg in wanted:
            roots.add(parent)
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in wanted:
            roots.add(os.path.dirname(path))
    return sorted(roots, key=len, reverse=True)


class Extractor:
    def __init__(self, root: str, name: str, source_roots: list[str]):
        self.root = os.path.abspath(root)
        self.name = name
        self.files = python_files(self.root)
        self.trees: dict[str, ast.Module] = {}
        self.code: dict[str, str] = {}
        for path in self.files:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    self.code[path] = f.read()
                self.trees[path] = ast.parse(self.code[path], filename=path)
            except SyntaxError as e:
                print(f"python-extractor: skipped {self.rel(path)}: {e.msg} line {e.lineno}", file=sys.stderr)
        if source_roots:
            self.source_roots = sorted((os.path.join(self.root, r) for r in source_roots), key=len, reverse=True)
        else:
            self.source_roots = find_source_roots(self.root, self.trees)
        self.project = jedi.Project(self.root, added_sys_path=self.source_roots, smart_sys_path=False)
        self.classes: list[dict] = []
        self.methods: list[dict] = []
        self.method_fqns: set[str] = set()
        self.fields: list[dict] = []
        self.calls: list[dict] = []
        self.inheritance: list[dict] = []
        self.overrides: list[dict] = []
        # (abs path, line, name) of a def / class -> its graph FQN
        self.def_at: dict[tuple[str, int, str], str] = {}
        self.class_methods: dict[str, dict[str, str]] = {}  # class fqn -> method name -> fqn
        self.class_bases: dict[str, list[str]] = {}
        self.stats = Counter()

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    def module_name(self, path: str) -> str:
        for r in self.source_roots:
            if path.startswith(r.rstrip(os.sep) + os.sep) or os.path.dirname(path) == r:
                relp = os.path.relpath(path, r)
                break
        else:
            relp = os.path.relpath(path, self.root)
        mod = os.path.splitext(relp)[0].replace(os.sep, ".")
        return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod

    # ---- pass 1: declarations ------------------------------------------------

    def declare(self) -> None:
        for path, tree in self.trees.items():
            mod = self.module_name(path)
            end = tree.body[-1].end_lineno if tree.body else 1
            self.classes.append(self.class_node(mod, mod.rsplit(".", 1)[-1], "MODULE", mod, path, 1, end))
            self.declare_body(path, mod, mod, tree.body, in_class=False)

    def declare_body(self, path, mod, owner, body, in_class):
        for node in body:
            if isinstance(node, ast.ClassDef):
                fqn = f"{owner}.{node.name}" if in_class else f"{mod}.{node.name}"
                self.classes.append(self.class_node(fqn, node.name, "CLASS", mod, path, node.lineno, node.end_lineno,
                                                    enclosing=owner if in_class else ""))
                self.def_at[(path, node.lineno, node.name)] = fqn
                self.class_methods[fqn] = {}
                self.declare_body(path, mod, fqn, node.body, in_class=True)
                for stmt in node.body:
                    self.declare_fields(path, fqn, stmt)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.declare_function(path, owner, node, in_class)

    def declare_fields(self, path, cls_fqn, stmt):
        targets = []
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            targets = [stmt.target.id]
        elif isinstance(stmt, ast.Assign):
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        for t in targets:
            self.fields.append({"fqn": f"{cls_fqn}#{t}", "name": t, "classFqn": cls_fqn,
                                "type": ast.unparse(stmt.annotation) if isinstance(stmt, ast.AnnAssign) else "",
                                "filePath": self.rel(path), "lineStart": stmt.lineno, "source": SOURCE})

    def declare_function(self, path, owner, node, in_class):
        params = []
        for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            params.append({"name": a.arg, "type": ast.unparse(a.annotation) if a.annotation else "", "annotations": []})
        if in_class and params and params[0]["name"] in ("self", "cls"):
            params = params[1:]
        fqn = f"{owner}#{node.name}({','.join(p['name'] for p in params)})"
        if fqn in self.method_fqns:  # redefined later in the same scope: keep the first
            self.def_at[(path, node.lineno, node.name)] = fqn
            return
        self.method_fqns.add(fqn)
        decorators = [ast.unparse(d) for d in node.decorator_list]
        mods = ["private" if node.name.startswith("_") and not node.name.startswith("__") else "public"]
        if not in_class or "staticmethod" in decorators:
            mods.append("static")
        if "abstractmethod" in decorators or "abc.abstractmethod" in decorators:
            mods.append("abstract")
        lines = self.code[path].splitlines()
        start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        self.methods.append({
            "fqn": fqn, "name": node.name, "classFqn": owner,
            "returnType": ast.unparse(node.returns) if node.returns else "",
            "parameters": params, "modifiers": mods, "throwsTypes": [], "isConstructor": node.name == "__init__",
            "filePath": self.rel(path), "lineStart": start, "lineEnd": node.end_lineno,
            "annotations": [{"fqn": d, "name": d.rsplit(".", 1)[-1]} for d in decorators],
            "body": "\n".join(lines[start - 1: node.end_lineno]), "javadoc": ast.get_docstring(node) or "",
            "source": SOURCE,
        })
        self.def_at[(path, node.lineno, node.name)] = fqn
        if in_class:
            self.class_methods.setdefault(owner, {})[node.name] = fqn

    def class_node(self, fqn, name, kind, pkg, path, start, end, enclosing=""):
        return {"fqn": fqn, "name": name, "kind": kind, "packageName": pkg, "superClass": "",
                "enclosingClass": enclosing, "filePath": self.rel(path), "lineStart": start,
                "lineEnd": end, "source": SOURCE}

    # ---- pass 2: resolution --------------------------------------------------

    def resolve(self) -> None:
        for path, tree in self.trees.items():
            script = jedi.Script(self.code[path], path=path, project=self.project)
            self.resolve_scope(path, script, tree.body, owner=None, cls=None)

    def resolve_scope(self, path, script, body, owner, cls):
        for node in body:
            if isinstance(node, ast.ClassDef):
                cls_fqn = self.def_at.get((path, node.lineno, node.name))
                for base in node.bases:
                    parent = self.target_of(script, base)
                    if parent and cls_fqn:
                        self.inheritance.append({"childFqn": cls_fqn, "parentFqn": parent, "relationType": "EXTENDS"})
                        self.class_bases.setdefault(cls_fqn, []).append(parent)
                self.resolve_scope(path, script, node.body, owner=None, cls=cls_fqn)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_fqn = self.def_at.get((path, node.lineno, node.name))
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        self.stats["calls"] += 1
                        callee = self.target_of(script, sub.func, call=True)
                        if callee and fn_fqn:
                            self.calls.append({"callerFqn": fn_fqn, "calleeFqn": callee, "line": sub.lineno})
                        else:
                            self.stats["unresolved"] += 1

    def target_of(self, script, expr, call=False) -> str | None:
        """FQN of what `expr` names: the identifier at its end (`a.b.c` -> `c`)."""
        node = expr.attr if isinstance(expr, ast.Attribute) else (expr.id if isinstance(expr, ast.Name) else None)
        if node is None:
            return None
        line, col = expr.end_lineno, expr.end_col_offset - 1
        try:
            defs = script.goto(line, col, follow_imports=True, follow_builtin_imports=False)
            if not defs:
                defs = script.infer(line, col)
        except Exception:
            return None
        for d in defs:
            fqn = self.fqn_of(d, call)
            if fqn:
                return fqn
        return None

    def fqn_of(self, d, call) -> str | None:
        if d.module_path and d.line:
            key = (os.path.abspath(str(d.module_path)), d.line, d.name)
            fqn = self.def_at.get(key)
            if fqn:
                if d.type == "class" and call:
                    init = self.class_methods.get(fqn, {}).get("__init__")
                    return init or None  # instantiating a class without its own __init__: no method to call
                return fqn
        # Outside the project (stdlib / third party): a stub the importer marks external.
        full = d.full_name
        if not full or d.type not in ("function", "class"):
            return None
        if d.type == "class":
            return full if not call else f"{full}#__init__()"
        owner, _, name = full.rpartition(".")
        return f"{owner}#{name}()" if owner else None

    def link_overrides(self) -> None:
        for cls, methods in self.class_methods.items():
            for name, fqn in methods.items():
                if name.startswith("__") and name != "__init__":
                    continue
                parent = self.inherited(cls, name, seen=set())
                if parent and parent != fqn:
                    self.overrides.append({"methodFqn": fqn, "overridesFqn": parent})

    def inherited(self, cls, name, seen):
        for base in self.class_bases.get(cls, []):
            if base in seen:
                continue
            seen.add(base)
            if name in self.class_methods.get(base, {}):
                return self.class_methods[base][name]
            found = self.inherited(base, name, seen)
            if found:
                return found
        return None

    def run(self) -> dict:
        self.declare()
        self.resolve()
        self.link_overrides()
        known = {m["fqn"] for m in self.methods}
        to_project = sum(c["calleeFqn"] in known for c in self.calls)
        print(f"python-extractor: {len(self.trees)} files, source roots {[self.rel(r) or '.' for r in self.source_roots]}, "
              f"{len(self.classes)} classes, {len(self.methods)} methods, {self.stats['calls']} calls: "
              f"{len(self.calls)} resolved ({to_project} to project code), {self.stats['unresolved']} unresolved",
              file=sys.stderr)
        return {
            "version": "1.0", "exportType": "full", "project": {"name": self.name},
            "classes": self.classes, "methods": self.methods, "fields": self.fields,
            "callGraph": self.calls, "inheritance": self.inheritance,
            "methodOverrides": self.overrides, "adapters": ["python-jedi"],
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root")
    ap.add_argument("--name")
    ap.add_argument("--source-root", action="append", default=[],
                    help="folder (relative to root) where imports start; repeatable")
    args = ap.parse_args()
    ex = Extractor(args.root, args.name or os.path.basename(os.path.abspath(args.root)), args.source_root)
    json.dump(ex.run(), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
