package com.onelens.plugin.framework.jscommon

import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.ApiCallData
import com.onelens.plugin.export.CallsApiEdge
import com.onelens.plugin.export.ImportsEdge
import com.onelens.plugin.export.JsFunctionData
import com.onelens.plugin.export.JsModuleData
import com.onelens.plugin.framework.workspace.Workspace
import java.nio.file.Path

/**
 * Shared accumulator contract for the framework-agnostic JS/TS collectors
 * (JsModuleCollector, ApiCallCollector, ModuleNameBinder). Both Vue3Context and
 * NextjsContext implement it so the collectors work for either frontend.
 */
interface JsCommonSink {
    val projectBase: Path
    val aliases: Map<String, Path>
    val symlinks: List<SymlinkResolver.SymlinkEntry>
    val workspace: Workspace
    val modules: MutableList<JsModuleData>
    val functions: MutableList<JsFunctionData>
    val imports: MutableList<ImportsEdge>
    val apiCalls: MutableList<ApiCallData>
    val callsApi: MutableList<CallsApiEdge>

    fun relativize(abs: Path): String

    /** PSI roots to traverse for a file. Default = the file itself (plain .ts/.tsx/.jsx).
     *  Vue overrides this to descend into SFC <script setup> embedded blocks. */
    fun scriptRoots(file: PsiFile): List<PsiElement> = listOf(file)
}

inline fun <reified T : PsiElement> JsCommonSink.findAll(file: PsiFile): List<T> =
    scriptRoots(file).flatMap { PsiTreeUtil.findChildrenOfType(it, T::class.java) }
