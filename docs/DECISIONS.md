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

*To append a new ADR, copy the heading format and add at the
bottom. Do not rewrite or delete earlier entries.*
