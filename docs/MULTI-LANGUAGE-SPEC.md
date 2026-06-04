# Multi-Language Extension — Design Spec

**Status:** Draft · **Date:** 2026-06-04 · **Scope:** Extend OneLens from Java/Spring-only to Java, Android (Kotlin), .NET, Python, Go, and Vue.js, with cross-stack full-stack tracing as the headline capability.

> Read [LESSONS-LEARNED.md](LESSONS-LEARNED.md) first. This spec assumes the existing import/graph/retrieval brain stays; we are widening the *extraction* surface and *neutralizing* Java/Spring assumptions in the brain — not rewriting it.

> **All-phases status (2026-06-04).** Every phase now has a working, unit-tested implementation at the **extraction-contract layer** — reference extractors that emit the normalized JSON, all feeding one loader + the cross-stack linker. **51 tests pass** (`uvx pytest tests/`). Per language: Vue (frontend) ✅, Kotlin/Android ✅, Go ✅, Python ✅, .NET/C# ✅ — each detects routes/endpoints across the common frameworks and a single Vue `axios` call links to **any** of them (verified on real files: Vue→Go/Python/.NET/Kotlin all link). **Two honest limits:** (1) not validated against a live FalkorDB (down here; embedded backend uninstallable), so DB write/query Cypher is FakeDB + pure-core tested only; (2) extractors are standalone **reference** parsers — production extraction moves into the IntelliJ-Platform plugin modules (Kotlin/Go/Python/Vue PSI) and a Roslyn `dotnet tool` (.NET), reusing this exact JSON contract. See §9.

---

## 1. Decisions locked for this spec

| Decision | Choice | Consequence |
|---|---|---|
| First milestone | **Cross-stack full-stack trace** (Vue → REST endpoint → backend handler) | Phase 2 ships Vue + one backend + an HTTP-contract linking layer, not breadth. |
| Packaging | **IDE-plugin-centric** (JetBrains IDEs) | One IntelliJ-Platform plugin with optional language modules; a separate companion extractor only for .NET. |
| Spec output | This document | Drives Phase 0 code work. |

---

## 2. The core architectural fact

OneLens's moat is *"IntelliJ PSI → 100% type accuracy."* That moat **does not extend to a single IDE** across these six stacks — but it mostly extends across the **IntelliJ Platform**, which is not the same thing as "IntelliJ IDEA."

GoLand, PyCharm, WebStorm, and Android Studio are all built on the IntelliJ Platform and ship their own type-accurate PSI for their language. A single plugin built against the platform SDK — with **optional** dependencies on each language module — runs in all of them, and each language's collectors only activate when that PSI is present.

| Stack | Type-accurate engine | Host IDE | In one plugin? |
|---|---|---|---|
| Java | IntelliJ PSI (`com.intellij.modules.java`) | IDEA / Android Studio | ✅ (have it) |
| Android (Kotlin) | Kotlin PSI + **UAST** (`org.jetbrains.kotlin`) | IDEA / Android Studio | ✅ |
| Go | Go PSI (`org.jetbrains.plugins.go`) | **GoLand** | ✅ |
| Python | Python PSI (`com.intellij.modules.python`) | **PyCharm** | ✅ |
| Vue / TS | JS/TS PSI + Vue plugin (`JavaScript`, `org.jetbrains.plugins.vue`) | **WebStorm** / IDEA Ultimate | ✅ |
| **.NET / C#** | **Roslyn** (out-of-process ReSharper backend) | **Rider** | ❌ — separate extractor |

**Implication:** the plugin today hard-depends on `com.intellij.modules.java` ([plugin.xml](../plugin/src/main/resources/META-INF/plugin.xml)) and builds against `platformType = IC` ([gradle.properties](../plugin/gradle.properties)). To go multi-language we (a) make the Java dependency **optional**, (b) split collectors into per-language modules each gated on their PSI module, and (c) build/distribute the plugin for each target IDE. .NET gets a standalone Roslyn-based companion CLI that emits the same JSON.

```
IDEA / Android Studio ─┐
GoLand ────────────────┤  ONE IntelliJ-Platform plugin
PyCharm ───────────────┤  (optional per-language modules, shared collector interface)  ──┐
WebStorm ──────────────┘                                                                  │
                                                                                          ├─► normalized JSON ─► onelens import ─► FalkorDB + ChromaDB
Rider / dotnet ── standalone Roslyn extractor (companion CLI) ────────────────────────────┘        (language-agnostic brain)
```

The Python CLI (import, graph, retrieval, semantic) stays the single language-agnostic brain. Today it is ~70–80% language-neutral; Phase 0 closes the gap.

---

## 3. Phase 0 — schema & brain neutralization (foundation)

No new language ships here. We remove every Java/Spring assumption baked into the brain so a second language is *configuration*, not a rewrite. Each item below is a concrete, located change.

### 3.1 Normalized node/edge schema

Add a mandatory `lang` discriminator to every node (`java | kotlin | csharp | python | go | vue`). Generalize labels to a superset and stop overloading `Method` for free functions:

- Nodes: `Class`, `Interface`, `Method`, `Function` (free/standalone), `Field`, `Module`, `Annotation`, `Endpoint`, **`Component`** (Vue SFC), **`HttpCall`** (frontend outbound call site).
- Edges (existing keep working): `CALLS`, `EXTENDS`, `IMPLEMENTS`, `HAS_METHOD`, `HAS_FIELD`, `OVERRIDES`, `ANNOTATED_WITH`, `HANDLES`, `INJECTS`, `MODULE_DEPENDS`.
- New cross-stack edges: **`CALLS_ENDPOINT`** (`HttpCall` → `Endpoint`), **`RENDERS`** / **`USES_COMPONENT`** (Vue component graph).

### 3.2 Stop re-parsing FQNs — carry a structured ID

The brain currently recovers structure by string-splitting FQNs on `#` and `(` — a Java-only format. Replace with an explicit, language-neutral identity carried in the JSON so the brain never parses syntax:

```jsonc
{
  "id": "java::com.example.UserService#create(java.lang.String)",  // opaque, unique, the graph key
  "lang": "java",
  "kind": "method",
  "container": "java::com.example.UserService",   // was: fqn.split("#")[0]
  "simpleName": "create",                         // was: split("#")[1].split("(")[0]
  "isConstructor": false,                         // was: name == className heuristic
  "displayName": "UserService#create(String)"     // for UI/snippets only — never parsed
}
```

Touch points to convert from "parse the FQN" to "read the field":
- [loader.py:127](../python/src/onelens/importer/loader.py#L127) and [:169](../python/src/onelens/importer/loader.py#L169) — external-stub class extraction + constructor detection.
- [delta_loader.py:134-174](../python/src/onelens/importer/delta_loader.py#L134) — same logic, mirrored.
- [analysis.py:88](../python/src/onelens/graph/analysis.py#L88) — `_compact_trace` signature shortening (use `displayName`).
- [code_miner.py:235](../python/src/onelens/miners/code_miner.py#L235) — short-name resolution (use `simpleName`).

### 3.3 Language profiles (replace hardcoded Java/Spring constants)

Introduce `python/src/onelens/lang/profiles/<lang>.yaml`, one profile per language, consumed where constants are hardcoded today:

| Profile key | Replaces (Java/Spring hardcode) | Location |
|---|---|---|
| `entry_point_annotations` / `entry_point_markers` | `['Scheduled','PostConstruct','EventListener','KafkaListener']` | [pagerank.py:81](../python/src/onelens/importer/pagerank.py#L81) |
| `trivial_method_names` / `trivial_prefixes` | `{toString,hashCode,equals,...}`, `get/set/is/has/can` | [code_miner.py:71](../python/src/onelens/miners/code_miner.py#L71) |
| `importance_annotations` | `Transactional`, `Service`, `Controller`, `Repository` boosts | [code_miner.py:203-219](../python/src/onelens/miners/code_miner.py#L203) |
| `framework` (DI/route flavors) | Spring bean-type injection filter | [analysis.py:211-256](../python/src/onelens/graph/analysis.py#L211) |

Example (`go.yaml`): `entry_point_markers: [http.HandleFunc, grpc.RegisterService, "func main"]`, `trivial_prefixes: []`, naming convention `PascalCase` for exported.

### 3.4 Schema DDL becomes label-set-driven

[schema.py](../python/src/onelens/importer/schema.py) currently hardcodes labels and FTS indexes. Drive index creation from the node-label superset (§3.1) so adding `Component`/`Function`/`HttpCall` needs no DDL edits per language. **Watch the ChromaDB metadata schema** (`{wing, room, hall, fqn, type, importance, filed_at}`) — any drift between full and delta writes silently breaks `wing`-scoped filtering (LESSONS-LEARNED). Add `lang` to that metadata in **both** paths simultaneously.

**Exit criterion for Phase 0:** existing Java graphs import byte-identical (the Java profile reproduces today's behavior), and the brain contains zero `split("#")` / hardcoded-annotation occurrences.

### 3.5 Implementation status (2026-06-04)

**Landed & verified** (Java behavior asserted byte-identical against the pre-refactor logic in isolation):
- `python/src/onelens/lang/` — new package.
  - `profiles.py`: `LanguageProfile` frozen dataclass + registry for `java/kotlin/python/go/csharp/vue`. **Deviation from §3.3:** profiles are Python dataclasses, not YAML — no runtime file I/O or extra dependency, and the CI mypy/ruff guard type-checks them. Java profile reproduces the old constants exactly.
  - `identity.py`: single home for container/simple-name/params/constructor/trivial parsing. Prefers structured node fields (`container`, `simpleName`, `isConstructor`); falls back to profile-driven syntax parsing (Java-exact).
- [pagerank.py:81](../python/src/onelens/importer/pagerank.py#L81) — entry-point seeds now `all_entry_point_annotations()` (union across profiles; superset of the old 4, so pure-Java graphs are unchanged).
- [code_miner.py](../python/src/onelens/miners/code_miner.py) — `_is_trivial_method`, `_compute_importance`, and `_short_name/_short_class/_short_params` route through `identity` + the node's `lang` profile. New `_fqn_lang` map captures per-node language during `_build_indexes`.

**Phase 0 now COMPLETE (2026-06-04):** `inner_class_sep` added to `LanguageProfile` (+ `identity.innermost_class`); `loader.py` and `delta_loader.py` external-stub container extraction + constructor detection now route through `identity.container_fqn` / `identity.simple_name` / `identity.is_constructor`; `lang` is persisted on `Class`/`Method` nodes. Java inner-class `Outer$Inner` constructor detection verified ([test_lang_identity.py](../python/tests/test_lang_identity.py)). **Still deferred:** adding `lang` to the ChromaDB drawer metadata in both full + delta paths (semantic layer is already language-agnostic for retrieval; this is an enhancement, and the LESSONS-LEARNED full-vs-delta drift footgun means it should land as one careful change).

## 5.4 Phase 2 implementation status (2026-06-04) — Vue ↔ Java cross-stack

The headline full-stack-trace vertical slice is implemented and tested (33 passing tests, no live infra):

- **Schema** — `Component` + `HttpCall` node labels/indexes ([schema.py](../python/src/onelens/importer/schema.py)); `CALLS_ENDPOINT`, `USES_COMPONENT`, `MAKES_CALL` edges; both added to `db.py` `NODE_TYPES`.
- **Linking** — [cross_stack.py](../python/src/onelens/importer/cross_stack.py): pure `normalize_path` (collapses `{id}` / `:id` / `${id}` / `<int:id>` → `/{}`, strips host+query+trailing slash) and pure `link_http_calls` (exact = 1.0, suffix/base-prefix = 0.6, unmatched surfaced not dropped). `apply_cross_stack_links` is the thin DB wrapper, run as a post-import phase in `load_full`.
- **Vue extractor** — [vue_extractor.py](../python/src/onelens/extractors/vue_extractor.py): standalone, dependency-free parser → normalized JSON (`Component`/`HttpCall`/`USES_COMPONENT`). Detects `axios.<m>()`, `fetch()` (+method option), `axios({method,url})`; resolves `.vue` import edges; skips commented calls. CLI: `python -m onelens.extractors.vue_extractor <dir> <out.json>`.
- **Loader** — loads `components`/`httpCalls`/`componentEdges`; emits `MAKES_CALL` + `USES_COMPONENT`; runs cross-stack linking after PageRank.
- **Analysis** — `get_endpoint_consumers` ("which Vue components break if I change this endpoint?") + `get_fullstack_trace` (Component → HttpCall → Endpoint → handler → backend `CALLS*` flow).
- **Tests** — [python/tests/](../python/tests/): `test_lang_identity`, `test_cross_stack`, `test_vue_extractor`, `test_fullstack_integration` (proves `.vue` source → extracted HttpCall → linked Spring endpoint, incl. the typo'd-call-is-unmatched case). Run with `uvx pytest tests/` (system Python lacks pytest).

**Not yet validated against a live graph DB:** FalkorDB was down and the embedded `falkordblite` backend isn't installable in this env, so `apply_cross_stack_links` and the new analysis Cypher are unit-tested (pure core + FakeDB orchestration) but not exercised end-to-end against a real store. Run `onelens import-graph` on a Java graph + a merged Vue export once FalkorDB is up to confirm.

**Remaining for production Phase 2:** per the IDE-plugin-centric decision, move Vue extraction into a WebStorm/JS PSI plugin module emitting this same JSON (the standalone extractor stays as the reference + test oracle); wire a `onelens vue-import`/merge CLI command via `mcp_server.py` (single source of truth) + regenerate `cli_generated.py`.

---

## 4. Phase 1 — Android / Kotlin (validates the abstraction)

Cheapest second language; proves Phase 0 on the JVM before any non-JVM work.

- Make `com.intellij.modules.java` **optional** in plugin.xml; add a Kotlin module gated on `org.jetbrains.kotlin`.
- Reimplement collectors against **UAST** (`UClass`, `UMethod`, `UCallExpression`) where possible — UAST gives one API over Java *and* Kotlin, shrinking long-term duplication. Where UAST is insufficient (Kotlin-specific: extension functions, top-level functions → `Function` nodes, `object`/companion, coroutines), fall back to Kotlin PSI.
- Drop the `.endsWith(".java")` delta filter (DeltaTracker) → driven by the active language module's file types.
- Emit `lang: "kotlin"`. Android specifics (Activities/Fragments/ViewModels as entry points) go in `android` profile additions.

**Exit criterion:** a Kotlin/Android project graphs with correct call/inheritance/override edges and Android entry points seed PageRank.

---

## 5. Phase 2 — Cross-stack full-stack trace (the headline)

Pair **Vue** (frontend) with **one backend**. Recommended backend: **Go** (cleanest type story via Go PSI / `go/types`, no DI indirection to model) — but Java already works, so the fastest path to a *demo* is **Vue ↔ existing Java/Spring**, then generalize. Decide per §7.

### 5.1 Vue extraction (WebStorm / JS+Vue PSI)
- Parse SFCs via the Vue plugin PSI: `Component` nodes (one per `.vue`), `USES_COMPONENT`/`RENDERS` edges from `<template>` tags and imports, Pinia stores as `Class`-like nodes, composables as `Function`.
- **`HttpCall` nodes:** detect outbound calls — `axios.get/post(...)`, `fetch(...)`, generated API clients — and capture `(httpMethod, pathTemplate)` from the literal/template argument. This is the frontend half of the contract.

### 5.2 Backend endpoints (already modeled)
`Endpoint` nodes already carry `(httpMethod, path)` via `HANDLES`. No new model — just ensure each backend extractor emits them with normalized path templates.

### 5.3 The linking layer (`CALLS_ENDPOINT`)
A post-import pass (new `python/src/onelens/importer/cross_stack.py`) matches `HttpCall` → `Endpoint` by `(method, normalized path)`:
- Normalize both sides: `/users/{id}` (Spring) ≡ `/users/:id` (Vue Router-ish) ≡ `` `/users/${id}` `` (template literal) → canonical `/users/{}`.
- Match on `(METHOD, canonicalPath)`; emit `CALLS_ENDPOINT` with a `confidence` property (exact vs. fuzzy/base-URL-stripped).
- Log unmatched calls — **no silent drops** (a Vue call with no backend match is a real finding: dead endpoint or typo'd path).
- Extend `onelens trace` / `onelens impact` to traverse `CALLS_ENDPOINT`, so "what frontend breaks if I change this endpoint" and "trace this button to its DB write" work end-to-end.

**Exit criterion:** `onelens trace --target "<vue-component>"` reaches a backend handler, and `onelens impact --endpoint "PATCH:/users/{id}"` lists the Vue components that call it.

---

## 6. Phase 3 — remaining backends

- **Python (PyCharm PSI):** `Function` nodes for module-level defs, `__init__` as constructor, decorators → `Annotation` (FastAPI/Flask routes → `Endpoint`). Duck-typing means `CALLS` edges are best-effort; lean on Pyright-grade inference where the PSI exposes it.
- **.NET / C# (Rider — the outlier):** standalone Roslyn (`Microsoft.CodeAnalysis`) console tool emitting the normalized JSON. Roslyn's `SemanticModel` gives PSI-grade accuracy. Map: `INamedTypeSymbol`→`Class`/`Interface`, `IMethodSymbol`→`Method`, attributes→`Annotation`, `[ApiController]`/`[HttpGet]`→`Endpoint`. Ships as a `dotnet tool`, not an IDE plugin. This is the heaviest item — budget for it accordingly.
- **Go** (if not chosen in Phase 2): Go PSI in GoLand; interfaces are structural — model `IMPLEMENTS` by method-set satisfaction, not declared inheritance.

---

## 7. Open decisions (resolve before Phase 2 code)

1. **Phase 2 backend:** fastest demo (Vue ↔ existing Java) vs. cleanest new extractor (Vue ↔ Go). Recommend Vue ↔ Java for the demo, then Go to prove the extractor abstraction.
2. **Plugin distribution:** one marketplace listing per IDE vs. a single multi-IDE listing. Affects CI matrix in [release.yml](../.github/workflows/release.yml).
3. **.NET sync UX:** no VFS auto-sync without a Rider plugin — accept manual/CI-triggered `dotnet onelens-extract` for .NET, or invest in a Rider plugin later.

---

## 8. Risks

- **`platformType = IC` has no Go/Python/JS PSI.** Building/testing those modules requires the corresponding IDE SDKs (GoLand/PyCharm/WebStorm) in CI — a real CI-matrix cost.
- **ChromaDB metadata drift** when adding `lang` (full vs. delta paths) — the recurring LESSONS-LEARNED footgun. One change, both paths, same commit.
- **Cross-stack false matches** — base URLs, API versioning (`/v1/`), and proxy rewrites break naive `(method,path)` matching. Confidence scoring + unmatched logging is mandatory, not optional.
- **Structural typing (Go/Python)** breaks the Java polymorphic-dispatch assumptions in [analysis.py:139-167](../python/src/onelens/graph/analysis.py#L139); gate that logic behind the language `framework` profile.

---

## 9. All-phases implementation (2026-06-04)

Every language now has a working reference extractor under [python/src/onelens/extractors/](../python/src/onelens/extractors/), each emitting the normalized JSON (`classes`/`methods`/`endpoints`/`components`/`httpCalls`) that the (now language-neutral) [loader.py](../python/src/onelens/importer/loader.py) imports and [cross_stack.py](../python/src/onelens/importer/cross_stack.py) links. Loader change: endpoints are read from a top-level `endpoints` list (any backend), not just `spring.endpoints`; `HANDLES` is emitted for every endpoint naming a handler.

| Phase | Language | Extractor | Frameworks / routes detected | CLI |
|---|---|---|---|---|
| 2 | **Vue** | `vue_extractor.py` | `axios.<m>()`, `fetch()`, `axios({method,url})`, `.vue` import → `USES_COMPONENT` | `python -m onelens.extractors.vue_extractor <dir> <out.json>` |
| 1 | **Kotlin/Android** | `kotlin_extractor.py` | Spring `@RequestMapping`+`@GetMapping/...`, Ktor `get("/x"){}`; class/object/interface, fun | `... kotlin_extractor ...` |
| 3 | **Go** | `go_extractor.py` | net/http `HandleFunc`, gin/echo/chi `r.GET(...)`; funcs + receiver methods | `... go_extractor ...` |
| 3 | **Python** | `python_extractor.py` | FastAPI/APIRouter decorators, Flask `@app.route(methods=)`, Django `path()`; via stdlib `ast` | `... python_extractor ...` |
| 3 | **.NET/C#** | `csharp_extractor.py` | ASP.NET `[Route]`+`[HttpGet(...)]` (combines `[controller]` prefix), minimal-API `app.MapGet(...)` | `... csharp_extractor ...` |

Cross-stack matching is backend-agnostic: `normalize_path` collapses every param dialect (`{id}` / `:id` / `${id}` / `<int:id>`) to `/{}` and folds case, so one Vue call links to a Go, Python, .NET, or Kotlin endpoint identically (proven in [test_multistack_integration.py](../python/tests/test_multistack_integration.py) and on real files).

### What "production" still needs (not done — environment/by-design)
1. **Live-DB validation** — run a real `onelens import-graph` (Java graph + merged extractor JSON) once FalkorDB is up; the DB Cypher is unit-tested via FakeDB only.
2. **Move extraction into IDE plugins** — per the IDE-plugin-centric decision, Kotlin/Go/Python/Vue extraction becomes IntelliJ-Platform plugin modules (their PSI); .NET becomes a Roslyn `dotnet tool`. The standalone extractors remain the reference + test oracle and emit the identical JSON.
3. **CLI/MCP wiring** — add `onelens <lang>-import`/merge commands via `mcp_server.py` (source of truth) + regenerate `cli_generated.py`.
4. **Depth** — call graphs for the new languages (only Java/Kotlin-PSI give true call edges today); `lang` in ChromaDB drawer metadata (full+delta, drift footgun); bean/polymorphic analysis gated per-language profile.

### Parser limitations (reference extractors)
These are regex/`ast` text parsers, not full compilers. Known gaps, all resolved by the eventual PSI/Roslyn path: Go/C#/Kotlin route detection is line/heuristic-based (handles same-line and split-line layouts, but not arbitrary macro/builder indirection); Python is `ast`-accurate for decorators but doesn't resolve dynamically-registered routes; net/http `HandleFunc` registers all methods but is recorded as `GET`. Test coverage: [test_backend_extractors.py](../python/tests/test_backend_extractors.py), [test_vue_extractor.py](../python/tests/test_vue_extractor.py).
