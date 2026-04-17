# Contributing

The canonical contributor guide lives at
[**docs/contributing.md**](./docs/contributing.md). Start there.

Quick summary:

- Open an issue before large PRs.
- Run `cd plugin && ./gradlew compileKotlin buildPlugin` for plugin
  changes, and `cd python && ruff check . && pytest -q` for Python
  changes, before submitting.
- Read `docs/LESSONS-LEARNED.md` before touching the importer, delta
  pipeline, embeddings, or FalkorDB schema.
- Be kind. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
- Governance and decision-making: [docs/governance.md](./docs/governance.md).
