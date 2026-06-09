# E5 · Stage 2b — `TestLoader` SubdocLoader

Extract the tests subsystem (dual-label `:TestCase` + `MOCKS`/`SPIES`/derived
`TESTS` edges) into one class owning both paths. This subsystem demoted on every
delta before this session's fix — consolidating it makes that class of bug
impossible. Gate: `python/scripts/parity_check.py` → 19/19 green.

## New file `python/src/onelens/importer/loaders/tests.py`

`TestLoader(SubdocLoader)` with `json_key = "tests"`:

- `load_full(self, writer, progress, data, wing)` — **move the body of
  `loader.py::GraphLoader._load_tests` verbatim**, translating:
  - `self._batch_add_label(...)` → `writer.batch_add_label(...)`
  - `self._batch_edges_with_props(...)` → `writer.batch_edges_with_props(...)`
  - `self.db.execute(...)` → `writer.db.execute(...)`
  - the `graph_wing` parameter → `wing`
  Keep every Cypher string, prop list, and the derived `:TESTS` pass byte-identical.

- `apply_delta(self, writer, data, wing)` — **move the body of
  `delta_loader.py::DeltaLoader._replace_tests` verbatim**, translating:
  - `self.db.execute(...)` → `writer.db.execute(...)`
  - `self._chunks(...)` → a local `_chunks` (copy the small static helper into this module)
  - the `wing` parameter stays `wing`
  Note `_replace_tests` reads top-level `data["tests"]`/`["mockBeans"]`/`["spyBeans"]`
  (tests are a full re-scan in delta, like Spring) — so `apply_delta` takes the FULL
  delta `data` dict, not `upserted`.

## Wire into the orchestrators

- `loader.py`: at the `self._load_tests(progress, data, graph_wing)` call (~line 621),
  replace with `TestLoader().load_full(self.writer, progress, data, graph_wing)`.
  DELETE the now-dead `def _load_tests(...)` method (~line 1069). Add the import.
- `delta_loader.py`: at `self._replace_tests(data, wing=graph_wing)` (~line 477),
  replace with `TestLoader().apply_delta(self.writer, data, graph_wing)`. DELETE the
  now-dead `def _replace_tests(...)` method (~line 781). Add the import.

## Constraints
- Pure move + rename of accessor (`self._batch*`→`writer.batch*`, `self.db`→`writer.db`).
  No Cypher / prop / label / JSON-key change. Graph output byte-identical.
- Only: new `loaders/tests.py` + edits to `loader.py`, `delta_loader.py`.
- Do NOT touch docs/trackers. Do NOT modify `loaders/base.py` or `annotations.py`.
- Preserve call ORDERING (tests run where `_load_tests`/`_replace_tests` are called today —
  AFTER Spring, since MOCKS/SPIES target SpringBean and TESTS derives from CALLS).

## Verification (paste full output; must be green)
```
cd /home/dipendra-sharma/projects/onelens
~/.onelens/venv/bin/python -m py_compile \
  python/src/onelens/importer/loader.py python/src/onelens/importer/delta_loader.py \
  python/src/onelens/importer/loaders/tests.py && echo COMPILE OK
~/.onelens/venv/bin/python python/scripts/parity_check.py 2>&1 | tail -4
```
Required: `PARITY OK: 19 checks green` (the test-label + TESTS-edge + no-demotion
invariants are in the gate).
