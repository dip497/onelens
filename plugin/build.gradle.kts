import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("java")
    alias(libs.plugins.kotlin)
    alias(libs.plugins.kotlinSerialization)
    alias(libs.plugins.intelliJPlatform)
    alias(libs.plugins.kover)
}

group = providers.gradleProperty("pluginGroup").get()
version = providers.gradleProperty("pluginVersion").get()

kotlin {
    jvmToolchain(21)
}

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    // JSON serialization for export output
    implementation(libs.kotlinx.serialization.json)

    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.opentest4j)
    testImplementation(libs.mockk) {
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-core")
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-core-jvm")
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-bom")
    }

    intellijPlatform {
        pluginVerifier()
        create(providers.gradleProperty("platformType"), providers.gradleProperty("platformVersion"))
        bundledPlugins(providers.gradleProperty("platformBundledPlugins").map { it.split(',') })
        plugins(providers.gradleProperty("platformPlugins").map { it.split(',').filter(String::isNotBlank) })
        bundledModules(providers.gradleProperty("platformBundledModules").map { it.split(',') })
        testFramework(TestFrameworkType.Platform)
        // Enables LightJavaCodeInsightFixtureTestCase + JAVA_17 light project
        // descriptor for Java PSI tests. Without this the Java resolver tests
        // run under the bare mock JDK and can't resolve `Set.of`, `String`, etc.
        testFramework(TestFrameworkType.Plugin.Java)

        // Marketplace plugins whose exact build id we don't want to pin. The Gradle plugin
        // queries JetBrains Marketplace for a version compatible with the current
        // platformVersion at configuration time. See:
        // https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin-dependencies-extension.html
        //
        // These are optional at runtime (config-file split in plugin.xml); the plugin still
        // installs into IDEs that lack them.
        compatiblePlugins(
            providers.gradleProperty("platformCompatiblePlugins")
                .map { it.split(',').filter(String::isNotBlank) }
                .orElse(emptyList())
        )
    }
}

intellijPlatform {
    pluginConfiguration {
        name = providers.gradleProperty("pluginName")
        version = providers.gradleProperty("pluginVersion")

        ideaVersion {
            sinceBuild = providers.gradleProperty("pluginSinceBuild")
        }
    }

    pluginVerification {
        ides {
            recommended()
        }
    }
}

kover {
    reports {
        total {
            xml {
                onCheck = true
            }
        }
    }
}

tasks {
    wrapper {
        gradleVersion = providers.gradleProperty("gradleVersion").get()
    }

    // Bundle the OneLens skill (SKILL.md + references/*.md) into the plugin JAR
    // so `InstallSkillAction` can ship it to ~/.claude/skills/onelens/ without
    // requiring users to have the repo checked out. Source: skills/onelens/ at
    // the project root (one level above plugin/). Runs on every build;
    // processResources copies the whole directory into the jar under /skills/onelens/.
    processResources {
        from("${project.rootDir.parent}/skills") {
            into("skills")
            include("onelens/SKILL.md")
            include("onelens/references/**")
        }
        // Bundle the Python source tree so PythonEnvManager can install
        // onelens[context] into a fresh venv on a machine with no repo
        // checked out and no PyPI release. Extracted on first sync to
        // ~/.onelens/source/ and installed via `uv pip install -e`.
        // Exclude build artifacts, caches, and local-only dev files.
        from("${project.rootDir.parent}/python") {
            into("python")
            exclude(
                "**/.venv/**",
                "**/__pycache__/**",
                "**/*.egg-info/**",
                "**/.pytest_cache/**",
                "**/.mypy_cache/**",
                "**/.ruff_cache/**",
                "**/dist/**",
                "**/build/**",
                "**/*.pyc",
                "benchmarks/**",
                "trial_*.py",
                "modal_index*.py",
            )
        }
    }
}
