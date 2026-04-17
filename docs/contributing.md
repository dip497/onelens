# Contributing

Thank you for considering a contribution. OneLens is an opinionated
project; contributions that fit the opinions ship fastest.

## Ways to help today

1. **Open an issue if documentation is unclear, wrong, or missing
   something.** Link to the paragraph.
2. **Try OneLens on your own Spring Boot codebase** and tell us
   where accuracy, speed, or UX breaks. These are the highest-
   signal reports we get.
3. **Propose a concrete mechanic** via an `rfc:`-labelled issue —
   new collector, new retrieval feature, new backend.
4. **Add a regression case to the internal benchmark suite** if you
   catch a retrieval bug. See `python/benchmarks/` (local, gitignored
   — ask a maintainer for access).

## Setup

### Plugin

```bash
cd plugin
./gradlew compileKotlin        # fast feedback loop
./gradlew buildPlugin          # full build
# plugin zip at build/distributions/onelens-graph-builder-<version>.zip
```

### Python

```bash
cd python
pip install -e ".[context]"    # includes Qwen3 + mxbai deps
ruff format .
ruff check .
mypy src/onelens               # advisory today
pytest -q                      # if tests present
```

### End-to-end test

```bash
docker run -d --name falkordb -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
onelens import-graph <your-export.json> --graph testproj --context --clear
onelens stats --graph testproj
onelens retrieve --query "authentication" --graph testproj
```

## Before you open a PR

- **Read `docs/LESSONS-LEARNED.md`** if your change touches graph
  import, delta handling, embeddings, or FalkorDB FTS. Nearly every
  non-obvious bug in that document cost us hours; the file is how
  we cash in the tuition.
- **Run `./gradlew compileKotlin`** for plugin changes. A CLI rename
  slipped through once because this wasn't gated.
- **Run `ruff check .`** for Python changes.
- **Regenerate `cli_generated.py`** (`fastmcp generate-cli`) if you
  added or changed an `@mcp.tool`.

## Pull request etiquette

- One logical change per PR.
- Title in imperative mood ("Add X", not "Added X").
- Link the issue the PR closes.
- Update `CHANGELOG.md` under `[Unreleased]` for user-visible
  changes.
- For new retrieval behaviour, include a benchmark before/after
  (single-tool pass rate and, where relevant, scenario pass rate).
- Expect review. Most non-trivial PRs get one round of feedback.

## Governance

BDFL-led pre-1.0 — see [governance.md](./governance.md). Larger
proposals go through an `rfc:`-labelled issue with a one-week
comment period before implementation.

## Code of conduct

Be kind, be honest, be specific. Full
[Code of Conduct](../CODE_OF_CONDUCT.md).
