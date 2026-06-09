# E5 · Stage 2a — first `SubdocLoader`: AnnotationLoader

Proves the registry pattern on the safest subsystem (annotations — the
`attr_props` promotion + label mapping are *verbatim duplicated* in `loader.py`
and `delta_loader.py`). One class owns both the full and delta paths, so they
can no longer drift. Gate: `python/scripts/parity_check.py` → 19/19 green.

## New package `python/src/onelens/importer/loaders/`

**`__init__.py`** — empty (the `LOADERS` registry lands in Stage 3).

**`base.py`**:
```python
class SubdocLoader:
    """One graph subsystem, owning BOTH import paths so they cannot diverge.
    json_key is the top-level export key this loader reads."""
    json_key: str = ""
    def load_full(self, writer, progress, data: dict, wing: str) -> None: ...
    def apply_delta(self, writer, upserted: dict, wing: str) -> None: ...
```

**`annotations.py`** — `AnnotationLoader(SubdocLoader)` with `json_key = "annotations"`:
- Module-level shared helpers (the de-duplicated logic):
  ```python
  _LABEL_BY_KIND = {"CLASS": "Class", "METHOD": "Method", "FIELD": "Field"}
  def _label_for(a: dict) -> str: return _LABEL_BY_KIND.get(a.get("targetKind", "CLASS"), "Field")
  def _attr_props(a: dict) -> dict:
      out = {}
      for k, v in (a.get("attrValues") or {}).items():
          if not v or v == "<dynamic>": continue
          out[f"attr_{k}"] = v
      return out
  def _edge(a: dict) -> dict:
      return {"src": a["targetFqn"], "dst": a["annotationFqn"],
              "attributes": a.get("attributes", "{}"), "attr_props": _attr_props(a)}
  ```
- `load_full(self, writer, progress, data, wing)` — replicate `loader.py`'s current
  behavior EXACTLY:
  1. Dedup Annotation node fqns from `data["annotations"]` (key `annotationFqn`) **plus**
     class-level annotations (`data["classes"][*]["annotations"][*]["fqn"]`), discard "",
     build `[{"fqn", "name": fqn.split('.')[-1]}]`, `writer.batch_nodes(progress,
     "Annotations", nodes, "Annotation", "fqn", ["name"])`.
  2. Group edges by `_label_for` into Class/Method/Field, `writer.batch_annotation_edges(
     progress, label, edges)` per non-empty group.
- `apply_delta(self, writer, upserted, wing)` — replicate `delta_loader.py` 8b EXACTLY:
  1. `annotations = upserted.get("annotations", [])`; if empty, return.
  2. MERGE Annotation nodes (dedup on `annotationFqn`, `ON CREATE SET a.name =
     split(fqn,'.')[-1]`), batched via `writer.db.execute` + the existing chunk size.
  3. Per label, DELETE existing `ANNOTATED_WITH` on the upserted targets
     (`MATCH (n:{label} {fqn})-[r:ANNOTATED_WITH]->() DELETE r`).
  4. Per label, CREATE fresh edges from `_edge(a)` with `SET r += edge.attr_props`.
  Use `writer.db` for execute and a local chunker (copy `_chunks` or accept a batch size).

## Make `GraphWriter` primitives tolerate `progress=None`

`apply_delta` has no progress bar. In `graph_writer.py`, guard every progress
interaction in `batch_nodes` / `batch_annotation_edges` (and any other batch method
they call) so `progress=None` is a no-op (e.g. `if progress is not None: progress.update(...)`).
Pure additive guard — does not change behavior when progress is provided.

## Wire into the orchestrators

- `loader.py`: replace the Annotation-node block (~lines 145-153) AND the
  ANNOTATED_WITH edge block (~lines 494-525) with:
  `from onelens.importer.loaders.annotations import AnnotationLoader` (top of file) and,
  at the edge-block location, `AnnotationLoader().load_full(self.writer, progress, data, graph_wing)`.
  Remove the now-dead inline code. (The node-dedup must move INTO load_full — so delete
  the inline node block too and let load_full do both nodes + edges. Keep call ordering:
  load_full must run where the edge block currently is, AFTER base nodes exist.)
- `delta_loader.py`: replace the 8b block (~lines 429-490) with
  `from onelens.importer.loaders.annotations import AnnotationLoader` and
  `AnnotationLoader().apply_delta(self.writer, upserted, graph_wing)`.
  NOTE: `delta_loader`'s `DeltaLoader` has `self.db` but not a `self.writer`. Add
  `self.writer = GraphWriter(db)` in `DeltaLoader.__init__` (import GraphWriter from
  graph_writer) so the SubdocLoader can use shared primitives.

## Constraints
- No change to any Cypher semantics, prop list, label, attr key, or JSON key. Behavior identical.
- Only: new `loaders/` package + edits to `loader.py`, `delta_loader.py`, `graph_writer.py`.
- Do NOT touch docs/trackers.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile python/src/onelens/importer/graph_writer.py \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/base.py python/src/onelens/importer/loaders/annotations.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -3
```
Required: `PARITY OK: 19 checks green`.
