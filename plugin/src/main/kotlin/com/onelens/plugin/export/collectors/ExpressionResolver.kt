package com.onelens.plugin.export.collectors

import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiAnnotation
import com.intellij.psi.PsiAnnotationMemberValue
import com.intellij.psi.PsiArrayInitializerExpression
import com.intellij.psi.PsiArrayInitializerMemberValue
import com.intellij.psi.PsiClassObjectAccessExpression
import com.intellij.psi.PsiClassType
import com.intellij.psi.PsiEnumConstant
import com.intellij.psi.PsiExpression
import com.intellij.psi.PsiField
import com.intellij.psi.PsiMethodCallExpression
import com.intellij.psi.PsiModifier
import com.intellij.psi.PsiReferenceExpression
import com.intellij.psi.PsiType
import com.intellij.psi.util.InheritanceUtil
import com.intellij.psi.util.PsiUtil
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Resolves Java expressions to JSON-shaped values using IntelliJ PSI.
 *
 * Compile-time constants (literals, `static final` primitive/String refs, arithmetic,
 * string concat) are delegated to `PsiConstantEvaluationHelper` — the same engine the
 * compiler uses. The no-AuxEvaluator overload returns null for every method call by
 * design, so collection factories and other structural shapes are walked explicitly
 * using native PSI node types — no text parsing.
 *
 * Collection-factory detection is a semantic heuristic, not a hardcoded whitelist:
 * a call is treated as a value-producing factory when the resolved method is `static`
 * and its return type implements `java.util.Collection`, `java.util.Map`, or
 * `java.lang.Iterable`. This covers JDK (`Set.of`, `Arrays.asList`), Guava
 * (`Sets.newHashSet`), Eclipse Collections, Vavr, and user builders automatically
 * without a library-name list.
 *
 * `Optional.of(x)` / `Stream.of(x)` are excluded (their return types are not
 * Collection/Map/Iterable). User `MyBuilder.of(...)` returning a domain type is
 * excluded. Everything else renders as [DYNAMIC] so the graph stays honest.
 */
object ExpressionResolver {

    const val DYNAMIC: String = "<dynamic>"

    private const val COLLECTION_FQN: String = "java.util.Collection"
    private const val MAP_FQN: String = "java.util.Map"
    private const val ITERABLE_FQN: String = "java.lang.Iterable"

    /** Resolve an expression to a JsonElement. Never throws. */
    fun resolve(expr: PsiExpression?): JsonElement {
        if (expr == null) return JsonPrimitive(DYNAMIC)
        return try { resolveInternal(expr) } catch (_: Throwable) { JsonPrimitive(DYNAMIC) }
    }

    /** Resolve an annotation attribute value (array, class ref, nested annotation, expression). */
    fun resolveAnnotationValue(value: PsiAnnotationMemberValue?): JsonElement {
        if (value == null) return JsonPrimitive(DYNAMIC)
        return try {
            when (value) {
                is PsiArrayInitializerMemberValue ->
                    JsonArray(value.initializers.map { resolveAnnotationValue(it) })
                is PsiAnnotation -> resolveNestedAnnotation(value)
                is PsiExpression -> resolveInternal(value)
                else -> JsonPrimitive(value.text ?: DYNAMIC)
            }
        } catch (_: Throwable) { JsonPrimitive(DYNAMIC) }
    }

    /**
     * Flatten a resolved element into string tokens for a FalkorDB array property.
     * Enables `WHERE 'READ' IN node.argList` without JSON substring traps.
     */
    fun flatten(elem: JsonElement): List<String> {
        val out = mutableListOf<String>()
        walkFlat(elem, out)
        return out
    }

    /** Best-effort type string for an expression (used for EnumConstant.argTypes). */
    fun typeOf(expr: PsiExpression?): String {
        if (expr == null) return "?"
        return try { expr.type?.canonicalText ?: "?" } catch (_: Throwable) { "?" }
    }

    private fun resolveInternal(expr: PsiExpression): JsonElement {
        // 1. Compiler-grade constant folding (JLS constant expressions only).
        val facade = JavaPsiFacade.getInstance(expr.project)
        facade.constantEvaluationHelper.computeConstantExpression(expr)?.let { return toJson(it) }

        // 2. Array initializer: {A, B, C}
        if (expr is PsiArrayInitializerExpression) {
            return JsonArray(expr.initializers.map { resolve(it) })
        }

        // 3. Class literal: Foo.class → class identifier string.
        //    Prefer resolved FQN; fall back to the reference element's short text
        //    (what the user wrote) rather than `PsiType.toString()`, which leaks
        //    debug formatting like "PsiType:String" for unresolved references.
        if (expr is PsiClassObjectAccessExpression) {
            val type = expr.operand.type
            val fqn = PsiUtil.resolveClassInType(type)?.qualifiedName
                ?: expr.operand.innermostComponentReferenceElement?.qualifiedName
                ?: expr.operand.innermostComponentReferenceElement?.referenceName
                ?: expr.operand.text
            return JsonPrimitive(fqn)
        }

        // 4. Reference: enum constant, non-foldable static field, local var, etc.
        if (expr is PsiReferenceExpression) {
            return when (val target = expr.resolve()) {
                is PsiEnumConstant -> JsonPrimitive(target.name)
                is PsiField -> JsonPrimitive(target.name)
                else -> JsonPrimitive(expr.referenceName ?: expr.text ?: DYNAMIC)
            }
        }

        // 5. Method call: walk args iff semantically a collection factory.
        if (expr is PsiMethodCallExpression && isCollectionFactory(expr)) {
            return JsonArray(expr.argumentList.expressions.map { resolve(it) })
        }

        return JsonPrimitive(DYNAMIC)
    }

    /**
     * A call qualifies as a collection factory when the resolved method is static
     * and its return type is a subtype of Collection / Map / Iterable. Uses
     * `InheritanceUtil.isInheritor` for transitive supertype checks — no string
     * matching on class names.
     */
    private fun isCollectionFactory(call: PsiMethodCallExpression): Boolean {
        val method = call.resolveMethod() ?: return false
        if (!method.hasModifierProperty(PsiModifier.STATIC)) return false
        val returnClass = (method.returnType as? PsiClassType)?.resolve() ?: return false
        return InheritanceUtil.isInheritor(returnClass, COLLECTION_FQN) ||
            InheritanceUtil.isInheritor(returnClass, MAP_FQN) ||
            InheritanceUtil.isInheritor(returnClass, ITERABLE_FQN)
    }

    private fun resolveNestedAnnotation(ann: PsiAnnotation): JsonElement {
        val fqn = ann.qualifiedName ?: return JsonPrimitive(DYNAMIC)
        val attrs = ann.parameterList.attributes.associate { attr ->
            (attr.name ?: "value") to resolveAnnotationValue(attr.value)
        }
        return JsonObject(mapOf("@$fqn" to JsonObject(attrs)))
    }

    private fun walkFlat(elem: JsonElement, out: MutableList<String>) {
        when (elem) {
            is JsonPrimitive -> out.add(if (elem is JsonNull) "" else elem.content)
            is JsonArray -> elem.forEach { walkFlat(it, out) }
            is JsonObject -> elem.values.forEach { walkFlat(it, out) }
            JsonNull -> out.add("")
        }
    }

    private fun toJson(value: Any?): JsonElement = when (value) {
        null -> JsonNull
        is Boolean -> JsonPrimitive(value)
        is Number -> JsonPrimitive(value)
        is String -> JsonPrimitive(value)
        is Char -> JsonPrimitive(value.toString())
        // `computeConstantExpression` returns a PsiType for class literals
        // (`Foo.class`). Render it as the resolved FQN or canonical text —
        // never `toString()`, which leaks "PsiType:String"-style debug output.
        is PsiType -> JsonPrimitive(
            PsiUtil.resolveClassInType(value)?.qualifiedName ?: value.canonicalText
        )
        else -> JsonPrimitive(value.toString())
    }
}
