# Decision Log

Architectural Decision Records (ADRs) for OneLens. Each entry
captures the decision, the context, the alternatives considered,
and the trigger that would revisit it. Append-only — never
rewrite history.

Format: `ADR-NNN · YYYY-MM-DD · <title>` then a short body.

---

## ADR-001 · 2026-04-17 · Project scaffolded via project-ignition

**Decision.** OneLens's OSS scaffold (`AGENTS.md`, `CODE_OF_CONDUCT.md`,
`SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/*.md`,
`.claude/` dogfood) was generated in a single pass via the
`project-ignition` skill.

**Context.** The baseline "what the project looks like on day one
of public release" is itself a decision worth recording so future
readers know the scaffold was intentional, not accidental.

**Alternatives.** Hand-rolled scaffold (rejected — slow and
inconsistent); third-party generator (rejected — none match the
agent-coding + OSS hygiene combo).

**Revisit when.** The scaffold needs significant rework or a
different project template is adopted.

---

## ADR-002 · 2026-04-17 · Dual-license MIT OR Apache-2.0

**Decision.** Primary code publishes under the dual licence
"MIT OR Apache-2.0". Files carry no per-file licence header; the
root `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE` cover the
entire tree. The pre-existing single-MIT `LICENSE` file was
preserved as `LICENSE-MIT` verbatim and the root `LICENSE` was
rewritten as a dual-licence pointer.

**Context.** MIT alone lacks Apache-2.0's explicit patent grant,
which matters for infrastructure-grade adoption by enterprises.
Dual MIT/Apache-2.0 is the dominant convention for Rust and
increasingly for polyglot OSS tools; it maximises both adoption
(MIT for the risk-averse) and enterprise fit (Apache-2.0 for
legal review).

**Alternatives.** MIT-only (rejected — no patent grant),
Apache-only (rejected — reduces casual-adoption surface),
GPL/AGPL (rejected — corporate hostility).

**Revisit when.** A specific enterprise adopter requires
different licensing, or the OSS landscape shifts enough that
dual-licensing becomes anti-pattern.

---

## ADR-003 · 2026-04-17 · Target agents: Claude Code + Codex (MCP-compatible)

**Decision.** The `.claude/` dogfood setup is authored for Claude
Code primarily. The CLI and MCP server are agent-agnostic: any
MCP-aware client (Cursor, Continue, Cline, Codex) consumes the
same operations via stdio.

**Context.** The project lead's own workflow is Claude Code + bash
+ skill. MCP is the portability layer for other agents; no
dedicated editor integrations ship by default.

**Alternatives.** Claude-only (rejected — reduces reach to one
tool), polyglot editor integrations (rejected — cost of
maintaining five integrations without community demand).

**Revisit when.** A community-contributed adapter for another
specific agent ships and proves useful.

---

## ADR-004 · 2026-04-17 · FalkorDB is the default graph backend

**Decision.** FalkorDB runs on `localhost:17532` (Docker port
mapping) as the default. FalkorDBLite (embedded, no Docker) and
Neo4j are supported via a pluggable `GraphDB` interface.

**Context.** FalkorDB ships a browser UI on `:3001` (huge for
debugging Cypher), supports Cypher, and is lightweight. Neo4j is
heavier and requires auth setup. FalkorDBLite is convenient for
laptops without Docker but has slower cold-start.

**Alternatives.** Neo4j-only (rejected — setup friction),
FalkorDBLite default (rejected — browser UI is too useful to
lose), custom graph storage (rejected — reinvention without
benefit).

**Revisit when.** FalkorDB's licence or maintenance posture
changes, or a user cohort explicitly needs Neo4j-primary.

---

## ADR-005 · 2026-04-17 · MCP server is the source of truth for CLI

**Decision.** Every CLI command is an `@mcp.tool` in
`python/src/onelens/mcp_server.py`. The `cli_generated.py` file
is produced by `fastmcp generate-cli` and is never hand-edited.

**Context.** Keeping CLI and MCP tool surface in two hand-edited
files guarantees they drift. A FastMCP-generated CLI keeps them
lockstep at the cost of a ~4 s import-time overhead on CLI
startup.

**Alternatives.** Hand-maintained CLI + hand-maintained MCP server
(rejected — drift). One-way import from CLI to MCP (rejected —
CLI frameworks don't expose enough metadata).

**Revisit when.** FastMCP's generator can't express a tool we
need, or the import-time overhead becomes a user-facing
complaint.

---

## ADR-006 · 2026-04-17 · PageRank is a boost, not a ranking source

**Decision.** Personalized PageRank scores are computed at import
time (seeded by REST endpoints / `@Scheduled` / `@EventListener` /
`@PostConstruct`), stored as node properties, and used only as a
multiplicative boost on results already matched by FTS + semantic
retrieval. They are *not* an RRF input.

**Context.** Using PageRank as an RRF source leaks
topologically-central but query-irrelevant methods into results.
Using it as a post-match boost preserves retrieval precision
while still surfacing "important" methods first among equals.

**Alternatives.** PageRank as an RRF source (rejected —
verified in benchmarks to hurt precision). No PageRank signal at
all (rejected — leaves "which of these is important" to the
cross-encoder, which has no structural signal).

**Revisit when.** Benchmark suite shows the boost is either not
helping or actively hurting.

---

## ADR-007 · 2026-04-17 · ChromaDB metadata schema is canonical and immutable

**Decision.** Every drawer writes the canonical metadata schema:
`{wing, room, hall, fqn, type, importance, filed_at}`. Both full
and delta write paths use this schema. Deviations break
wing-scoped retrieval silently.

**Context.** A prior bug had `_method_metadata` writing
`{graph, class, file, line}` while `_mine_methods` wrote the
canonical schema, so any delta upsert corrupted the per-graph
scope for downstream searches.

**Alternatives.** Allow adapter-specific metadata (rejected —
silent drift). Validate via a Pydantic model (deferred — will
land when we have a reason to break the schema).

**Revisit when.** A new retrieval dimension genuinely requires a
new metadata key; that's an additive schema change.

---

## ADR-008 · 2026-04-17 · Cascade delete by ID-prefix, not by metadata filter

**Decision.** When a class is removed, its method drawers are
purged by scanning ChromaDB for drawer IDs with prefix
`method:<classFqn>#` and deleting them directly. We do not filter
by metadata.

**Context.** A prior bug tried to delete by a `class` metadata
key that was never written; the operation silently no-op'd and
orphaned drawers accumulated. ID-prefix deletes work regardless
of metadata schema version.

**Alternatives.** Metadata-filter delete (rejected — schema-
version-coupled). Full rebuild on class removal (rejected —
defeats the purpose of delta imports).

**Revisit when.** ChromaDB adds a first-class cascade primitive
that doesn't depend on metadata consistency.

---

## ADR-009 · 2026-04-17 · IntelliJ plugin auto-installs the Python venv

**Decision.** The plugin creates `~/.onelens/venv/` via `uv` on
first sync and installs `onelens[context]` (includes semantic
retrieval dependencies) automatically. Users do not manually
install the CLI.

**Context.** Manual install instructions kill adoption. "Click
sync, watch it work" is the UX bar. `uv` is fast enough that the
first-run cost is acceptable.

**Alternatives.** Ask users to `pip install onelens` themselves
(rejected — friction). Bundle a pre-built Python binary
(rejected — cross-OS packaging cost).

**Revisit when.** `uv` behaves differently on a supported OS, or
we need to support offline/air-gapped installs (part of M2).

---

## ADR-010 · 2026-04-17 · Claude Code skill is bundled into the plugin JAR

**Decision.** `skills/onelens/SKILL.md` is copied into the plugin
JAR at build time (`processResources` in `build.gradle.kts`). The
"Install Skill" action drops it to `~/.claude/skills/onelens/`.
No manual copy step.

**Context.** The skill and the plugin version in lockstep — a
user who installs plugin v0.1.0 gets skill v0.1.0. No version
skew possible.

**Alternatives.** Ship the skill as a separate download
(rejected — two-step install). Inline the skill content into a
Kotlin string (rejected — merges binaries with docs ugly).

**Revisit when.** The skill needs to version independently of
the plugin (unlikely pre-1.0).

---

---

## ADR-011 · 2026-04-17 · Framework-adapter SPI for multi-stack support

**Decision.** Introduce a `FrameworkAdapter` extension point so each
language/framework lives in its own subpackage under
`plugin/src/main/kotlin/com/onelens/plugin/framework/<adapter-id>/`. The
existing Java/Spring collectors are wrapped as `SpringBootAdapter`; a new
`Vue3Adapter` is the second adapter. `ExportService.exportFull` discovers
active adapters via the EP and merges their outputs into a single JSON
document; per-adapter subdocs live under top-level keys (`vue3: {…}`).

**Context.** OneLens was hardcoded to Java: `ExportService` called seven
collectors in a fixed order, `ExportDocument` had flat Java-centric keys,
and `plugin.xml` hard-depended on `com.intellij.modules.java` so the JAR
would not install on WebStorm. Adding a Vue 3 adapter in place would have
duplicated the Java flow; modelling it as a peer via an SPI keeps each
stack's logic self-contained, makes future stacks (Kotlin, Vert.x, FastAPI)
additive, and lets users run a Vue-only sync on WebStorm.

**Alternatives.**

- Single mega-collector per language with hand-rolled switching inside
  `ExportService` (rejected — every new stack would touch the
  orchestrator and `ExportDocument` grows unbounded).
- Separate plugins for Java and Vue (rejected — Marketplace UX worse,
  shared infra like auto-sync and skill install would be duplicated).
- Neo4j Fabric for federated multi-graph queries (deferred — FalkorDB
  lacks `USE <graph>` and switching backends is a much larger change;
  the `wing` property on nodes plus a monograph covers 10+ repos per
  instance, enough until team-hosted scale forces federation).

**Revisit when.** >10 repos per FalkorDB instance and monograph queries
become too noisy, or a stack needs a fundamentally different graph shape
the additive subdoc can't express.

---

## ADR-012 · 2026-04-17 · plugin.xml split via optional config-file deps

**Decision.** `plugin.xml` declares only `com.intellij.modules.platform`
hard. All language/framework machinery goes into stack-specific config
files declared `optional` with `config-file=`:
`framework-springboot.xml` (gated on `com.intellij.modules.java`),
`spring-features.xml` (gated on `com.intellij.spring`),
`framework-vue3.xml` (gated on `org.jetbrains.plugins.vue`).

**Context.** The hard `<depends>com.intellij.modules.java</depends>` in
the original plugin.xml refused installation on WebStorm and PyCharm
Community — exactly the IDEs a Vue / Python user would have. The
IntelliJ platform supports optional deps with config files; adapters
register their extension-point contributions from those files so the
core plugin loads even if a given stack's IDE module is absent.

**Alternatives.**

- Keep the hard Java dep and tell Vue users to install IDEA Ultimate
  (rejected — user's target environment is WebStorm).
- Runtime feature-flag checks inside every Kotlin collector (rejected —
  ClassNotFoundError risk at plugin load; config-file gating happens in
  the platform before anything Kotlin loads).

**Revisit when.** The IntelliJ platform deprecates `config-file` or we
decide to publish separate plugins per stack for Marketplace reasons.

---

## ADR-013 · 2026-04-17 · platformType IU (Ultimate) for dev, runtime portable

**Decision.** `plugin/gradle.properties` sets `platformType = IU` so the
sandbox + test classpath contain the JavaScript + Vue plugins (both
bundled in Ultimate, not in Community). `platformCompatiblePlugins` stays
wired in `build.gradle.kts` for future Marketplace plugins, but is empty
for now. The shipped plugin's `sinceBuild = 251` gates IDE *version*, not
*edition* — combined with ADR-012's config-file split, the JAR installs
cleanly on WebStorm, PyCharm, IDEA Community, and Ultimate.

**Context.** Attempted `compatiblePlugins("JavaScript")` against
`platformType = IC` and hit `No plugin update with id='JavaScript'
compatible with 'IC-251.26927.53' found in JetBrains Marketplace` — the
JavaScript plugin is Ultimate-bundled, not a Marketplace entry. IU is
the only way to get JS + Vue on the test classpath without per-version
version pinning.

**Alternatives.**

- Stay on IC and pin a Marketplace build of the Vue plugin (rejected —
  no standalone JavaScript plugin on Marketplace for IC).
- Dual-build IC + IU in CI with matrix jobs (deferred — not needed until
  we want automated verification on IC-specific code paths).

**Revisit when.** JetBrains ships a standalone JavaScript plugin on
Marketplace for IC, or the Ultimate dev footprint (~1.5 GB) proves too
heavy for contributors.

---

## ADR-014 · 2026-04-17 · Skill layout — single skill, per-stack references

**Decision.** One `skills/onelens/SKILL.md` hub plus
`skills/onelens/references/jvm.md` and `.../vue3.md`. The hub
(~100 lines) stays in context always; references load lazily when the
hub's stack-detection step determines which stack the active wing
belongs to. Plugin bundles both the hub and the references directory;
`InstallSkillAction` copies both.

**Context.** The initial instinct was to create separate
`onelens-jvm` / `onelens-vue3` skills. That would have split triggering
across two descriptions, risked Claude picking the wrong one for
cross-stack questions, and forced duplicated "answer principles" text.
The skill-creator's domain-organization pattern (hub +
`references/*.md`) is the canonical fix: one trigger surface,
progressive disclosure of stack-specific content, cross-stack queries
live only in the hub.

**Alternatives.**

- Two separate skills with independent descriptions (rejected — ambiguous
  trigger for cross-stack questions, doubles install surface).
- Single monolithic SKILL.md (rejected — broke through the recommended
  <500-line budget; non-relevant stack content polluted every
  invocation's context).

**Revisit when.** Enough stacks land (Vert.x, FastAPI, Kotlin) that the
hub itself grows beyond ~200 lines — at that point move the
stack-detection table into `references/stack-detection.md`.

---

---

## ADR-015 · 2026-04-18 · Block-list hook prevents client names leaking in

**Decision.** Add a `PreToolUse` hook
(`.claude/hooks/block-client-names.sh`) that reads
`.claude/hooks/client-names.txt` and refuses any `Write` / `Edit` /
`NotebookEdit` tool call whose `file_path`, `content`, or `new_string`
contains a forbidden term (case-insensitive substring). The block list
is editable only for maintainers; contents stay out of commits by design
because the file itself also counts against the hook (adding a name to
the list and committing it would leak the name).

At the same time we swept the existing tree and rewrote 12 references to
a real-world test-target repo into generic phrasing ("a large Vue 3
repo", "the reference Java backend"). CHANGELOG and PROGRESS call it
out explicitly.

**Context.** The convention section of `CLAUDE.md` already said
"`grep -rIn "<client-name>"` before public push". That rule kept getting
forgotten in-session, and a swath of plugin + docs code shipped with a
specific client repo name embedded. Catching drift at Write/Edit time
turns the rule into enforcement instead of etiquette. The list file +
hook pattern keeps the fix centralized: new client relationships add
one line to `client-names.txt`, retire by deleting the line.

**Alternatives.**

- Keep relying on the manual `grep` convention (rejected — already
  proven unreliable over multiple sessions).
- Add a CI job that greps the working tree (rejected as the *only*
  line of defence — catches drift late, after PRs are already open;
  still a useful second layer).
- Ban the terms via `.gitignore` / `pre-commit` (rejected as sole
  mechanism — pre-commit runs in dev loops only; the Claude-Code hook
  catches the moment an edit is proposed, not just at commit time).

**Revisit when.** The block list outgrows a simple substring match
(multi-word fuzzy matches, regex needs) — at that point swap the
`grep -qiF` core for a Python matcher keeping the same input contract.

---

## ADR-016 · 2026-04-18 · Modal remote — bake weights into image, drop the volume

**Decision.** The Modal embed + rerank image (`python/src/onelens/
remote/modal_app.py`) now pre-fetches `Qwen/Qwen3-Embedding-0.6B` and
`BAAI/bge-reranker-base` at image-build time via
`run_function(_prefetch_weights)`; the former `onelens-models`
`modal.Volume` is removed. The base image also switches from
`debian_slim` to `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` so
`onnxruntime-gpu` actually loads the `CUDAExecutionProvider` instead
of silently falling back to CPU.

**Context.** Cold starts were hitting repeated 9p snapshot-restore
failures — Modal's docs (explicitly) warn that *"Deleting files in a
Volume used during restore will cause restore failures"*. Every
restore failure burned 30 s of tail latency and occasionally wedged
the container. The offending path was the volume-mounted HF cache;
models get periodically evicted / refreshed, which races the restore.

**Alternatives.**
- Keep the volume, make the HF cache read-only (rejected — HF client
  still writes metadata files on resolve; not truly read-only).
- Switch to a pre-downloaded image layer without killing the volume
  (rejected — residual volume mount means same restore race).
- Bake weights into the image, accept the ~2.5 GB growth (**picked**).
  Trade image pull cost once per deploy for zero restore failures and
  strictly-local weight loads on every container.

**Revisit when.** We need > 1 model variant per workspace (Mxbai
large, multilingual reranker, etc.) and image size blows past the
per-deploy pull-cost budget — at which point a pinned snapshot tag
on the volume, combined with `scaledown_window=0` to avoid restores,
becomes the better deal.

---

## ADR-017 · 2026-04-18 · Rerank scores normalized in `Reranker.score`, Modal wrapper passthrough

**Decision.** `python/src/onelens/context/reranker.py` now squashes
raw cross-encoder logits through `sigmoid(x)` before returning.
`python/src/onelens/remote/modal_app.py::Embedder.rerank` is a plain
passthrough over `Reranker.score` — no further transformation.

**Context.** Retrieval filters on `ONELENS_MIN_RERANK_SCORE=0.02`
which assumes a 0-1 probability range. `fastembed.TextCrossEncoder.
rerank` surfaces raw logits (roughly [-10, +10] for bge-reranker-
base), so every hit dropped below threshold and `hybrid_retrieve`
returned an empty list — the regression caught in the Vue-3 dogfood.
A prior fix added the squash only in the Modal wrapper; the local
path (`ONELENS_RERANK_BACKEND=none` or tests instantiating `Reranker`
directly) stayed broken.

**Alternatives.**
- Keep the squash only in Modal, document the local path (rejected —
  silent divergence between backends, future regression magnet).
- Move the threshold to logits-space with per-model calibration
  (rejected — threshold becomes model-specific, breaks the
  swap-the-reranker-backend contract we want to preserve).
- Squash once in `Reranker.score`, Modal wrapper passthrough (**picked**
  — single normalization point, identical range for local and remote).

**Revisit when.** We move to a reranker that already emits
probabilities (certain MiniLM-class checkpoints do); at that point
the sigmoid becomes a no-op at best, slightly harmful at worst, and
should be gated on model metadata.

---

## ADR-018 · 2026-04-18 · FTS Vue query results return prefixed `<type>:<key>` fqns

**Decision.** `python/src/onelens/graph/queries.py` prefixes every
Vue-label FTS result with the matching ChromaDB drawer-id prefix —
`component:`, `composable:`, `store:`, `route:`, `apicall:`,
`jsmodule:`, `jsfunction:`. The returned `fqn` column is treated as
a drawer id by the retrieval layer.

**Context.** Retrieval fuses FalkorDB FTS results and ChromaDB
semantic results via RRF (`_rrf_fuse`) and then resolves `filePath`
/ line ranges with `_fetch_locations_batch`. Both layers key on the
ChromaDB drawer-id shape (`<type>:<key>`). The original Vue-label
queries returned `node.name` / `node.fqn` / `node.filePath` raw —
semantic hits (`route:UsersList`) and FTS hits (`UsersList`) were
treated as different entries by RRF, and the prefix-partitioned Vue
block in `_fetch_locations_batch` skipped any id without a `:`.

**Alternatives.**
- Strip the prefix inside the retrieval layer (rejected — spreads
  the format contract across two files, every new Vue label drops
  back into the same trap).
- Move drawer-id construction into a helper called from both sides
  (deferred — the single-source-of-truth helper is worth doing but
  not gating this fix).
- Prefix at the query source (**picked** — matches the existing
  Component / Composable / Store convention already in the file;
  one-line diff per query).

**Revisit when.** The drawer-id prefix scheme changes (e.g. we
introduce a namespace separator or a wing-scoped id) — at that
point the helper extraction in the deferred alternative becomes
the right move.

---

*To append a new ADR, copy the heading format and add at the
bottom. Do not rewrite or delete earlier entries.*
