# OneLens headless exporter (Docker)

> **Status: EXPERIMENTAL / UNVERIFIED.** The Dockerfile in this directory
> has **not been smoke-tested** against a real `docker run`. The
> `ENTRYPOINT` invokes `/opt/idea/bin/idea.sh` directly, but
> `jetbrains/qodana-jvm` actually ships `ENTRYPOINT ["/opt/idea/bin/qodana"]`
> (the Qodana CLI wrapper that consumes `QODANA_TOKEN` for Ultimate license
> checkout). Invoking `idea.sh` directly bypasses that wrapper, so the
> Ultimate license may not check out and Spring/JPA model resolution may
> fail. Until someone confirms (or fixes the entrypoint), treat this as a
> starting point, not a working CI path.
>
> The **verified** headless path is the Gradle task:
> `./gradlew headlessExport -PonelensProject=… -PonelensOutput=…`
> (deterministic for plain-Java, Spring Boot, and complex multi-layer Spring
> Boot apps — see `docs/headless.md`). Use that for now.

Run the OneLens PSI export in a container, no IDE required. Produces the
same export JSON the in-IDE Tools → OneLens → Sync Graph produces, then
exits. The downstream `onelens call-tool onelens_import` consumes the JSON
separately (graph + embeddings are built outside this image).

## Build

```bash
# From the repo root.
./gradlew buildPlugin
docker build \
  -t onelens/headless \
  -f docker/Dockerfile \
  --build-arg ONELENS_PLUGIN_ZIP=plugin/build/distributions/onelens-graph-builder-0.1.0.zip \
  .
```

Override `--build-arg ONELENS_PLUGIN_ZIP=...` if `pluginVersion` in
`plugin/gradle.properties` differs from `0.1.0`.

## Run

```bash
docker run --rm \
  -v /abs/path/to/your/spring/project:/src \
  -v /abs/path/to/output:/out \
  -e QODANA_TOKEN=<your-qodana-token> \
  onelens/headless
```

The container writes `/out/<graphId>-full-<timestamp>.json` and exits.
Stdout reports the file path + class/method/call counts.

## Import the JSON (outside the container)

The export is just structural facts. To build the graph + embeddings:

```bash
onelens call-tool onelens_import \
  --export-path /path/to/output/<graph>-full-*.json \
  --graph myapp \
  --backend falkordblite \
  --context            # optional: also build ChromaDB embeddings
```

`--backend falkordblite` is embedded (no Docker needed for the DB).
`--context` adds the semantic/embedding layer (~20 min first run on a large
project).

## Licensing — read this before relying on this image

`jetbrains/qodana-jvm` packages IntelliJ **Ultimate** in headless mode.
That's the whole reason it's the base: the OneLens Spring/JPA collectors
need the Ultimate-only Spring plugin model (`@Bean`/autowire candidates, JPA
entity metadata) to resolve. Community platform PSI alone won't see those.

This means:

- **You need a Qodana license** (Cloud or PErpetual) — pass `QODANA_TOKEN`.
  The Qodana floor is roughly **$40/dev/month, 10-dev minimum (~$4,800/yr)**
  per the repo's own `docs/design/PLAN-onboard-cli.md` §9 risk assessment.
  This image is the "works today, costs money" option, not the OSS default.
- **For a license-free CI path**, don't use this image. The project's
  intended license-free headless tier is **scip-java** (compiler-grade, no
  Spring layer) — see `docs/competitive-landscape.md` §N and the Phase Y4
  plan in `docs/design/context-engine-founding-research.md`. That's a
  separate, future track; this Dockerfile is the PSI-depth path.

If your project has **no Spring/JPA** (plain Java/Kotlin), the Community
platform resolves everything you need and you can swap the base to a
Community-headless image. The plugin itself installs fine on Community via
the optional config-file `<depends>` in `plugin.xml`.

## Troubleshooting

- **`QODANA_TOKEN` not set / license checkout fails** → the Ultimate
  platform won't start. Set the token, or use a Community base (see above).
- **`/src` not a project** → the starter needs an IntelliJ-openable project
  (`.idea/`, or importable `pom.xml`/`build.gradle`). Mount the repo root.
- **Spring beans/endpoints missing from the export** → you're on a
  Community-tier base without the Spring plugin. Use `qodana-jvm` or an
  Ultimate-licensed platform.
- **Bundled JBR is the wrong JDK for your project** → qodana-jvm pins a
  specific JetBrains Runtime. For a different JDK, extend the image and set
  `JAVA_HOME` (reported upstream as QD-14397).

## What this image does NOT do

- No graph DB inside the container. FalkorDB/falkordblite is a Python-side
  concern at import time.
- No embeddings inside the container. `onelens_import --context` builds them.
- No delta path. Headless is full-export only; delta needs the live VFS
  listener, which is an in-IDE feature.

See `docs/headless.md` for the broader headless-mode story and the two
other ways to run it (Gradle task, raw `idea.sh`).
