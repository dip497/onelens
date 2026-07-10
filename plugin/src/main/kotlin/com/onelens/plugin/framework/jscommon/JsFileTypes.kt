package com.onelens.plugin.framework.jscommon

import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.fileTypes.UnknownFileType

object JsFileTypes {
    /** js, ts, mjs, jsx, tsx, vue — filtered to registered types. */
    fun script(): List<FileType> {
        val ftm = FileTypeManager.getInstance()
        return listOf("js", "ts", "mjs", "jsx", "tsx", "vue")
            .map { ftm.getFileTypeByExtension(it) }
            .filter { it != UnknownFileType.INSTANCE }
            .distinct()
    }

    /**
     * Vendored / generated directories that must never enter the graph: third-party
     * deps and build output. IntelliJ's own excludes handle this when a project is
     * opened through its build system, but a directory-opened / headless project (or a
     * pnpm monorepo whose `.pnpm` store isn't marked excluded) leaks them into
     * FileTypeIndex — a real export of a Next.js monorepo was 96% `node_modules`.
     * Applied uniformly to every JS/TS file enumeration in the shared collectors.
     */
    private val VENDOR_DIR = Regex("""(^|/)(node_modules|\.next|\.nuxt|\.turbo|\.svelte-kit|dist|out|coverage|\.output)/""")

    /**
     * True when [path] lies inside a vendored / generated directory.
     *
     * MUST be given a PROJECT-RELATIVE path. Passing an absolute path matches ancestor
     * directories outside the project — a repo checked out at `~/out/app` or a CI
     * workspace under `/builds/dist/` would match on every file and silently emit an
     * EMPTY JS/TS subgraph with no error. Use [isVendorFile] when you hold a
     * VirtualFile + the sink.
     */
    fun isVendorPath(relativePath: String): Boolean = VENDOR_DIR.containsMatchIn(relativePath)

    /** Relativizes against the sink's project base before the vendor check. */
    fun isVendorFile(file: com.intellij.openapi.vfs.VirtualFile, sink: JsCommonSink): Boolean =
        isVendorPath(sink.relativize(java.nio.file.Paths.get(file.path)))
}
