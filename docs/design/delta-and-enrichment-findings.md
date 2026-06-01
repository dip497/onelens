# Delta usability + graph enrichment — review findings & plan

Three parallel reviewers + gap-finder ran 2026-06. Consolidated below.
Source: delta-correctness reviewer, delta-UX reviewer, graph-richness gap-finder.

## Core delta invariant

`delta(A→B)` applied to `graph(A)` must equal `full-import(B)`. Every node/edge/
property the full loader writes but delta forgets = silent drift.

**Root cause of the worst bugs:** modified-file classes are added to `deletedClasses`
(`DeltaExportService.kt:176`), so step 1 `DETACH DELETE`s them — which strips
dual-labels (`:JpaEntity`, `:TestCase`, `:EnumConstant`) and inbound structural edges
(`CONTAINS`, `HAS_COLUMN`, `REGISTERED_AS`). Steps 2-3 re-`MERGE` only the base
`:Class`/`:Method`. Every richer layer is silently dropped each delta and never rebuilt.

## Delta correctness — must-fix (produces wrong graph)

| # | Layer | Effect | Fix |
|---|-------|--------|-----|
| 1 | JPA | modified `@Entity` demotes to plain Class; HAS_COLUMN/RELATES_TO/REPOSITORY_FOR/QUERIES vanish; SQL→JPA bridge stale | ship `jpa` in delta + re-apply dual-labels & edges |
| 2 | Tests | `:TestCase` label + MOCKS/SPIES/TESTS edges destroyed every delta (Spring wipe kills bean-targeted mock edges) | ship tests/mockBeans/spyBeans, re-derive after _replace_spring |
| 4 | Apps/Packages | modified class detaches from package tree; new packages missing | re-emit CONTAINS(Package→Class) for upserted classes |
| 5 | Spring `wing` | Endpoint/Bean lose `wing` → Vue↔Spring HITS bridge = 0 edges; REGISTERED_AS gone; INJECTS loses qualifier; SpringAutoConfig gone | stamp wing + full props in _replace_spring |
| 6 | CALLS | method that stops calling keeps phantom CALLS edges (only affected_callers cleared) | delete outbound CALLS for every upserted method |
| 9 | EnumConstant | split into 2 nodes (:Field + :EnumConstant) vs single dual-labeled in full | MERGE Field SET e:EnumConstant |

Drift risks: #8 enclosingClass dropped, #11 endpoints never re-mined in ChromaDB +
importance drifts (partial callGraph), #13 external-stub orphans after rename,
#16 delta sets lineStart/End=0 → trivial-method misclassification skips embeddings.

## Delta UX — must-fix (daily use)

1. **DATA LOSS:** `ExportState` git-hash/timestamp advances after *export*, before
   `syncToGraph` confirms. `syncToGraph` return value ignored (`AutoSyncService.kt:163`).
   Import fails (FalkorDB down / Python crash) → diff base advances → window never
   re-emitted → permanent silent staleness. **Top priority.**
2. No "last successful sync" / stale indicator; status reverts to READY after error.
3. `.kt`/`.vue` saves never trigger auto-sync (`AutoSyncFileListener` gates on `.java`).
4. Saves landing mid-sync are dropped, not queued.
5. Branch switch/rebase: no `merge-base --is-ancestor` guard → giant/garbage delta.
6. Uncommitted churn re-emits whole working set every save.
7. Spring full re-scan every single-file delta (latency floor).
8. Auto-sync OFF by default; onboarding copy misleads ("every save delta-syncs").

## Graph enrichment backlog (make it rich)

### Tier 0 — free (data already exported, loader drops it). No plugin rebuild.
1. Method props: `visibility`, `isStatic`, `isAbstract`, `isDeprecated`, `paramCount`,
   `isTransactional`, `isAsync` — from existing `modifiers`/annotations.
2. `THROWS` edge (Method→exception Class) — from `MethodData.throwsTypes`.
3. `HAS_PARAMETER` edge / `paramTypes` — from `MethodData.parameters`.
4. `RETURNS` edge (Method→Class) — promote `returnType` string to edge.

### Tier 1 — one CallGraphCollector body-walk pass (biggest jump)
5. `READS_FIELD`/`WRITES_FIELD` (Method→Field) — data-flow.
6. `INSTANTIATES` (Method→Class via `new`).
7. `THROWS_STMT`/`CATCHES` (in-body raise/swallow sites).

### Tier 2 — framework semantics
8. `ConfigProperty` node + `READS_CONFIG` (@Value/@ConfigurationProperties keys).
9. `PUBLISHES_EVENT`/`LISTENS_FOR` (event-driven flow link).
10. `RemoteCall`/`CALLS_REMOTE` (Feign structural; RestTemplate/Kafka heuristic).

## Execution order

1. Phase 1 — delta correctness (#1,2,4,5,6,9,8) — pure Python, ships first.
2. Phase 2 — delta UX data-loss (#1) + stale indicator — plugin.
3. Phase 3 — Tier 0 enrichment — pure Python loader.
4. Phase 4 — Tier 1 data-flow — plugin collector + loader.
