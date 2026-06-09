# E5 · Stage 3c — `DataFlowLoader` (READS_FIELD / WRITES_FIELD / INSTANTIATES)

Mirror of Stage 3b for the data-flow edges. Shared edge-list **builder**;
path-specific writes (full `MATCH` via `batch_edges_with_props`; delta
`MATCH` for field edges + `MERGE`-inline for INSTANTIATES). Gate: 19/19 parity
(asserts READS_FIELD + INSTANTIATES present full; WRITES_FIELD present + stale
INSTANTIATES purged on delta).

## New file `python/src/onelens/importer/loaders/data_flow.py`

```python
def _build(dataflow: dict):
    """Shared builder. dataflow = the 'dataFlow' subdoc. Returns
    (reads, writes, instantiations) edge dicts — the previously-duplicated logic."""
    reads, writes = [], []
    for fa in dataflow.get("fieldAccesses", []) or []:
        e = {"src": fa.get("accessorFqn", ""), "dst": fa.get("fieldFqn", ""),
             "line": fa.get("line", 0)}
        if not e["src"] or not e["dst"]:
            continue
        (writes if fa.get("mode") == "write" else reads).append(e)
    instantiations = [{"src": i.get("methodFqn", ""), "dst": i.get("classFqn", ""),
                       "line": i.get("line", 0)}
                      for i in dataflow.get("instantiations", []) or []
                      if i.get("methodFqn") and i.get("classFqn")]
    return reads, writes, instantiations

class DataFlowLoader:
    def load_full(self, writer, progress, data): ...      # reads data["dataFlow"]
    def apply_delta(self, writer, upserted): ...           # reads upserted["dataFlow"]
```

**IMPORTANT** — match the CURRENT edge-dict shapes exactly. Read both blocks
first and make `_build` produce dicts identical to today's loader.py (~343-364)
and delta_loader.py (~290-313). If the current loader build differs in any key
(e.g. includes `line` or not), `_build` must match it byte-for-byte; if loader
and delta currently differ in a key, STOP and report — do not silently pick one.

- `load_full(self, writer, progress, data)`:
  - `reads, writes, instantiations = _build(data.get("dataFlow") or {})`
  - write via `writer.batch_edges_with_props(progress, "READS_FIELD", reads, "Method",
    "fqn", "Field", "fqn", ["line"])`, same for `WRITES_FIELD`, and
    `"INSTANTIATES"` (Method→Class) — exactly as loader.py does today.
- `apply_delta(self, writer, upserted, batch_size=500)`:
  - DELETE old `READS_FIELD|WRITES_FIELD|INSTANTIATES` over `[m["fqn"] for m in
    upserted.get("methods", [])]` (via `writer.db.execute` + local `_chunks`).
  - `reads, writes, instantiations = _build(upserted.get("dataFlow") or {})`
  - write exactly as delta_loader.py 6c does today: READS/WRITES via the
    `MATCH (m:Method), (f:Field) MERGE` loop; INSTANTIATES via the
    `MERGE (c:Class {fqn}) ON CREATE SET c.external = true ...` MERGE-inline loop.

## Wire into the orchestrators

- `loader.py`: in the data-flow block (~343-364), replace the inline build + writes with
  `DataFlowLoader().load_full(self.writer, progress, data)`. KEEP the core ext-stub
  pre-collection (~237) that adds INSTANTIATES targets to `ext_class_fqns` — untouched.
  Add the import.
- `delta_loader.py`: replace the 6c block (~279-313) with
  `DataFlowLoader().apply_delta(self.writer, upserted)`. Add the import. The DELETE list
  is computed inside apply_delta from `upserted["methods"]`, so the existing
  `upserted_method_fqn_list` (kept for 6c earlier) may now be unused — if nothing else
  references it, it can be removed; if unsure, leave it.

## Constraints
- `_build` output identical to today's edge dicts. No Cypher/prop/label/JSON-key change.
  Writes stay path-specific. Only the 3 files named. Don't touch ext-stub pre-collection,
  other loaders, base.py, or delta's `_chunks`.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/data_flow.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
grep -c "def _chunks" python/src/onelens/importer/delta_loader.py   # >= 1
```
Required: `PARITY OK: 19 checks green`.
