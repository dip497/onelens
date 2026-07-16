# E5 · Stage 1 — extract `graph_writer.py` (shared write primitives)

Foundational, behavior-preserving step toward the `SubdocLoader` registry
(ADR-034). Establishes the shared module that later stages extend; removes the
`delta_loader → loader` helper-import smell. **Zero wire-format / graph-output
change.** Gate: `python/scripts/parity_check.py` stays `PARITY OK: 19 checks green`.

## Target

New file **`python/src/onelens/importer/graph_writer.py`**:

1. Module-level — moved verbatim from `loader.py`:
   - constants `NODE_BATCH = 1000`, `EDGE_BATCH = 500`
   - `_PRIMITIVES`, `_TXN_ANNOS`, `_ASYNC_ANNOS`, `_DEPRECATED_ANNOS`
   - functions `_normalize_type`, `_anno_simple_names`, `_enrich_method`
2. New class `GraphWriter`:
   ```python
   class GraphWriter:
       def __init__(self, db, node_batch=NODE_BATCH, edge_batch=EDGE_BATCH):
           self.db = db; self.node_batch = node_batch; self.edge_batch = edge_batch
       # the 6 batch helpers, moved from GraphLoader, renamed public (drop `_`):
       def batch_nodes(self, progress, desc, items, label, pk, props): ...
       def batch_edges(self, progress, desc, edges, ...): ...
       def batch_edges_with_props(self, progress, desc, edges, ...): ...
       def batch_add_label(self, progress, desc, items, ...): ...
       def batch_edges_simple(self, progress, desc, edges, ...): ...
       def batch_annotation_edges(self, progress, label, edges): ...
   ```
   Bodies move verbatim; replace `self.db` reads (unchanged) and any
   `NODE_BATCH`/`EDGE_BATCH` references with `self.node_batch`/`self.edge_batch`.

## `loader.py` changes (call sites stay identical)

- Delete the moved module-level defs; `from onelens.importer.graph_writer import
  GraphWriter, _normalize_type, _enrich_method, _anno_simple_names, NODE_BATCH, EDGE_BATCH`.
- `GraphLoader.__init__`: add `self.writer = GraphWriter(db)`.
- Replace the 6 `def _batch_*` method bodies with thin delegations so **every
  existing `self._batch_*(...)` call site is unchanged**:
  ```python
  def _batch_nodes(self, *a, **k): return self.writer.batch_nodes(*a, **k)
  ```

## `delta_loader.py` changes

- The two in-function imports `from onelens.importer.loader import _enrich_method`
  / `_normalize_type` → `from onelens.importer.graph_writer import ...`.

## Constraints

- No change to any Cypher, prop list, label, or JSON key. Pure relocation + delegation.
- Do NOT touch docs, CHANGELOG, PROGRESS, or any file outside the three named.
- Do NOT alter `delta_loader.py`'s inline Cypher (later stages handle that).

## Verification (must pass, paste output)

```bash
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/{graph_writer,loader,delta_loader}.py
~/.onelens/venv/bin/python python/scripts/parity_check.py | tail -3
~/.onelens/venv/bin/python tools/extractors/python_ast_extractor.py \
  python/src/onelens --name chk >/tmp/x.json && echo "extractor OK $(wc -c </tmp/x.json) bytes"
```
Required: parity prints `PARITY OK: 19 checks green`.
