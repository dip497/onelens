"""Merge several OneLens export JSONs into one graph's export.

One component can span languages (an agent in Go + Python + C#, an edge server in
Go + Java + C#). Each extractor writes its own export; this merges them so the
component is imported, ranked and searched as ONE graph.

  python merge_exports.py --name <graph> out.json part1.json part2.json ...

Rules, applied recursively:
- list of objects: concatenated; an object whose `fqn` (else `id`) was already
  seen is dropped, so the first part wins; objects without either are dropped
  only when identical (the same call edge from two parts).
- dict: merged key by key. `stats` counters are summed.
- anything else: the first non-empty value wins.
- `project.name` is set to --name; `adapters` is the union.
"""

import argparse
import json
import sys


def _key(item):
    if isinstance(item, dict):
        for k in ("fqn", "id"):
            if item.get(k):
                return (k, item[k])
    return ("json", json.dumps(item, sort_keys=True))


def _merge_list(a: list, b: list) -> list:
    seen = {_key(x) for x in a}
    out = list(a)
    for x in b:
        k = _key(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _merge(a, b, path=""):
    if a is None or a == "" or a == [] or a == {}:
        return b
    if b is None:
        return a
    if isinstance(a, list) and isinstance(b, list):
        return _merge_list(a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if path == "stats" and isinstance(out.get(k), int) and isinstance(v, int):
                out[k] = out[k] + v
            else:
                out[k] = _merge(out.get(k), v, k)
        return out
    return a


def merge(parts: list[dict], name: str) -> dict:
    doc: dict = {}
    for p in parts:
        doc = _merge(doc, p)
    doc["exportType"] = "full"
    doc.setdefault("version", "1.0")
    doc["project"] = dict(doc.get("project") or {}, name=name)
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", required=True, help="graph name written to project.name")
    ap.add_argument("out")
    ap.add_argument("parts", nargs="+")
    args = ap.parse_args()
    parts = []
    for path in args.parts:
        with open(path, encoding="utf-8") as f:
            parts.append(json.load(f))
    doc = merge(parts, args.name)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    counts = {k: len(doc.get(k) or []) for k in ("classes", "methods", "fields", "callGraph")}
    print(f"merged {len(parts)} exports into {args.out}: {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
