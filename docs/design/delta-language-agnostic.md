# Design — Language-agnostic delta (incremental) sync

Status: **proposed** (plan). Owner: TBD. Supersedes the Java-only delta path.
Related: ADR-034 (import-side SubdocLoader registry), Phase A (FrameworkAdapter
SPI), Phase B2/E (Vue + multi-language). PROGRESS row `W7-ext` is blocked on this.

## Context — the problem

OneLens incremental ("delta") export is **Java-only**. A `.vue`/`.ts`/`.py`
change is invisible to it: the graph silently goes stale, so every non-Java
re-sync must be a **full** re-export (minutes, not seconds). This is **not an
IntelliJ limitation** — IntelliJ's VFS `BulkFileListener`, incremental indexing,
and git integration are all language-agnostic. The coupling is self-inflicted,
in three hardcoded `.java` filters plus a one-method collector SPI:

| # | Where | What it does |
|---|-------|--------------|
| 1 | `plugin/.../autosync/AutoSyncFileListener.kt` | `if (!file.name.endsWith(".java")) return` — IDE live-sync ignores non-Java saves |
| 2 | `plugin/.../export/delta/DeltaTracker.kt` | git-diff filtered to `.java` only |
| 3 | `plugin/.../export/delta/DeltaExportService.kt` | calls the Java collector set directly, **bypassing the `FrameworkAdapter` registry** the full export uses |

The full export is already multi-language (it iterates registered
`FrameworkAdapter`s — `SpringBootAdapter`, `Vue3Adapter` — and merges each one's
output under its `jsonKey`, see `ExportService.discoverAdapters`). Delta never
adopted that registry. The `Collector` SPI
(`plugin/.../framework/FrameworkAdapter.kt`) has only a full-pass
`collect(ctx): CollectorOutput` — no incremental variant — so the per-file delta
logic lives in hand-written Java collectors outside the adapter system.

## Key insight — delta already runs two modes

`DeltaExportService.exportDeltaForFiles` does **not** treat all data the same:

- **True per-file incremental** for the class graph: classes/methods/fields/
  calls/inheritance/annotations/data-flow are collected only for
  `affectedClasses` (the changed files).
- **Full re-scan + replace-all** for cross-class subsystems: Spring, JPA, tests,
  modules are re-collected over the *whole* project every delta, and the Python
  side replaces all of that subsystem's nodes/edges (the comment in the code:
  *"per-class filtering loses cross-class edges"*).

Replace-all-when-dirty is already the proven pattern for anything whose edges
cross file boundaries — which is exactly what Vue (components ↔ stores ↔ routes ↔
api-calls), Pinia, and JS-module import graphs are. So the generalization is not
"make every adapter do per-file incremental" (hard, risky); it is **"let each
adapter declare its dirty-set and re-emit, defaulting to replace-all."**

## Design

### 1. Language-agnostic change detection (validated against the Platform SDK)

Drop the three `.java` filters. Change detection answers one question — *which
files changed* — and is already language-neutral. **Validated against the
IntelliJ Platform SDK (deepwiki on `JetBrains/intellij-community` + SDK docs),
there are official platform abstractions that beat raw `git diff`:**

- **IDE live-sync → `ChangeListManager`** (VCS-agnostic, not git-specific).
  `ChangeListManager.getInstance(project).getAffectedFiles()` /
  `.getStatus(VirtualFile)` returns modified/added/deleted files across git, svn,
  hg, … with zero shell-out. Subscribe a `ChangeListListener` for live updates.
  (It tracks *uncommitted* local changes vs VCS head — perfect for the IDE.)
- **VFS listener → `AsyncFileListener`, not `BulkFileListener`.** The current
  `AutoSyncFileListener` uses the blocking `BulkFileListener`; the SDK's
  non-blocking `AsyncFileListener` (`prepareChange` → `ChangeApplier`) is the
  recommended variant for change-driven re-processing (the platform's own
  `VcsDirtyScopeVfsListener` uses the async path). Drop the `.java` filter while
  we're in there.
- **Headless baseline → Merkle tree of file hashes, NOT git** (this is how
  **Cursor** does it — see Prior art). `ChangeListManager` only knows changes vs
  the *current* head — it can't diff against an arbitrary past *export* revision
  across a fresh headless JVM, and deepwiki confirms "compare to a specific
  historical revision" forces VCS-specific APIs. So the headless baseline stays
  self-managed — a **Merkle tree**: hash every file, derive each folder's hash
  from its children, persist the tree (root + nodes) in `ExportState`. A delta
  compares the persisted root hash, then **descends only into subtrees whose hash
  changed** — so an untouched module is skipped with a single comparison, not a
  per-file walk (matters on the 28-module / ~10K-file backend). This is
  **strictly better than the current git-diff**: VCS-agnostic, works on a
  **non-git checkout** (directly fixing the fall-back-to-full we hit), and
  skips unchanged subtrees in O(changed) not O(files). Git diff becomes an
  optional fast-path, never a requirement.
- **Adapter file enumeration → `FileTypeIndex.getFiles(fileType, scope)`** is the
  language-agnostic way for an adapter to list "its" files (e.g. all `.vue`),
  used by the replace-all path and by `fileExtensions` dirty-detection.

`DeltaTracker` is refactored into a `ChangeSource` seam with two impls:
`VcsChangeSource` (IDE, `ChangeListManager`) and `HashBaselineChangeSource`
(headless, content-hash vs `ExportState`). Both return the same
`ChangedFiles(modified, deleted)` with extensions intact.

### 2. Extend the adapter SPI (two small additions)
```kotlin
interface FrameworkAdapter {
    val id: String
    val jsonKey: String
    fun detect(project: Project): Boolean
    fun collectors(): List<Collector>

    // NEW — which files this adapter owns, for delta dirty-detection.
    val fileExtensions: Set<String>            // {"java"}, {"vue","ts","js","mjs"}

    // NEW — emit a delta section for the changed files. DEFAULT = replace-all:
    // re-run full collectors and tag the section so the importer wipes+reloads
    // this adapter's nodes for the wing. Adapters that can do true per-file
    // incremental (the JVM class graph) override this.
    fun collectDelta(ctx: CollectContext, changed: ChangedFiles): AdapterDelta =
        AdapterDelta.replaceAll(runFullCollectors(ctx))   // default impl
}

data class ChangedFiles(val modified: List<String>, val deleted: List<String>)
data class AdapterDelta(
    val jsonKey: String,
    val mode: DeltaMode,                       // REPLACE_ALL | UPSERT_DELETE
    val data: JsonElement,                     // adapter-shaped, same as full
    val deleted: DeletedRefs = DeletedRefs(),  // only for UPSERT_DELETE
)
```
- **Vue3Adapter**: keep default (`REPLACE_ALL`) — re-scan when any owned file is
  dirty. Correct for adds/renames/deletes with zero per-file bookkeeping.
- **SpringBootAdapter**: override `collectDelta` to keep today's behaviour —
  `UPSERT_DELETE` for the class graph (the existing `affectedClasses` path) +
  `REPLACE_ALL` for its Spring/JPA/test sub-sections.

### 3. Adapter-keyed delta document
Replace the hardcoded `DeltaDocument` (Java-shaped `upserted`/`deleted`/`spring`/
`jpa`) with an adapter-keyed envelope mirroring the full `ExportDocument`:
```jsonc
{
  "exportType": "delta",
  "version": "...", "timestamp": "...", "basedOnTimestamp": "...",
  "changedFiles": [...],
  "sections": [
    { "jsonKey": "spring-boot", "mode": "UPSERT_DELETE", "deleted": {...}, "data": {...} },
    { "jsonKey": "vue3",        "mode": "REPLACE_ALL",   "data": {...} }
  ]
}
```
`DeltaExportService` becomes a thin orchestrator: detect changed files → for each
registered adapter whose `fileExtensions` intersect the dirty set, call
`collectDelta` → assemble `sections`. Adapters whose files didn't change are
skipped entirely (cheap no-op deltas).

### 4. Import side — finish the SubdocLoader symmetry
The import registry (ADR-034) already has per-subsystem `apply_delta`
(`SpringLoader`, `JpaLoader`, `TestLoader`, `EnumLoader`, `DataFlowLoader`,
`AnnotationLoader`, `TypeFlowLoader`). `DeltaLoader.apply_delta`
(`python/.../importer/delta_loader.py`) iterates `sections` and dispatches by
`jsonKey` + `mode`:
- `REPLACE_ALL` → `DELETE` all of the adapter's node labels scoped to the wing,
  then bulk-insert (reuse the full loader's insert).
- `UPSERT_DELETE` → today's DETACH-DELETE-then-MERGE class-graph path.

Add a **Vue/JS loader `apply_delta`** (replace-all by wing) — the full Vue loader
already exists (`loader.py` JsModule/Component/Store/Route/ApiCall inserts from
B2.JS.3); `apply_delta` = `DELETE … WHERE wing=$wing` for the Vue labels + reuse
the full insert. HITS cross-stack edges are recomputed on insert as today.

## 5. Graph rebuild + semantic (embedding) reconciliation

A delta is not just "write changed nodes" — three layers must stay consistent:
the **structural graph**, the **derived global data** (PageRank, cross-stack
HITS), and the **ChromaDB embeddings**. The embedding layer is the expensive one
and the reason replace-all needs care.

### 5a. The decoupling principle — graph replace-all ≠ embedding replace-all
The graph side can afford to **wipe + reinsert** an adapter's nodes (cheap
Cypher, ms–seconds). The embedding side **cannot** re-encode everything — a
2,500-component Vue frontend would re-embed on every save (minutes; unusable).
So the embedding reconcile MUST stay incremental *even when the graph does
replace-all*. The mechanism is a **content-hash gate**:

- Store a `body_hash` (hash of the exact embedded text) in each ChromaDB
  drawer's metadata (today's schema: `wing/room/hall/fqn/type/importance/filed_at`
  → add `body_hash`).
- On reconcile, for each candidate drawer compute its `body_hash`; **skip the
  ONNX encode if the hash matches** the stored one. ChromaDB upsert-by-id is
  idempotent, so unchanged drawers are no-ops.
- Net: a 1-component change → graph wipes+reinserts all Vue nodes (fast) but the
  embedder re-encodes exactly **one** drawer. Replace-all becomes free on the
  embedding layer.

### 5b. Generalize `mine_upserts` to all embeddable node types
Today `CodeMiner.mine_upserts` (`miners/code_miner.py`) is Java-only
(`method:<fqn>`, `class:<fqn>`, accepts `{classes, methods, callGraph}`). The
Vue drawer formatters (`_mine_vue_components/composables/stores`, with the
import-stripping that boosts Vue recall) exist but run **only in full `mine`**.
Lift them behind the same deterministic-ID + content-hash path so delta re-embeds
Vue too:
- Deterministic IDs per type: `component:<id>`, `composable:<id>`, `store:<id>`,
  `jsfn:<id>` (alongside the existing `method:`/`class:`/`endpoint:`).
- Delete by ID / ID-prefix on removal (today's `delete_by_ids` /
  `delete_methods_of_classes` cascade — generalize the prefix set per type).
- Drive it from the **same adapter/SubdocLoader registry** as the graph: each
  loader that owns embeddable nodes declares its drawer formatter + ID scheme.
  One registry, three consumers (graph write, embed reconcile, delete cascade).

### 5c. Derived global recompute after a delta
- **PageRank** — already re-run on delta (`delta_loader.py:398`, whole-graph
  NetworkX, ~5–15 s). Keep. (Note: PageRank is computed on the Java *call* graph
  via REST/scheduled seeds, so Vue nodes legitimately have no `pagerank` — that's
  why the frontend graph shows none; not a delta bug.)
- **Cross-stack HITS** (Vue `ApiCall` ↔ Spring `Endpoint`, matched on
  `normalizedPath`) — must be recomputed for the affected wing whenever a delta
  touches `Endpoint` **or** `ApiCall` nodes (a backend endpoint rename
  invalidates the frontend's HITS, and vice-versa). The full loader calls
  `bridge_http.compute_hits`; delta is HITS-aware (delta_loader references the
  "HITS zeroed" bug #5) but the rebuild must explicitly re-run `compute_hits`
  for any wing whose endpoints/api-calls changed. Cheap (indexed path match).

### 5d. Atomicity + cost
- **Wipe window:** replace-all is DELETE-then-INSERT, so a concurrent query could
  see a half-empty adapter section. falkordblite is single-user/embedded so the
  risk is low, but prefer **MERGE-upsert + delete-orphans-by-id** over
  DELETE-all-then-insert where practical, to avoid an empty window. Decision per
  loader.
- **Embedder warmth:** re-embedding needs the local ONNX embedder. A headless
  one-shot cold-loads it (~22–30 s) per invocation; for frequent deltas run
  `onelens daemon start` to keep it warm (~200 ms/drawer). With the content-hash
  gate, most deltas encode 0–N drawers, so even cold-load is paid once for a
  near-empty reconcile. `--context` is opt-in on delta just as on full import.

## Prior art (web-validated, 2026-06)

The design is not novel — it matches what the leading code-intelligence tools do.
This de-risks it substantially:

- **Cursor — Merkle tree of file/folder hashes** (`cursor.com/blog/secure-codebase-indexing`,
  Engineer's Codex). Cursor hashes every file, folds folder hashes from children,
  and syncs only changed subtrees → re-embeds only changed chunks. **This is
  exactly our headless baseline (§1)** — adopt the tree, not a flat hash list.
- **Sourcegraph — structural/keyword over semantic.** Sourcegraph deprecated its
  embeddings product and centers on **SCIP (a continuous, exact code graph) +
  Zoekt keyword search**, positioning embeddings as "approximate … best combined
  with keyword and structural search." **Takeaway: the exact layer is the graph;
  embeddings are the approximate, best-effort layer.** So the *graph* delta must
  be correct and is the priority; the *embedding* delta can be eventually-
  consistent (content-hash-gated, lazy, even optional). This reorders our plan.
- **SCIP — language-agnostic, per-document indexing** (`github.com/scip-code/scip`).
  The industry-standard structural format is per-file and language-agnostic by
  design, with incremental indexing as the goal — confirms our adapter-keyed,
  per-file-change direction.
- **GitHub Stack Graphs — incremental, zero-config, per-file partial graphs**
  (Strange Loop, tree-sitter). Each file's partial graph is computed
  independently and stitched at query time, so a change invalidates only that
  file. This is the **Phase 3 north star** (true per-file incremental with no
  global recompute) beyond our pragmatic Phase 1.
- **CocoIndex / Continue.dev — incremental RAG, "only re-process what changed",
  chunk-level granularity + content hashing.** Confirms our per-drawer
  (per-method / per-component) embedding granularity + `body_hash` gate is the
  right shape (doc-level re-embedding is the known anti-pattern).

## Staged plan

Ordering follows the prior-art lesson: **the graph is the exact layer (do it
first, must be correct); embeddings are approximate (do it second, best-effort).**

**Phase 1a — language-agnostic GRAPH delta (the moat, exact).** Ships working Vue
delta for the structural graph:
1. Drop the 3 `.java` filters. Refactor `DeltaTracker` into a `ChangeSource`
   seam: `VcsChangeSource` (IDE, `ChangeListManager`) + `HashBaselineChangeSource`
   (headless, content-hash diff via `ExportState.fileHashes` — **removes the git
   requirement**, fixes the non-git-checkout fall-back-to-full we hit). Switch
   `AutoSyncFileListener` to `AsyncFileListener`. Both return
   `ChangedFiles(modified, deleted)` with extensions intact (build dirs excluded).
2. Add `fileExtensions` + `collectDelta` (default replace-all) to the SPI;
   `Vue3Adapter` uses default; `SpringBootAdapter` overrides to preserve current
   Java incremental + Spring/JPA/test replace-all.
3. Convert `DeltaDocument` → adapter-keyed `sections` envelope; `DeltaExportService`
   becomes the registry orchestrator.
4. `DeltaLoader.apply_delta` dispatches `sections` by `jsonKey`+`mode`; add Vue
   `apply_delta` (replace-all by wing).
5. **HITS reconcile** (cheap, exact — belongs with 1a): after applying any
   section that touched `Endpoint` or `ApiCall`, re-run `bridge_http.compute_hits`
   for that wing. (PageRank already re-runs — `delta_loader.py:398`.)
6. Verify graph parity + Vue round-trip (below).

**Phase 1b — embedding reconcile (approximate, best-effort, can ship after 1a).**
The graph is correct after 1a; semantic search just lags until this lands:
7. Add `body_hash` to the ChromaDB drawer metadata + a content-hash skip in the
   mining path; generalize `CodeMiner.mine_upserts` to Vue/JS drawers
   (`component:`/`composable:`/`store:`/`jsfn:`) via the same registry, with
   delete-by-prefix on removal. A graph replace-all then re-encodes only
   content-changed drawers (the §5a decoupling).
8. Verify "1 drawer re-encoded, not 2,500" (below).

**Phase 2 — true per-file incremental for big frontends (optimization, later).**
Only if replace-all re-scan is too slow on a huge SPA. Give `Vue3Adapter` an
`UPSERT_DELETE` `collectDelta` scoped to changed `.vue` files + per-file deleted
refs. The envelope already supports it; no further SPI change.

## Files

Plugin (Kotlin):
- `framework/FrameworkAdapter.kt` — SPI additions (`fileExtensions`, `collectDelta`, `AdapterDelta`/`ChangedFiles`/`DeltaMode`)
- `framework/springboot/SpringBootAdapter.kt` — override `collectDelta` (port existing Java incremental + Spring/JPA/test replace-all out of `DeltaExportService`)
- `framework/vue3/Vue3Adapter.kt` — `fileExtensions = {vue,ts,js,…}`, default replace-all
- `export/delta/DeltaExportService.kt` — becomes the adapter-registry orchestrator + `sections` envelope
- `export/delta/DeltaTracker.kt` → `ChangeSource` seam: `VcsChangeSource` (`ChangeListManager`) + `HashBaselineChangeSource` (content-hash vs `ExportState`; no git dependency)
- `export/ExportState.kt` — extend `fileHashes` to carry per-file content hash (baseline for headless diff)
- `autosync/AutoSyncFileListener.kt` — `BulkFileListener` → `AsyncFileListener`, drop `.java` filter; `autosync/AutoSyncService.kt` — debounce any source ext
- adapters use `FileTypeIndex.getFiles(fileType, scope)` to enumerate owned files

Python:
- `importer/delta_loader.py` — `sections` dispatch by `jsonKey`+`mode`; re-run `compute_hits` when endpoints/api-calls change
- `importer/loaders/vue3.py` (or extend existing) — `apply_delta` replace-all by wing
- `importer/loaders/__init__.py` / registry — register Vue loader for delta
- `miners/code_miner.py` — generalize `mine_upserts` to Vue/JS drawer types + delete-by-prefix; add `body_hash` content-gate (skip unchanged encodes)
- `importer/schema.py` / ChromaDB metadata — add `body_hash` to the drawer schema (`wing/room/hall/fqn/type/importance/filed_at/body_hash`); keep full + delta write paths in sync (LESSONS-LEARNED: schema drift silently breaks `wing` filtering)
- `context/bridge_http.py` — `compute_hits` callable per-wing on delta

## Verification (end-to-end)

1. **Java parity (no regression):** full + delta on a Spring fixture, compare
   graphs node/edge-for-node/edge (golden diff) against current `main`. Must be
   identical.
2. **Vue delta round-trip** on `tools/` (or the headless Vue fixture): full
   import → edit one `.vue` (add a component / change an api-call path) → delta
   → assert the Component/ApiCall node updated; delete a `.vue` → assert the node
   is gone (no orphan edges); rename → assert no duplicate.
3. **Headless:** `ONELENS_DELTA=true scripts/onelens-headless.sh resync <vue-proj>
   <graph>` produces a small delta JSON (KB, `exportType: delta`) and the import
   auto-detects it. (Requires the project be a git repo — headless baseline.)
4. **Mixed monorepo:** a commit touching both `.java` and `.vue` → one delta with
   two `sections`, both applied.
5. **Embedding reconcile:** with `--context`, edit one `.vue` body → delta →
   assert ChromaDB re-encoded exactly **1** drawer (not all 2,500; check
   `body_hash` skip via mine stats), the changed component is now retrievable,
   and a deleted component's drawer is purged. Unchanged-content rename → 0
   re-encodes.
6. **HITS after cross-stack change:** rename a Spring endpoint path via delta →
   assert the frontend `ApiCall`→`Endpoint` HITS edge re-matches (not zeroed).
7. **Cost guard:** a single-file delta on the 28-module backend completes in
   seconds (structural) + bounded embedding encodes; confirm PageRank refresh
   (~5–15 s) dominates, not a full re-mine.

## Open decisions (for discussion)

- **Replace-all granularity for Vue:** whole-adapter vs per-Vue-root. Whole-
  adapter is simplest + correct; per-root limits blast radius in multi-root
  workspaces. Start whole-adapter.
- **Deletion semantics under REPLACE_ALL:** wipe-by-wing assumes one adapter
  owns a label-set per wing. Confirm no label is shared across adapters in a
  single graph (Vue↔Spring share only HITS edges, recomputed on insert — safe).
- **IDE live-sync debounce** now fires on more extensions; confirm the 5-s
  debounce + per-collector guards keep a `.vue` save cheap (replace-all Vue
  re-scan must stay sub-second on warm index, else gate Phase 2).
