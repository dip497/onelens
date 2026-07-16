# E5 · Stage 2d — `SpringLoader` SubdocLoader

Extract the Spring subsystem (`SpringBean`/`Endpoint`/`SpringAutoConfig` nodes +
`HANDLES`/`INJECTS`/`REGISTERED_AS` edges, all `wing`-stamped) into one class
owning both paths. This is the subsystem whose delta path dropped the `wing`
stamp and zeroed the Vue↔Spring HITS bridge before this session's fix. Gate:
`python/scripts/parity_check.py` → 19/19 green. ONLY Spring — leave `_replace_modules`
and the Module subsystem untouched.

## Dependency facts (verified — preserve)

- Spring NODE block: loader.py ~174-210 (`if spring:` → beans, endpoints, autoConfigs).
  `graph_wing` is computed at line 160, before it.
- Spring EDGE block: loader.py ~441-468 (`if spring:` → HANDLES, INJECTS, REGISTERED_AS).
- Nothing between lines 210-440 reads `:SpringBean`/`:Endpoint`. Tests (which read
  SpringBean via MOCKS/SPIES) run at ~line 622, AFTER. So Spring nodes+edges can fold
  into one `load_full` at the node location (~174). Endpoints/beans created before edges
  within the call; HANDLES needs Method (line 111, exists) + Endpoint (same call);
  REGISTERED_AS needs Class (line 100) + SpringBean (same call).

## New file `python/src/onelens/importer/loaders/spring.py`

`SpringLoader(SubdocLoader)`, `json_key = "spring"`, local `_chunks` helper.

- `load_full(self, writer, progress, data, wing)`:
  - `spring = data.get("spring")`; if falsy, return.
  - Replicate loader.py's Spring logic, COMBINING the node block (~174-210) and edge
    block (~441-468) into one body — NODES first (beans→`writer.batch_nodes`,
    endpoints→`writer.batch_nodes`, autoConfigs→`writer.batch_nodes`), THEN EDGES
    (HANDLES→`writer.batch_edges`, INJECTS→`writer.batch_edges_with_props`,
    REGISTERED_AS→`writer.batch_edges`). Translate `self._batch_*`→`writer.batch_*`,
    `graph_wing`→`wing`. Every Cypher string, prop list, label, and `wing` stamp byte-identical.
- `apply_delta(self, writer, data, wing)`:
  - `spring = data.get("spring")`; if falsy, return.
  - Move `delta_loader.py::DeltaLoader._replace_spring` (line 542) body verbatim,
    translating `self.db.execute`→`writer.db.execute`, `self._chunks`→local `_chunks`.

## Wire into the orchestrators

- `loader.py`: DELETE the inline Spring node block (~174-210) and the inline Spring
  edge block (~441-468). At the NODE location insert
  `SpringLoader().load_full(self.writer, progress, data, graph_wing)`. Add the import.
- `delta_loader.py`: replace `self._replace_spring(spring, wing=graph_wing)` (~465) with
  `SpringLoader().apply_delta(self.writer, data, graph_wing)`. DELETE the dead
  `_replace_spring` method (line 542). Add the import. Keep the surrounding
  `if spring is not None:` guard. DO NOT touch `_replace_modules` or its call.

## Constraints
- No Cypher / prop / label / JSON-key change. Pure move + accessor rename. Byte-identical graph.
- Only: new `loaders/spring.py` + edits to `loader.py`, `delta_loader.py`. Do NOT modify
  base.py / annotations.py / tests.py / jpa.py / docs / `_replace_modules`.
- Do NOT delete delta_loader's `_chunks` (used by many methods — NOT dead).
- Preserve ordering: Spring loads after Class/Method/Field nodes, before tests/SQL.

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/spring.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
grep -c "def _replace_spring" python/src/onelens/importer/delta_loader.py   # must print 0
grep -c "def _replace_modules" python/src/onelens/importer/delta_loader.py  # must STILL print 1
```
Required: `PARITY OK: 19 checks green`, `_replace_spring`=0, `_replace_modules`=1.
