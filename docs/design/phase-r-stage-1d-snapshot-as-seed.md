# Phase R · Stage 1d — Snapshot-as-seed

**Status:** draft, pending implementation (2026-04-21)
**Owner:** griflet
**Depends on:** Stage 1a (CLI/MCP), Stage 1b (plugin UI), Stage 1c (Published/Installed tabs)

## Problem

A new dev joins the team and receives `myapp-8.7.4.tgz` via
Slack. They install the plugin, drop the bundle in
`~/.onelens/bundles/`, click Install in the Snapshots tab. Now they
have `@8.7.4` as a read-only snapshot — queryable, but useless for
day-to-day work:

- Live graph `myapp` (no `@tag`) still doesn't exist.
- Sync Graph does a 20-minute full export from zero on their branch.
- The 8.7.4 snapshot was a museum piece, not an onboarding shortcut.

The snapshot has the *entire* indexed codebase at 8.7.4's commit. The
dev's branch usually descends from 8.7.4 with ≤100 file changes. Using
8.7.4 as a seed for their live graph turns a 20-minute full sync into
a 30-second delta.

## Goal

One action: `Start working from this snapshot`. After promotion:

1. Live graph `myapp` = state @ 8.7.4.
2. DeltaTracker knows the baseline commit.
3. First Sync Graph = `git diff <8.7.4-sha>..HEAD` → delta-only import.
4. Subsequent syncs behave normally (last-sync diff).

## Non-goals (deferred)

- **Phase 1e** — auto-rebuild embeddings after promote when snapshot's
  `includesEmbeddings=false`.
- **Phase 1f** — per-branch live graphs (`myapp@feature/x` as
  a writable namespace). Requires DeltaTracker + workspace resolution
  rewrite. Much bigger.

## UX

### Entry points

- Right-click Published row → `Start working from this snapshot`
  (install-then-promote in one step).
- Right-click Installed row → `Start working from this snapshot`
  (just promote, already extracted).

### Confirm dialog — 3 guards

1. **Live graph exists.**  
   Message: *"Replace current live graph (myapp) with state
   from @8.7.4? Your current graph will be overwritten."*  
   OK / Cancel.

2. **Embeddings absent AND semantic-index enabled.**  
   Inline warning in same dialog: *"Snapshot doesn't include embeddings
   — semantic search will be empty until you rebuild the semantic
   index."*  
   Doesn't block; user OKs with awareness.

3. **Branch doesn't descend from tag commit.**  
   Check via `git merge-base --is-ancestor <commitSha> HEAD`.  
   If fail: *"Your current branch doesn't descend from @8.7.4. Delta
   from this baseline may include thousands of files. Continue anyway?"*  
   **Warn, don't block** (validated by git + Bazel precedent — neither
   errors on non-ancestor fetch/cache-hit; devs legitimately work on
   sibling branches off older tags). Default button = Continue.

### Post-promote visibility

- Status tab: secondary line `Seeded from @8.7.4` under Branch label,
  while `.onelens-baseline` marker present.
- Notification toast: *"OneLens graph seeded from @8.7.4. Next sync
  will delta from this point."*

### Marker lifetime

**One-shot.** After the first successful `SyncComplete` event, the
plugin deletes the `.onelens-baseline` file. Subsequent syncs use the
normal last-sync diff base. Marker is *initial seed only*, not
permanent baseline.

### Reset path (if seed turns out wrong)

Right-click on the empty space in Snapshots list → `Force full
re-sync` (or via Status → Advanced menu). Clears marker + deletes live
graph rdb, forces full import on next Sync.

### First-run nudge (Phase 1d +)

If live graph absent AND ≥1 bundle in `~/.onelens/bundles/`: on
plugin startup, show balloon — *"Skip the 20-min sync — start working
from @<latest-tag>?"* with `Use snapshot` / `Sync fresh` / `Later`
actions. Deferred to a polish pass; core 1d ships without the balloon.

## Implementation

### Python — new MCP tool

`python/src/onelens/mcp_server.py` — add after
`onelens_snapshots_pull`:

```python
@mcp.tool
def onelens_snapshot_promote(graph: str, tag: str) -> dict:
    """Seed the live graph from an installed <graph>@<tag> snapshot.

    Copies the snapshot's rdb + context into the live-graph slot,
    renames the internal FalkorDB Lite graph key from `<graph>@<tag>`
    to `<graph>`, and writes `.onelens-baseline` marker so DeltaTracker
    can diff from the tag's commit on the next sync.
    """
    ...
```

Implementation in `python/src/onelens/snapshots/seed.py` (new module):

1. Verify `~/.onelens/graphs/<graph>@<tag>/<graph>@<tag>.rdb` exists.
2. Read snapshot's manifest.json — pull `commitSha`.
3. Copy rdb to `~/.onelens/graphs/<graph>/<graph>.rdb` (overwrite).
4. Run `GRAPH.COPY <graph>@<tag> <graph>` + `GRAPH.DELETE <graph>@<tag>`
   + `SAVE` inside the newly-copied rdb (same pattern as
   `_rename_graph_in_rdb` in consumer.py).
5. Copy `~/.onelens/context/<graph>@<tag>/` →
   `~/.onelens/context/<graph>/` if the source dir exists.
6. Write `~/.onelens/graphs/<graph>/.onelens-baseline`:
   ```json
   {
     "tag": "8.7.4",
     "commitSha": "4b7ae2d…",
     "promotedAt": "2026-04-21T10:15:32Z",
     "schemaVersion": 3,
     "embedder": "Qwen3-Embedding-0.6B",
     "producerVersion": "0.1.0"
   }
   ```
   (All fields copied from the snapshot's `manifest.json`. DeltaTracker
   cross-checks `schemaVersion` + `producerVersion` before trusting
   the seed — mismatch → warn + fall back to full sync.)
7. Return `{live_rdb, live_context, commitSha, warnings}`.

**Atomicity order** (any step failure = bail, no marker written):
  1. Copy rdb to live slot.
  2. Run GRAPH.COPY + GRAPH.DELETE + SAVE (rename internal key).
  3. Copy context dir (if present).
  4. Only after all three succeed: write marker.

Partial promote without marker is recoverable — live graph works,
DeltaTracker sees no marker, next sync uses last-sync timestamp diff
(or falls back to full if no timestamp). Partial promote *with* marker
would silently corrupt semantic search (ChromaDB wing/room/hall drift
per ADR-007); hence marker is last, after context copy.

### Plugin — DeltaTracker change

`plugin/src/main/kotlin/com/onelens/plugin/export/delta/DeltaTracker.kt`:

- Read `~/.onelens/graphs/<graph>/.onelens-baseline` JSON at tracker
  init per sync call.
- **Consume immediately**: extract `commitSha` + version fields, then
  delete the marker *before* the diff runs. Prevents double-fire if
  the SyncComplete cleaner races (research: Nix precedent = permanent
  sidecar; our model = one-shot like `MERGE_HEAD` — so consume at
  entry, not exit).
- Cross-check `schemaVersion` + `producerVersion` against current
  plugin's values. Mismatch → log warning, discard marker, fall back
  to full sync. Rationale: SharedIndexes precedent — schema drift
  between indexer versions silently corrupts results.
- If valid: override diff-base commit with `marker.commitSha`. Log
  `"Seeded baseline consumed: diff from @<tag> (<commitSha>..HEAD)"`.
- If absent or invalid: existing behavior (timestamp-based diff).

### Plugin — marker cleanup

**Not a separate listener.** DeltaTracker consumes the marker at entry
(see above). Separate SyncComplete cleanup is redundant and introduces
a race window. If DeltaTracker consumes and the sync fails mid-run,
the marker is already gone — next retry falls back to full sync. That
is correct: a half-applied seed followed by a timestamp-diff would
pile partial state.

### Plugin — action

`plugin/.../actions/StartFromSnapshotAction.kt` (new, programmatic):

```kotlin
object StartFromSnapshotAction {
    fun run(project: Project, graph: String, tag: String, alreadyInstalled: Boolean) {
        // 1. Off-EDT: git merge-base check, read manifest for commitSha + embeddings flag.
        // 2. Build confirm-dialog text based on guards triggered.
        // 3. On approve: Task.Backgroundable shells:
        //    - If !alreadyInstalled: onelens_snapshots_pull --repo local
        //    - onelens_snapshot_promote --graph <g> --tag <t>
        // 4. Notification + refresh panel.
    }
}
```

### Plugin — right-click menu

In `OneLensSnapshotsToolWindow.kt`:

- `showPublishedContextMenu` → add menu item `Start working from this
  snapshot` (before the separator + Delete).
- `showLocalContextMenu` → same, before the separator + Delete.

### Plugin — Status tab provenance

In `OneLensToolWindow.kt`:

- Read marker in `refreshAsync`.
- Pass to `render`; if present, show `Seeded from @<tag>` on a new
  secondary line under the `Branch:` label.
- When marker absent, hide the line.

### Tracker updates

- `CHANGELOG.md` — Stage 1d block with file list.
- `docs/PROGRESS.md` — R8 row ✅.
- `docs/DECISIONS.md` — ADR-026 "Snapshot-as-seed = one-shot marker,
  not permanent baseline. Rationale: matches user mental model (seed
  the live graph once, then sync normally). Alternatives rejected:
  (a) permanent `baseline` field on every export → conflicts with
  branch switches and merges; (b) per-branch live graphs → Phase 1f
  scope."

## Validation

### End-to-end smoke (manual)

1. Precondition: `myapp-8.7.4.tgz` in `~/.onelens/bundles/`.
2. Simulate fresh dev:  
   ```bash
   rm -rf ~/.onelens/graphs/myapp
   rm -rf ~/.onelens/context/myapp
   ```
3. Plugin Snapshots tab → right-click `8.7.4` Published row →
   `Start working from this snapshot`.
4. Confirm the 3 guards fire correctly (live-missing skipped,
   embeddings warning if applicable, ancestor check).
5. Verify:
   - `~/.onelens/graphs/myapp/myapp.rdb` exists, 48 MB.
   - `~/.onelens/graphs/myapp/.onelens-baseline` present with
     `commitSha`.
   - `onelens call-tool onelens_status --graph myapp` returns
     ~199,794 nodes (parity with 8.7.4 snapshot).
6. `git checkout -b feature/test-seed`, modify 1 Java file, Sync Graph.
7. Verify export JSON header `fromCommit` = 8.7.4's sha, not zero or
   live-graph last-timestamp.
8. Verify SyncComplete completes (exitCode = 0), marker deleted.
9. Second Sync Graph → delta uses last export's commit, NOT 8.7.4 —
   marker is gone.

### Regression check

- Non-promoted dev (no marker): Sync Graph behavior unchanged.
- Promote + failed import (simulate by killing mid-run): marker stays,
  next retry re-does seed diff.
- Two installed snapshots + promote one → other snapshot unaffected.

## Risks

1. **GRAPH.COPY on 48 MB rdb takes ~5 s** — acceptable, shown in
   progress indicator text.
2. **User promotes while auto-sync running** — race. Guard:
   `StartFromSnapshotAction.run` checks `AutoSyncService.isRunning` and
   blocks with "Auto-sync active; wait for it to finish" if true.
3. **Snapshot commit orphaned** (tag deleted from git history) — 
   `git merge-base --is-ancestor` fails. Handled by guard 3.
4. **Context dir copy fails** (permissions, disk full) — **bail, do not
   write marker**. Live rdb is already in place so structural queries
   work; DeltaTracker sees no marker, falls back to normal diff. User
   sees notification: "seed partially applied — semantic search may
   need rebuild." No half-state with phantom marker.
5. **Marker JSON parse failure** — DeltaTracker logs + ignores marker,
   falls back to normal diff base. Never blocks a sync.
6. **Schema/producer version mismatch** (snapshot produced by plugin
   v1.2, consumed by v1.4 with new node types) — DeltaTracker detects
   mismatch, discards marker, falls back to full sync. Notification
   surfaces the drift: "snapshot schema v2, plugin expects v3 — seed
   skipped." Validated by SharedIndexes (keys on indexer version for
   exactly this reason).
7. **Uncommitted live-graph edits lost on overwrite** — unlikely since
   no UI for manual `onelens query` mutations, but a `Cypher REPL`
   Phase 2 feature would surface this. Log the overwrite with the
   old rdb's size + last-modified, so user can grep idea.log if
   confused.
8. **FalkorDB Lite `SAVE` behavior** — in Redis server SAVE is
   synchronous blocking; in FalkorDB Lite embedded it may short-circuit
   since the rdb persists on every op. Verify once in smoke test;
   if Lite ignores SAVE, the GRAPH.COPY state is already on disk via
   Lite's auto-persist.

## Revisit when

- **Phase 1e lands (embedding auto-rebuild):** update UX guard 2 to
  offer `Start + rebuild embeddings` as a second button.
- **Phase 1f lands (per-branch graphs):** promote becomes one of
  several write-target choices; UX changes fundamentally.
- **User feedback shows people forget they seeded from X:** add a
  persistent "baseline provenance" log (separate from the one-shot
  marker), surfaced in Status tab history.

## Cross-references

- Phase R spec: `docs/design/phase-r-release-snapshots.md`
- ADR-024 (Lite-first snapshots, GitHub Releases primary)
- ADR-025 (unified tool window with tabs)
- Stage 1a/b/c in CHANGELOG
