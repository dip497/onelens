# E5 · Stage 3b — `TypeFlowLoader` (RETURNS / THROWS / HAS_PARAMETER)

Core-enrichment loader (operates on the `methods` list, not a top-level overlay
key). The DUPLICATION being removed is the edge-list **building** (the
`_normalize_type` filtering + param iteration) — identical in loader.py and
delta_loader.py. The WRITES legitimately differ and STAY: full uses
`writer.batch_edges` (MATCH against stubs the core pre-collects into
`ext_class_fqns`); delta uses `MERGE`-inline (self-creates the stub). Do NOT
unify the write mechanism — only share the list-builder. Gate: 19/19 parity.

## New file `python/src/onelens/importer/loaders/type_flow.py`

```python
from onelens.importer.graph_writer import _normalize_type

def _build(methods):
    """Shared edge-list builder — the previously-duplicated logic.
    Returns (returns, throws, has_param) edge dicts."""
    returns, throws, has_param = [], [], []
    for m in methods:
        rt = _normalize_type(m.get("returnType", ""))
        if rt:
            returns.append({"src": m["fqn"], "dst": rt})
        for tt in m.get("throwsTypes", []) or []:
            et = _normalize_type(tt)
            if et:
                throws.append({"src": m["fqn"], "dst": et})
        for i, p in enumerate(m.get("parameters", []) or []):
            pt = _normalize_type(p.get("type", ""))
            if pt:
                has_param.append({"src": m["fqn"], "dst": pt,
                                  "position": i, "name": p.get("name", "")})
    return returns, throws, has_param

class TypeFlowLoader:
    def load_full(self, writer, progress, methods):
        # build, then write via writer.batch_edges / batch_edges_with_props
        # exactly as loader.py does today (MATCH; stubs pre-exist).
        ...
    def apply_delta(self, writer, methods, batch_size=500):
        # delete old RETURNS|THROWS|HAS_PARAMETER on the upserted method fqns,
        # then build, then MERGE-inline writes — exactly as delta_loader does today.
        ...
```

`load_full` body = the WRITE half of loader.py's type-flow block (the
`_batch_edges(... "RETURNS" ...)`, `"THROWS"`, `_batch_edges_with_props(...
"HAS_PARAMETER" ...)` calls) using the lists from `_build`, with
`self._batch_*`→`writer.batch_*`.

`apply_delta` body = delta_loader.py's 6b block: the
`MATCH (m:Method {fqn})-[r:RETURNS|THROWS|HAS_PARAMETER]->() DELETE r` over the
upserted method fqns, then the three `MERGE`-inline write loops (each
`MERGE (c:Class {fqn: edge.dst}) ON CREATE SET c.external = true, ...`), using
the lists from `_build`, with `self.db`→`writer.db`, `self._chunks`→a local
`_chunks` (copy the helper).

## Wire into the orchestrators

- `loader.py`: in the type-flow EDGE block (~334-360), replace the inline
  `returns/throws/has_param` building + the three write calls with
  `TypeFlowLoader().load_full(self.writer, progress, methods)`. KEEP the core
  external-stub pre-collection (~221-235) that adds type-flow target types to
  `ext_class_fqns` — that is core's stub job, NOT part of this loader. Add the import.
- `delta_loader.py`: replace the 6b block (~275-325 — the `_normalize_type` import,
  the DELETE over `upserted_method_fqn_list`, the build, the three MERGE writes) with
  `TypeFlowLoader().apply_delta(self.writer, methods)`. Add the import.
  IMPORTANT: `upserted_method_fqn_list` may be used by the data-flow block (6c) right
  after — check; if 6c still references it, keep its assignment line. (TypeFlowLoader
  computes its own delete list internally from `methods`.)

## Constraints
- The shared `_build` must produce edge dicts identical to today's. No Cypher / prop /
  label / JSON-key change. Write mechanisms stay path-specific (full MATCH, delta MERGE).
- Only: new `loaders/type_flow.py` + edits to `loader.py`, `delta_loader.py`.
- Do NOT touch the core ext-stub pre-collection, other loaders, base.py, or `_chunks` in delta.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/type_flow.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
grep -c "def _chunks" python/src/onelens/importer/delta_loader.py   # >= 1
```
Required: `PARITY OK: 19 checks green` (asserts RETURNS + THROWS present full,
and the delta path keeps them).
