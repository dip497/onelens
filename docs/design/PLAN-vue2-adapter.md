# PLAN — Vue 2 support

Status: implemented (see PROGRESS Phase V2) — with corrections, recorded below
Author: OneLens
Related: ADR-036 (Next.js adapter), `framework/jscommon/`, `framework/vue3/`

## Summary

Vue 2 support is **not a new adapter**. It is a Vue-2 *mode* of the existing Vue
adapter: two new collectors, one detection widening, one alias fallback. The
JS/TS half of the stack (modules, imports, api-calls, routes) is already
version-agnostic and works on Vue 2 files today.

Estimated surface: **3 new files, 4 edited files, 0 Python changes.**
For scale: the Next.js adapter was 13 new files + a Python loader + a delta path.

## Why not a `Vue2Adapter`

A separate adapter would duplicate `Vue3Collector`'s orchestration, the context
class, the snapshot logic, and every shared collector call site — to express a
difference that is entirely *inside two collectors*. Vue 2 and Vue 3 share:

- the same `.vue` SFC file type and the same IntelliJ `VueFile` PSI tree
- the same `vue-router` route-object shape (v3 vs v4 differ in the router
  *constructor*, not in the `{ path, name, component, children }` records that
  `LazyRouteCollector` reads)
- the same axios/fetch call sites (`ApiCallCollector`)
- the same ES module graph (`JsModuleCollector`)

Two adapters would also both `detect()` true on a Vue 2 repo that has migrated
some files, and `ExportService`'s `lastContext` side-channel dispatch assumes one
active Vue context. Keep one adapter, add a `vueMajor` field to the context.

## Graph schema: no new node types

Vue 2 concepts map onto existing nodes:

| Vue 2 | Existing node | Note |
|-------|---------------|------|
| Options-API SFC | `Component` | `scriptSetup=false`; `props`/`emits` already modelled |
| Vuex module | `Store` | `state`/`getters`/`actions` fields already exist; add `mutations` |
| Mixin | *(none — `Component.mixins` string list)* | Modelling as `Composable` needs import resolution of the identifiers; deferred, see ADR-038 |
| `mapState`/`mapActions` | `USES_STORE` | Same edge, different call syntax |
| `vue-router` route | `Route` | Unchanged |

`StoreData` gains one field (`mutations: List<String>`) and `ComponentData`
gains `mixins: List<String>`. Both default-empty, so Vue 3 exports are
byte-identical and no importer change is required — the Python loader already
ignores unknown-but-absent fields.

Add `vueVersion: Int` to `Vue3Data` so a query can tell the two apart. Do NOT
rename `Vue3Data` / the `vue3` jsonKey — the rename would touch the loader, the
delta path, the skill, and every doc, to buy nothing. Note the naming debt in
DECISIONS and move on.

## Phase 1 — Detection (~10 lines)

`Vue3Adapter.detect()` currently regexes `"vue"\s*:\s*"[\^~]?3`. Widen to
capture the major and store it:

```kotlin
private val VUE_DEP_PATTERN = Regex(""""vue"\s*:\s*"[\^~>=\s]*([23])\.""")
```

Return the detected major from detection so `Vue3Collector` can branch. A repo
with both (monorepo, one Vue 2 app + one Vue 3 app) picks per-package-json —
the existing 2-level monorepo scan already enumerates them.

**Check:** unit test pinning `^2.6.14`, `~2.7.0`, `2.6.11`, `^3.4.0`, `>= 2.6`
to the right major. Pure-logic, no platform fixture — same pattern as
`NextjsPureLogicTest`.

## Phase 2 — Options-API components (the real work)

New `OptionsApiCollector`. Runs only when `vueMajor == 2`, over the same `.vue`
file list `SfcScriptSetupCollector` walks.

Target shape:

```js
export default {
  name: 'UserCard',
  props: { title: String, active: { type: Boolean, required: true } },
  data() { return { open: false } },
  computed: { fullName() {...}, ...mapState('user', ['profile']) },
  methods: { save() {...}, ...mapActions('user', ['fetchProfile']) },
  watch: { title(v) {...} },
  mixins: [formMixin],
  components: { ChildCard },
}
```

Extraction, all from `JSObjectLiteralExpression` off the default export:

- `props` — **reuse `SfcScriptSetupCollector.extractProps` verbatim**. The
  Options-API `props` value and the `defineProps({...})` first argument are the
  same object/array literal grammar. Extract that private method into a shared
  `VuePropParser` object; do not re-implement it.
- `emits` — Vue 2 has no `emits` option in 2.6. Collect `this.$emit('x')` call
  sites instead and dedupe the literal first args.
- `methods` / `computed` / `watch` keys → new `ComponentData` fields? **No.**
  Fold `methods` keys into the existing body text for embedding and skip the
  rest. Adding four list fields to the node buys queries nobody has asked for.
- `mixins` → `mixins: List<String>` (identifier text; resolved to fqn in
  Phase 4).
- `components` → local registration map, needed by Phase 4 `RENDERS`.

### The silent-empty-graph hazard

`SfcScriptSetupCollector.extractComponent` returns `null` when no compiler macro
and no literal `<script setup>` is found. On a Vue 2 repo that is *every file* —
the export succeeds, reports zero errors, and emits an empty component graph.
This is the exact failure mode of the `isVendorPath` absolute-path bug.

Guard by construction: after the component pass, if `.vue` files were found but
`ctx.components` is empty, log a **warning** naming the detected `vueMajor`.
A one-line assertion beats a post-mortem.

**Check:** a Vue 2 SFC fixture asserting props/mixins/methods extraction, plus
a case asserting a Vue 3 `<script setup>` file is still handled by the *old*
collector when `vueMajor == 3` (no regression).

## Phase 3 — Vuex stores

New `VuexStoreCollector`, modelled on `PiniaStoreCollector`'s structure
(cheap text pre-filter → `ReadAction` → object-literal walk).

Two shapes to handle:

```js
// 1. Namespaced module file
export default {
  namespaced: true,
  state: () => ({ items: [] }),
  getters: { count: s => s.items.length },
  mutations: { SET_ITEMS(s, v) { s.items = v } },
  actions: { async fetch({ commit }) {...} },
}

// 2. Root store
export default new Vuex.Store({ modules: { user, tickets } })
```

Text pre-filter: `Vuex` | `namespaced` | `mutations` (Pinia's probe is
`defineStore`). Module files often have none of the three at the top of the
file, so also accept a file under a `store/` or `stores/` directory.

Identity: keep the `fqn = "<filePath>::<name>"` rule that Pinia uses. Vuex
module names are *directory-derived* and collide constantly across features
(`store/user/index.js` and `store/admin/user.js` both named `user`), so
fqn-keyed MERGE matters more here than it did for Pinia, not less.

`name` = the namespace path when derivable (`user/profile`), else the filename.
`id` = same as name — Vuex has no `defineStore('id')` equivalent, so the two
collapse. Keep both fields populated so importer code stays shape-agnostic.

**Check:** fixture asserting a namespaced module yields state/getters/
mutations/actions keys, and that two same-named modules in different
directories get distinct fqns.

## Phase 4 — Edges (defer most of it)

`CallThroughResolver` currently links components → Pinia stores by resolving
`useXStore()` calls. Vue 2's equivalent is `mapState`/`mapGetters`/
`mapActions`/`mapMutations` spread into `computed`/`methods`, plus
`this.$store.dispatch('user/fetch')` string paths.

Ship only the first: `mapXxx('namespace', [...])` has the namespace as a string
literal in argument 0, which resolves to a store fqn with the same lookup table
`CallThroughResolver` already builds. That is a ~40-line branch.

**Defer** to a follow-up, and say so in PROGRESS rather than silently:

- `this.$store.dispatch('user/fetch')` string-path resolution — needs a
  namespace→fqn index and covers a minority of call sites in most repos.
- Mixin → component `USES_COMPOSABLE` edges — needs import resolution of the
  `mixins: [x]` identifiers.
- `RENDERS` from the local `components: {}` map. Next.js's `RendersResolver`
  cost a full debugging cycle (the extensionless-fqn bug) for 11 edges. Vue 2's
  version has the same shape and the same trap; it is not worth paying twice
  before anyone asks for it.

## Phase 5 — Alias fallback (~15 lines)

`ViteAliasResolver` reads jsconfig/tsconfig `paths` + `vite.config`. Vue 2 repos
are vue-cli/webpack: aliases live in `vue.config.js` under
`configureWebpack.resolve.alias` or `chainWebpack`.

Do **not** write a webpack-config parser — `vue.config.js` is executable JS and
parsing it properly means evaluating it.

Lazy fix that covers the overwhelming majority: vue-cli hardcodes `@` → `<root>/src`,
and scaffolds a `jsconfig.json` that already declares it. Add a fallback — if no
alias for `@` was resolved and `<root>/src` exists, register it:

```kotlin
// ponytail: vue-cli's universal `@`→src default. Real vue.config.js alias
// parsing needs JS evaluation; add only if a repo shows custom aliases.
```

Applies to Vue 3 too (a Vite repo with no jsconfig gets the same default), so
put it in `ViteAliasResolver`, not in the Vue 2 branch.

**Check:** unit test — empty config dir + a `src/` → yields `@`; explicit
jsconfig `@` → not overwritten.

## Delta

Vue is still full-export-only (see ADR-037 and the `delta_export_is_java_only`
constraint: `DeltaTracker` has hardcoded `.java` filters and the Collector SPI
has no scoped-delta hook). Vue 2 inherits that. **Do not wire delta in this
plan** — it is a `jscommon`-wide problem that should be solved once for Vue 2,
Vue 3, and Next.js together, not a third time per-adapter.

`scripts/onelens-headless.sh resync --frontend` already warns and does a full
re-export, so the operational path is correct today.

## Verification (do not skip — this is where the last three adapters broke)

Every phase E2E against a real Vue 2 repo, checking **counts, not exit codes**:

```
components > 0            # Phase 2 — the silent-empty trap
stores > 0                # Phase 3
usesStore > 0             # Phase 4
imports resolve to real modules, not raw '@/...' strings   # Phase 5
```

The Next.js work established that E2E verification and code review find
**disjoint** bug classes — E2E caught 4 bugs, review caught 7 more including two
data-loss classes E2E could not see. Budget for both.

## Out of scope

- Vue 2.7 `<script setup>` / `@vue/composition-api` — if a file has the macros,
  the *existing* Vue 3 collector already handles it. Run both collectors when
  `vueMajor == 2` and let each skip what it does not recognize. Zero extra work.
- Class components (`vue-property-decorator`) — a distinct TS decorator grammar.
  Add only if a target repo uses it.
- Vue 2 → 3 migration analysis. Different product.

## Sequencing

Phases 1→2→3 are the shippable core; 4 and 5 are independent and can land in
either order. Phase 2 alone makes a Vue 2 repo visible in the graph at all,
which is most of the user-facing value.

---

## Postmortem — what the plan got wrong

The plan named four gaps. Implementation against fixtures closed all four. Then
profiling a **real** Vue 2.7.16 codebase (2114 SFCs, 44 Vuex modules) surfaced
five more, every one of which would have shipped a silently-empty or badly
incomplete subgraph.
Recording them because the pattern generalises: *fixtures encode what you already
believe; only real code disputes it.*

**1. Vuex modules use named exports, not a default object.**
The plan assumed `export default { state, getters, mutations, actions }`. All 44
modules used `export const state = {…}` / `export const getters = {…}` as separate
top-level declarations. The shape probe matched nothing → **zero stores**.
Fixed by falling back to top-level `const <section>` declarations
(`VuexStoreCollector.namedExportSections`).

**2. Namespaces come from the directory, not the filename.**
Modules live at `state/modules/<ns>/module.js` — 44 files all named `module.js`.
The plan's filename fallback named every namespace the literal string `"module"`,
collapsing all 44 into one id and producing **zero USES_STORE edges**. Fixed by
anchoring on the last store-marker segment and dropping generic filenames
(`index` / `module` / `store`).

**3. `createNamespacedHelpers`, not namespace-literal `mapState`.**
The plan wired `mapState('ns', […])`. That form appeared **0 times**; all 44 call
sites used `createNamespacedHelpers('userGroup')`. Handling only the planned form
would again have emitted zero edges.

**4. Directory names and registered namespaces use different casing.**
Directories are kebab-case (`user-group/`), namespaces camelCase (`userGroup`).
Raw string comparison misses every store. Fixed with a normalised lookup key
(`namespaceKey`) rather than by guessing a convention and rewriting the name.

**5. Modules are not always one-module-per-file.**
8 of 44 `module.js` files declared no module of their own — they were *registries*
exporting `modules = { key: factory() }`, composing into `<parent>/<key>` namespaces
(`status/request`, `form/problem`). Supporting them took store coverage from 36/44 to
44/44 and surfaced 95 additional namespaces the graph had been missing entirely.

**Bonus — the `@`→`src` fallback was actively wrong here.** This repo maps `@` to
the project ROOT and uses `@src` for `src/`. Assuming the vue-cli default would have
mis-resolved every `@/…` import to a sibling of the intended file instead of failing
loudly. The fallback is now last-resort only, behind a real parser for
`aliases.config.js` (17 aliases, none of which any of the planned sources declared —
the repo has no jsconfig, no tsconfig, and an executable `vue.config.js`).

**Takeaway for the next adapter.** The plan's verification section said to check
counts rather than exit codes, and that is what caught these — but only because the
profiling happened against a real repo *before* declaring done. Do the profiling
pass first next time: `grep -c` for each shape the collectors assume, on the actual
target, and treat any zero as a design error rather than a coding one.
