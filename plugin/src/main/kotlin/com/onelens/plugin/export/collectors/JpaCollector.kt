package com.onelens.plugin.export.collectors

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiAnnotation
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiClassType
import com.intellij.psi.PsiField
import com.intellij.psi.PsiLiteralExpression
import com.intellij.psi.PsiType
import com.intellij.psi.search.searches.AnnotatedElementsSearch
import com.intellij.psi.util.PsiTreeUtil
import com.onelens.plugin.export.JpaColumn
import com.onelens.plugin.export.JpaData
import com.onelens.plugin.export.JpaEntity
import com.onelens.plugin.export.JpaRepository
import com.onelens.plugin.export.JpaRepositoryQuery
import com.onelens.plugin.framework.workspace.Workspace

/**
 * PSI-native JPA collector. Produces [JpaData] with:
 *   - every `@Entity` / `@MappedSuperclass` class, its `@Table` name, and
 *     per-field `@Id` / `@Column` / `@JoinColumn` / relation annotations.
 *   - every `*Repository` interface that extends one of Spring Data's
 *     repository roots, with the entity type parameter and each
 *     derived-query method (`findByX`, `countByX`, `existsByX`, ...).
 *
 * No dependency on `com.intellij.jpa` or `com.intellij.spring.data` — all
 * information is in the annotation + inheritance surface that plain Java PSI
 * exposes, so this works on IC as well as IU.
 */
object JpaCollector {

    private val LOG = logger<JpaCollector>()

    private val ENTITY_ANNOS = listOf(
        "jakarta.persistence.Entity",
        "javax.persistence.Entity",
    )
    private val MAPPED_SUPER_ANNOS = listOf(
        "jakarta.persistence.MappedSuperclass",
        "javax.persistence.MappedSuperclass",
    )
    private val TABLE_ANNOS = listOf(
        "jakarta.persistence.Table",
        "javax.persistence.Table",
    )
    private val ID_ANNOS = listOf(
        "jakarta.persistence.Id",
        "javax.persistence.Id",
        "jakarta.persistence.EmbeddedId",
        "javax.persistence.EmbeddedId",
    )
    private val COLUMN_ANNOS = listOf(
        "jakarta.persistence.Column",
        "javax.persistence.Column",
    )
    private val JOIN_COLUMN_ANNOS = listOf(
        "jakarta.persistence.JoinColumn",
        "javax.persistence.JoinColumn",
    )

    private val RELATION_ANNOS = mapOf(
        "jakarta.persistence.OneToOne" to "OneToOne",
        "javax.persistence.OneToOne" to "OneToOne",
        "jakarta.persistence.OneToMany" to "OneToMany",
        "javax.persistence.OneToMany" to "OneToMany",
        "jakarta.persistence.ManyToOne" to "ManyToOne",
        "javax.persistence.ManyToOne" to "ManyToOne",
        "jakarta.persistence.ManyToMany" to "ManyToMany",
        "javax.persistence.ManyToMany" to "ManyToMany",
    )

    private val REPOSITORY_ROOTS = listOf(
        "org.springframework.data.repository.Repository",
        "org.springframework.data.repository.CrudRepository",
        "org.springframework.data.repository.PagingAndSortingRepository",
        "org.springframework.data.jpa.repository.JpaRepository",
        "org.springframework.data.repository.reactive.ReactiveCrudRepository",
        "org.springframework.data.mongodb.repository.MongoRepository",
    )

    private val QUERY_PREFIXES = listOf(
        "findBy", "findAllBy", "findFirstBy", "findTopBy",
        "getBy", "readBy", "queryBy", "searchBy", "streamBy",
        "countBy", "existsBy", "deleteBy", "removeBy",
    )

    fun collect(project: Project, workspace: Workspace): JpaData? {
        if (ReadAction.compute<Boolean, Throwable> { DumbService.isDumb(project) }) {
            LOG.info("JpaCollector skipped — dumb mode")
            return null
        }
        // Split entity + repository scans into separate NonBlockingReadActions
        // so EDT write-intent requests can interleave between the two passes.
        // Previously the outer ReadAction.compute held the read lock across
        // both walks plus all their column/FK dereferences — on 700+ entity
        // / 500+ repo projects this surfaced as the SuvorovProgress freeze
        // from LESSONS-LEARNED #1.
        val entities = try {
            com.intellij.openapi.application.ReadAction
                .nonBlocking<List<JpaEntity>> {
                    val facade = JavaPsiFacade.getInstance(project)
                    val scope = workspace.scope(project)
                    collectEntities(project, facade, scope, workspace)
                }
                .executeSynchronously()
        } catch (e: Throwable) {
            LOG.debug("JpaCollector[entities] failed: ${e.message}")
            emptyList()
        }
        val repositories = try {
            com.intellij.openapi.application.ReadAction
                .nonBlocking<List<com.onelens.plugin.export.JpaRepository>> {
                    val facade = JavaPsiFacade.getInstance(project)
                    val scope = workspace.scope(project)
                    collectRepositories(project, facade, scope, workspace)
                }
                .executeSynchronously()
        } catch (e: Throwable) {
            LOG.debug("JpaCollector[repositories] failed: ${e.message}")
            emptyList()
        }

        if (entities.isEmpty() && repositories.isEmpty()) {
            LOG.info("No JPA entities or repositories found")
            return null
        }
        LOG.info("JpaCollector: ${entities.size} entities, ${repositories.size} repositories")
        return JpaData(entities = entities, repositories = repositories)
    }

    private fun collectEntities(
        project: Project,
        facade: JavaPsiFacade,
        scope: com.intellij.psi.search.GlobalSearchScope,
        workspace: Workspace,
    ): List<JpaEntity> {
        val classes = HashSet<PsiClass>()
        for (annoFqn in ENTITY_ANNOS + MAPPED_SUPER_ANNOS) {
            val annoClass = facade.findClass(annoFqn, com.intellij.psi.search.GlobalSearchScope.allScope(project))
                ?: continue
            AnnotatedElementsSearch.searchPsiClasses(annoClass, scope).forEach { classes += it }
        }

        val out = ArrayList<JpaEntity>()
        for (psiClass in classes) {
            val classFqn = psiClass.qualifiedName ?: continue
            if (!isInWorkspace(psiClass, workspace)) continue

            val tableName = findTableName(psiClass) ?: psiClass.name ?: continue
            val schema = findTableAttr(psiClass, "schema") ?: ""

            val idFields = ArrayList<String>()
            val columns = ArrayList<JpaColumn>()

            // `fields` (own only) — NOT `allFields`. A concrete @Entity that extends
            // a @MappedSuperclass already gets its parent's fields in the DB via
            // JPA inheritance; re-emitting them per subclass inflates counts and
            // creates duplicate HAS_COLUMN edges pointing at the same column FQN.
            for (field in psiClass.fields) {
                val fieldFqn = "$classFqn#${field.name}"
                val annos = field.annotations
                val isId = annos.any { it.qualifiedName in ID_ANNOS }
                if (isId) idFields += fieldFqn

                val columnName = findColumnName(annos) ?: field.name
                val nullable = findBooleanAttr(annos, COLUMN_ANNOS, "nullable") ?: true
                val unique = findBooleanAttr(annos, COLUMN_ANNOS, "unique") ?: false

                val (relation, targetFqn) = detectRelation(field)

                // Skip fields that have no JPA metadata at all — they're transient.
                val hasJpaAnno = annos.any { a ->
                    a.qualifiedName.let { q ->
                        q in COLUMN_ANNOS || q in ID_ANNOS || q in JOIN_COLUMN_ANNOS ||
                            q in RELATION_ANNOS.keys
                    }
                }
                if (!hasJpaAnno && !isId) {
                    // Still emit if column naming is the implicit one AND field is
                    // in an @Entity — JPA treats every non-transient field as a
                    // column by default. We keep columnName = field.name.
                }

                columns += JpaColumn(
                    fieldFqn = fieldFqn,
                    columnName = columnName,
                    nullable = nullable,
                    unique = unique,
                    relation = relation,
                    targetEntityFqn = targetFqn,
                )
            }

            out += JpaEntity(
                classFqn = classFqn,
                tableName = tableName,
                schema = schema,
                idFieldFqns = idFields,
                columns = columns,
            )
        }
        return out
    }

    private fun collectRepositories(
        project: Project,
        facade: JavaPsiFacade,
        scope: com.intellij.psi.search.GlobalSearchScope,
        workspace: Workspace,
    ): List<JpaRepository> {
        val all = com.intellij.psi.search.GlobalSearchScope.allScope(project)
        val rootClasses = REPOSITORY_ROOTS.mapNotNull { facade.findClass(it, all) }
        if (rootClasses.isEmpty()) return emptyList()

        val candidates = HashSet<PsiClass>()
        for (root in rootClasses) {
            com.intellij.psi.search.searches.ClassInheritorsSearch
                .search(root, scope, /*checkDeep=*/true, /*checkInheritance=*/true, /*includeAnonymous=*/false)
                .forEach { if (it.isInterface) candidates += it }
        }

        val out = ArrayList<JpaRepository>()
        for (repo in candidates) {
            val classFqn = repo.qualifiedName ?: continue
            if (!isInWorkspace(repo, workspace)) continue
            // @NoRepositoryBean marks abstract intermediate interfaces like
            // a large project's GenericEntityRepository — real user-facing repos don't
            // carry it. Without this guard we'd emit the generic base + one
            // dummy "T" entity.
            if (repo.annotations.any {
                    it.qualifiedName == "org.springframework.data.repository.NoRepositoryBean"
                }) continue

            val entityFqn = resolveEntityParameter(repo) ?: continue
            val queries = repo.methods.filter { m ->
                QUERY_PREFIXES.any { prefix -> m.name.startsWith(prefix) }
            }.map { m ->
                JpaRepositoryQuery(
                    methodFqn = "$classFqn#${m.name}(${m.parameterList.parameters.joinToString(",") { it.type.canonicalText }})",
                    methodName = m.name,
                    kind = "derived",
                )
            }
            out += JpaRepository(
                classFqn = classFqn,
                entityFqn = entityFqn,
                derivedQueries = queries,
            )
        }
        return out
    }

    /**
     * Resolve the entity type parameter by walking the super-chain with full type
     * substitution. projects often use a common pattern:
     *   `UserRepository extends GenericEntityRepository<User, Long>`
     *   `GenericEntityRepository<T,ID> extends JpaRepository<T,ID>`
     * Walking only direct supers misses `UserRepository` entirely because its
     * direct super (`GenericEntityRepository`) isn't in REPOSITORY_ROOTS. We need
     * to follow the chain, substituting type args at each step, until we hit
     * a root and read the first (now-resolved) type argument.
     */
    private fun resolveEntityParameter(repo: PsiClass): String? {
        val facade = JavaPsiFacade.getInstance(repo.project)
        val rootClasses = REPOSITORY_ROOTS.mapNotNull {
            facade.findClass(it, com.intellij.psi.search.GlobalSearchScope.allScope(repo.project))
        }
        if (rootClasses.isEmpty()) return null

        for (rootClass in rootClasses) {
            val substitutor = com.intellij.psi.util.TypeConversionUtil
                .getClassSubstitutor(rootClass, repo, com.intellij.psi.PsiSubstitutor.EMPTY)
                ?: continue
            val firstTypeParam = rootClass.typeParameters.firstOrNull() ?: continue
            val resolvedType = substitutor.substitute(firstTypeParam) ?: continue
            val fqn = (resolvedType as? PsiClassType)?.resolve()?.qualifiedName
            if (!fqn.isNullOrBlank() && fqn != "java.lang.Object") return fqn
        }
        return null
    }

    private fun findTableName(psiClass: PsiClass): String? {
        for (anno in psiClass.annotations) {
            if (anno.qualifiedName in TABLE_ANNOS) {
                val name = findLiteralAttr(anno, "name")
                if (!name.isNullOrBlank()) return name
            }
        }
        for (anno in psiClass.annotations) {
            if (anno.qualifiedName in ENTITY_ANNOS) {
                val name = findLiteralAttr(anno, "name")
                if (!name.isNullOrBlank()) return name
            }
        }
        return psiClass.name
    }

    private fun findTableAttr(psiClass: PsiClass, attr: String): String? {
        for (anno in psiClass.annotations) {
            if (anno.qualifiedName in TABLE_ANNOS) {
                return findLiteralAttr(anno, attr)
            }
        }
        return null
    }

    private fun findColumnName(annos: Array<PsiAnnotation>): String? {
        for (anno in annos) {
            if (anno.qualifiedName in COLUMN_ANNOS || anno.qualifiedName in JOIN_COLUMN_ANNOS) {
                val name = findLiteralAttr(anno, "name")
                if (!name.isNullOrBlank()) return name
            }
        }
        return null
    }

    private fun findBooleanAttr(
        annos: Array<PsiAnnotation>,
        targetAnnoFqns: List<String>,
        attr: String
    ): Boolean? {
        for (anno in annos) {
            if (anno.qualifiedName in targetAnnoFqns) {
                val v = anno.findAttributeValue(attr)
                val text = (v as? PsiLiteralExpression)?.value?.toString() ?: v?.text ?: continue
                return when (text.lowercase()) {
                    "true" -> true
                    "false" -> false
                    else -> null
                }
            }
        }
        return null
    }

    private fun findLiteralAttr(anno: PsiAnnotation, attr: String): String? {
        val v = anno.findAttributeValue(attr) ?: return null
        val lit = (v as? PsiLiteralExpression)?.value?.toString()
        if (lit != null) return lit
        return v.text?.removeSurrounding("\"")
    }

    private fun detectRelation(field: PsiField): Pair<String?, String?> {
        for (anno in field.annotations) {
            val rel = RELATION_ANNOS[anno.qualifiedName] ?: continue
            val target = resolveRelationTarget(field, anno) ?: return rel to null
            return rel to target
        }
        return null to null
    }

    private fun resolveRelationTarget(field: PsiField, anno: PsiAnnotation): String? {
        // targetEntity = Foo.class takes priority if present
        val explicit = anno.findAttributeValue("targetEntity")
        if (explicit != null) {
            val text = explicit.text.removeSuffix(".class").trim()
            if (text.isNotBlank() && text != "void") return text
        }
        // Infer from field type: Collection<E> → E, else E.
        val type = field.type
        if (type is PsiClassType) {
            val resolved = type.resolve() ?: return null
            val fqn = resolved.qualifiedName ?: return null
            val isCollection = fqn in listOf(
                "java.util.List", "java.util.Set", "java.util.Collection",
                "java.util.SortedSet", "java.util.NavigableSet",
            ) || fqn.startsWith("java.util.")
            return if (isCollection) {
                (type.parameters.firstOrNull() as? PsiClassType)?.resolve()?.qualifiedName
            } else fqn
        }
        return null
    }

    private fun isInWorkspace(psiClass: PsiClass, workspace: Workspace): Boolean {
        val file = psiClass.containingFile?.virtualFile ?: return false
        return workspace.contains(file.path)
    }
}
