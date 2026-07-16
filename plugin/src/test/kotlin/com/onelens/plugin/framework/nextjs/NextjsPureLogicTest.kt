package com.onelens.plugin.framework.nextjs

import com.onelens.plugin.export.delta.DeltaTracker
import com.onelens.plugin.framework.jscommon.JsFileTypes
import com.onelens.plugin.framework.nextjs.collectors.NextPsiUtil
import junit.framework.TestCase

/**
 * Pure-logic tests for the Next.js adapter — no IntelliJ platform fixture, so they run in
 * milliseconds and are safe in CI (the `BasePlatformTestCase` suites boot a full IDE and
 * are slow/flaky).
 *
 * Every case here pins a bug that actually shipped and was caught only by a manual
 * end-to-end export against a real repo. Keep them cheap and keep them failing loudly.
 */
class NextjsPureLogicTest : TestCase() {

    // ── JsFileTypes.isVendorPath ────────────────────────────────────────────────
    // Shipped bug: the check was fed the ABSOLUTE VirtualFile path, so a repo checked
    // out under `~/out/` or `/builds/dist/` matched on an ancestor segment and the whole
    // JS/TS subgraph came out EMPTY with no error. isVendorPath now takes a
    // project-relative path; these cases pin both directions.

    fun testVendorPathMatchesVendoredDirs() {
        assertTrue(JsFileTypes.isVendorPath("node_modules/react/index.js"))
        assertTrue(JsFileTypes.isVendorPath("apps/web/node_modules/x/y.ts"))
        assertTrue(JsFileTypes.isVendorPath(".next/static/chunk.js"))
        assertTrue(JsFileTypes.isVendorPath("packages/ui/dist/index.js"))
        assertTrue(JsFileTypes.isVendorPath("coverage/lcov-report/x.js"))
    }

    fun testVendorPathDoesNotMatchRealSource() {
        assertFalse(JsFileTypes.isVendorPath("apps/web/app/page.tsx"))
        assertFalse(JsFileTypes.isVendorPath("packages/ui/src/button.tsx"))
        // Substring lookalikes must not trip the segment-anchored regex.
        assertFalse(JsFileTypes.isVendorPath("src/routes/dist-picker.tsx"))
        assertFalse(JsFileTypes.isVendorPath("src/outbox/mailer.ts"))
        assertFalse(JsFileTypes.isVendorPath("src/distributor/index.ts"))
    }

    /** The regression itself: an ancestor dir named `out`/`dist` must not nuke the graph. */
    fun testVendorPathIsRelativeNotAbsolute() {
        // What an absolute path used to look like on a machine whose checkout lives
        // under a directory called `out`. Relative form is what callers now pass.
        assertFalse(JsFileTypes.isVendorPath("app/page.tsx"))
        // And the absolute form is exactly why we must not pass it:
        assertTrue(JsFileTypes.isVendorPath("/home/me/out/myapp/app/page.tsx"))
    }

    // ── NextPsiUtil.computeUrl ──────────────────────────────────────────────────
    // App-Router segment → URL. Drives Route.urlPath and RouteHandler endpoint fqns.

    fun testComputeUrlRootIsSlash() {
        assertEquals("/", NextPsiUtil.computeUrl(emptyList()).urlPath)
    }

    fun testComputeUrlStripsRouteGroups() {
        val r = NextPsiUtil.computeUrl(listOf("(app)", "admin", "persons"))
        assertEquals("/admin/persons", r.urlPath)
        assertEquals("(app)", r.group)
    }

    fun testComputeUrlDynamicSegment() {
        val r = NextPsiUtil.computeUrl(listOf("(app)", "admin", "persons", "[id]"))
        assertEquals("/admin/persons/:id", r.urlPath)
        assertEquals(listOf("id"), r.paramNames)
    }

    fun testComputeUrlCatchAllAndOptionalCatchAll() {
        assertEquals("/api/*ids", NextPsiUtil.computeUrl(listOf("api", "[...ids]")).urlPath)
        assertEquals("/api/*ids", NextPsiUtil.computeUrl(listOf("api", "[[...ids]]")).urlPath)
        assertEquals(listOf("ids"), NextPsiUtil.computeUrl(listOf("api", "[...ids]")).paramNames)
    }

    fun testComputeUrlDropsParallelSlots() {
        assertEquals("/photo", NextPsiUtil.computeUrl(listOf("@modal", "photo")).urlPath)
    }

    fun testComputeUrlNestedDynamicUnderGroup() {
        val r = NextPsiUtil.computeUrl(listOf("(app)", "admin", "forms", "[formId]", "build"))
        assertEquals("/admin/forms/:formId/build", r.urlPath)
        assertEquals(listOf("formId"), r.paramNames)
    }

    // ── NextPsiUtil.JSX_MARKER ──────────────────────────────────────────────────
    // Shipped bug: the textual JSX probe was `</|/>|<[A-Z]`, and `<[A-Z]` matches
    // TypeScript generics — so PascalCase non-components became phantom ReactComponents
    // and bogus RENDERS edges were fabricated from type arguments.

    fun testJsxMarkerAcceptsRealJsx() {
        assertTrue(NextPsiUtil.JSX_MARKER.containsMatchIn("return <div/>"))
        assertTrue(NextPsiUtil.JSX_MARKER.containsMatchIn("return <Foo />"))
        assertTrue(NextPsiUtil.JSX_MARKER.containsMatchIn("return <Foo>bar</Foo>"))
    }

    fun testJsxMarkerRejectsTypeScriptGenerics() {
        assertFalse(NextPsiUtil.JSX_MARKER.containsMatchIn("new Map<String, Foo>()"))
        assertFalse(NextPsiUtil.JSX_MARKER.containsMatchIn("useState<User>()"))
        assertFalse(NextPsiUtil.JSX_MARKER.containsMatchIn("const x: Array<Foo> = []"))
        assertFalse(NextPsiUtil.JSX_MARKER.containsMatchIn("useQuery<TodoList>()"))
    }

    // ── DeltaTracker.isTracked ──────────────────────────────────────────────────
    // Shipped behaviour: delta detection was `.java`-only, so a .tsx edit reported
    // NoChanges and left the graph stale.

    fun testIsTrackedCoversFrontendAndJvmSources() {
        assertTrue(DeltaTracker.isTracked("src/App.tsx"))
        assertTrue(DeltaTracker.isTracked("src/main.ts"))
        assertTrue(DeltaTracker.isTracked("a/b/Foo.java"))
        assertTrue(DeltaTracker.isTracked("a/b/Foo.kt"))
        assertTrue(DeltaTracker.isTracked("src/App.vue"))
    }

    fun testIsTrackedRejectsNonSource() {
        assertFalse(DeltaTracker.isTracked("README.md"))
        assertFalse(DeltaTracker.isTracked("pom.xml"))
        assertFalse(DeltaTracker.isTracked("assets/logo.png"))
        assertFalse(DeltaTracker.isTracked("noextension"))
    }
}
