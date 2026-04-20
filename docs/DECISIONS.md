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

## ADR-019 · 2026-04-18 · Palace MCP — MemPalace-shaped surface, diverging KG store

**Decision.** Ship a parallel MCP server `onelens-palace` that mirrors
MemPalace's 19-tool interface, but store the temporal knowledge graph
in a dedicated FalkorDB graph (`onelens_palace_kg`) instead of SQLite.
Drawers stay in the existing per-wing ChromaDB collections; no schema
change on the main collection. Agent diaries live in Chroma under
`wing=agent:<name>`. A WAL at `~/.onelens/palace/wal/write_log.jsonl`
records every write.

**Context.** We want a cross-source navigation + fact layer on top of
the code graph. MemPalace already ships this vocabulary
(wings / rooms / halls / drawers / tunnels / triples). Adopting it
verbatim means any agent trained against MemPalace drives OneLens with
zero re-learning. Our code graph already runs in FalkorDB, so a
SQLite-backed KG would force a Python-side join for every `kg_query`
that targets a code FQN.

**Alternatives.**
- SQLite literal parity (rejected — loses structural projection).
- Reuse each wing's graph for triples (rejected — code re-import with
  `--clear` would nuke facts).
- Dedicated FalkorDB graph + structural projection on query (picked).

**Revisit when.** FalkorDB variable-length traversal with predicate
filters stops being a bottleneck — at that point drop the Python-side
hop unroll in `palace_traverse` and deepen `kg_query`.

---

## ADR-020 · 2026-04-18 · Halls as a dual taxonomy — source axis + content axis

**Decision.** Keep OneLens's existing source-axis halls
(`hall_code / hall_git / hall_issues / hall_cicd / hall_runtime /
hall_decisions / hall_docs`) unchanged in `CodeMiner`. Add an
orthogonal content-axis set — `hall_signature`, `hall_event`,
`hall_fact`, `hall_doc` — used by Palace-authored drawers (notes,
diaries, hand-asserted facts). Both vocabularies live in the same
`hall` metadata field.

**Context.** OneLens's `hall_*` constants are a source-of-signal
taxonomy (where did the drawer come from). The Palace plan proposed
splitting `hall_code` into five content classes. Collapsing the axes
would either corrupt source-of-signal semantics or force a ChromaDB
metadata migration on every existing drawer.

**Alternatives.**
- Single taxonomy, full migration (rejected — breaks existing data and
  every hall consumer).
- Drop halls for Palace drawers (rejected — loses content-class filter
  on notes/diaries/facts).
- Dual taxonomy (picked).

**Revisit when.** A third consumer needs a new hall semantic. At that
point promote `hall` to a structured multi-key metadata
(`hall_source`, `hall_content`, ...) and ship a one-shot re-mine.

---

## ADR-021 · 2026-04-18 · Workspace abstraction for multi-repo / multi-module indexing

**Decision.** Introduce an explicit `Workspace` concept above the
IntelliJ-project level. A workspace is declared by a committed
`onelens.workspace.yaml` with N `roots` (each optionally a separate
git repo), a stable `graph` name, and policies for duplicate FQNs,
delta tracking, and per-app PageRank. The plugin, collectors, delta
tracker, and Python loader all consume a single `Workspace` object
instead of reading `project.basePath` / `project.name` directly.
Absent a config file, an implicit single-root workspace is
synthesised — full backward compatibility.

**Context.** OneLens silently equated "IntelliJ project" with "unit of
indexing". That broke in three independent ways for real
multi-module JVM codebases:

1. **Collector scope.** `GlobalSearchScope.projectScope(project)` in
   every collector excluded sibling Maven modules linked via a parent
   pom's `<module>../otherRepo/common</module>` reference. Their
   classes were invisible even though PSI could resolve calls into
   them; the graph got dangling edges to FQNs with no nodes.
2. **File paths.** `file.path.removePrefix(basePath)` on a sibling
   file left a `../otherRepo/...` path that broke snippet fetching
   in Python retrieval.
3. **Full-import loader used `CREATE`** in bulk UNWIND. Plugin-style
   repos routinely fork `com.acme.Constants` across 10+ plugin dirs,
   each a valid compile unit under its own module. One duplicate
   aborted the whole import.

Add to this: the delta tracker ran `git diff` only inside the primary
repo, so changes to a sibling `common/` were invisible; and graph
names were locked to `project.name` with no knob for OSS adopters
who want a stable, CI-friendly graph id.

All of these are symptoms of the same missing abstraction. The fix
is to name that abstraction — **Workspace** — and make every
boundary-sensitive subsystem consume it.

**Alternatives.**

- **Hack `projectScope` to union linked Maven projects only**
  (rejected — hides the concept, doesn't solve delta / loader /
  graph-name problems, keeps one-repo-one-graph assumption).
- **One graph per repo, federation layer on top** (deferred — proper
  answer for cross-*workspace* queries, but doesn't help within a
  workspace that legitimately spans repos, e.g. monorepo + sibling
  lib or plugin-fork architectures).
- **Infer everything from IntelliJ's module graph at sync time**
  (rejected — not reproducible in CI without an IDE; OSS adopters
  running headless builds need a committed file).
- **Per-adapter workspace** (rejected — a workspace is a graph-level
  concern; adapters already share the graph via the `wing` property
  and would have to re-agree on boundaries).

**Revisit when.** Two concrete signals:
(a) A single workspace legitimately needs to span ≥5 git repos and
config ergonomics start to rot — at which point the YAML schema
gains glob roots and per-root inherit semantics. (b) Users demand
cross-workspace federated queries (M3 roadmap item), which is a
*different* abstraction layered on top of workspaces, not a
replacement.

See `docs/workspaces.md` for the config schema and migration notes.
The loader-side blocker is already live:
`python/src/onelens/importer/loader.py::_batch_nodes` switched from
`CREATE` to `MERGE` so duplicate FQNs upsert instead of aborting the
batch. The remaining work (collector-side scope, file-path
normalisation, multi-git delta, policy knobs) lands in v1.2.

---

## ADR-022 · 2026-04-18 · App and Package as adapter-agnostic graph primitives

**Decision.** Promote `App` and `Package` to first-class node types
in the shared graph schema, owned by the core (not any single
adapter). Each `FrameworkAdapter` is responsible for *emitting* App
and Package nodes for its stack, using adapter-appropriate detection:

- `SpringBootAdapter`: `App` per `@SpringBootApplication` (main class
  package + `@ComponentScan` resolution → `SCANS_PACKAGE`). `Package`
  per JVM package.
- `Vue3Adapter`: `App` per detected Vue app root (already implicit
  in `Vue3Adapter.detect()`). `Package` per `src/` subdirectory.
- Future `FastAPIAdapter`: `App` per `FastAPI()` instance; `Package`
  per Python module.
- Future `GoAdapter`: `App` per `main()` package; `Package` per Go
  import path.

Edges: `CONTAINS` (App → Class / Method / Endpoint),
`HAS_CLASS` (Package → Class), `PARENT_PACKAGE` (Package → Package).
`Method.appFqns[]` and `Class.appFqns[]` are denormalised for fast
filter on large graphs.

**Context.** Real microservice monorepos have multiple entrypoints
per repo (the reference motadata server has 18 `@SpringBootApplication`
classes across modules; same pattern appears in JHipster samples,
Netflix OSS, and Spring Cloud demos). Today OneLens flattens them
into one topology: PageRank blends endpoints across apps, impact
analysis can't answer "which service handles this endpoint", and
cross-service call edges are invisible. Every one of those is a
first-order question for architecture-aware AI context.

Package-as-node unlocks aggregation queries (per-package PageRank,
coupling metrics, split-package detection) essentially for free —
classes already carry `packageName`, and the edges are a one-time
derivation pass in the loader.

Keeping both primitives adapter-agnostic means cross-stack queries
work without schema negotiation: "which Vue apps hit endpoints
defined by which Spring apps" joins on `App` + `Endpoint` regardless
of which adapter emitted each node.

**Alternatives.**

- **App-as-Spring-only concept** (rejected — every other framework
  with a main entrypoint needs the same node; duplicating it per
  adapter splits the vocabulary).
- **`packageName` as a property only** (rejected — blocks
  package-level aggregation, can't represent cross-package coupling
  as an edge).
- **Only `App`, no `Package`** (rejected — package aggregation is
  cheap to add alongside and answers a real class of questions).
- **Adapter-specific `App` subtypes** (deferred — may be necessary
  if per-app analysis diverges enough; for now `App.type` as a
  property covers `spring-boot` / `vue3` / `fastapi` / `go`).

**Revisit when.** A framework lands whose "application boundary"
genuinely can't be expressed as `App` with a package-ish membership
rule — e.g. actor systems where boundaries are message-routing
concerns. At that point consider `Scope` as a sibling primitive and
let adapters pick.

---

## ADR-023 · 2026-04-18 · Dual engine — PSI in-IDE, metadata in CI

**Decision.** The long-term architecture has two import engines
behind the same JSON schema: the existing IntelliJ-PSI engine (for
dev-time accuracy) and a headless metadata engine that parses JAR
contents and Spring Boot's standardised metadata files
(`spring-configuration-metadata.json`,
`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`,
`spring.factories`, `spring.binders`) plus bytecode via ASM. Same
export format → same loader → same graph.

**Context.** OSS adoption needs a zero-IDE path: a GitHub Action that
imports a graph on PR, a CLI that runs on a CI box without IDEA
installed. The PSI engine is and remains the accuracy moat — 100%
type-resolved, overload-aware, Spring-plugin-integrated when Ultimate
is available. But it requires a developer to open the project in
IntelliJ, which kills CI and kills adopters who only learn about
OneLens through a PR comment.

The IntelliJ Spring plugin's public API (documented at
`plugins.jetbrains.com/docs/intellij/spring-api.html`,
`com.intellij.spring.*`) gives the PSI engine free access to bean
graph, `@Profile`, `@ComponentScan` class-literal resolution,
`@Import` chain, `spring.factories` auto-config resolution, Spring
MVC endpoint model, and Spring Data query derivation — *if* the user
has Ultimate and the `com.intellij.spring` / `com.intellij.spring.boot`
plugins enabled. The metadata engine gives the CI path a
lower-fidelity but fully accurate-for-what-it-covers subset of the
same information, straight from the standardised files Spring Boot
emits at build time.

Neither engine is privileged. A workspace may be imported by
whichever is available; if both produce exports for the same
workspace, the last one wins on node properties (thanks to
ADR-021's `MERGE`).

**Alternatives.**

- **PSI-only, forever** (rejected — kills CI adoption, kills any
  adopter without IntelliJ).
- **Parse Java source in Python via tree-sitter or javalang**
  (rejected as a primary strategy — no overload resolution, no
  generic inheritance, no `@ComponentScan` class-literal handling;
  acceptable as a *supplemental* source for method bodies in CI mode
  where exact PSI is unavailable).
- **Ship a headless IntelliJ in CI via IDEA Community + scripts**
  (rejected — ~1.5 GB image, slow cold start, licensing surface for
  Ultimate-only APIs is still fragile).
- **Use Spring's own `spring-boot-maven-plugin` at build time to
  emit a richer manifest** (deferred — would require user co-op on
  build config; nice-to-have, not on the critical path).

**Revisit when.** The metadata engine hits a capability gap that
matters enough to block OSS adopters (e.g. users demand transaction
propagation traces from CI, which neither standardised metadata nor
ASM bytecode can reconstruct). At that point consider requiring an
IntelliJ Headless CI adapter as a second-tier CI path, or asking
adopters to generate an augmented manifest via a custom Maven /
Gradle plugin.

Cross-references: ADR-011 (framework adapter SPI), ADR-012
(plugin.xml optional config-file split — makes Spring-plugin API
usage opt-in without hard-coupling core to Ultimate), ADR-021
(workspace abstraction — both engines consume the same workspace
config).

---

*To append a new ADR, copy the heading format and add at the
bottom. Do not rewrite or delete earlier entries.*

---

## ADR-024 · Release snapshots: Lite-first, GitHub Releases primary, cosign-keyless (2026-04-20)

**Decision.** Phase R Stage 1a ships release snapshots as
developer-triggered, Lite-first, distributed through GitHub Releases
with Sigstore keyless signing (`cosign sign-blob` / `cosign
verify-blob`). A pinned `onelens-index` tag hosts a stable-URL
`snapshots.json` catalog; consumers fetch one JSON and never paginate.
The producer bundles `~/.onelens/graphs/<graph>/<graph>.rdb` (+ optional
ChromaDB drawer) into `onelens-snapshot-<graph>-<tag>.tgz` with a
bundle-internal `manifest.json` v3 carrying `schemaVersion`,
`commitSha`, `embedder`, and `falkordbLite` fields. On consumer side
the restored rdb is renamed via `GRAPH.COPY` + `GRAPH.DELETE` so the
internal graph key matches `<graph>@<tag>` (FalkorDB Lite binds the key
into the rdb — filename rename is insufficient).

No CI / webhook / auto-build in Stage 1. No per-branch graphs (live
graph follows HEAD; snapshots are tag-keyed).

**Context.** Teams today share graphs via ad-hoc `scripts/bundle.sh` /
`restore.sh`, which assume Docker FalkorDB, carry no SHA256 or
signature, and don't fit a `<graph>@<tag>` naming scheme. First sync on
a fresh laptop costs 20 min; onboarding + API-diff / regression-hunt
workflows are gated on this. Community pressure from Graphiti-style
temporal models and Sourcegraph-style CI-auto upload was evaluated and
rejected for Stage 1 (see Alternatives).

**Alternatives.**

- **Extend `bundle.sh` to handle Lite.** Rejected — Lite path is
  structurally different (file copy vs `docker exec BGSAVE`), and
  piling both into one bash script hurts reviewability. New Python
  producer + consumer gives typed signatures, testable seams, and
  reuses `httpx` / `hashlib` / `tarfile` / `subprocess` we'd need
  anyway.
- **Graphiti-style bi-temporal invalidation (`valid_at`/`invalid_at`
  per edge).** Rejected — git tags already express time for a code
  graph; adding a temporal predicate to every Cypher hurts query
  cost and readability.
- **Sourcegraph-style CI-auto upload on every commit.** Deferred
  (Phase R.1+) — requires either an IntelliJ headless harness
  (`gradle runIdeForUiTests`) or a standalone Kotlin-CLI extraction
  of the collectors (not started). Stage 1 ships the manual
  developer-triggered CLI path so adopters aren't blocked on CI work
  that has a clear operational owner.
- **Ed25519 / GPG signatures.** Rejected — key management burden
  with no transparency log. Sigstore keyless (OIDC → Fulcio → Rekor)
  is the modern 2026 baseline for OSS dev-tool artifacts.
- **Ship `snapshots.json` pagination.** Rejected for Stage 1 — at the
  observed cadence (normal tagging, ~20-250 snapshots per repo over
  years) one flat JSON fits comfortably in a CDN-cached asset.
  Revisit when any single repo's catalog exceeds 500 entries.
- **Publisher-side graph-key rename (COPY/DELETE at bundle time).**
  Rejected — the rename cost (load 200k nodes into redislite → COPY
  → DELETE → SAVE) is paid every publish. Moving it to consumer-side
  pull means it happens once per restore, and publish stays a fast
  file copy + metadata write.
- **Embed `manifest.json` outside the tarball.** Rejected — schema
  version + FalkorDB version must travel with the artifact to guard
  against consumer/producer drift. SCIP's "metadata travels inside"
  pattern applies.
- **Per-branch graphs as the snapshot mental model.** Rejected —
  50 GB+ disk at 1000 branches on a typical workstation; branches
  are handled by the existing live graph + delta sync, not by
  snapshots.

**Revisit when.** (a) We ship the headless-collector CLI — promotes
Phase R Stage 1 (manual) to CI (Phase R.1 auto). (b) A single repo's
snapshot catalog crosses ~500 entries, requiring pagination on
`snapshots.json`. (c) We launch the Cloud tier — at which point
coordination across repos, RBAC, and audit replace the CLI + GitHub
Releases workflow for enterprise orgs (Cloud is strictly additive;
OSS keeps everything above intact forever).

Cross-references: ADR-022 (FalkorDB Lite as default backend — the
substrate snapshots ride on), ADR-023 (metadata engine — future CI
path for snapshot producers without IntelliJ), `docs/design/phase-r-release-snapshots.md`
(full spec).

## ADR-025 · One tool window with tabs, not multiple sidebar entries (2026-04-20)

**Decision.** OneLens ships a single IntelliJ tool window (`OneLens`,
right anchor) with `Content` tabs for each surface — `Status` today,
`Snapshots` shipped in Phase R Stage 1b, `Query` / `Retrieve` /
`Diff` reserved for later. Secondary tool windows (`OneLens Snapshots`,
etc.) are rejected.

**Context.** Phase R Stage 1b initially shipped a separate `OneLens
Snapshots` tool window to avoid touching the working Status panel.
Resulting UI had two separate sidebar entries with duplicated graph /
backend context, split mental model, and unclear home for new Publish
/ Pull actions. Future Phase R.1+ work adds more surfaces (Query
console, Retrieve NL search, Diff); continuing the pattern would
balloon to 4–5 sidebar icons for one plugin.

**Alternatives considered.**
- *Secondary tool window per feature.* Rejected: sidebar clutter, no
  shared header, duplicated graph/backend display, each feature
  relearns the same state wiring.
- *Single flat panel with sections.* Rejected: doesn't scale past 3
  surfaces; Cypher console and snapshot list want full panel real
  estate each.
- *Modal dialogs for ephemeral surfaces (Publish/Pull).* Kept for
  Publish because publishing is a one-shot action; rejected for
  Snapshots list because listing is a persistent workspace concern
  that benefits from being parked in the sidebar.

**Consequences.**
- Single `<toolWindow id="OneLens">` in `plugin.xml`; adding a tab is a
  one-line change in `OneLensToolWindowFactory.createToolWindowContent`.
- Shared header + graph picker + backend badge can be extracted as a
  reusable `JBPanel` (Phase 2) without touching tab content.
- Actions live in a single `OneLens.Actions` action group so any tab
  can surface a button via `ActionManager.getInstance().getAction(id)` —
  Publish is mirrored on Status toolbar + Snapshots toolbar without
  code duplication.
- Future framework adapters (Vue3, Spring) can contribute tabs via a
  future `oneLensTab` extension point, preserving the
  single-tool-window contract.

**Revisit when.** (a) A tab's responsibilities grow beyond what a
single vertical panel can carry and splitting into a dedicated tool
window becomes genuinely simpler. (b) We add a truly orthogonal
surface (e.g. a project-wide settings dashboard independent of the
current graph) that doesn't share the Status header.

Cross-references: ADR-009 (plugin auto-installs Python venv — same
principle: one visible touchpoint, orchestrate the rest),
ADR-011 (framework-adapter SPI — guides the future
`oneLensTab` extension point shape).

## ADR-026 · Snapshot-as-seed marker = one-shot, not permanent baseline (2026-04-21)

**Decision.** When a user promotes a release snapshot to be the live
graph's seed ("Start working from this snapshot"), the plugin writes
`~/.onelens/graphs/<graphId>/.onelens-baseline` — a JSON file
carrying `{tag, commitSha, promotedAt, schemaVersion, producerVersion,
embedder}`. The marker is **consumed (read + deleted) at DeltaTracker
entry on the next sync**, not cleaned up on a separate SyncComplete
event. One-shot lifecycle: seed once, then every subsequent sync is
normal last-export-timestamp diff. There is no permanent
"baseline" field on every export.

**Context.** Phase R Stage 1d ships the onboarding shortcut: new dev
pulls a shared release snapshot, promotes it, and Sync Graph deltas
the branch diff from tag commit instead of doing a 20-min full
reindex. Two design axes had to be chosen:

1. Marker lifecycle — one-shot consume vs permanent sidecar.
2. Marker placement — co-located with artifact vs central registry.

**Alternatives considered.**

- *Permanent `baseline` field on every export state record.* Rejected:
  snapshots are an onboarding shortcut, not a long-term contract.
  A permanent baseline would fight with branch switches (merge commits
  disconnect the lineage), squash merges (tag commit disappears from
  history), and the single-repo mental model (one live graph = one
  ongoing state, not "forever-diffed from 8.7.4"). Users who want
  durable per-branch state want Phase 1f per-branch live graphs, not a
  sticky baseline.
- *Content-addressed baseline (Nix/Bazel pattern — hash the snapshot's
  rdb, key the diff by hash, not commit).* Rejected: our delta is
  git-diff-driven, not input-hash-driven. Hashing an rdb doesn't help
  when the question is "which Java files changed since commit X?".
- *SyncComplete listener cleanup (write marker at promote, delete on
  successful sync).* Rejected: two-sync race where the second sync
  fires before the first's listener clears the marker would re-apply
  the seed twice. Consume-at-entry eliminates the race at the cost of
  one scenario (sync fails mid-run → marker gone → next retry falls
  back to full sync; but full sync is correct, just slow).
- *Central registry file `~/.onelens/promotions.json`.* Rejected:
  co-located dotfile next to the artifact is the dominant pattern
  (`.git/shallow`, `CACHEDIR.TAG`, `PG_VERSION` in PostgreSQL data
  dirs). Registry adds a single-point-of-failure for no concurrency or
  discoverability benefit at our scale.

**Consequences.**

- DeltaTracker has exactly one integration point — `consumeBaselineMarker`
  reads + deletes at the top of `getChangedFiles`. Any caller that
  doesn't go through DeltaTracker (e.g., a direct CLI `git diff`) won't
  consume the marker, so it persists until the next Sync via the IDE.
  Acceptable: the marker is advisory; live graph works either way.
- Schema-version mismatch (`marker.schemaVersion != plugin's 3`) =
  discard marker, fall back to full sync. Matches SharedIndexes
  precedent — prevents silent cross-version corruption when a v1.2
  snapshot is promoted inside v1.4.
- Atomicity order at promote time (rdb → GRAPH.COPY rename → context
  → marker) means a half-applied seed never writes a marker. Partial
  state is recoverable via "run Sync Graph, it'll full-sync fresh."
- `promotedAt` is UTC ISO8601 (not epoch ms) — cross-TZ devs see
  sensible timestamps.

**Revisit when.**

- **Phase 1f (per-branch live graphs) ships.** Per-branch graphs
  would want a durable "this graph's baseline is @X" contract, not
  a one-shot marker. Promote would become a lookup key, not a seed
  action.
- **A snapshot lineage / provenance log is requested.** Today the
  marker vanishes after first sync; no record of "live graph was
  seeded from @8.7.4 on 2026-04-21." If users want debugging/audit
  history, add a separate append-only log (`~/.onelens/graphs/<g>/.onelens-seeds`)
  alongside the one-shot marker — orthogonal.
- **Multiple concurrent dev machines sharing a network `~/.onelens/`.**
  The marker isn't file-lock protected; two machines reading the
  same marker would both consume it. Unlikely (each dev has local
  `~/`), but if it happens, wrap `consumeBaselineMarker` in a
  file-lock.

Cross-references: ADR-007 (ChromaDB metadata schema canonical — seed
must promote context atomically with rdb to avoid wing/room/hall drift),
ADR-024 (Lite-first snapshots — substrate this builds on),
ADR-025 (unified tool window — right-click menu on snapshot rows is
where `Start working from this snapshot` lives),
`docs/design/phase-r-stage-1d-snapshot-as-seed.md` (full spec).

