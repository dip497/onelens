# OneLens headless exporter.
#
# Runs the OneLensExportStarter ApplicationStarter inside Qodana's headless
# IntelliJ Platform JVM — no GUI, no EDT. Produces an export JSON that the
# Python `onelens call-tool onelens_import` consumes separately.
#
# Why qodana-jvm: the IntelliJ Community platform alone does NOT resolve
# Spring/JPA model classes the OneLens collectors depend on (`@Bean`/autowire
# candidates, JPA entity metadata). Those ship only with IntelliJ Ultimate.
# qodana-jvm is a maintained, headless Ultimate-platform image, so the PSI
# collectors get the same type-accurate model they get inside the IDE.
#
# Licensing: qodana-jvm requires a Qodana license (Cloud or PErpetual).
# Pass QODANA_TOKEN at runtime. See docker/README.md for the cost note and
# the Community-only fallback (loses Spring/JPA depth).
#
# Build:
#   ./gradlew buildPlugin
#   docker build -t onelens/headless \
#     -f docker/Dockerfile \
#     --build-arg ONELENS_PLUGIN_ZIP=plugin/build/distributions/onelens-graph-builder-0.1.0.zip \
#     .
#
# Run:
#   docker run --rm \
#     -v /abs/path/to/your/spring/project:/src \
#     -v /abs/path/to/output:/out \
#     -e QODANA_TOKEN=<your-token> \
#     onelens/headless
#
# Then import the JSON outside the container:
#   onelens call-tool onelens_import \
#     --export-path /output-dir/<graph>-full-*.json \
#     --graph myapp
#
# Image layout (qodana-jvm): IDE root at /opt/idea, launcher at
# /opt/idea/bin/idea.sh (on PATH), plugins at /opt/idea/plugins/, bundled
# JetBrains Runtime at /opt/idea/jbr. See docs/headless.md.

FROM jetbrains/qodana-jvm:latest

# The plugin ZIP produced by `./gradlew buildPlugin`. Override at build time
# if the version differs from gradle.properties:pluginVersion.
ARG ONELENS_PLUGIN_ZIP=onelens-graph-builder-0.1.0.zip
COPY ${ONELENS_PLUGIN_ZIP} /tmp/onelens-plugin.zip

# Install the plugin into the IDE's plugin directory. The ZIP ships with a
# top-level onelens-graph-builder/ dir, so unzipping directly under
# /opt/idea/plugins/<name> would double-nest (invalid plugin layout — the
# loader scans /opt/idea/plugins/<dir>/lib/*.jar directly). Unzip to a
# scratch dir and move the inner dir into place.
RUN unzip -q /tmp/onelens-plugin.zip -d /tmp/ol-plugin \
    && mv /tmp/ol-plugin/onelens-graph-builder /opt/idea/plugins/onelens-graph-builder \
    && rm -rf /tmp/onelens-plugin.zip /tmp/ol-plugin

# Project in, JSON out. /src must contain a project IntelliJ can open
# (has .idea/ or is importable from pom.xml/build.gradle). /out receives
# the <graphId>-full-<ts>.json written by ExportService.exportFull.
VOLUME ["/src", "/out"]

# ONELENS_OUTPUT tells ExportConfig.outputPath where to land the JSON. The
# starter also accepts --output-dir on the command line, which overrides this.
ENV ONELENS_OUTPUT=/out

# Headless launcher. The command name `onelens-export` matches the `id` on
# <appStarter> in plugin.xml (the platform reads it from there, not from
# ApplicationStarter.getCommandName). `--project /src` and `--output-dir /out`
# map to the bind mounts above.
#
# WARNING — UNVERIFIED (see docker/README.md "Status: experimental"):
#   This ENTRYPOINT invokes idea.sh directly. The jetbrains/qodana-jvm image
#   actually sets ENTRYPOINT ["/opt/idea/bin/qodana"] (the Qodana CLI wrapper
#   that consumes QODANA_TOKEN for license checkout). Invoking idea.sh
#   directly BYPASSES that wrapper, so:
#     - the Ultimate license is not checked out → Spring/JPA model may not resolve
#     - Qodana-injected JVM args are not applied
#   Until a `docker build && docker run` smoke-test confirms `onelens-export`
#   works through idea.sh on this base (or the entrypoint is switched to the
#   qodana wrapper, which may reject onelens-export as an unknown command),
#   treat the Docker path as EXPERIMENTAL. The verified headless path is the
#   Gradle task (./gradlew headlessExport) — see docs/headless.md.
ENTRYPOINT ["/opt/idea/bin/idea.sh", "onelens-export", "--project", "/src", "--output-dir", "/out"]
