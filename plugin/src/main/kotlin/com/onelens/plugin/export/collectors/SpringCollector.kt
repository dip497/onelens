package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.module.ModuleManager
import com.intellij.openapi.project.Project
import com.intellij.psi.*
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.searches.AnnotatedElementsSearch
import com.onelens.plugin.export.*

/**
 * Collects Spring-specific data: beans, wiring, endpoints.
 *
 * Two modes:
 * 1. If Spring plugin (com.intellij.spring) is available: uses SpringManager APIs
 *    for full bean model, dependency injection, request mappings
 * 2. Fallback: annotation-based detection (@Service, @Component, @Controller,
 *    @Repository, @RestController, @RequestMapping, @Autowired)
 *
 * The fallback covers most cases since Spring Boot apps primarily use annotations.
 */
object SpringCollector {

    private val LOG = logger<SpringCollector>()

    // Spring stereotype annotations
    private val BEAN_ANNOTATIONS = mapOf(
        "org.springframework.stereotype.Service" to "SERVICE",
        "org.springframework.stereotype.Component" to "COMPONENT",
        "org.springframework.stereotype.Repository" to "REPOSITORY",
        "org.springframework.stereotype.Controller" to "CONTROLLER",
        "org.springframework.web.bind.annotation.RestController" to "REST_CONTROLLER",
        "org.springframework.context.annotation.Configuration" to "CONFIGURATION",
    )

    private val MAPPING_ANNOTATIONS = listOf(
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.GetMapping",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.PutMapping",
        "org.springframework.web.bind.annotation.DeleteMapping",
        "org.springframework.web.bind.annotation.PatchMapping",
    )

    private val HTTP_METHOD_MAP = mapOf(
        "GetMapping" to "GET",
        "PostMapping" to "POST",
        "PutMapping" to "PUT",
        "DeleteMapping" to "DELETE",
        "PatchMapping" to "PATCH",
        "RequestMapping" to "ALL",
    )

    fun collect(project: Project): SpringData? {
        return ReadAction.compute<SpringData?, Throwable> {
            val facade = JavaPsiFacade.getInstance(project)
            val scope = GlobalSearchScope.projectScope(project)

            val beans = mutableListOf<SpringBean>()
            val endpoints = mutableListOf<SpringEndpoint>()
            val injections = mutableListOf<SpringInjection>()

            // Discover beans via stereotype annotations
            for ((annotationFqn, beanType) in BEAN_ANNOTATIONS) {
                val annotationClass = facade.findClass(annotationFqn, GlobalSearchScope.allScope(project))
                    ?: continue

                AnnotatedElementsSearch.searchPsiClasses(annotationClass, scope).forEach { psiClass ->
                    val classFqn = psiClass.qualifiedName ?: return@forEach
                    val beanName = classFqn.substringAfterLast('.').replaceFirstChar { it.lowercase() }

                    beans.add(SpringBean(
                        name = beanName,
                        classFqn = classFqn,
                        type = beanType
                    ))

                    // Find @Autowired fields → injections
                    collectInjections(psiClass, classFqn, injections)

                    // Find endpoints on controllers
                    if (beanType in listOf("CONTROLLER", "REST_CONTROLLER")) {
                        collectEndpoints(psiClass, classFqn, endpoints)
                    }
                }
            }

            if (beans.isEmpty()) {
                LOG.info("No Spring beans found")
                return@compute null
            }

            LOG.info("Collected ${beans.size} beans, ${endpoints.size} endpoints, ${injections.size} injections")
            SpringData(beans = beans, endpoints = endpoints, injections = injections)
        }
    }

    private fun collectInjections(
        psiClass: PsiClass,
        classFqn: String,
        injections: MutableList<SpringInjection>
    ) {
        // Field injection: @Autowired fields
        for (field in psiClass.fields) {
            val hasAutowired = field.annotations.any {
                it.qualifiedName == "org.springframework.beans.factory.annotation.Autowired"
            }
            if (hasAutowired || isInjectedByDefault(field, psiClass)) {
                injections.add(SpringInjection(
                    targetClassFqn = classFqn,
                    targetFieldOrParam = field.name,
                    injectedClassFqn = field.type.canonicalText,
                    injectionType = "FIELD"
                ))
            }
        }

        // Constructor injection: constructor params (Spring auto-wires if single constructor)
        val constructors = psiClass.constructors
        if (constructors.size == 1) {
            val constructor = constructors[0]
            for (param in constructor.parameterList.parameters) {
                injections.add(SpringInjection(
                    targetClassFqn = classFqn,
                    targetFieldOrParam = param.name ?: "",
                    injectedClassFqn = param.type.canonicalText,
                    injectionType = "CONSTRUCTOR"
                ))
            }
        }
    }

    private fun isInjectedByDefault(field: PsiField, psiClass: PsiClass): Boolean {
        // In Spring, if there's no @Autowired but the field type matches a known bean
        // and the class is a Spring component, it might be injected via constructor.
        // We only detect explicit @Autowired and constructor injection here.
        return false
    }

    private fun collectEndpoints(
        psiClass: PsiClass,
        classFqn: String,
        endpoints: MutableList<SpringEndpoint>
    ) {
        // Class-level @RequestMapping prefix
        val classPrefix = extractMappingPath(psiClass.modifierList)

        for (method in psiClass.methods) {
            for (annotation in method.annotations) {
                val annotationName = annotation.qualifiedName ?: continue
                if (annotationName !in MAPPING_ANNOTATIONS.map { it }) continue

                val shortName = annotationName.substringAfterLast('.')
                val httpMethod = HTTP_METHOD_MAP[shortName] ?: "ALL"
                val methodPath = extractPathFromAnnotation(annotation)
                val fullPath = combinePaths(classPrefix, methodPath)

                val paramSignature = method.parameterList.parameters.joinToString(",") {
                    try { it.type.canonicalText } catch (_: Exception) { "?" }
                }
                val handlerFqn = "$classFqn#${method.name}($paramSignature)"

                endpoints.add(SpringEndpoint(
                    path = fullPath,
                    httpMethod = httpMethod,
                    controllerFqn = classFqn,
                    handlerMethodFqn = handlerFqn
                ))
            }
        }
    }

    private fun extractMappingPath(modifierList: PsiModifierList?): String {
        if (modifierList == null) return ""
        for (annotation in modifierList.annotations) {
            if (annotation.qualifiedName == "org.springframework.web.bind.annotation.RequestMapping") {
                return extractPathFromAnnotation(annotation)
            }
        }
        return ""
    }

    private fun extractPathFromAnnotation(annotation: PsiAnnotation): String {
        // Try "value" first, then "path"
        val value = annotation.findAttributeValue("value")
            ?: annotation.findAttributeValue("path")
            ?: annotation.findAttributeValue(null)  // default attribute

        return when (value) {
            is PsiLiteralExpression -> value.value?.toString() ?: ""
            is PsiArrayInitializerMemberValue -> {
                value.initializers.firstOrNull()?.let {
                    (it as? PsiLiteralExpression)?.value?.toString()
                } ?: ""
            }
            else -> value?.text?.removeSurrounding("\"") ?: ""
        }
    }

    private fun combinePaths(prefix: String, path: String): String {
        val p = prefix.trimEnd('/')
        val s = path.trimStart('/')
        return when {
            p.isEmpty() && s.isEmpty() -> "/"
            p.isEmpty() -> "/$s"
            s.isEmpty() -> p
            else -> "$p/$s"
        }
    }
}
