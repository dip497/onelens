import org.jetbrains.intellij.platform.gradle.TestFrameworkType
import org.jetbrains.intellij.platform.gradle.tasks.RunIdeTask

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

    // Official MCP Kotlin SDK (modelcontextprotocol + JetBrains). Used by
    // OneLensMcpClient to POST tool calls over Streamable HTTP to the
    // plugin-owned Python MCP child. Version aligned with Ktor 3.3.3 per
    // the SDK's libs.versions.toml. `ktor-client-cio` is the pure-Kotlin
    // engine; ships clean inside IntelliJ's classloader.
    // Official MCP Kotlin SDK — pinned to 0.9.0 because 0.10+ ships
    // metadata compiled with Kotlin 2.3, which the IntelliJ Platform
    // 2025.1-bundled Kotlin compiler (2.1.20) cannot read. 0.9.0 was
    // published against Kotlin 2.1 / Ktor 2.3 and loads cleanly in the
    // plugin classloader. Bump to 0.11+ when the IntelliJ platform
    // bumps its Kotlin toolchain.
    // Ktor CIO is the pure-Kotlin HTTP engine used by the transport;
    // alternatives (OkHttp / Apache) pull platform-conflicting deps.
    implementation("io.modelcontextprotocol:kotlin-sdk-client:0.9.0")
    implementation("io.ktor:ktor-client-cio:2.3.12")

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

    // Headless export — runs the OneLensExportStarter ApplicationStarter
    // inside a real IntelliJ Platform JVM launched from the prepared sandbox,
    // with no display. Writes ~/.onelens/exports/<graph>-full-<ts>.json and
    // exits. PSI + collectors are exercised exactly as in the IDE; only the
    // GUI/EDT is absent. See OneLensExportStarter.kt + docs/headless.md.
    //
    // Usage:
    //   ./gradlew headlessExport \
    //     -PonelensProject=/abs/path/to/spring/app \
    //     [-PonelensOutput=/abs/path/to/outdir]
    //
    // Implementation note: we configure the plugin's built-in `runIde` task
    // (which already has platformType / platformVersion / splitMode / plugins
    // wired by the intellij-platform-gradle-plugin) and inject our starter
    // command as its argv. Registering a fresh RunIdeTask requires
    // re-declaring all of that wiring; reusing runIde avoids it. `headlessExport`
    // is then a thin alias that depends on runIde so the user-facing command
    // reads naturally and enforces the required -PonelensProject property.
    named<RunIdeTask>("runIde") {
        // Only meaningful when driving the headless starter; runIde's normal
        // use (popping a GUI IDE) is unaffected for other invocations because
        // these args are only consumed when the IDE is launched.
        val projectPath = providers.gradleProperty("onelensProject")
            .orElse(providers.environmentVariable("ONELENS_PROJECT"))
        val outputPath = providers.gradleProperty("onelensOutput")
            .orElse(providers.environmentVariable("ONELENS_OUTPUT"))
            .orElse("")
        argumentProviders.add {
            val proj = projectPath.orNull ?: return@add emptyList()
            val out = outputPath.orNull?.takeIf { it.isNotBlank() }
                ?: "${System.getProperty("user.home")}/.onelens/exports"
            val args = mutableListOf("onelens-export", "--project", proj, "--output-dir", out)
            // Read delta flag at execution time (not configuration time) to
            // avoid configuration-cache serialization issues.
            if (System.getenv("ONELENS_DELTA")?.toBooleanStrictOrNull() == true) {
                args.add("--delta")
            }
            args
        }
        // Headless: no EDT, no Swing. The platform + our starter honor this.
        systemProperty("java.awt.headless", "true")
        // Auto-link Maven/Gradle projects on open. Without this, a headless
        // open of a project with a pom.xml/build.gradle shows an "unlinked
        // project" notification (which a user would click) and never imports
        // — so no source roots, no indexing, empty export. AUTO links it
        // without UI. Same registry key the IDE writes when the user picks
        // "Import" on the unlinked-project balloon.
        systemProperty("external.system.link.unlinked.projects", "AUTO")
        // Isolated system/ dir per run. The shared build/idea-sandbox index
        // contaminates across projects: the scanner reports "0 files for
        // indexing" on subsequent runs because it thinks a prior project's
        // index already covers the new files. This is a documented platform
        // behavior — bentolor/idea-cli-inspector's troubleshooting verbatim:
        // "The analysis seems to produce different results on subsequent runs…
        // Try if deleting the system/ directory prior to executing produces
        // stable results." JetBrains' own inspection-plugin uses a fresh
        // locked system/ dir per run (SystemPathManager + marker.ipl lock).
        // We point idea.system.path (NOT idea.home.path — that must stay the
        // real IDE install or bootstrap crashes) at a per-output location.
        // Set ONELENS_SYSTEM_DIR to override (e.g. a CI-specific path).
        val systemDir = providers.environmentVariable("ONELENS_SYSTEM_DIR")
            .orElse(layout.buildDirectory.dir("onelens-system").map { it.asFile.path })
        systemProperty("idea.system.path", systemDir.get())
        // Configurable max heap for large projects. The platform default
        // (~2GB) is fine for fixtures but a 45K-file enterprise codebase
        // hits memory pressure → GC compaction → index rebuild → timeout.
        // Override via -PonelensXmx=4g (or ONELENS_XMX env). No-op for the
        // default fixture runs.
        val xmx = providers.gradleProperty("onelensXmx")
            .orElse(providers.environmentVariable("ONELENS_XMX"))
        xmx.orNull?.let { jvmArgs("-Xmx$it") }
    }

    register("headlessExport") {
        group = "onelens"
        description = "Run the OneLens PSI export headlessly (no GUI). Writes JSON, then exits."
        dependsOn("runIde")
        // Note: we intentionally do NOT validate -PonelensProject here. A
        // doFirst closure would capture `providers` and break Gradle 9's
        // configuration cache (cannot serialize Gradle script object refs).
        // runIde's argumentProviders already no-ops when the property is
        // absent, and a missing property just launches a normal IDE — the
        // user-visible failure mode is "IDE opened instead of export", which
        // the docs call out. Keeping this task config-cache-compatible.
    }
}
