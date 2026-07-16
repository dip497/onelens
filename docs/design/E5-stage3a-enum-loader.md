# E5 · Stage 3a — `EnumLoader` SubdocLoader

Extract the enum-constant subsystem (`:Field:EnumConstant` dual-label +
`HAS_ENUM_CONSTANT`) into one class owning both paths. This is the subsystem
that delta split into TWO nodes before this session's fix. Gate:
`python/scripts/parity_check.py` → 19/19 green (asserts `ACTIVE.labels ==
['EnumConstant','Field']`).

## Dependency facts (verified — preserve)

- loader.py: enum dual-label block ~131-138 (`_batch_add_label(... "EnumConstant" ...)`)
  needs `Field` nodes (created line 120) — so it runs after fields. The
  `HAS_ENUM_CONSTANT` edge block is at ~322-326. Combine both into one `load_full`
  at the dual-label location (~131).
- delta_loader.py: the enum handling is INLINE in `apply_delta` (~165-212): strip
  `:EnumConstant` label from upserted classes' constants (REMOVE, not DETACH DELETE),
  re-`MERGE (e:Field) SET e:EnumConstant`, then `HAS_ENUM_CONSTANT`. It reads
  `upserted["classes"]` (for the strip list) and `upserted["enumConstants"]`.
  NOTE: the DETACH-DELETE of enum constants in the class-deletion cascade
  (delta_loader.py ~line 69) is part of CORE deletion — DO NOT move it.

## New file `python/src/onelens/importer/loaders/enums.py`

`EnumLoader(SubdocLoader)`, `json_key = "enumConstants"`, local `_chunks`.

- `load_full(self, writer, progress, data, wing)`:
  - `enum_constants = data.get("enumConstants", [])`.
  - dual-label (loader ~131-138) via `writer.batch_add_label`, THEN build + write
    `HAS_ENUM_CONSTANT` (loader ~322-326) via `writer.batch_edges`. Byte-identical Cypher/props.
- `apply_delta(self, writer, data, wing)`:
  - `upserted = data.get("upserted", {})`; `classes = upserted.get("classes", [])`;
    `enum_consts = upserted.get("enumConstants", [])`.
  - Move the inline delta enum block (~165-212) verbatim: the REMOVE-label strip over
    `[c["fqn"] for c in classes]`, the `MERGE (e:Field) SET e:EnumConstant ...`, and the
    `HAS_ENUM_CONSTANT` MERGE. Translate `self.db.execute`→`writer.db.execute`,
    `self._chunks`→local `_chunks`.

## Wire into the orchestrators

- `loader.py`: DELETE the inline dual-label block (~131-138) and the inline
  `HAS_ENUM_CONSTANT` edge block (~322-326). At the dual-label location insert
  `EnumLoader().load_full(self.writer, progress, data, graph_wing)`. Add the import.
  (Note: `enum_constants` may be referenced later in loader for the external-stub or
  other logic — grep; if `enum_constants` is used elsewhere, keep a local
  `enum_constants = data.get("enumConstants", [])` assignment so those references resolve,
  but the node/edge WRITING moves into EnumLoader.)
- `delta_loader.py`: replace the inline enum block (~165-212) with
  `EnumLoader().apply_delta(self.writer, data, graph_wing)`. Add the import. Leave the
  class-cascade DETACH DELETE (~69) untouched.

## Constraints
- No Cypher / prop / label / JSON-key change. Byte-identical graph.
- Only: new `loaders/enums.py` + edits to `loader.py`, `delta_loader.py`. Do NOT modify
  other loaders, base.py, docs, or the core deletion cascade.
- Do NOT delete delta_loader's `_chunks`.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/enums.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
grep -c "def _chunks" python/src/onelens/importer/delta_loader.py   # must be >= 1
```
Required: `PARITY OK: 19 checks green`. The `ACTIVE dual-labeled` and `delta: User STILL
dual-labeled` checks specifically exercise enum + dual-label correctness.
