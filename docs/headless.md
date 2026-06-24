# Headless export mode

OneLens's PSI collectors normally run inside IntelliJ via Tools → OneLens →
Sync Graph. **Headless mode** runs the same collectors without a GUI —
useful for CI, reproducible builds, no-IDE servers, and containers. It
writes the same export JSON the IDE does; the downstream
`onelens call-tool onelens_import` consumes it separately.

This is the architecture `docs/design/PLAN-onboard-cli.md` Phase 5 specified
and `docs/design/context-engine-founding-research.md` §8.6 calls the "depth
tier without IDE open." The mechanism is an IntelliJ `ApplicationStarter`
(`OneLensExportStarter`) that the platform invokes when the IDE is launched
with the `onelens-export` command.

## What it produces

`~/.onelens/exports/<graphId>-full-<timestamp>.json` — a single
self-describing JSON document with every class, method, field, call edge,
inheritance edge, Spring bean, endpoint, JPA entity, and (if present) Vue 3
node. The exact same bytes the in-IDE sync produces. Then it exits.

It does **not** import into a graph DB or build embeddings. Those are a
separate `onelens call-tool onelens_import` step — by design, the export
and import are decoupled (see `docs/architecture.md` "Data flows").

## Three ways to run it

### 1. Gradle task (dev / local)

Boots the platform in-process against the prepared sandbox — the same
mechanism the plugin's own tests use to run PSI headless. Requires no
Docker, but does require the platform JARs the Gradle plugin downloads.

```bash
cd plugin
./gradlew headlessExport \
  -PonelensProject=/abs/path/to/your/spring/app
  # optional: -PonelensOutput=/abs/path/to/outdir
```

The task sets `java.awt.headless=true`, launches `idea.sh` from the sandbox
with `onelens-export --project … --output-dir …`, and the starter writes
the JSON. Look for `onelens-export: wrote …` on stdout.

### 2. Docker (CI / reproducible)

The `jetbrains/qodana-jvm` base image ships a headless IntelliJ Ultimate +
Spring/JPA model, so the collectors get the same type-accurate resolution
they get in the IDE.

```bash
./gradlew buildPlugin
docker build -t onelens/headless -f docker/Dockerfile \
  --build-arg ONELENS_PLUGIN_ZIP=plugin/build/distributions/onelens-graph-builder-0.1.0.zip .
docker run --rm \
  -v /abs/path/to/project:/src \
  -v /abs/path/to/output:/out \
  -e QODANA_TOKEN=<token> \
  onelens/headless
```

See `docker/README.md` for the licensing caveat (Qodana license required;
this is the "works today, costs money" option, not the OSS default).

### 3. Raw `idea.sh` (any IntelliJ install)

If you already have IntelliJ Ultimate installed (and the OneLens plugin
loaded into it), skip both Gradle and Docker:

```bash
idea.sh onelens-export --project /abs/path/to/project --output-dir /out
```

The platform discovers the `<appStarter id="onelens-export">` from the
installed plugin and routes the command to `OneLensExportStarter.main`.

## After the export: build the graph

```bash
onelens call-tool onelens_import \
  --export-path ~/.onelens/exports/<graph>-full-*.json \
  --graph myapp \
  --backend falkordblite \
  --context        # optional: also build ChromaDB embeddings
```

`--backend falkordblite` is embedded (no Docker). `--context` adds the
semantic layer — slow on first run, fast on delta. Without `--context`,
you get the structural graph only (impact, trace, query, search all work;
`retrieve` won't).

## When to use headless vs the IDE

| Situation | Use |
|---|---|
| Daily coding, want live auto-sync on save | IDE (Tools → OneLens → Sync Graph) |
| CI: gate a PR on "does the export build cleanly" | Headless (Gradle or Docker) |
| No IntelliJ license on the build server | Headless via Docker (Qodana) or scip-java tier (future) |
| Reproducible export across machines | Headless (Docker) — identical platform version pinned |
| Generating fixtures / golden exports for tests | Headless (Gradle) |

## Licensing — the honest constraint

PSI itself runs on the Community platform. But the **Spring plugin model**
(`@Bean`/`@Autowired`/`@Qualifier` candidates, JPA entity metadata) that
the Spring/JPA collectors depend on ships only with **IntelliJ Ultimate**.
So a headless run against a Spring Boot project needs an Ultimate-licensed
platform:

- **Gradle task** uses the platform version pinned in
  `plugin/gradle.properties` (`platformType = IU` = Ultimate). Fine for dev;
  not for redistribution.
- **Docker (qodana-jvm)** is Ultimate, requires a Qodana token. ~$40/dev/mo
  floor — see `docs/design/PLAN-onboard-cli.md` §9.
- **Plain Java/Kotlin (no Spring/JPA)** works on Community for free; swap
  the base.

The project's planned license-free headless tier is **scip-java**
(compiler-grade, javac plugin, no IDE) — see
`docs/competitive-landscape.md` §N. That's a separate future track; the
ApplicationStarter + this Dockerfile are the PSI-depth path.

## What headless mode does NOT do

- **No embeddings.** The export is structural facts only. Embeddings are
  `onelens_import --context`'s job.
- **No FalkorDB preflight / no CLI shell-out.** The starter sets
  `autoImport = false` and `buildSemanticIndex = false` deliberately — the
  JSON is the deliverable.

## Delta export (incremental re-sync)

Headless mode supports git-diff-based delta exports — only changed files are
re-collected, producing a small `delta` JSON instead of a full `full` JSON.

### How it works

1. After each export (full or delta), the starter writes the current git HEAD
   commit + file→classes map to `~/.onelens/graphs/<graphId>/.onelens-lastexport`.
2. On the next `--delta` run, it loads this state and runs
   `git diff --name-status <lastExportCommit> HEAD` to find changed files.
3. Only those files' classes are re-collected (via `DeltaExportService`).
4. The delta JSON has `exportType: "delta"` — the Python importer auto-detects
   it and applies incrementally (MERGE upserts + DETACH DELETE removed).

### Usage

```bash
# First run: full export (seeds the delta state)
./gradlew headlessExport \
  -PonelensProject=/path/to/project \
  -PonelensOutput=/tmp/exports

# Import the full export
onelens call-tool onelens_import \
  --export-path /tmp/exports/myproject-full-*.json \
  --graph myproject

# ... edit files, commit ...

# Subsequent runs: delta export (only changed files)
ONELENS_DELTA=true ./gradlew headlessExport \
  -PonelensProject=/path/to/project \
  -PonelensOutput=/tmp/exports

# Import the delta (auto-detected)
onelens call-tool onelens_import \
  --export-path /tmp/exports/myproject-delta-*.json \
  --graph myproject
```

### Performance

| | Full export | Delta export (1 file changed) |
|---|---|---|
| Export time | ~4 min (warm) | ~30 s |
| Import time | ~25 s | ~15 s |
| JSON size | ~700 MB | ~16 MB |

### Delta state management

The delta state marker lives at `~/.onelens/graphs/<graphId>/.onelens-lastexport`.
This is **outside** IntelliJ's isolated `system/` dir, so it persists across
headless JVM invocations. If the marker is missing or the schema version
mismatches, the delta automatically falls back to a full export.

Branch switches / rebases are detected via `git merge-base --is-ancestor` — if
the last-export commit is no longer an ancestor of HEAD, a full re-export is
forced (the diff would be meaningless).

### Auto-sync with watchexec

For hands-off incremental sync, use an external file watcher that triggers
the delta command:

```bash
# Install watchexec (Rust, no JVM dependency)
cargo install watchexec
# or: brew install watchexec

# Auto-sync on file changes (10s debounce)
watchexec -e java,kt,vue,js,ts --debounce 10000 -- \
  bash -c '
    ONELENS_DELTA=true ./gradlew headlessExport \
      -PonelensProject=/path/to/project \
      -PonelensOutput=/tmp/exports && \
    onelens call-tool onelens_import \
      --export-path $(ls -t /tmp/exports/*.json | head -1) \
      --graph myproject
  '
```

This pattern matches how Qodana and SonarQube handle incremental analysis —
git-diff scoping + persisted index cache. No long-running IntelliJ daemon
needed.

## Multi-project workspaces

Headless mode supports multi-root workspaces via `onelens.workspace.yaml`.
When the YAML declares sibling repos as roots, the starter:

1. Discovers the primary project's pom.xml via Maven
2. Adds sibling repo pom.xml files as managed Maven projects
3. Resolves all modules (primary + siblings) in one Maven import pass
4. Indexes sibling module source roots so `PsiShortNamesCache` finds them

### Workspace YAML format

```yaml
version: 1
name: myapp
graph: myapp
roots:
  - path: .                    # primary project (required)
    buildTool: maven
  - path: ../my-plugins        # sibling repo
    buildTool: maven
  - path: ../my-frontend       # Vue 3 frontend
    buildTool: npm
policies:
  duplicateFqn: merge
```

### Multi-project with inter-project dependencies

If sibling repos depend on artifacts built from the primary project (e.g.,
plugins depending on `com.example.common`), run `mvn install -DskipTests` on
the primary project first:

```bash
# Install primary artifacts to ~/.m2/repository
cd /path/to/primary && mvn install -DskipTests -q

# Now sibling repos can resolve their dependencies
./gradlew headlessExport \
  -PonelensProject=/path/to/primary \
  -PonelensOutput=/tmp/exports
```

Without this, Maven creates modules for the sibling repos but can't resolve
their dependencies → IntelliJ can't create proper source roots → those
classes won't be in the stub index → missing from the export.

### Cross-stack linking (Vue → Spring)

To link a Vue frontend's API calls to a Spring backend's endpoints via `HITS`
edges, import each project into the **same graph**:

```bash
# Import backend (Spring endpoints)
onelens call-tool onelens_import --export-path backend.json --graph myapp

# Import frontend (Vue API calls) into the SAME graph
onelens call-tool onelens_import --export-path frontend.json --graph myapp

# HITS edges are created automatically during import — they match
# Vue ApiCall.normalizedPath to Spring Endpoint.normalizedPath
# across different wing stamps.
```

## How it works (internals)

```
idea.sh onelens-export --project /src --output-dir /out
   │
   ▼
platform dispatches by `id` on <appStarter> in plugin.xml
   │
   ▼
OneLensExportStarter.main(args)
   ├─ log + parse args (--project, --output-dir)
   ├─ invokeLater → executeOnPooledThread {       ← off-EDT (see Gotchas #2)
   │     ProjectManager.loadAndOpenProject(path)  ← headless project open
   │     DumbService.waitForSmartMode()           ← gate 1: required dumb tasks
   │     waitForStubIndexPopulated(project)       ← gate 2: deferred scanner (see #1)
   │     VFS refresh of project root              ← gate 3: workspace.scope (see #3)
   │     ExportConfig(autoImport=false, buildSemanticIndex=false)
   │     ExportService.exportFull(project, config, indicator=null)
   │         └─ same collectors as Tools → Sync Graph (zero GUI coupling)
   │     println("onelens-export: wrote <path> (<counts>)")
   │     Application.exit() + 60s watchdog exitProcess  ← see Gotchas #4
   │  }
```

`ExportService.exportFull` is unchanged — the starter just supplies a
`Project` and `ExportConfig` instead of an `AnActionEvent` +
`ProgressIndicator`. The collectors (`SpringCollector`, `JpaCollector`,
`CallGraphCollector`, …) are pure PSI readers with zero AWT/Swing
references (verified by grep across `export/`).

## Operational gotchas (paid for in blood)

These are the four things that produce a silently-empty export (`0 classes`)
or a thrown `IndexNotReadyException` in headless mode. Each was diagnosed
from a real failure during development; the fixture run is now
**deterministic (3/3 consecutive successes)**.

1. **Three indexing gates, not one — and the index-gate must CATCH
   `IndexNotReadyException`, not propagate it.** `DumbService.waitForSmartMode()`
   returns after the *required* dumb tasks (SDK pre-index), but the *deferred*
   `UnindexedFilesScanner` (which populates the stub index) runs as a separate
   startup activity afterward. The starter therefore polls
   `JavaPsiFacade.findClass(sentinelFqn)` + `PsiShortNamesCache.allClassNames`
   until both resolve. **Critical:** those PSI calls hit
   `FileBasedIndexImpl.ensureUpToDate`, which THROWS `IndexNotReadyException`
   during dumb mode rather than returning empty. An early version of the gate
   let that propagate out of the `ReadAction` — which killed the export with
   a non-deterministic `IndexNotReadyException` (the exact symptom that looked
   like a "platform race"). The gate wraps every probe in
   `try { … } catch (IndexNotReadyException) { /* keep polling */ }` and
   re-waits via `waitForSmartMode`. This single fix turned a flaky 1-in-N
   success into 3/3 deterministic. The devil's-advance review's threading
   critique pointed here; the stack trace confirmed it.

2. **Don't block the EDT.** An earlier version ran `waitForSmartMode` +
   `exportFull` inside `invokeLater` directly on the EDT. On heavy-Gradle
   projects this self-deadlocked: the scanner publishes dumb-mode transitions
   via EDT callbacks, and blocking the EDT in `waitForSmartMode` stalled the
   very machinery that ends dumb mode. The starter now hops to a pooled thread
   via `executeOnPooledThread` for all blocking work.

3. **The project's directory must have no `.idea/` ancestor.** When you call
   `loadAndOpenProject(path)`, IntelliJ walks UP the tree and adopts the
   nearest enclosing `.idea/` as the project. If your target project lives
   inside a repo that has a root `.idea/` (e.g. the OneLens repo itself), the
   parent becomes the project, the module's content root resolves one level
   too high, source roots get dropped, and the stub index has nothing to
   index → `0 classes`. The verification fixture lives at
   `tools/headless-fixture/` but must be COPIED to a path with no `.idea`
   ancestor (e.g. `/tmp`) before opening. A real standalone project (not
   nested in another IntelliJ project) is unaffected.

4. **`Application.exit()` doesn't always terminate the JVM under Gradle.**
   Under `runIde`/JavaExec, non-daemon threads (indexers, coroutines, the
   Gradle worker itself) keep the JVM alive after `exit()` returns, so the
   process hangs until an external timeout kills it. The starter uses a
   **graceful-primary + watchdog** contract: `Application.exit()` is the
   primary path (flushes lifecycle, runs `ApplicationLifecycleListener`s);
   a generous `SHUTDOWN_WATCHDOG_SEC` (60s) daemon thread force-exits via
   `exitProcess` ONLY if the graceful path wedges, logging at `WARN` when
   it fires so a real shutdown bug is visible. Under Gradle the watchdog
   fires routinely (that's the documented JavaExec-worker case); outside
   Gradle it would indicate a genuine leak. `closeAndDispose(project)` is
   wrapped in try/catch — it throws "write thread only" if a Maven import
   is still mid-flight, non-fatal once the export is written.

**Isolated `system/` dir per run.** The gradle task points
`idea.system.path` at `build/onelens-system/` (overridable via
`ONELENS_SYSTEM_DIR`). The shared `build/idea-sandbox` index cache
contaminates across projects — the scanner can report "0 files for indexing"
on a subsequent run because it thinks a prior project's index already covers
the new files. This is a documented platform behavior (see
`bentolor/idea-cli-inspector`'s troubleshooting: "different results on
subsequent runs — try deleting the system/ directory"). The isolated dir
keeps each export's index clean. Do NOT override `idea.home.path` — that must
point at the real IDE install or bootstrap crashes.

## Verification fixtures

### Plain Java — `tools/headless-fixture/`

A minimal 2-class Java project (`Greeter.java`, `Counter.java`). Run after
copying to a `.idea`-free path:

```bash
cp -r tools/headless-fixture /tmp/headless-fixture
cd plugin
./gradlew headlessExport -PonelensProject=/tmp/headless-fixture -PonelensOutput=/tmp/out
```

Expected: `onelens-export: wrote … (2 classes, 5 methods, 4 calls, 0 endpoints)`.
**Verified deterministic: 3/3 consecutive runs produced identical counts**
(`2 classes, 5 methods, 4 calls`) with `exit=0`, ~3-8 s export, ~90 s total
wall-clock. The export JSON contains `com.onelens.fixture.Greeter` and
`com.onelens.fixture.Counter` with 5 methods and 4 call edges:
`Counter.increment → Counter.current`, `Greeter.main → Greeter.greet`,
`Greeter.main → Greeter.<init>`, `Greeter.main → PrintStream.println`
(the last proves the JDK index resolves).

### Spring Boot — `tools/spring-fixture/`

A minimal Spring Boot app (`@SpringBootApplication` + `@RestController` +
`@Service` + `@Configuration` + `@Bean` + `@Autowired`, with
`spring-boot-starter-web` as a real Maven dependency so the stereotype +
endpoint annotations resolve via PSI). This exercises the **depth tier** the
headless feature exists for.

```bash
cp -r tools/spring-fixture /tmp/spring-fixture
cd plugin
./gradlew headlessExport -PonelensProject=/tmp/spring-fixture -PonelensOutput=/tmp/out
```

Expected: `onelens-export: wrote … (4 classes, 6 methods, 3 calls, 2 endpoints)`.
**Verified deterministic: 3/3 consecutive runs (1 cold + 2 warm) produced
identical counts** with `exit=0`, ~6-7 s export. The JSON contains:
- **4 beans** with correct stereotypes (`@SpringBootApplication`,
  `@RestController`, `@Service`, `@Configuration`)
- **2 endpoints**: `GET /api/greetings → hello()`,
  `GET /api/greetings/{name} → greetByName(String)` (class-level
  `@RequestMapping` correctly merged with method-level `@GetMapping`)
- **1 injection**: constructor `@Autowired` of `GreetingService` into
  `GreetingController`
- **1 app**: the `@SpringBootApplication` entrypoint

### Complex Spring Boot — `tools/complex-spring-fixture/`

A realistic multi-layer Spring Boot app (14 hand-written classes across 6
packages + the `spring-boot-starter-data-jpa`/`validation` deps that pull in
the full Spring + JPA + Hibernate model). This is the most rigorous
verification — it exercises every collector: API→Service→Repository→Domain
layering, two `@RestController`s, service-to-service composition, Spring Data
`JpaRepository` interfaces, `@Entity`/`@MappedSuperclass`/`@Table`/`@Column`/
`@ManyToOne`/`@JoinColumn`, an enum, four records, and a `@Configuration`
with two `@Bean` methods.

```bash
cp -r tools/complex-spring-fixture /tmp/complex-fixture
cd plugin
./gradlew headlessExport -PonelensProject=/tmp/complex-fixture -PonelensOutput=/tmp/out
```

Expected: `onelens-export: wrote … (17 classes, 55 methods, 57 calls, 5 endpoints)`.
**Verified deterministic: 2/2 consecutive runs (cold + warm) produced
identical counts** with `exit=0`, ~8-11 s export. The JSON contains:
- **17 classes** (incl. 4 record types + 1 enum detected as distinct kinds)
- **5 endpoints** across both controllers — exact paths + HTTP methods +
  handler FQNs, including path-var (`GET /api/customers/{email}`) and
  query-param (`GET /api/orders?status=…`) binding
- **3 JPA entities** — `Customer` (`customers`), `Order` (`orders`), plus the
  `@MappedSuperclass` `AbstractEntity` (detected as an entity too)
- **2 JPA repositories** — `CustomerRepository`/`OrderRepository`, both
  correctly typed to their entities, with derived queries
  (`findByEmail`, `existsByEmail`, `findByStatus`, `countByStatus`) surfaced
- **9 inheritance edges** — the `@MappedSuperclass` edges
  (`Customer → AbstractEntity`, `Order → AbstractEntity`), both repos
  `→ JpaRepository`, the enum `→ java.lang.Enum`, and all 4 records
  `→ java.lang.Record` (the record + enum detection is bonus depth)
- **8 beans** (4 stereotype beans + 2 repository interfaces + 2 `@Bean`-method
  beans) and **5 injections** (constructor injection across controllers +
  services + service-to-service composition)
- **1 app** node (`@SpringBootApplication`)

This fixture is the proof that the headless export produces a complete,
type-accurate knowledge graph for a realistic Spring Boot application — every
collector fired correctly, end-to-end, deterministically.

## External-system (Maven/Gradle) import synchronization

External-system projects (Maven, Gradle) require explicit import
synchronization that plain-Java projects don't. The async external-system
import is the single hardest part of headless PSI export — three independent
race conditions had to be closed, each a real failure mode observed during
development:

1. **The stub-index gate must CATCH `IndexNotReadyException`, not propagate
   it.** PSI index reads (`JavaPsiFacade.findClass`,
   `PsiShortNamesCache.allClassNames`) throw `IndexNotReadyException` during
   dumb mode rather than returning empty. The gate's probes wrap every read
   in `try { … } catch (IndexNotReadyException) { /* keep polling */ }`.

2. **Maven doesn't use the unified external-system notification bus.** The
   first attempt subscribed only to `ExternalSystemProgressNotificationManager`
   (the Gradle path) and never saw Maven imports — Maven has its OWN
   message-bus topic (`MavenImportListener.TOPIC` with `importFinished`),
   because it predates the unified external-system framework. The starter
   subscribes to BOTH. The Maven half is consumed through a **typed adapter**
   (`com.onelens.plugin.headless.maven.MavenHeadlessImport`) compiled against
   the Maven plugin classes via an optional
   `<depends config-file="maven-headless.xml">org.jetbrains.idea.maven</depends>`
   (the same Spring/Vue/Git optional-dep pattern already in `plugin.xml`) plus
   Maven added to `platformBundledPlugins` so the adapter has compile-time
   references to `MavenImportListener` / `MavenProjectsManager`. (An earlier
   version reached those via ~85 lines of reflection; that was strictly worse
   — a Maven-API rename would silently stop the event instead of failing the
   build.) The adapter is no-op when Maven isn't installed (Gradle / plain
   Java) — a 5-second fallback releases the wait latch if no pom registers.

3. **Maven doesn't auto-import reliably in headless mode, and
   `MavenProjectsManager.hasProjects()` can be FALSE on warm cache.** The
   `external.system.link.unlinked.projects=AUTO` flag is not enough — on
   warm-cache runs Maven's lazy startup activity defers re-registering the
   pom, so neither the auto-import nor `hasProjects()` sees it. The starter
   explicitly calls `forceUpdateAllProjectsOrFindAllAvailablePomFiles()` to
   discover + register the pom, then `scheduleImportAndResolve()` to kick the
   import. The `importFinished` listener (from #2) is the completion signal;
   on its fire, the starter re-waits for smart mode (the post-import reindex)
   and re-runs the stub-index gate.

All three are event-driven (subscribe to the real completion event + force
the work), not proxy-gated. This is what makes the Spring Boot export
deterministic rather than retry-dependent. The Gradle path uses
`ExternalSystemTaskNotificationListener.onEnd` with `RESOLVE_PROJECT` and
already auto-fires (Gradle's sync is less lazy than Maven's in headless), so
it doesn't need the forced-discovery step.

This is a stricter fix than the workaround JetBrains' own `mcp-jetbrains`
([issue #87](https://github.com/JetBrains/mcp-jetbrains/issues/87), open May
2026) currently uses (per-call `runReadActionInSmartMode` retry).



