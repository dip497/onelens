# Roadmap

Pre-1.0. Aspirational and subject to change. Current release line:
`0.1.0`.

Companion docs:
- [VISION-AND-ROADMAP.md](./VISION-AND-ROADMAP.md) — longer narrative.
- [PROGRESS.md](./PROGRESS.md) — per-feature tracker (what's shipped,
  in progress, deferred).
- [DECISIONS.md](./DECISIONS.md) — ADR log.

## M1 — "OneLens works end-to-end on one Spring Boot monolith" (shipping now)

Ship criteria: *a 10K-class project goes from `git clone` to
AI-queryable graph in under 30 minutes, with < 5 s delta re-sync
on file save.*

Included:

- [x] IntelliJ plugin with PSI-based full export.
- [x] Python CLI with FalkorDB import + weighted FTS.
- [x] Impact analysis (`onelens impact`) with polymorphic + bean
      narrowing.
- [x] Execution trace (`onelens trace`).
- [x] Delta export + delta import.
- [x] Semantic search (Qwen3 + ChromaDB + mxbai rerank).
- [x] Hybrid retrieve with query router + PageRank boost.
- [x] MCP server as single source of truth for CLI.
- [x] Plugin auto-installs Python venv via `uv`.
- [x] Bundled Claude Code skill + install action.
- [x] Auto-sync on file save (debounced).
- [x] GitHub Actions: CI + tagged release.
- [x] 95%+ on the internal retrieval benchmark suite.

Deferred:

- [ ] Public benchmark dataset (sanitised).
- [ ] Windows-native packaging (works via WSL today).

## M2 — "OneLens is adoption-ready across teams"

Ship criteria: *a second engineering org can adopt OneLens without
custom patches.*

- [x] Multi-project graphs in one FalkorDB instance (via the `wing`
      property on every node; cross-wing `HITS` edges link Vue
      ApiCall ↔ Spring Endpoint).
- [x] Framework-adapter SPI (`FrameworkAdapter`) so new stacks land
      additively. Java/Spring and Vue 3 ride on it today.
- [x] Vue 3 adapter (full import): Components, Composables, Stores,
      Routes, ApiCalls, USES_STORE (direct + 1-hop indirect),
      USES_COMPOSABLE, DISPATCHES, CALLS_API, HITS cross-stack bridge.
- [x] Full-loader `MERGE` — duplicate FQNs no longer abort bulk
      imports (2026-04-18). See CHANGELOG `[Unreleased]`.
- [ ] **Workspaces (Phase C).** Declarative
      `onelens.workspace.yaml` with N roots, stable graph id,
      policies for duplicate FQNs / multi-git delta / per-app
      PageRank. Unblocks multi-module + sibling-repo JVM
      codebases. Design landed (ADR-021, `docs/workspaces.md`);
      collector-side scope + loader policy knobs are the next
      code changes. Non-JVM adapters ride the same abstraction.
- [ ] **`App` + `Package` as adapter-agnostic graph primitives**
      (ADR-022). `SpringBootAdapter` emits `App` per
      `@SpringBootApplication`; `Vue3Adapter` emits `App` per
      detected Vue root; future stacks follow the same rule.
      Enables per-app PageRank and cross-stack queries like
      "which Vue apps hit endpoints defined by which Spring
      apps".
- [ ] IntelliJ marketplace listing.
- [ ] Hardened `uv` / `pip` fallback for air-gapped environments.
- [ ] Incremental PageRank on delta imports.
- [ ] Vue delta + auto-sync (Phase B2 — `DeltaTracker`, file listener,
      and `delta_loader` Vue branch).
- [ ] Kotlin project support (PSI already covers it; needs
      collector audit + tests).
- [ ] Public benchmark harness so adopters can measure on their
      own code.

## M3 — "OneLens is the default Java context provider for AI
coding"

Ship criteria: *one well-known Spring Boot OSS project or one
named enterprise org adopts OneLens as their default AI context
source.*

- [ ] First-class MCP integration in Cursor / Continue / Cline (not
      just Claude Code).
- [ ] TypeScript / Python collector spikes.
- [ ] Cross-repo graph stitching (monorepo + satellite services).
- [ ] Hosted retrieval option for orgs that don't want to run
      FalkorDB + embedding models themselves.
- [ ] **Dual import engine** (ADR-023) — IntelliJ Spring plugin
      API for in-IDE accuracy (bean graph, `@Profile`,
      `spring.factories`, `AutoConfiguration.imports`, Spring MVC
      endpoint model, Spring Data query derivation), headless
      metadata engine for CI (parses
      `spring-configuration-metadata.json`,
      `AutoConfiguration.imports`, `spring.factories`,
      `spring.binders`, plus ASM bytecode). Same export schema,
      same loader — users pick per environment.
- [ ] **GitHub Action** wrapping the metadata engine: on every
      PR, import the delta graph and post an impact summary as a
      review comment. Primary OSS adoption hook.
- [ ] **Cross-service HTTP call resolver** — `RestTemplate`,
      `WebClient`, `@FeignClient`, `@HttpExchange` → target
      endpoint. `CALLS_SERVICE` / `CALLS_ENDPOINT` edges. Closes
      the microservice architecture view.
- [ ] **Async boundary graph** — `@Async`, `@EventListener`,
      `@Scheduled`, `@KafkaListener`, `@RabbitListener`,
      `@JmsListener`. `Topic` / `Event` nodes with
      `PUBLISHES_TO` / `LISTENS_TO` edges.
- [ ] **Data-layer impact** — JPA `@Entity`, repository methods,
      `@Query` SQL (via the IntelliJ JPA plugin in Ultimate or
      manual parse). `Entity` / `Table` / `Column` nodes,
      `READS` / `WRITES` edges.
- [ ] **Config property lineage** — `@Value("${foo.bar}")`,
      `@ConfigurationProperties`, `application.yml`. `ConfigKey`
      nodes + `READS_CONFIG` edges. "If I rename this property,
      what breaks?"
- [ ] **Custom collector SPI** — `META-INF/services/com.onelens.CustomCollector`
      so adopters register domain-specific PSI walkers
      (`@FeatureFlag`, `@AuditLog`, `@RateLimited`) without
      forking the plugin.

## Principles for deciding what lands when

- **Cut scope to ship.** Every "not in M1" buys speed.
- **PSI accuracy before breadth.** Better to do Java perfectly
  than ten languages poorly.
- **Open primitives, paid management.** Core always free. Hosting
  / team features are the paid surface, not the core.
- **Earn permission to grow.** No governance paperwork until the
  product validates with real users.
- **Respect existing standards.** MCP, Cypher, ChromaDB, cross-
  encoder rerank — all adopted, none reinvented.
