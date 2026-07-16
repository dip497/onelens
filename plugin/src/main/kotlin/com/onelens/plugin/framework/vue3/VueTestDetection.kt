package com.onelens.plugin.framework.vue3

/**
 * Single source of truth for recognising test-originated files in the Vue3 /
 * JavaScript export pipeline. Every Vue3 collector that emits nodes tagged
 * `isTest` routes through [isTestFile] so the convention lives in one place.
 *
 * Why tag rather than exclude: Java exports include `src/test/java/...Test.java`
 * classes (they carry unique FQNs, so they coexist with production classes).
 * The Vue3 pipeline mirrors that — test files are indexed AND tagged, letting
 * retrieval / Cypher distinguish `WHERE NOT s.isTest` (production) from
 * `WHERE s.isTest` (test doubles, vi.mock factories). No data loss, consistent
 * with the existing Java behaviour.
 *
 * Conventions covered (Vitest + Jest + common Vue CLI layouts):
 *   - `__tests__/` directory segment (Vitest default, Vue CLI)
 *   - `.test.js` / `.test.ts` / `.test.mjs` suffix (Jest / Vitest default)
 *   - `.spec.js` / `.spec.ts` / `.spec.mjs` suffix (Jest / Cypress / Vue CLI)
 *   - top-level `tests/` / `e2e/` / `test/` directory (common monorepo layout)
 *
 * Explicitly NOT matched:
 *   - a file merely containing the word "test" (false positives — e.g.
 *     `latest.js`, `testerUtils.js`)
 *   - `.vue` files (test components live in `.test.js` wrappers, not `.vue`)
 */
private val TEST_FILE_PATTERNS = listOf(
    Regex("""(^|/)__tests__/"""),
    Regex("""\.(test|spec)\.(js|ts|mjs|jsx|tsx)$"""),
    Regex("""(^|/)(tests?|e2e)/"""),
)

fun isTestFile(filePath: String): Boolean {
    if (filePath.isEmpty()) return false
    return TEST_FILE_PATTERNS.any { it.containsMatchIn(filePath) }
}
