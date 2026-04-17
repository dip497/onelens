package com.onelens.plugin.framework.vue3.resolver

import junit.framework.TestCase
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText

/**
 * Pure-logic tests for [ViteAliasResolver.resolveImport]. The disk-IO surface
 * ([ViteAliasResolver.resolve]) is exercised by a VFS-backed test in a later pass —
 * here we pin the import-matching algorithm, which is the hot path collectors use.
 */
class ViteAliasResolverTest : TestCase() {

    private val base: Path = Path.of("/tmp/fake-project")

    private val aliases = mapOf(
        "@" to base.resolve("src"),
        "@ui" to base.resolve("src/ui"),
        "@utils" to base.resolve("src/utils"),
        "@state" to base.resolve("src/state"),
    )

    fun testExactAliasResolves() {
        val r = ViteAliasResolver.resolveImport(aliases, "@ui")
        assertEquals(base.resolve("src/ui"), r)
    }

    fun testPrefixedAliasResolves() {
        val r = ViteAliasResolver.resolveImport(aliases, "@ui/components/Button")
        assertEquals(base.resolve("src/ui/components/Button"), r)
    }

    fun testLongestMatchWins() {
        // "@" also matches "@ui/..." but "@ui" is longer; must win.
        val r = ViteAliasResolver.resolveImport(aliases, "@ui/Foo")
        assertEquals(base.resolve("src/ui/Foo"), r)
    }

    fun testShortAliasFallsThroughToGeneric() {
        val r = ViteAliasResolver.resolveImport(aliases, "@/components/Header.vue")
        assertEquals(base.resolve("src/components/Header.vue"), r)
    }

    fun testUnknownAliasReturnsNull() {
        assertNull(ViteAliasResolver.resolveImport(aliases, "foo/bar"))
        assertNull(ViteAliasResolver.resolveImport(aliases, "@unknown/x"))
    }

    fun testBlankImportReturnsNull() {
        assertNull(ViteAliasResolver.resolveImport(aliases, ""))
    }

    /** Tsconfig/jsconfig parse path — full IO round trip in a temp dir. */
    fun testTsConfigPathsParse() {
        val tmp = Files.createTempDirectory("vue-alias-test")
        tmp.resolve("jsconfig.json").writeText(
            """
            {
              "compilerOptions": {
                "paths": {
                  "@/*": ["src/*"],
                  "@ui/*": ["src/ui/*"],
                  "@utils/*": ["src/utils/*"]
                }
              }
            }
            """.trimIndent()
        )
        val resolved = ViteAliasResolver.resolveFromBase(tmp)
        assertEquals(3, resolved.size)
        assertEquals(tmp.resolve("src"), resolved["@"])
        assertEquals(tmp.resolve("src/ui"), resolved["@ui"])
    }

    /** Vite-config fallback path — inline `resolve.alias` block. */
    fun testViteConfigLiteralAliasParse() {
        val tmp = Files.createTempDirectory("vue-vite-test")
        tmp.resolve("vite.config.js").writeText(
            """
            import { defineConfig } from 'vite'
            export default defineConfig({
              resolve: {
                alias: {
                  '@': 'src',
                  '@ui': 'src/ui',
                  '@state': 'src/state'
                }
              }
            })
            """.trimIndent()
        )
        val resolved = ViteAliasResolver.resolveFromBase(tmp)
        assertTrue("must see @ui alias", resolved.containsKey("@ui"))
        assertEquals(tmp.resolve("src/ui"), resolved["@ui"])
    }

    fun testEmptyWhenNoConfig() {
        val tmp = Files.createTempDirectory("vue-empty-test")
        val resolved = ViteAliasResolver.resolveFromBase(tmp)
        assertTrue(resolved.isEmpty())
    }

    /**
     * Real-world shape: jsconfig carries a narrow subset for IDE-only; vite.config
     * carries the canonical full list. Merge must yield the union with vite winning.
     * Regression against a real-world Vue 3 repo setup (jsconfig=1, vite=27).
     */
    fun testMergeUnionWithViteWinning() {
        val tmp = Files.createTempDirectory("vue-merge-test")
        tmp.resolve("jsconfig.json").writeText(
            """
            {
              "compilerOptions": {
                "paths": {
                  "@/*": ["src-old/*"]
                }
              }
            }
            """.trimIndent()
        )
        tmp.resolve("vite.config.js").writeText(
            """
            import path from 'path'
            export default {
              resolve: {
                alias: {
                  '@': path.resolve(__dirname, './src'),
                  '@ui': path.resolve(__dirname, './ui'),
                  '@state': path.resolve(__dirname, './src/state')
                }
              }
            }
            """.trimIndent()
        )
        val resolved = ViteAliasResolver.resolveFromBase(tmp)
        assertEquals("should merge both sources", 3, resolved.size)
        // vite wins on conflict — must resolve to src, not src-old
        assertEquals(tmp.resolve("src"), resolved["@"])
        assertEquals(tmp.resolve("ui"), resolved["@ui"])
        assertEquals(tmp.resolve("src/state"), resolved["@state"])
    }
}
