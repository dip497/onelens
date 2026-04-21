package com.onelens.plugin.settings

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.ide.passwordSafe.PasswordSafe

/**
 * Small wrapper around IntelliJ's [PasswordSafe] for the OpenAI-compat
 * embedder API key. We store this separately from [OneLensSettings] because
 * the latter round-trips through XmlSerializer into a plaintext file under
 * the config directory — fine for booleans and paths, wrong for secrets.
 *
 * Scope key is constant per install: swapping keys replaces the stored value.
 */
object OpenAiSecrets {

    private val ATTR = CredentialAttributes(
        generateServiceName("OneLens", "openai_embed_api_key"),
        "apiKey",
    )

    fun set(apiKey: String) {
        val trimmed = apiKey.trim()
        if (trimmed.isEmpty()) {
            PasswordSafe.instance.set(ATTR, null)
        } else {
            PasswordSafe.instance.set(ATTR, Credentials("apiKey", trimmed))
        }
    }

    fun get(): String? = PasswordSafe.instance.getPassword(ATTR)

    fun isPresent(): Boolean = !get().isNullOrBlank()
}
