# AGENTS.md

Rules for any coding agent working inside this repository (Codex,
Claude Code, Cursor, Continue, Cline, Windsurf, Aider, others).
Self-contained — no external references required.

## Project

OneLens — code knowledge graph for Java/Spring Boot projects. Gives AI
100% type-accurate understanding of a codebase via IntelliJ PSI, plus
semantic search over method bodies and javadoc. Polyglot monorepo:
Python CLI/importer/MCP server + Kotlin/Gradle IntelliJ plugin.

Public documentation lives under `docs/`. Start with
`docs/introduction.md`, `docs/concepts.md`, and `docs/architecture.md`.
Every subtle bug we've already paid for is catalogued in
`docs/LESSONS-LEARNED.md` — read it before touching the importer,
delta pipeline, embeddings, or FalkorDB schema.

## Critical rules

- **Read `docs/LESSONS-LEARNED.md` before changing graph import,
  delta handling, embeddings, or FalkorDB FTS code.** Each lesson
  encodes a specific production failure.
- **MCP server is the source of truth for the CLI.** Edit
  `python/src/onelens/mcp_server.py`; `cli_generated.py` is produced
  by `fastmcp generate-cli` — never hand-edit.
- **Preserve the ChromaDB metadata schema** (`wing`, `room`, `hall`,
  `fqn`, `type`, `importance`, `filed_at`). Drift between full and
  delta write paths silently breaks wing-scoped retrieval.
- **Type-hint all public Python APIs.** `mypy` is advisory today;
  aim for `--strict` where practical.
- **Kotlin: run `./gradlew compileKotlin` before committing
  plugin changes.** A silent CLI rename has already shipped once
  because this wasn't gated — CI now catches it.
- **No client names in the repo or memory.** Before public push,
  `grep -rIn "<client-name>"` for any leaked identifiers.
- Use `pathlib.Path`, not `os.path` / `str` paths.
- Use `logging`, not `print`, in library code.

## Dev commands

```
# Python
cd python
pip install -e ".[context]"
ruff format .
ruff check .
pytest -q                       # if tests present
mypy src/onelens                # advisory

# Plugin
cd plugin
./gradlew compileKotlin
./gradlew buildPlugin           # → plugin/build/distributions/

# End-to-end
docker run -d -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest
onelens import-graph <json> --graph myproj --context
onelens stats --graph myproj
```

All checks (Kotlin compile, plugin build, Python ruff/mypy advisory,
pytest where present) must pass before a PR is merged.

## Workflow

- Docs before code for non-trivial design.
- One logical change per commit and per PR.
- Branches: `feature/<scope>`, `fix/<scope>`, `docs/<scope>`,
  `rfc/<name>`.
- Commits in imperative mood.
- Update `CHANGELOG.md` for user-visible changes.
- Non-trivial proposals go through an `rfc:`-labelled issue with
  one-week comment period before implementation PR.
- Record non-trivial design decisions in `docs/DECISIONS.md` as new
  ADRs.

## Communication

Match the project lead's tone. Keep technical substance exact.

## Licensing

Dual MIT OR Apache-2.0 at the user's option. New source files need
no per-file licence header; the root `LICENSE`, `LICENSE-MIT`, and
`LICENSE-APACHE` cover the tree.

## Token Efficiency

- Never re-read files you just wrote or edited.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo large blocks of code or file contents unless asked.
- Batch related edits into single operations.
- Skip confirmations like "I'll continue...". Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarise what you just did unless the result is ambiguous.
