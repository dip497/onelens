package com.onelens.plugin.framework.vue3.collectors

import com.intellij.lang.javascript.psi.JSExpression
import com.intellij.lang.javascript.psi.JSObjectLiteralExpression
import com.onelens.plugin.export.PropData

/**
 * Parses a Vue prop declaration into [PropData].
 *
 * Shared because Vue 2 and Vue 3 declare props with the SAME grammar in two
 * different places:
 *
 *   Vue 3: `defineProps({ title: String })`      — the macro's first argument
 *   Vue 2: `export default { props: { … } }`     — the `props` option value
 *
 * Both accept the object form and the shorthand array form, so one parser
 * serves both collectors. Extracted out of `SfcScriptSetupCollector` rather
 * than duplicated — the two would drift on the next edge case otherwise.
 */
object VuePropParser {

    /**
     * Supported shapes (identical across Vue 2 and Vue 3):
     *   - `{ title: String }`                        → PropData("title", "String")
     *   - `{ count: { type: Number, default: 0 } }`  → type=Number, default="0"
     *   - `{ active: { type: Boolean, required: true } }` → required=true
     *   - `['title', 'id']`                          → names only, no types
     *
     * Returns an empty list for anything else (a computed prop object, a
     * spread of an imported constant). Unresolvable is reported as absent,
     * never as a guess.
     */
    fun parse(arg: JSExpression?): List<PropData> {
        if (arg == null) return emptyList()
        if (arg is JSObjectLiteralExpression) {
            return arg.properties.mapNotNull { prop ->
                val key = prop.name ?: return@mapNotNull null
                when (val v = prop.value) {
                    is JSObjectLiteralExpression -> PropData(
                        name = key,
                        type = v.findProperty("type")?.value?.text.orEmpty(),
                        required = v.findProperty("required")?.value?.text == "true",
                        defaultValue = v.findProperty("default")?.value?.text,
                    )
                    else -> PropData(name = key, type = v?.text.orEmpty())
                }
            }
        }
        // Array form: props: ['a', 'b'] / defineProps(['a', 'b'])
        return STRING_LITERAL_RE.findAll(arg.text)
            .map { PropData(name = it.groupValues[1]) }
            .toList()
    }

    internal val STRING_LITERAL_RE = Regex("""['"]([^'"]+)['"]""")
}
