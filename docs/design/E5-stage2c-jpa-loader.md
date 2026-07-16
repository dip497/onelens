# E5 · Stage 2c — `JpaLoader` SubdocLoader

Extract the JPA subsystem (dual-label `:JpaEntity`/`:JpaColumn`/`:JpaRepository`
+ `HAS_COLUMN`/`RELATES_TO`/`REPOSITORY_FOR`/`QUERIES` edges) into one class
owning both paths. This is the subsystem that **demoted modified entities to
plain `:Class` on every delta** before this session's fix. Gate:
`python/scripts/parity_check.py` → 19/19 green.

## Dependency facts (verified — preserve these)

- `Class`/`Method`/`Field` nodes are created at loader.py lines 100/111/120 —
  BEFORE the JPA node block (line 221). JPA edges (`RELATES_TO`→entity,
  `REPOSITORY_FOR`→entity, `QUERIES`→Method) therefore have their endpoints by 221.
- Nothing between lines 281–521 reads `:JpaEntity`/`:JpaColumn`/`:JpaRepository`.
- `_load_sql` (line 629) reads JPA nodes via graph queries — JPA must be loaded
  before it. Loading JPA nodes+edges together at the current NODE location (~221)
  keeps them available for SQL. **Do not move JPA loading after line 629.**

## New file `python/src/onelens/importer/loaders/jpa.py`

`JpaLoader(SubdocLoader)`, `json_key = "jpa"`, with a local `_chunks` helper.

- `load_full(self, writer, progress, data, wing)`:
  - `jpa = data.get("jpa")`; if falsy, return.
  - Replicate, in order, the loader.py JPA logic, COMBINING the two currently-separate
    blocks into one method body — first the NODE dual-labels (loader.py ~221-280:
    `JpaEntity` via `writer.batch_add_label`, `JpaColumn`, `JpaRepository`), THEN the
    EDGES (loader.py ~522-580: `HAS_COLUMN`, `RELATES_TO`, `REPOSITORY_FOR`, `QUERIES`).
  - Translate `self._batch_add_label`→`writer.batch_add_label`,
    `self._batch_edges`→`writer.batch_edges`,
    `self._batch_edges_with_props`→`writer.batch_edges_with_props`, `graph_wing`→`wing`.
    Every Cypher string, prop list, label name, and the `wing` stamping stays byte-identical.
- `apply_delta(self, writer, data, wing)`:
  - `jpa = data.get("jpa")`; if falsy, return.
  - Move the body of `delta_loader.py::DeltaLoader._replace_jpa` (line 675) verbatim,
    translating `self.db.execute`→`writer.db.execute`, `self._chunks`→local `_chunks`,
    `wing` stays `wing`.

## Wire into the orchestrators

- `loader.py`: DELETE the inline JPA node block (~221-280) and the inline JPA edge
  block (~522-580). At the NODE location (where the node block was, ~221), insert
  `JpaLoader().load_full(self.writer, progress, data, graph_wing)`. Add the import.
  (One combined call replaces both deleted blocks; the edge-block site just gets the
  inline code removed.)
- `delta_loader.py`: replace `self._replace_jpa(jpa, wing=graph_wing)` (~474) with
  `JpaLoader().apply_delta(self.writer, data, graph_wing)` — NOTE pass `data`, not
  `jpa` (apply_delta extracts `data["jpa"]` itself). DELETE the dead `_replace_jpa`
  method (line 675). Add the import. Keep the `jpa = data.get("jpa")` guard line that
  precedes the call only if it's still needed; the call is now unconditional (apply_delta
  guards internally) — simplest is to keep the existing `if jpa is not None:` guard.

## Constraints
- No Cypher / prop / label / JSON-key change. Pure move + accessor rename. Byte-identical graph.
- Only: new `loaders/jpa.py` + edits to `loader.py`, `delta_loader.py`. Do NOT touch
  base.py / annotations.py / tests.py / docs.
- Preserve ordering: JPA loads after Class/Method/Field nodes and before `_load_sql`.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/jpa.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
grep -c "def _replace_jpa" python/src/onelens/importer/delta_loader.py   # must print 0
```
Required: `PARITY OK: 19 checks green` (asserts JpaEntity dual-label, HAS_COLUMN,
table rename, and no-demotion on delta).
