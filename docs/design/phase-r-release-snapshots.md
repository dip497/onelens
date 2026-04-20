# Phase R — Release Snapshots

> Status: Draft (2026-04-20). Owner: OneLens core. Supersedes the ad-hoc `bundle.sh` / `restore.sh` share flow.

Release Snapshots turn OneLens from a "single developer's graph" into a
**shareable, versioned, historical** artifact. Each software release
produces an immutable indexed graph (`<graph-name>@<tag>`) published to
GitHub Releases; teammates `pull` and query side-by-side with live dev
graphs. Unlocks API-diff, regression-hunt, and onboarding workflows
without the 20-minute embedding pass.

---

## 1. Problem statement

Today, sharing a built OneLens graph requires `scripts/bundle.sh` +
`scripts/restore.sh` over an ad-hoc channel (SCP, NFS share). That works
for a 2-person team and nobody else.

What we actually want:

- **Immutable per-release graphs** — `myapp@v1.0.0` is the exact
  graph captured at tag `v1.0.0`, forever. Queries against it are stable.
- **Zero-setup onboarding** — new hire runs one command, has main's graph.
- **Cross-release diff** — "what endpoints changed between v1.5 and v2.0?"
  as a Cypher set-diff, not a manual swagger review.
- **CI-built** — developers don't own the publishing, a release workflow
  does.
- **Free for OSS users** — GitHub Releases as transport; no server infra
  until an org demands one.

## 2. Non-goals

- Automatic branch-per-graph (addressed in a separate Workspace-C
  extension; distinct mental model).
- Bi-temporal invalidation à la Graphiti — git tags already express time.
- Automatic snapshot GC / retention policies (manual `gh release delete`
  for v1; enterprise adds policy later).
- Real-time cross-repo query federation — stays Cloud-tier (§5).

## 3. Use cases

| # | Role | Question | Works today? |
|---|---|---|---|
| 1 | Backend dev | "What endpoints were removed between v1.5 and v2.0?" | No — one graph only |
| 2 | QA / release eng | "Which migrations ran between two release tags?" | No |
| 3 | Security eng | "What code existed at v1.0.0 when CVE-X was reported?" | No — graph was overwritten |
| 4 | New hire | "I have a fresh checkout, how do I get a ready graph?" | 20-min first sync |
| 5 | PM | "How did our public API surface grow over the last 3 releases?" | Manual Swagger diff |
| 6 | Tech lead | "Run /onelens against v2.0.0 before approving the RC" | No — no stable target |

## 4. OSS scope (ships in Phase R, free forever under Apache-2.0 / MIT)

Everything needed for a 5-person team to run the full workflow without
paying anyone.

### 4.1 Artifact format

```
onelens-snapshot-<graph>-<tag>.tgz
├── manifest.json                 # schema version, embedder, FalkorDB version,
│                                 #   source commit sha, build timestamp,
│                                 #   collector versions, bundle size
├── graphs/<graph>@<tag>/*.rdb    # FalkorDB Lite data
├── context/<graph>@<tag>/        # ChromaDB (optional — gated by
│                                 #   --include-embeddings flag)
└── README.md                     # restore instructions
```

- `manifest.json` schema is versioned (`manifestVersion: 1`); future
  producers add fields, older consumers ignore unknown keys. Never remove
  keys — deprecate instead.
- FalkorDB Lite rdb files are **version-coupled to the FalkorDB binary**.
  Bake FalkorDB version into manifest + filename. Consumer refuses to
  load on major-version mismatch, warns on minor.

### 4.2 Distribution — GitHub Releases (primary)

Why GitHub Releases:

- 2 GiB per asset (400 MB bundles fit 5×), no bandwidth metering, no
  hidden GitHub LFS trap (documented pitfall — LFS has a 1 GB/month
  free bandwidth cap that destroys large-artifact UX).
- Every OSS repo already has it. Zero new infra.
- `gh api /repos/{o}/{r}/releases` enumerates tags. Machine-readable.

**Publishing** (R1 — CLI):

```bash
onelens snapshot publish v1.0.0 \
  --graph myapp \
  --include-embeddings \
  --repo myorg/myapp
# → syncs → bundle.sh → gh release upload → cosign sign → slsa attest
```

**Consuming** (R2 — CLI + MCP):

```bash
onelens call-tool onelens_snapshots_list --graph myapp
# returns [{tag, size, published_at, verified}]

onelens call-tool onelens_snapshots_pull --graph myapp --tag v1.0.0
# → downloads → cosign verify-blob → restore.sh → graph myapp@v1.0.0
```

**Published assets per release:**

| File | Purpose |
|---|---|
| `onelens-snapshot-<graph>-<tag>.tgz` | The bundle |
| `onelens-snapshot-<graph>-<tag>.tgz.sha256` | Checksum, one line |
| `onelens-snapshot-<graph>-<tag>.tgz.sig` | Cosign signature bundle |
| `onelens-snapshot-<graph>-<tag>.intoto.jsonl` | SLSA v1.0 provenance |

### 4.3 Static manifest — `snapshots.json`

One **pinned** release (tag `onelens-index`) hosts a single asset at the
stable URL `/releases/download/onelens-index/snapshots.json` containing
all published snapshots:

```json
{
  "graph": "myapp",
  "snapshots": [
    { "tag": "v2.0.0", "size": 412334567, "sha256": "…",
      "schemaVersion": 3, "embedder": "Qwen3-0.6B",
      "falkordbLite": "0.9.2", "includesEmbeddings": true },
    { "tag": "v1.0.0", "size": 398123456, "sha256": "…",
      "schemaVersion": 2, "embedder": "Qwen3-0.6B",
      "falkordbLite": "0.9.1", "includesEmbeddings": false }
  ]
}
```

- Consumer fetches ONE JSON, no pagination. CDN-cached by GitHub.
- `schemaVersion` lets the skill branch queries on availability —
  `EnumConstant` appears at v2+, dual-labels at v3+.
- Maintained by the CI action (R5); `onelens snapshot publish` can update
  it locally in the `--no-ci` path.

### 4.4 Signing & provenance — Sigstore + SLSA

Modern 2026 baseline. Not optional for anything OSS users will put in CI.

**Signing — Cosign keyless** (OIDC → Fulcio → short-lived cert →
Rekor-logged):

```yaml
# .github/workflows/snapshot-on-release.yml
- uses: sigstore/cosign-installer@v3
- run: cosign sign-blob --yes --bundle=${{ matrix.bundle }}.sig ${{ matrix.bundle }}
```

**Provenance — SLSA v1.0 Level 3** via
`actions/attest-build-provenance`. `.intoto.jsonl` posted alongside each
bundle. Consumer verifies:

```bash
cosign verify-blob --bundle bundle.sig --certificate-oidc-issuer https://token.actions.githubusercontent.com bundle.tgz
```

`onelens_snapshots_pull` runs this automatically; fails closed on
unverified bundles unless `--no-verify` is passed.

### 4.5 Skill integration — new recipe `references/recipes.md #16`

Canonical cross-release queries documented for Claude agents:

```cypher
// Endpoints removed between v1.5 and v2.0
MATCH (e1:Endpoint) WHERE e1.wing = 'myapp@v1.5.0'
OPTIONAL MATCH (e2:Endpoint)
  WHERE e2.wing = 'myapp@v2.0.0' AND e2.path = e1.path
WITH e1, e2 WHERE e2 IS NULL
RETURN e1.method, e1.path
```

(Requires cross-graph query — see §6 open question 3.)

### 4.6 Self-hosted backend (still OSS)

For air-gapped / privacy-sensitive users who can't use GitHub Releases:

- `onelens snapshot publish --backend s3://bucket/prefix` → uploads to
  any S3-compatible endpoint (AWS, MinIO, Backblaze B2). Emits the same
  `snapshots.json` manifest.
- `onelens snapshot pull --source https://my-minio/…/snapshots.json`
  consumer-side.
- Cosign signing still works (keyless OIDC only requires GitHub Actions
  runtime; self-hosted can fall back to `cosign generate-key-pair`
  with a documented keyring).

Kept in the OSS repo. The distinction from Cloud is **coordination, not
transport**.

## 5. Enterprise scope (OneLens Cloud, later)

Strictly additive — OSS users never lose capability.

### 5.1 Snapshot Portal

Central registry for N repos across an org, single browse-all URL.

**Why this can't be OSS:** GitHub Releases + `gh api` scales to dozens
of repos with manual bookkeeping; at 50 repos × 20 releases = 1,000
snapshots, discovery ("which repos have v2.0.0 published?", "who
queried the CVE graph when?") needs a server. OSS users with <10 repos
don't feel this.

### 5.2 RBAC + audit log

- Per-graph ACL (contractor sees `feature/*` only; full-time sees `main`).
- Query audit trail (who ran what Cypher against which snapshot when).
- SOC 2 / ISO 27001 export.

**Why this can't be OSS:** public GitHub Releases is all-or-nothing; no
way to express "this bundle is visible to group X." Requires auth'd
storage, which requires a server.

### 5.3 Webhook-driven auto-build

- GitHub App listens to release events → builds snapshot in managed
  runners → publishes to portal.
- Removes the "dev runs `onelens snapshot publish`" step entirely.

**Why this can't be OSS:** managing GH App credentials, a build farm,
and per-repo webhooks is SaaS operational work. OSS tier offers the
CI workflow template (R5); org pays to not run it.

### 5.4 Org-wide diff dashboard (web UI)

Visualization of API churn, dead-code growth, dependency drift across
the release history. Stakeholders who don't run Claude (PMs, compliance,
QA directors).

**Why this can't be OSS:** web UI is a full product. OSS gives the
underlying Cypher queries (recipe #16) — anyone can build a notebook.
Cloud ships the polished, opinionated view.

### 5.5 Shared semantic index

80 devs × 84k methods × Qwen3 = wasted GPU-hours. Cloud embeds once,
serves to all; org saves 99% of inference cost.

**Why this can't be OSS:** requires a hosted vector store with auth.
Individual users run ChromaDB fine.

### 5.6 Managed custom collectors

Enterprise onboarding contracts include OneLens team writing adapters
for proprietary frameworks (internal code generators, bespoke ORMs).
Upstreamed to OSS when generalizable.

**Why this is enterprise:** engineering hours, not capability.

---

## 6. Engineering plan

### R1 — CLI snapshot publisher (~4 hrs)

**Scope:** `onelens snapshot publish <tag> --graph <name> [flags]`.

Shell-out to existing `bundle.sh` under the hood; add:

- Git tag existence check (`git rev-parse <tag>`).
- Graph clean-state check (DeltaTracker → "no pending delta").
- Filename convention: `onelens-snapshot-<graph>-<tag>.tgz`.
- Writes `manifest.json` inside the tarball with:
  `{manifestVersion, graph, tag, commitSha, schemaVersion, embedder,
    falkordbLite, includesEmbeddings, buildTimestamp, collectorVersions}`.
- Optional `--include-embeddings` (off by default — halves bundle size).
- `--repo <org/repo>`: shells out to `gh release upload <tag>`.
- `--backend s3://…`: uploads to S3-compatible endpoint.
- Emits `.sha256`.

**Success:** `onelens snapshot publish v0.1.0 --graph myapp`
produces a tarball on GitHub Releases under the repo's `v0.1.0` tag.

### R2 — Consumer CLI + MCP tools (~3 hrs)

**New MCP tools (`python/src/onelens/mcp_server.py`):**

- `onelens_snapshots_list(graph, repo=None)` → reads `snapshots.json`
  manifest (static URL) OR paginates `gh api` fallback.
- `onelens_snapshots_pull(graph, tag, repo=None, verify=True)` →
  downloads bundle, cosign-verifies unless `verify=False`, restores
  via `restore.sh`, registers as `<graph>@<tag>`.

Adds ~150 LOC to `mcp_server.py`, ~50 LOC CLI wiring.

### R3 — Skill integration (~1 hr)

**`skills/onelens/references/recipes.md`:** new recipe #16
"cross-release diff" with 4 canonical patterns:

1. Endpoint surface diff.
2. Method signature change detection (same FQN, different return /
   parameter types).
3. Dead-code delta (methods present in old tag, absent in new).
4. SQL migration inventory between tags.

**`SKILL.md`:** add decision-tree row `"compare two releases / API diff"
→ recipes.md #16`. Document the cross-graph `wing` filter pattern
(every OneLens node already carries `wing = '<graph>@<tag>'` when
loaded from a snapshot).

### R4 — Plugin UX (~3 hrs)

- Status panel: "Snapshots: v1.0.0, v1.1.0 · [Fetch latest]" row.
- OneLens tool window: dropdown to select active query target
  (live graph vs a specific snapshot).
- "Install Snapshot" action wrapping `onelens_snapshots_pull`.

### R5 — CI snapshot producer (~1 day)

**The unknown:** headless plugin sync in CI. Three realistic paths:

- **(a) `gradle runIdeForUiTests` harness** — IntelliJ's own test
  runner. Works but heavy CI runners + fragile. Reference:
  intellij-platform-plugin-template.
- **(b) Extract collectors into a standalone Kotlin CLI** — reuse
  `plugin/src/main/kotlin/com/onelens/plugin/export/collectors/*.kt`
  without the IDE. Requires `ProjectEnvironment` setup (AnalysisAPI or
  Kotlin Compiler testbed).  Viable; ~2-3 days' work.
- **(c) Ship R1 manual workflow only in Phase R** — dev runs
  `onelens snapshot publish` on tag push, period. CI is Phase R.1.

**Ship (c) in R5. Defer (b) to Phase R.1** — avoids blocking R1-R4 on
the headless collector unknown.

### R6 — (Phase R.1) Headless collector

Separate phase. Path (b) — standalone Kotlin CLI wrapping collectors.
Enables fully automated CI. Not blocking OSS launch.

---

## 7. Schema drift & backward compatibility

Snapshots published on v0.1 of OneLens lack features added in v0.2
(e.g., dual-labels, `JpaColumn`). Three guard mechanisms:

1. **`schemaVersion` in manifest** (inside tarball AND in
   `snapshots.json`). Monotonic int; bump on any collector output change.
2. **Skill recipes branch on `schemaVersion`** — recipe #16 has an "if
   schemaVersion < N, use fallback Cypher without feature X" section.
3. **Refuse-to-load bands** — consumer refuses snapshots with a
   `schemaVersion` more than 1 major behind current `onelens-cli`.
   Forces stale snapshot republish rather than silent wrong results.

**Policy:** producer NEVER removes fields from manifest; only adds.
Consumer tolerates unknown fields. Classic forward-compat.

## 8. Migration from existing `bundle.sh` users

`bundle.sh` stays. `onelens snapshot publish` is the documented
workflow, but power users who script against `bundle.sh` directly are
unaffected. No deprecation; `publish` is strictly higher-level.

`restore.sh` gains a deprecation warning when called against a bundle
without a manifest (pre-Phase-R bundles). Told to use
`onelens snapshot pull`.

---

## 9. Go-to-market staging

**Stage 1 — OSS completeness (ship now, 8-10 hrs total):**
R1 + R2 + R3 + R4. Release as OneLens v0.3.0 minor. Blog post:
"Share your code graph across a team in one command."

**Stage 2 — OSS polish (~3 months later):**
R5 (CI producer) + R6 (headless collector). Removes the
"dev runs publish" step. Release as v0.4.0.

**Stage 3 — Commercial (post-OSS adoption signal; ≥6 months out):**
OneLens Cloud — Snapshot Portal + RBAC + dashboard + shared embeddings.
Pricing: per-repo-indexed/month ($99/repo, volume discount over 10
repos). Enterprise tier custom-priced with SSO, SOC2, on-prem option.

**Adoption signal for Stage 3:** 1000 GitHub stars, 20 external
contributors, 50 orgs running OSS (detected via optional Scarf Gateway
telemetry — opt-in only).

---

## 10. Success metrics

**Stage 1:** Can a teammate go from "nothing installed" to "querying
the graph at v1.0.0" in ≤3 minutes using only the README?
Bundle-download bandwidth < 1 GB/mo for early adopters (bumps us into
the "plausible to share publicly" category).

**Stage 2:** 80% of releases across the 10 most-active forks have a
snapshot published automatically.

**Stage 3:** 10 paying orgs by month 12 post-Cloud launch. $10k MRR.

---

## 11. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Sourcegraph-style license backlash | Medium | Never remove OSS features; only add Cloud. Document commitment in `GOVERNANCE.md`. |
| Bundle > 2 GB GitHub asset cap | Low | zstd (saves 30-40%); graph-only (no embeddings) default; split tarball if needed. |
| Schema drift silently breaks old snapshots | Medium | `schemaVersion` refuse-to-load band + skill fallback recipes. |
| FalkorDB Lite version mismatch | Medium | Version bake into manifest + filename; consumer refuses mismatch. |
| Cosign verification fails on self-hosted (no OIDC) | Low | Document keyring fallback; offer `--no-verify` escape hatch with warning. |
| GitHub rate limits on public anonymous pulls | Low | Caching CDN front (GitHub Releases already CDN'd); optional Scarf Gateway with PAT config. |
| Dev forgets to publish on tag (R1 manual) | High | R5 CI closes this; until then, document the release checklist. |

---

## 12. Open questions

1. **Cross-graph query ergonomics.** FalkorDB Lite holds one graph per
   DB instance. A single-query `UNION` across `<graph>@v1` and
   `<graph>@v2` is not possible; must run two queries and join
   client-side. Is that acceptable for recipe #16, or do we want a
   `onelens_diff` helper tool that orchestrates?
2. **Snapshot granularity below tag.** Should we allow
   `onelens snapshot publish nightly-<date>` alongside tags? Useful for
   non-tag-releasing projects. (Low priority; v1 is tag-only.)
3. **Embedding model evolution.** If we swap Qwen3 for something else
   later, old snapshots' embeddings are unusable. Manifest must include
   `embedder` so consumers know; skill's semantic-retrieval recipes
   must gate on model match. Is automatic re-embedding on pull
   acceptable, or opt-in?
4. **Scarf Gateway in front of GitHub Releases.** Privacy benefit vs.
   telemetry collection — align with project governance.
5. **License of enterprise-only modules.** When we ship Cloud, how
   do we license the portal code — closed-source SaaS? SSPL? BUSL?
   Decide before first Cloud commit.

---

## 13. References

- [GitHub Releases — About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) — 2 GiB/asset cap, no bandwidth meter.
- [Sigstore Cosign](https://docs.sigstore.dev/cosign/overview/) — keyless signing pattern used throughout 2026 OSS tooling.
- [SLSA v1.0 spec](https://slsa.dev/spec/v1.0/levels) — Level 3 via `actions/attest-build-provenance`.
- [Sourcegraph's 2023 license change retrospective](https://github.com/sourcegraph/sourcegraph/issues/53528) — the anti-pattern we avoid.
- [Graphiti incremental model](https://github.com/getzep/graphiti) — confirmation that additive/immutable updates are the industry direction.
- [SCIP metadata-travels-with-artifact pattern](https://docs.sourcegraph.com/cli/references/code-intel/upload) — influences manifest.json in bundle.
- [Scarf Gateway](https://github.com/scarf-sh/gateway) — optional download analytics for OSS.
- [OneLens bundle.sh / restore.sh](../../scripts/bundle.sh) — the existing OSS share flow this spec formalizes.
