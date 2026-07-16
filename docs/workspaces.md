# Workspaces

Status: **design spec** — pre-implementation. See
[DECISIONS.md ADR-021](./DECISIONS.md) for the decision record.

A **workspace** is OneLens's unit of indexing: one logical codebase that
maps to one graph. A workspace can span:

- a single repo with a single module (current default),
- a multi-module Maven / Gradle monorepo,
- a primary repo plus sibling repos linked via relative module refs
  (common pattern for plugin systems and shared libraries),
- a federation of microservices sharing a `common` library repo.

Workspaces are **declarative**. A checked-in `onelens.workspace.yaml`
makes the indexing boundary reproducible across machines and CI,
instead of depending on which IntelliJ project happens to be open.

## Why this exists

Before workspaces, OneLens had one implicit concept — the "IntelliJ
project" — and every subsystem quietly hardcoded it:

- Collectors scoped to `GlobalSearchScope.projectScope(project)` — only
  modules IntelliJ considered "managed in this project" got walked.
- File paths were stripped of `project.basePath`, so files from a
  linked sibling module outside that root got `../otherRepo/...`
  relative paths that broke snippet fetching downstream.
- Graph name was derived from `project.name`, with no user-facing
  knob to pin it.
- The delta tracker ran `git diff` only in the primary repo; changes
  to a linked sibling's `common/` module were invisible.
- The Python full loader used `CREATE` on bulk UNWIND, so a single
  duplicate FQN anywhere in the export aborted the whole import —
  which happens naturally in plugin forks (`com.acme.Constants` in
  10 different plugin dirs) and library monorepos.

Workspaces lift every one of those assumptions into explicit config.

## The config file

```yaml
# onelens.workspace.yaml — committed at the workspace root.
version: 1
name: myapp            # human-readable; goes into docs / logs
graph: myapp           # FalkorDB graph name + ChromaDB `wing`

roots:
  - path: .                    # primary root (relative to this file)
    buildTool: maven           # maven | gradle | auto (default: auto-detect)
  - path: ../myapp-plugins
    buildTool: maven
    include: ["*/pom.xml"]     # optional glob — link *all* unlinked poms,
                               # useful when a parent pom only declares
                               # a subset (assembly-descriptor builds).

policies:
  duplicateFqn: merge          # merge | warn | error | suffix-by-module
                               # merge  : last-write-wins (default, safe)
                               # warn   : first-wins, log rest
                               # error  : fail fast (old behaviour)
                               # suffix-by-module: emit `Foo@moduleName`
  delta:
    tracker: git-multi         # git | git-multi (default: git-multi when
                               # >1 root, else git)
  perApp:
    enabled: true              # emit App nodes per @SpringBootApplication,
                               # @FastAPI app, main() entrypoint, etc.
                               # Adapters decide what qualifies.
    pagerankPerApp: true       # seed PageRank once per App's entrypoints;
                               # store as Method.pagerank_by_app map.

exclude:
  - "**/target/**"
  - "**/build/**"
  - "**/node_modules/**"
  - "**/.venv/**"
```

Everything except `name` has a default. A workspace with a single root
and default policies behaves identically to today's
single-IntelliJ-project setup — backward compatibility is a hard
requirement of v1.2.

## Discovery rules

1. If `onelens.workspace.yaml` exists at the IntelliJ project root, use
   it.
2. Else, walk up from the project root looking for one (up to the
   filesystem root or a `.git` without a parent workspace file).
3. Else, synthesise an implicit workspace: one root = the project root,
   graph = `project.name`, policies = defaults. This keeps existing
   installs working with zero config.

The plugin emits a one-line log per sync:
`workspace = <name> (<N roots>, graph=<graph>, source=<file | implicit>)`

## Multi-root module collection

Each collector receives a **workspace-scoped** `CollectContext`:

```kotlin
data class CollectContext(
    val project: Project,
    val workspace: Workspace,          // new
    val indicator: ProgressIndicator?,
    val progressFraction: Double = 0.0
)
```

`workspace.scope()` returns a `GlobalSearchScope` that unions the
source roots of every linked Maven / Gradle module across every
declared root. File-path normalisation is done against
`workspace.relativize(vfile)`, which tries each root in declaration
order and returns the first match — so a file from
`../myapp-server/common/...` becomes
`myapp-server/common/...` rather than a brittle `../` path.

Adapters do **not** need to re-implement scope logic. `SpringBootAdapter`,
`Vue3Adapter`, and future adapters call `ctx.workspace.scope()` where
they previously called `GlobalSearchScope.projectScope(project)`.

## FQN duplicates — the real-world reality

JVM workspaces routinely ship duplicate class FQNs:

- Plugin systems that fork `com.acme.Constants` per client.
- Shaded JARs rewriting package roots.
- Generated code with the same FQN in build + source paths.
- Vendored dependencies.

Rather than fight this, the v1.2 loader `MERGE`s node creation on the
primary key. The policy field controls what happens *when* a duplicate
is seen at collection time:

| Policy | Collector behaviour | Loader behaviour |
|--------|--------------------|------------------|
| `merge` (default) | Emit all occurrences | UNWIND MERGE upserts, last-write-wins |
| `warn` | First-wins; log rest with file paths | MERGE (idempotent for first) |
| `error` | Fail export on second occurrence | N/A |
| `suffix-by-module` | Emit `Foo@moduleName` FQN | UNWIND MERGE, distinct keys |

The blocker fix is already live in `python/src/onelens/importer/loader.py`
(`_batch_nodes` switched from `CREATE` to `MERGE`). The policy knob
comes with v1.2.

## Multi-git delta tracker

`DeltaTracker.getChanges(workspace)` iterates every root, runs
`git diff --name-status` against the per-root last-sync hash, and
merges results into one changed-files set. A root without a git dir
is skipped (not an error — covers vendored checkouts).

State persists under `~/.onelens/workspaces/<graph>/delta-state.json`
keyed by root path, so re-syncs after linking a new sibling don't
full-rebuild everything.

## App and Package primitives

`App` and `Package` are **adapter-agnostic** node types:

- `SpringBootAdapter` emits `App` nodes for `@SpringBootApplication`
  classes and `CONTAINS` edges via `@ComponentScan` resolution.
- `Vue3Adapter` emits one `App` per detected Vue app root.
- A future `FastAPIAdapter` emits `App` per `FastAPI()` instance.
- A future `GoAdapter` emits `App` per `main()` package.

`Package` nodes are emitted by whichever adapter owns the language's
package concept; Java uses dotted packages, Vue uses directory-path
"packages", Go uses import paths.

Cross-adapter queries (e.g. "which Vue apps hit endpoints defined by
which Spring apps") work through `App` as a shared vocabulary.

## Migration

- **No config file** → behaviour is identical to pre-v1.2. No action
  required.
- **Single repo, want a stable graph name** → add a three-line yaml:
  ```yaml
  version: 1
  name: my-service
  graph: my-service
  ```
- **Multi-module sibling repo** → add a second root under `roots:`.
  First sync after the addition will be a full re-import (not a
  delta); subsequent syncs are incremental across all roots.

## Non-goals (v1.2)

- **Cross-workspace federated queries.** Two graphs = two queries,
  union in the caller. Federation lands in v2.0 (see roadmap M3).
- **Non-JVM language workspaces with unusual layouts.** The YAML
  schema is agnostic but the default discovery rules assume Maven /
  Gradle / `package.json` presence. Custom `include:` globs cover
  edge cases.
- **Auto-link prompt UX in the IDE.** v1.2 reads a committed file.
  An IDE wizard that *generates* a workspace.yaml is v1.3.
