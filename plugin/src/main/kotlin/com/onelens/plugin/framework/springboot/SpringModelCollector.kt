package com.onelens.plugin.framework.springboot

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.module.ModuleManager
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiMethod
import com.intellij.spring.SpringManager
import com.intellij.spring.model.SpringBeanPointer
import com.intellij.spring.model.jam.JamSpringBeanPointer
import com.intellij.spring.model.xml.DomSpringBeanPointer
import com.onelens.plugin.export.SpringBean
import com.onelens.plugin.framework.workspace.Workspace

/**
 * Collects Spring beans via the IntelliJ Spring plugin's resolved model — strictly
 * richer than annotation scraping: captures @Bean factory methods, XML beans, JAM
 * beans, aliases, active profiles, @Primary, and scope as resolved by the IDE.
 *
 * LOADED LAZILY. Callers MUST guard invocation with a runtime check for the
 * `com.intellij.spring` plugin; this class statically imports SpringManager and
 * will NoClassDefFoundError on IDEs without Spring present. The guard in
 * [SpringBootCollector] ensures this class is never loaded on those IDEs.
 */
object SpringModelCollector {

    private val LOG = logger<SpringModelCollector>()

    fun collect(project: Project, workspace: Workspace): List<SpringBean> {
        if (ReadAction.compute<Boolean, Throwable> { DumbService.isDumb(project) }) {
            LOG.info("SpringModelCollector skipped — dumb mode")
            return emptyList()
        }
        val modules = ReadAction.compute<Array<com.intellij.openapi.module.Module>, Throwable> {
            ModuleManager.getInstance(project).modules
        }
        val out = ArrayList<SpringBean>()
        val seen = HashSet<String>()  // dedupe by classFqn|name

        // One ReadAction PER module instead of one around the whole scan.
        // The previous wrap-everything pattern held the read lock for the
        // full duration on 10k-bean projects, which blocked EDT write-intent
        // requests and surfaced as a SuvorovProgress freeze overlay. Giving
        // the lock up between modules lets editor events + JAM index updates
        // interleave. Each module's beans are processed inside a
        // NonBlockingReadAction so we yield if a write comes in mid-module,
        // then resume — matches the Vue3 collector pattern already in the
        // repo and LESSONS-LEARNED #1.
        for (module in modules) {
            ProgressManager.checkCanceled()
            val moduleBeans = try {
                com.intellij.openapi.application.ReadAction
                    .nonBlocking<List<SpringBean>> {
                        val manager = SpringManager.getInstance(project)
                        val model = try { manager.getCombinedModel(module) } catch (_: Throwable) { null } ?: return@nonBlocking emptyList()
                        val beans = try { model.getAllCommonBeans() } catch (_: Throwable) { return@nonBlocking emptyList() }
                        val profiles = runCatching { model.activeProfiles?.toList() ?: emptyList() }
                            .getOrDefault(emptyList())
                        val local = ArrayList<SpringBean>(beans.size)
                        for (pointer in beans) {
                            ProgressManager.checkCanceled()
                            val bean = toSpringBean(pointer, profiles, workspace) ?: continue
                            local += bean
                        }
                        local
                    }
                    .executeSynchronously()
            } catch (e: Throwable) {
                LOG.debug("SpringModelCollector failed for ${module.name}: ${e.message}")
                emptyList()
            }
            for (bean in moduleBeans) {
                val dedupKey = "${bean.classFqn}|${bean.name}|${bean.factoryMethodFqn ?: ""}"
                if (seen.add(dedupKey)) out += bean
            }
        }
        LOG.info("SpringModelCollector: ${out.size} beans across ${modules.size} modules")
        return out
    }

    private fun toSpringBean(
        pointer: SpringBeanPointer<*>,
        activeProfiles: List<String>,
        workspace: Workspace,
    ): SpringBean? {
        if (!pointer.isValid) return null
        val psiClass: PsiClass = try { pointer.beanClass } catch (_: Throwable) { return null } ?: return null
        val classFqn = psiClass.qualifiedName ?: return null

        // Filter to workspace — library beans (JDK, starters) pollute the graph.
        val containingFile = psiClass.containingFile?.virtualFile
        if (containingFile != null && !workspace.contains(containingFile.path)) return null

        val name = pointer.name ?: psiClass.name ?: return null

        val beanType = detectType(psiClass)

        // @Bean factory methods — extract the owning method FQN for provenance.
        // We read directly from the Jam-bean's PSI identity rather than reflecting
        // over SpringManager's internal class, which varies across IU releases.
        val factoryMethod = psiIdent(pointer)
        val (source, factoryMethodFqn) = when {
            factoryMethod != null -> "java-config" to factoryFqn(factoryMethod)
            pointer is DomSpringBeanPointer -> "xml" to null
            pointer is JamSpringBeanPointer -> "annotation" to null
            else -> "jam" to null
        }

        // Scope / primary resolved from PSI annotations — reliable across every
        // Spring bean variant (annotation, @Bean, XML via resolved class). The
        // Spring plugin does expose these on its subtype hierarchy, but the
        // concrete types vary across IDEA releases; reading PSI sidesteps that.
        val scope = resolveScope(psiClass, factoryMethod)
        val primary = hasAnnotation(
            psiClass, factoryMethod,
            "org.springframework.context.annotation.Primary"
        )

        return SpringBean(
            name = name,
            classFqn = classFqn,
            scope = scope,
            profile = null,
            dependencies = emptyList(),
            type = beanType,
            primary = primary,
            source = source,
            factoryMethodFqn = factoryMethodFqn,
            activeProfiles = activeProfiles,
        )
    }

    private fun psiIdent(pointer: SpringBeanPointer<*>): PsiMethod? =
        runCatching { pointer.springBean?.identifyingPsiElement as? PsiMethod }.getOrNull()

    private fun resolveScope(psiClass: PsiClass, factoryMethod: PsiMethod?): String {
        val holder = factoryMethod ?: psiClass
        val annos = when (holder) {
            is PsiMethod -> holder.annotations
            is PsiClass -> holder.annotations
            else -> emptyArray()
        }
        for (anno in annos) {
            if (anno.qualifiedName == "org.springframework.context.annotation.Scope") {
                val v = anno.findAttributeValue("value") ?: anno.findAttributeValue(null)
                val raw = (v as? com.intellij.psi.PsiLiteralExpression)?.value?.toString()
                    ?: v?.text?.removeSurrounding("\"")
                if (!raw.isNullOrBlank()) return raw.substringAfterLast('.').lowercase()
            }
        }
        return "singleton"
    }

    private fun hasAnnotation(psiClass: PsiClass, factoryMethod: PsiMethod?, fqn: String): Boolean {
        val holder = factoryMethod ?: psiClass
        val annos = when (holder) {
            is PsiMethod -> holder.annotations
            is PsiClass -> holder.annotations
            else -> emptyArray()
        }
        return annos.any { it.qualifiedName == fqn }
    }

    private fun factoryFqn(method: PsiMethod): String {
        val owner = method.containingClass?.qualifiedName ?: "<unknown>"
        val params = method.parameterList.parameters.joinToString(",") { it.type.canonicalText }
        return "$owner#${method.name}($params)"
    }

    private fun detectType(psiClass: PsiClass): String {
        val annos = psiClass.annotations.mapNotNull { it.qualifiedName }.toSet()
        return when {
            "org.springframework.web.bind.annotation.RestController" in annos -> "REST_CONTROLLER"
            "org.springframework.stereotype.Controller" in annos -> "CONTROLLER"
            "org.springframework.stereotype.Service" in annos -> "SERVICE"
            "org.springframework.stereotype.Repository" in annos -> "REPOSITORY"
            "org.springframework.context.annotation.Configuration" in annos -> "CONFIGURATION"
            "org.springframework.stereotype.Component" in annos -> "COMPONENT"
            else -> "BEAN"
        }
    }
}
