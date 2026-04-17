# Vue 3 PSI Proof-of-Concept — Findings

**Date:** 2026-04-17
**Platform:** IntelliJ IDEA Ultimate 2025.1.3 (build 251.26927.53)
**Vue plugin:** bundled with IU 2025.1.3 (`org.jetbrains.plugins.vue`)
**JavaScript plugin:** bundled with IU 2025.1.3 (`JavaScript`)

## Outcome

**PASS.** All six assertions succeeded on the first run. Vue 3 `<script setup>` macros, cross-file composable resolution, Pinia `defineStore` shape, and axios template-URL arguments are all accessible via the public JavaScript / Vue PSI APIs that we will rely on in Phase B. No pivot to regex/AST fallback needed.

Test source: `plugin/src/test/kotlin/com/onelens/plugin/framework/vue3/VuePsiPoCTest.kt`
Fixtures: `plugin/src/test/resources/vue-fixtures/`
Test report: `plugin/build/test-results/test/TEST-com.onelens.plugin.framework.vue3.VuePsiPoCTest.xml`
Runtime: 22.9s total (20.9s of that is first-test IDE warm-up; remaining five cases total 2s).

## APIs validated

| Concern | API used | Confirmed |
|---|---|---|
| Walk JS calls in a `.vue` SFC | `PsiTreeUtil.findChildrenOfType(vueFile, JSCallExpression::class.java)` | ✓ Works on the top-level `VueFile` PSI tree; Vue plugin stitches embedded JS into the same tree. |
| Locate `defineProps` | `JSCallExpression.methodExpression.text == "defineProps"` | ✓ |
| Extract prop declarations | `JSCallExpression.argumentList.arguments[0].text` | ✓ — argument textual body contains all prop keys (`title`, `count`, `active`). Structured walk of the JSObjectLiteralExpression is the next step for typed extraction. |
| `defineEmits` | same pattern | ✓ — array literal of event names readable. |
| `defineExpose` | same pattern | ✓ |
| Cross-file composable resolve | `JSCallExpression.methodExpression.reference.resolve()` → `JSFunction` | ✓ — `useCounter()` in `UsesComposable.vue` resolves to its `export function useCounter()` in `useCounter.js` across files. |
| Pinia `defineStore` | same call-walk | ✓ — id literal (`'user'`) present in `args[0]`, options object in `args[1]`. |
| axios template URL | `JSCallExpression.argumentList.arguments[0].text` | ✓ — template-string ` `/${moduleName}/search/byqual` ` surfaces raw as text, ready for `UrlTemplateExtractor` + `ModuleNameBinder` to tokenize. |

## Class/API names locked for Phase B

Phase B collectors will use:

- `com.intellij.lang.javascript.psi.JSCallExpression` — any `foo()` call site.
- `com.intellij.lang.javascript.psi.JSFunction` — resolved call target; has `.body`, `.parameters`, `.returnedExpressions`.
- `com.intellij.lang.javascript.psi.JSObjectLiteralExpression` — `defineProps({...})` argument; has `.properties` and per-property type.
- `com.intellij.lang.javascript.psi.JSReferenceExpression` — `methodExpression` of a call; `.reference.resolve()` for cross-file.
- `com.intellij.psi.util.PsiTreeUtil.findChildrenOfType` — tree walk.
- `com.intellij.testFramework.fixtures.BasePlatformTestCase` — collector unit-test base class (replaces the older `LightPlatformCodeInsightFixtureTestCase` mentioned in the plan; semantically equivalent).

`org.jetbrains.vuejs.*` classes were **not** needed for this PoC — the embedded-JS tree inside a `VueFile` exposes everything through the public JS PSI. Structured prop-type extraction (distinguishing `String` vs `{ type: Number, default: 0 }`) may benefit from `org.jetbrains.vuejs.codeInsight.VueScriptSetupMacroProcessor` (or similar) later; the textual fallback is already enough for name extraction.

## Implications for the plan

- **Decision 8 (PoC gate):** passes. Phase B unblocked.
- **B1 skeleton** can proceed as described — `SfcScriptSetupCollector`, `PiniaStoreCollector`, `ComposableCollector`, `ApiCallCollector` all viable.
- **Fallback path** documented in risks (regex/AST) stays on the shelf as insurance only.
- **No new risks surfaced.** The axios first-arg text includes the full template-string literal, so `UrlTemplateExtractor` can operate on the raw text without needing special PSI for template literals.

## Gradle plumbing that made this work

- `platformType = IU` in `gradle.properties`. Ultimate bundles `JavaScript` + `org.jetbrains.plugins.vue`. Community does not ship JS; Marketplace does not publish JS. See the failed `compatiblePlugins("JavaScript")` attempt in the decision log.
- Bundled plugins declared via `platformBundledPlugins = com.intellij.java,JavaScript,org.jetbrains.plugins.vue`.
- `platformCompatiblePlugins` wired for future use when Marketplace-only plugins are added; currently empty.
- Ship-time compatibility unchanged: the plugin JAR's `plugin.xml` declares Java / Spring / Vue as **optional** via `<depends optional="true" config-file="...">`, so the same build still installs on IC, WebStorm, and PyCharm.

## Work queue that PoC unblocks

Phase B Week 1 (per plan file `/home/dipendra-sharma/.claude/plans/ok-done-hai-kar-adaptive-zebra.md`):
1. `ViteAliasResolver` — investigate if the bundled JavaScript plugin exposes a resolved-alias API before writing config parsers.
2. `SymlinkResolver` — straightforward, no PSI research required.
3. Balloon notification for symlinks outside content roots.

Phase B Week 2 (collectors that consume the APIs validated above):
- `SfcScriptSetupCollector` — consume `JSObjectLiteralExpression.properties` inside `defineProps`/`defineEmits` arguments, emit `ComponentData` with typed `PropData`.
- `PiniaStoreCollector` — walk `defineStore` options arg; extract `state` function, `getters` / `actions` object members.
- `ComposableCollector` — regex-match `useX` function names + inspect return expression (ref-returning).
