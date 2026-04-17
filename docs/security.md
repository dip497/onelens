# Security

## Threat model

OneLens runs **entirely on the user's machine** by design. The
plugin reads source via IntelliJ PSI, the Python CLI reads
exported JSON and writes to a local FalkorDB (port `17532`) and
local ChromaDB. The embedding and rerank models (Qwen3 and mxbai)
run locally on CPU or GPU.

Surfaces that matter:

1. **Subprocess exec from the plugin** — the plugin shells out to
   the Python CLI with user-provided project paths. Path handling
   must escape properly; there must be no direct shell string
   interpolation of untrusted input.
2. **Local TCP port** — FalkorDB on `17532` is bound to
   `localhost` by default. If a user exposes it, they take
   responsibility for the exposure.
3. **File-system writes** — the plugin creates `~/.onelens/` and
   writes JSON exports there. No writes outside the user's home
   directory are performed.
4. **Claude Code skill install** — copies a bundled `SKILL.md` to
   `~/.claude/skills/onelens/SKILL.md`. Read-only side-effects on
   the Claude Code config tree.

## In scope (M1)

- **Subprocess command injection** — fixed: the CLI is invoked via
  `ProcessBuilder` with a list argument form, never via a shell
  string.
- **JSON export size limits** — loader streams UNWIND batches of
  1000 nodes / 500 edges; arbitrary-size input cannot OOM the
  importer.
- **ChromaDB schema drift** — unified canonical metadata across
  full + delta paths; tested via live round-trip.

## Out of scope (M1; may land M2 / M3)

- **Signed plugin distribution.** The plugin zip published to
  GitHub Releases is not code-signed. Users verify against the
  release tag's commit hash.
- **Auth on the FalkorDB port.** Default FalkorDB has no auth;
  users sharing a workstation should run it in a private
  container network.
- **Sandbox for the embedded Python subprocess.** The CLI runs
  with the user's full privileges.

## Reporting a vulnerability

See [`/SECURITY.md`](../SECURITY.md) for the canonical policy and
contact.

## Your responsibilities as a user

- Review diffs before merging upstream changes.
- Be skeptical of community contributions that ask for broad
  permissions (network I/O, shell-outs, new subprocess spawns).
- Keep IntelliJ, the plugin, and the Python venv up to date.
- Don't expose `localhost:17532` (FalkorDB) on a shared network
  without adding auth.

## A note on third-party content

OneLens does not install or execute third-party content beyond
its declared dependencies (FalkorDB client, ChromaDB,
sentence-transformers, NetworkX, cyclopts, FastMCP, etc.). The
embedding models it downloads on first use are hosted on
HuggingFace Hub; users are responsible for the integrity of those
downloads per HuggingFace's own guarantees.
