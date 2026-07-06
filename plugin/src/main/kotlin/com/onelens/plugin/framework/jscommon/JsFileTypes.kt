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

    fun isVendorPath(path: String): Boolean = VENDOR_DIR.containsMatchIn(path)
}
