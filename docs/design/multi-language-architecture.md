# Multi-language / multi-framework architecture

**Status:** Design · 2026-06 · derived from a 3-agent architecture audit
**Goal:** scale OneLens from "Java/Spring + Vue3" to **N languages × N frameworks**
without rewriting the core for each, and without losing the 100%-type-accuracy moat.

## 1. Where we are (audit findings)

### Plugin side — a real SPI, a leaky orchestrator

- `FrameworkAdapter` (`plugin/.../framework/FrameworkAdapter.kt:21`) is a genuine
  extension point: `id`, `jsonKey`, `detect()`, `collectors()`, registered via the
  `com.onelens.plugin.frameworkAdapter` EP, **dynamically gated** behind the IntelliJ
  language plugin it needs (`plugin.xml` `<depends optional config-file>` → Vue adapter
  only loads when the Vue plugin is present). Vue3 proves the pattern works.
- **Leak 1 — orchestrator downcast.** `ExportService` ignores the opaque
  `CollectorOutput.data` and instead does `when (collector) { is SpringBootCollector ->
  collector.lastResult; is Vue3Collector -> collector.lastContext }` (self-flagged P1
  debt, ADR-010). A third adapter can't be added without editing `ExportService`.
- **Leak 2 — language ⊗ framework conflation.** `FrameworkAdapter` bundles *how to parse*
  (Java PSI) with *what framework to derive* (Spring). There's no `LanguageExtractor`.
- **Leak 3 — framework bleed into the universal folder.** `JpaCollector.kt` /
  `SpringCollector.kt` live under `export/collectors/` (the *universal* Java folder), not
  `framework/springboot/`. `SpringBootAdapter.kt:55` already promises this relocation.

### Importer side — no SPI at all

- `GraphLoader.load_full()` (`loader.py:108`) is a ~1400-line god-method with a hardcoded
  `classes/methods/fields … if spring … if jpa … if vue3` chain. No registry, no dispatch.
- `delta_loader.py` **re-forks every subsystem** (Spring, JPA, tests, type-flow, data-flow,
  enums). The two write the same graph through two separately-maintained bodies of Cypher
  → the entire "delta diverges from full" bug class (a full session was spent patching it:
  Spring wing, phantom CALLS, enum split, JPA/test demotion). **The duplication is the
  root cause, not the individual bugs.**
- `schema.py` is one flat dict mixing every framework's labels.
- The importer privileges `classes/methods/fields/spring/jpa` as *top-level* JSON keys
  (implicitly Java) while Vue is a *nested subdoc*. There is no language-neutral core.

### The moat is real but non-portable

100% type accuracy = IntelliJ PSI, which is **per-language and ships inside an IDE**. There
is no single "PSI backend" to extend — Java support is the Java plugin, Python the PyCharm
plugin, Go the GoLand plugin (Ultimate-only). Scaling languages forces an extraction-backend
strategy, not just a new collector.

## 2. Target architecture

### Two orthogonal SPIs

Split the conflated adapter into **how to parse** and **what to derive**:

```kotlin
// Universal, language-neutral symbol graph — produced by ANY extractor.
data class SymbolGraph(
    val classes: List<ClassData>, val methods: List<MethodData>,
    val fields: List<FieldData>, val calls: List<CallEdge>,
    val inheritance: List<InheritanceEdge>,
    val source: ExtractorSource,   // PSI | LSP | TREE_SITTER  — accuracy tag
)

interface LanguageExtractor {
    val languageId: String                  // "java", "python", "typescript", "go"
    fun detect(project: Project): Boolean
    fun extract(ctx: CollectContext): SymbolGraph   // universal core ONLY
}

interface FrameworkAdapter {
    val id: String                          // "spring-boot", "django", "fastapi"
    val jsonKey: String
    val languageId: String                  // which extractor it rides on
    fun detect(project: Project): Boolean
    fun deriveOverlay(ctx: CollectContext, core: SymbolGraph): FrameworkOverlay
}
```

A framework adapter **consumes** the already-extracted universal graph instead of re-walking
files. `ExportService` becomes adapter-agnostic: run each detected `LanguageExtractor` → fill
the universal core; run each `FrameworkAdapter` whose `languageId` matched → merge overlays by
`jsonKey`. No `when (collector)`, no per-type progress fractions. The opaque-output promise the
SPI already makes is finally honored.

### Extraction-backend strategy (tiered, honest about accuracy)

| Tier | Backend | Accuracy | Cost | Use |
|------|---------|----------|------|-----|
| 1 | IntelliJ PSI per language | 100% (the moat) | needs that language's IDE plugin | Java today; Python (PyCharm), etc. |
| 2 | LSP (pyright, gopls, rust-analyzer, OmniSharp) | high, standalone | per-server integration | the realistic path for Go/C#/standalone-Python |
| 3 | tree-sitter | parse-accurate, resolution-weak | zero deps | floor for languages with no plugin/server |

Every emitted node carries `source = PSI|LSP|TREE_SITTER` so retrieval + the skill express
confidence honestly. The JSON-export → importer boundary is the right seam: a non-IntelliJ
extractor (LSP-driven CLI) can emit the same JSON with no plugin at all.

### Importer — registry, not god-method

```python
class SubdocLoader(Protocol):
    json_key: str
    def schema_fragment(self) -> dict: ...           # labels/indexes this loader owns
    def load_full(self, db, data, wing) -> None: ...
    def apply_delta(self, db, data, wing) -> None: ...   # SAME class → no fork

LOADERS = [CoreLoader(), SpringLoader(), JpaLoader(), TestLoader(),
           Vue3Loader(), DataFlowLoader(), AnnotationLoader()]
           # contributor appends DjangoLoader() — one line, no core edit
```

`load_full` and `apply_delta` both iterate `LOADERS`. The generic `_batch_nodes`/`_batch_edges`
helpers stay as the shared primitive. **One subsystem = one class implementing both paths**,
so full and delta can no longer drift — structurally killing this session's entire bug class.
`schema.py` becomes `core_schema` + per-loader fragments.

### Target package layout

```
plugin/.../
├── core/        LanguageExtractor.kt  FrameworkAdapter.kt  SymbolGraph.kt  ExportService.kt
├── lang/        java/JavaPsiExtractor  python/PythonExtractor(LSP)  ts/TsPsiExtractor
└── framework/   springboot/  jpa/  vue3/  react/  django/  fastapi/   ← Spring/JPA move here

python/src/onelens/importer/
├── loader.py        # GraphLoader.load_full — orchestration only (iterate LOADERS)
├── delta_loader.py  # DeltaLoader.apply_delta — orchestration only (iterate LOADERS)
├── loaders/         # core.py spring.py jpa.py tests.py vue3.py dataflow.py annotations.py
└── graph_writer.py  # shared batch primitives + _enrich_method / _normalize_type
```

## 3. Staged migration (never breaks shipped Java/Spring + Vue3)

Each step is independently shippable and verified by re-running a Java+Vue export and
diffing the JSON / golden graph — the wire format does not change until we choose to.

1. **Importer `LOADERS` registry behind the current output.** Extract the inline
   spring/jpa/vue3/test blocks into `SubdocLoader` classes with `load_full` + `apply_delta`;
   `loader.py` and `delta_loader.py` iterate the registry. Same JSON in, same graph out.
   **Highest value — kills the full/delta drift bug class.** Pay down first.
2. **Plugin: honor opaque `CollectorOutput`, kill the `ExportService` downcast.** Move the
   `lastResult`/`lastContext` data into `CollectorOutput.data`; orchestrator consumes it
   generically. Pure refactor, JSON unchanged.
3. **Plugin: split `LanguageExtractor` out of `FrameworkAdapter`; relocate Spring/JPA
   collectors under `framework/`.** The cleanup `SpringBootAdapter.kt:55` already promises.
4. **Validate the framework seam — add React (TypeScript).** Reuses the TS extractor Vue
   needs; no new language. Proves a framework adds with zero core edits.
5. **Validate the language seam — add Python via LSP/tree-sitter + Django/FastAPI.** Emits the
   same `SymbolGraph` JSON without the IntelliJ plugin; answers the moat question empirically
   via the `source` accuracy tag.

**Sequencing rationale:** steps 1–3 are pure refactors with zero wire-format change (safe on
shipped support) and pay down explicit ADR-010 + drift debt; steps 4–5 de-risk one axis each
(new framework, then new language) rather than both at once.

## 4. Decisions recorded

See `docs/DECISIONS.md`: ADR-032 (two-SPI split), ADR-033 (tiered extraction backends +
accuracy tag), ADR-034 (importer SubdocLoader registry kills full/delta fork).
