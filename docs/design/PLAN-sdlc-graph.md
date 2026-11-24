# Plan — SDLC graph layers (git, PRs, tests, runtime, advisories)

**Status:** Draft 2026-05-01
**Status of Phase X-DOCS:** 1 + 1b + 2 shipped; X-DOCS-3 (auto-sync) +
X-DOCS-4 (skill recipe) deferred. Docs are the **first non-code SDLC
layer** in the graph. This plan extends the same pattern to git
history, PRs/issues, test outcomes, runtime observability, and
security advisories.

---

## 1. Why now

OneLens already indexes:

- Code (Class / Method / Field / SpringBean / Endpoint / Annotation /
  EnumConstant / JpaEntity / JpaRepository / Component / Composable /
  Store / Route / ApiCall / JsModule / JsFunction).
- Tests (`Method:TestCase` dual-label, 10-kind taxonomy, TESTS / MOCKS
  / SPIES edges).
- SQL surface (Flyway + custom queries → DDL + entity edges).
- Docs (Phase X-DOCS — Doc / Section + MENTIONS to code).

The `HALL_*` constants in `context/config.py` already enumerate the
non-code halls our retrieval layer expects: `HALL_GIT`, `HALL_ISSUES`,
`HALL_CICD`, `HALL_RUNTIME`, `HALL_DECISIONS`. Empty today. Each
non-empty layer turns "ask the agent X" from `git log`+`grep` to a
single Cypher query the agent can chain with code edges.

## 2. Scope by phase

### Phase G — Git history (local, free, universal)

**G-1. `Commit` nodes + `TOUCHES` edges.** Ingest `git log` for last
N commits (default 1000). Per commit: sha, short_sha, author, email,
date, message, additions, deletions. Per-file stats via `--numstat`
become `TOUCHES` edges from `Commit` to existing `Class` /
`JsFunction` / `Component` nodes (matched by `filePath`).

Killer queries:
- Hottest classes: `MATCH (c:Commit)-[:TOUCHES]->(x:Class) WHERE c.timestamp > $cutoff RETURN x.fqn, count(c) ORDER BY count(c) DESC LIMIT 10`
- Endpoints changed in last release: `MATCH (c:Commit)-[:TOUCHES]->(x:Class)-[:HAS_METHOD]->(m:Method)-[:HANDLES]->(e:Endpoint) WHERE c.timestamp > $release_cutoff RETURN DISTINCT e.id`

**G-2. Blame on Method / Field.** Run `git blame --line-porcelain` per
file at import time, attribute lines to commits. Add `lastBlame`
property `{sha, author, date}` to `Method` and `Field` nodes.
Heavier — adds ~30 s per 1000 files. Opt-in via `--blame` flag.

Killer queries:
- "Who knows this code?" `MATCH (m:Method) WHERE m.fqn = $fqn RETURN m.lastBlame`
- Author expertise: `MATCH (m:Method) WHERE m.lastBlame.author = $author RETURN m.fqn` (with PageRank weighting → top contributions)

**G-3. Co-change index.** Compute pairs of `Class` that share ≥N
commits (default N=5) within a window. Materialise as `CO_CHANGES_WITH`
edges weighted by frequency. Alternative: leave as derived query —
cheaper but slower per-call.

Killer queries:
- "What changes with VendorService?" → top-K co-changers
- "Hidden coupling" — pairs in different packages co-changing often

**G-4. Test-touched-without-test-update detector.** Scan recent
commits for ones that `TOUCHES` a `Class` but no
`(:Method:TestCase)` referencing it. Emit `RegressionRisk` node
linked to the commit. Daily/weekly cron candidate, not a sync-time
operation.

### Phase I — PRs / Issues

**I-1. PR ingest** (`gh api repos/:owner/:repo/pulls`). Per PR:
number, title, author, merged_at, state, base/head sha. `MODIFIES`
edge from `PullRequest` to `Class` via the PR's diff (commits already
in graph from G-1 → reuse).

**I-2. Issue ingest** (`gh api`). `Issue` nodes + `ADDRESSES` edges
from `PullRequest` parsed from PR body / commit messages
(`Closes #123`, `Fixes #456`).

**I-3. Linear / Jira / Azure DevOps adapters** — same shape, different
API. Defer until users ask.

### Phase T-results — Test outcomes

**T-1. JUnit XML ingest.** Read `target/surefire-reports/*.xml` (Maven)
or `build/test-results/test/*.xml` (Gradle). Augment existing
`Method:TestCase` nodes with `lastRun: {status, duration_ms, when}`.

**T-2. Flake rate.** Track last K runs per test, compute pass/fail
ratio. `Method.flakeRate: float ∈ [0, 1]` property.

**T-3. Coverage delta.** Read `jacoco.xml` / `coverage.xml`. Mark
methods uncovered → `coverage: float ∈ [0, 1]` property.

### Phase O — Runtime / observability

**O-1. Sentry** — error events grouped by stack frame. Match top
frame's class:method against graph → `RuntimeError` nodes linked.

**O-2. Datadog APM** — slow spans, error rates per endpoint. Augment
`Endpoint` with `p95LatencyMs`, `errorRate1h`.

**O-3. GitHub Actions** — workflow runs, failed jobs, mean time to
green. Adjacent to PR ingest (Phase I).

Bigger lift — per-vendor adapters. Defer.

### Phase C — CVE / advisories

**C-1. OSV-Scanner integration.** Read `pom.xml` /
`build.gradle` / `package.json` deps; pipe through
`osv-scanner --json`. Emit `CveAdvisory` nodes per finding +
`AFFECTED_BY` edges to the `Class` consuming the dep (heuristic via
import statements — Phase B2.JS.3-style).

**C-2. End-of-life / deprecation feed.** Lower priority. Manual
curated list of "deprecated as of …" library + version.

## 3. Schema additions (cumulative)

```
NODE_TYPES extend:
    "Commit", "PullRequest", "Issue", "RuntimeError", "CveAdvisory"

REL_SCHEMA extend:
    Commit -[:TOUCHES {additions, deletions}]-> Class | JsFunction | Component
    Commit -[:AUTHORED_BY]-> Author     # if we promote authors to nodes
    PullRequest -[:CONTAINS_COMMIT]-> Commit
    PullRequest -[:MODIFIES]-> Class
    PullRequest -[:ADDRESSES]-> Issue
    Issue -[:MENTIONS]-> Class | Method | Endpoint   # via body parsing
    Method -[:HAS_LAST_RUN {status, duration_ms, when}]-> TestRun
    Class | Method -[:CO_CHANGES_WITH {weight}]-> Class | Method
    Method -[:HAS_BLAME {sha, author, date}]-> Commit  # optional, heavy
    RuntimeError -[:OCCURRED_IN]-> Method
    CveAdvisory -[:AFFECTS]-> Class
```

## 4. CLI / MCP surface (sketch)

```bash
# Phase G
onelens git ingest --since 90d --graph my-app          # Commit + TOUCHES
onelens git ingest --since 90d --blame --graph my-app  # + per-file blame
onelens git cochange --window 90d --min-pairs 5 --graph my-app   # CO_CHANGES_WITH

# Phase I
onelens pr ingest --since 90d --graph my-app
onelens issue ingest --since 90d --graph my-app

# Phase T
onelens tests ingest --reports target/surefire-reports --graph my-app

# MCP tools (agent-callable)
onelens_git_hot --graph X --window 90d --limit 10
onelens_blame --fqn com.x.VendorService#approve --graph X
onelens_cochange --fqn com.x.VendorService --graph X
onelens_pr_for --fqn com.x.VendorService --graph X
onelens_issue_for --fqn com.x.VendorService --graph X
onelens_test_status --fqn com.x.VendorServiceTest --graph X
```

## 5. Why this beats competitors

| Tool | Git history | PRs | Tests | Runtime | CVE |
|---|---|---|---|---|---|
| Graphify | ❌ | ❌ | ❌ | ❌ | ❌ |
| GitNexus | ❌ (only `detect_changes` against current diff) | ❌ | ❌ | ❌ | ❌ |
| Sourcegraph | ✅ commit search | ❌ in-graph | ❌ | ❌ | partial |
| blarify | ❌ | ❌ | ❌ | ❌ | ❌ |
| amplihack | conversation memory | ❌ | ❌ | ❌ | ❌ |
| **OneLens after Phase G+I+T** | ✅ + blame + co-change | ✅ + Issue ↔ code | ✅ + flake rate | ⬜ Phase O | ⬜ Phase C |

Combined with our existing PSI moat + Spring/JPA depth + Vue cross-stack
HITS + Doc↔Code MENTIONS, this is the **only graph that connects
business intent (Issue) → code change (PR/Commit) → architecture
(Class/Endpoint) → runtime (Method.lastRun, soon Endpoint.p95)**.

## 6. Phase G-1 ship plan (this turn)

Smallest valuable slice. ~250 LOC.

- `python/src/onelens/importer/git_loader.py` — new module.
- `python/src/onelens/graph/db.py` — `NODE_TYPES` += `["Commit"]`.
- `python/src/onelens/importer/schema.py` — `Commit_sha` index +
  `TOUCHES` rel doc.
- `mcp_server.py` — `onelens_git_ingest(workspace_root, graph, since,
  limit)` MCP tool + `onelens_git_hot(graph, window, limit)` MCP tool.
- Sub-process `git log --numstat --format='COMMIT %H%x09%ae%x09%at%x09%s'`
  parsing. Cap commits at 5000 (configurable). Idempotent MERGE on
  `Commit.sha`.

Deferred to G-2/G-3:
- Blame.
- Co-change.
- Author nodes (today inline `Commit.author`/`Commit.authorEmail`).

## 7. Open questions

- Author privacy: emit raw email vs hash. Default emit raw — index is
  local. Configurable scrub for OSS demo dumps.
- Mono-repo with multiple workspace roots: run `git log` per workspace
  primary root only? Probably yes; cross-root commits don't typically
  touch shared classes.
- Squash-merge histories: a single PR squash hides intermediate commits.
  Phase I-1 PR ingest restores that signal via `commits` API.
- Storage cost: 1000 commits × avg 5 files/commit = 5000 TOUCHES edges.
  Trivial. 100,000 commits × 20 files = 2M edges — still trivial for
  FalkorDB. Cap at `--since 5y` if users hit perf walls.
