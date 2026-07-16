# OneLens — Vue 3 Reference

> **⚠️ Migration notice** — CLI examples below use the legacy names
> `onelens query` / `onelens call-tool onelens_status`. The canonical form is
> `onelens call-tool onelens_query --cypher "..."` /
> `onelens call-tool onelens_status`. Content below is otherwise current.

Applies when the active graph has `Component`, `Composable`, `Store`, `Route`, or `ApiCall` nodes. Vue 3 coverage is built from IntelliJ / WebStorm's JavaScript + Vue plugin PSI, so type-resolution of `<script setup>` macros, cross-file composable imports, and Pinia `defineStore` arguments is accurate.

This reference is self-contained for Vue-only questions. For cross-stack traversals (Vue → Spring), see `queries-code.md` ("Full-stack trace").

## Schema

### Nodes

| Label | Key Properties | Description |
|-------|---------------|-------------|
| Component | filePath, name, scriptSetup, propNames, emits, exposes, body, wing | Vue 3 Single-File Component. `filePath` is relative + canonicalized through symlinks |
| Composable | fqn, name, filePath, body, wing | `useX()` function returning refs/computed/methods |
| Store | id, name, filePath, style, state, getters, actions, body, wing | Pinia `defineStore(...)`. `style` is `options` or `setup`; `state`/`getters`/`actions` are comma-separated names |
| Route | name, path, componentRef, meta, parentName, filePath, wing | vue-router route. `name` is interpolation-resolved from the sibling `config.js`. `componentRef` is the lazy-import target path |
| ApiCall | fqn, method, path, parametric, binding, callerFqn, filePath, wing | axios/fetch/api call site. `parametric=true` means the URL had a `${…}` interpolation; `binding` records the source variable (e.g. `"moduleName"` or `"unresolved"`) |

`wing` on every Vue node equals the `--graph` name. Cross-wing queries filter on `wing` to keep project data isolated in a shared FalkorDB instance.

### Edges

| Type | From → To | Meaning |
|------|-----------|---------|
| USES_STORE | Component/Composable → Store | Reads a Pinia store. `r.indirect=true` when the caller invoked a helper wrapper (e.g. `useTaskMethods()`) that internally calls the store; `r.via` names the wrapper |
| USES_COMPOSABLE | Component/Composable → Composable | Component or another composable invokes a composable |
| DISPATCHES | Route → Component | vue-router loads this lazy-imported component for the route |
| CALLS_API | Component/Composable → ApiCall | HTTP call site belongs to this caller |
| HITS | ApiCall → Endpoint | Cross-wing bridge: ApiCall path + method match a Spring Endpoint after normalization. Only exists when both wings are on one FalkorDB graph |

## CLI

```bash
onelens call-tool onelens_query --cypher "<CYPHER>" --graph <wing-name>
onelens call-tool onelens_status --graph <wing-name>
```

Vue-side `retrieve` / `impact` / `trace` are Phase B2 scope — today use Cypher for Vue and `retrieve` only against JVM wings.

### Verify the wing is indexed

```bash
onelens call-tool onelens_status --graph <wing-name>
```

Expect non-zero `Component` / `Store` / `Route` / `ApiCall` / `Composable`. If all zero or the wing is missing, re-run the IntelliJ "Sync Graph" action against that project. **Don't reach for `redis-cli`** — it's falkordb-only, port-coupled (17532), and bypasses backend abstraction. CLI route works across falkordb / falkordblite / neo4j.

## Query Patterns

### 1. Which components call an API endpoint by path?

Use `CONTAINS` on `a.path` because many calls are parametric (`/${moduleName}/search/byqual`).

```cypher
MATCH (c:Component)-[:CALLS_API]->(a:ApiCall)
WHERE a.path CONTAINS '/ticket' OR a.path CONTAINS 'ticket'
RETURN c.name AS component, a.method, a.path, a.parametric
ORDER BY component
LIMIT 30
```

### 2. Which stores does a component depend on (direct + indirect)?

`indirect=true` hits mean the component called a helper wrapper (e.g. `useXMethods()`) that internally invokes the store. `via` names the wrapper so the reader knows where to look next.

```cypher
MATCH (c:Component {name: 'TicketView'})-[r:USES_STORE]->(s:Store)
RETURN s.id, s.name, r.indirect, r.via
ORDER BY r.indirect, s.id
```

### 3. Route → component map — "what renders at /tickets?"

```cypher
MATCH (r:Route)-[:DISPATCHES]->(c:Component)
WHERE r.path CONTAINS '/t/' OR r.path CONTAINS 'ticket'
RETURN r.name AS route_name, r.path AS route_path, c.name AS component, c.filePath
LIMIT 30
```

### 4. Composable fanout — "who uses useCounter?"

```cypher
MATCH (caller)-[:USES_COMPOSABLE]->(co:Composable {name: 'useCounter'})
RETURN labels(caller)[0] AS type,
       coalesce(caller.name, caller.fqn) AS caller,
       caller.filePath
ORDER BY caller
```

### 5. Store surface — "what does useUserStore expose?"

```cypher
MATCH (s:Store {name: 'useUserStore'})
RETURN s.id, s.style, s.state, s.getters, s.actions, s.filePath
```

The `state`, `getters`, `actions` fields are comma-separated lists of property names (not full types). For the full body inspect `s.body` or read the file at `s.filePath`.

### 6. Orphan components — "which .vue files aren't rendered by any route?"

```cypher
MATCH (c:Component)
WHERE NOT EXISTS { MATCH (:Route)-[:DISPATCHES]->(c) }
RETURN c.name, c.filePath
ORDER BY c.filePath
LIMIT 50
```

Beware: many components are nested children rendered by a parent rather than by a route. The query is a hint, not a dead-code proof.

### 7. Find Pinia stores that are never used

```cypher
MATCH (s:Store)
WHERE NOT EXISTS { MATCH ()-[:USES_STORE]->(s) }
RETURN s.id, s.name, s.filePath
```

Works best after the `CallThroughResolver` has run during import — otherwise indirect usage via helpers looks like zero direct edges.

### 8. Find parametric URLs whose binding didn't resolve

```cypher
MATCH (a:ApiCall {parametric: true})
WHERE a.binding IS NULL OR a.binding IN ['unresolved', 'template']
RETURN a.method, a.path, a.callerFqn
ORDER BY a.path
LIMIT 30
```

These are candidates for the `ModuleNameBinder` to learn: the binding variable isn't a top-level `const = 'literal'`. For the bridge matcher this means no literal path variant was emitted, so `HITS` edges won't form.

## Understanding Vue PSI quirks

- **Dynamic imports in routes.** `component: () => import('./views/X.vue')` — the collector extracts the literal string out of the arrow body via text fallback (the JS PSI's `import(…)` node shape varies between plugin versions). Expect the exact relative path as typed.
- **`<script setup>` macros.** `defineProps({...})` / `defineEmits([...])` / `defineExpose({...})` are extracted textually for names. Typed extraction (distinguishing `String` vs `{ type: Number, default: 0 }`) is captured on `PropData` but the graph stores prop names only (`Component.propNames`).
- **Pinia options vs setup style.** Options style (`defineStore(id, { state, getters, actions })`) preserves the three categories separately. Setup style (`defineStore(id, () => { … return {...} })`) collapses state+getters+actions into `actions` because setup functions return a flat object.
- **Helper indirection.** Repos with `state/<slice>/helpers.js` that wrap store access are common. `CallThroughResolver` emits `USES_STORE {indirect: true, via: 'useXMethods'}` so the Component → Store relationship isn't invisible. When answering "which stores does X use", always include both direct and indirect edges.
- **API-helper files (`*-api.js`)** are a known gap. When API calls live in a plain JS helper (not a Component, not a `useX` composable), no `CALLS_API` edge is emitted because there is no node to anchor the edge to. The information is still in the graph — the `ApiCall.callerFqn` / `ApiCall.filePath` properties store where the call came from. To answer "which API calls exist for `/ticket/*`" use `MATCH (a:ApiCall) WHERE a.path CONTAINS 'ticket' RETURN a.method, a.path, a.callerFqn, a.filePath`. Cross-stack `HITS → Endpoint` traversals work regardless because HITS only needs `method` + normalized `path` on both sides. Phase B2 plan: import-chain resolution so `Component -> helper -> ApiCall` becomes a real 2-hop edge.
- **Symlinked sources (e.g. `src/ui → ../shared-ui`).** The symlink is followed and its files are treated as same-wing. If the target directory isn't an IntelliJ content root the plugin shows a balloon — accept the prompt so the graph includes those files.
- **Alias resolution.** `ViteAliasResolver` merges `jsconfig.json` / `tsconfig.json` paths with `vite.config.*` `resolve.alias`, with vite winning on conflicts. On a large real-world Vue 3 repo we verified 27 of 27 aliases resolve this way — a single `jsconfig` entry would otherwise miss 26.

## Tips

- Use `name` on Components/Stores/Composables and `path` on Routes/ApiCalls for most queries; `fqn` only when the user quotes one.
- `filePath` values are project-relative (`src/modules/ticket/…`). `CONTAINS` queries work well.
- `wing` filtering is automatic when your Cypher targets one project, but becomes essential when the graph holds multiple repos — add `WHERE c.wing = '<project>'` to avoid cross-project bleed.
- To answer "will this Vue change break the backend", pivot to the cross-stack section in `queries-code.md` — `ApiCall -[:HITS]-> Endpoint <-[:HANDLES]- Method` is the canonical path.
- If counts look wrong (0 stores, 0 routes), the cheap checks are: `stats` labels (is the wing actually indexed?), `package.json` (is `"vue": "^3…"` present so the adapter ran?), and `Vue3Adapter`'s log line "Active framework adapters: …".

## Answer principles

Same shared principles as the JVM reference: answer the question with evidence, don't dump pointers; structural reachability ≠ runtime execution (a `USES_STORE` edge means the code calls the store getter, not that the store is read in production); empty result = genuine no-match, don't invent synonyms; LIMIT to 20-30 by default.
