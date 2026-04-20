package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.module.ModuleUtilCore
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiAnnotation
import com.intellij.psi.PsiArrayInitializerMemberValue
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiClassObjectAccessExpression
import com.intellij.psi.PsiLiteralExpression
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.searches.AnnotatedElementsSearch
import com.onelens.plugin.export.AppData
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Finds `@SpringBootApplication` root classes in the workspace and resolves each
 * to an [AppData] with its scan-base packages. Resolution order, matching
 * Spring's own `SpringBootApplication`/`ComponentScan` contract:
 *
 *   1. `scanBasePackages` attribute value (String[]) — explicit packages.
 *   2. `scanBasePackageClasses` attribute value (Class[]) — each class's package.
 *   3. Default: the package containing the root class.
 *
 * Also merges `@ComponentScan` on the same class (attrs aliased). `@Import`
 * chains are not followed — explicit scan-declared packages win.
 */
object AppCollector {

    private val LOG = logger<AppCollector>()

    private const val SPRING_BOOT_APPLICATION =
        "org.springframework.boot.autoconfigure.SpringBootApplication"
    private const val COMPONENT_SCAN =
        "org.springframework.context.annotation.ComponentScan"

    fun collect(project: Project, workspace: Workspace): List<AppData> {
        return ReadAction.compute<List<AppData>, Throwable> {
            if (DumbService.isDumb(project)) {
                LOG.info("AppCollector skipped — dumb mode")
                return@compute emptyList()
            }
            val scope = workspace.scope(project)
            val facade = JavaPsiFacade.getInstance(project)
            val annoClass = facade.findClass(SPRING_BOOT_APPLICATION, GlobalSearchScope.allScope(project))
                ?: run {
                    LOG.info("@SpringBootApplication not on classpath — no apps emitted")
                    return@compute emptyList()
                }

            val roots = AnnotatedElementsSearch.searchPsiClasses(annoClass, scope).findAll()
                .filter { it.qualifiedName != null }
            if (roots.isEmpty()) return@compute emptyList()

            val out = ArrayList<AppData>(roots.size)
            for (root in roots) {
                val rootFqn = root.qualifiedName ?: continue
                val file = root.containingFile?.virtualFile ?: continue
                if (!workspace.contains(file.path)) continue

                val sbAnno = root.annotations.firstOrNull { it.qualifiedName == SPRING_BOOT_APPLICATION }
                val csAnno = root.annotations.firstOrNull { it.qualifiedName == COMPONENT_SCAN }

                val scanFromPackages = resolveStringArray(sbAnno, "scanBasePackages") +
                    resolveStringArray(csAnno, "basePackages") +
                    resolveStringArray(csAnno, "value")

                val scanFromClasses = resolveClassArrayPackages(sbAnno, "scanBasePackageClasses") +
                    resolveClassArrayPackages(csAnno, "basePackageClasses")

                val allScans = (scanFromPackages + scanFromClasses).distinct().filter { it.isNotBlank() }

                val defaultPackage = rootFqn.substringBeforeLast('.', "")
                val scanPackages = allScans.ifEmpty {
                    if (defaultPackage.isNotBlank()) listOf(defaultPackage) else emptyList()
                }

                val module = ModuleUtilCore.findModuleForPsiElement(root)
                val moduleNames = listOfNotNull(module?.name)

                out += AppData(
                    id = "app:spring-boot:$rootFqn",
                    name = root.name ?: rootFqn.substringAfterLast('.'),
                    type = "spring-boot",
                    rootFqn = rootFqn,
                    scanPackages = scanPackages,
                    moduleNames = moduleNames,
                )
            }
            LOG.info("AppCollector: ${out.size} Spring Boot apps")
            out
        }
    }

    private fun resolveStringArray(anno: PsiAnnotation?, attr: String): List<String> {
        val value = anno?.findAttributeValue(attr) ?: return emptyList()
        return when (value) {
            is PsiLiteralExpression -> listOfNotNull(value.value?.toString()).filter { it.isNotBlank() }
            is PsiArrayInitializerMemberValue -> value.initializers.mapNotNull {
                when (it) {
                    is PsiLiteralExpression -> it.value?.toString()
                    else -> it.text.removeSurrounding("\"").takeIf { s -> s.isNotBlank() }
                }
            }
            else -> listOfNotNull(value.text.removeSurrounding("\"").takeIf { it.isNotBlank() })
        }
    }

    private fun resolveClassArrayPackages(anno: PsiAnnotation?, attr: String): List<String> {
        val value = anno?.findAttributeValue(attr) ?: return emptyList()
        val refs = when (value) {
            is PsiClassObjectAccessExpression -> listOf(value)
            is PsiArrayInitializerMemberValue -> value.initializers.filterIsInstance<PsiClassObjectAccessExpression>()
            else -> emptyList()
        }
        return refs.mapNotNull { expr ->
            val typeClass = (expr.operand.type as? com.intellij.psi.PsiClassType)?.resolve()
            typeClass?.qualifiedName?.substringBeforeLast('.', "")?.takeIf { it.isNotBlank() }
        }
    }
}
