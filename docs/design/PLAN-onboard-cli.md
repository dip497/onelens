# Plan — Global CLI + `onelens onboard` + MCP decoupling

**Status:** Draft v2 · 2026-04-26 (research-validated)
**Owner:** unassigned
**Supersedes:** plugin-side `PythonEnvManager` bootstrap path
**Research backing:** Exa + Context7 + WebFetch sweep on uv/pipx, Claude Code MCP scopes, keyring fallback behavior, embedder leaderboards (CoIR Apr 2026), Continue.dev / GitNexus / Cody / Cursor onboarding patterns. Citations inline.

---

## 1. Problem

Today the IntelliJ plugin owns the entire bootstrap:
`PythonEnvManager` (660 LOC Kotlin) installs `uv`, creates the venv, extracts the bundled Python source, runs `uv pip install`, lazy-installs the semantic stack, and spawns the MCP child. Consequences:

- **No headless story.** CI / VS Code / non-IntelliJ shops can't onboard.
- **Plugin and CLI duplicate logic.** `installSemanticStack`, `installTensorrt`, GPU probe, key handling — all live in Kotlin, then again as CLI flags.
- **MCP lifecycle tied to IDE.** When IntelliJ exits, the MCP child dies. External Claude Code sessions lose the tool.
- **Secrets handled ad-hoc.** No keyring, no rotate, no validation. Easy to leak via `idea.log`.
- **Competitors (GitNexus, Graphify) install in one line.** OneLens onboarding feels heavy by comparison.

## 2. Goals

1. **Single source of truth.** All install / dep / config / key logic lives in the Python CLI. Plugin shells out.
2. **One-command onboarding.** `curl | sh` → `onelens onboard` and the user is indexing within ~60s on a typical box.
3. **Embedder choice up-front.** Local (GPU/CPU) vs cloud (OpenAI / Voyage / Cohere) decided at onboard, not buried in settings.
4. **Safe key storage.** OS keyring default, file fallback, env override. Never in MCP-exposed tools. Never logged.
5. **Plugin-independent MCP.** MCP server registers directly with Claude Code via `claude mcp add`. Plugin removal does not break the agent.
6. **Backwards compatible.** Existing `~/.onelens/venv` installs keep working. No forced reindex.

## 3. Non-goals

- Reimplementing Spring PSI on tree-sitter (separate "Phase B" track).
- Hosted SaaS / multi-tenant graph backend.
- VS Code extension (Phase 3, downstream of this plan).
- Migrating away from FastMCP.

---

## 4. Architecture

### 4.1 New install flow

**Primary path: `uv tool install`** (10-100× faster than pipx, no Python prereq, single binary). pipx kept as fallback for users who already have it. PyInstaller rejected: torch + transformers payload = 500 MB-1.5 GB.

```
# Option A — bootstrap (fresh box):
curl -LsSf https://onelens.dev/install.sh | sh
  ├─ install uv if missing      (curl https://astral.sh/uv/install.sh | sh)
  ├─ uv python install 3.11     (only if no system Python)
  └─ uv tool install onelens    → ~/.local/bin/onelens

# Option B — already has uv:
uv tool install onelens

# Option C — already has pipx:
pipx install onelens

cd <project>
onelens onboard
  ├─ probe system (python, uv, git, docker, gpu, driver)
  ├─ install missing deps                           (uv via curl, falkordblite via pip)
  ├─ ask: embedder backend?  → local | voyage (recommended cloud) | openai | skip
  │     ├─ local  → install onnxruntime-gpu + cuDNN + cuBLAS (~1 GB) [+ tensorrt opt]
  │     │           [Qwen3-Embedding-0.6B + mxbai rerank, GPU-accelerated]
  │     └─ cloud  → prompt API key → validate → store (keyring → file fallback)
  │                 [voyage-code-3 = CoIR 77.33, code-tuned SOTA Apr 2026 per voyageai.com]
  │                 [openai text-embedding-3-small = $0.02/1M, generic, fallback option]
  │                 [cohere/jina deferred — no clear advantage for code retrieval]
  ├─ pick graph backend                             → falkordblite (default) | falkordb | neo4j
  ├─ register MCP with Claude Code                  → project-scope `.mcp.json` (default)
  │                                                   `claude mcp add --scope project --transport stdio onelens -- onelens mcp serve`
  │                                                   `--global` flag for user-scope `~/.claude.json`
  ├─ install Claude Code skill                      → ~/.claude/skills/onelens/
  └─ first index                                    → onelens index --headless | "open IntelliJ now"
```

### 4.2 Plugin role after this plan

```kotlin
// Plugin pseudo-code post-refactor
val cli = which("onelens") ?: run {
    showBalloon("OneLens CLI not installed", action = "Run installer") {
        runProcess(listOf("bash", "-c", "curl -LsSf https://onelens.dev/install.sh | sh"))
    }
    return
}
runProcess(listOf(cli, "index", "--export", exportJson, "--graph", project.name))
```

Drop: `PythonEnvManager.installSemanticStack`, `installTensorrt`, `findUv`, `autoInstallUv`, `extractBundledSource`, `linkIntoLocalBin`. ~400 LOC removed.
Keep: PSI export collectors, `OneLensExportStarter` (Phase 2 headless), settings UI for `embedderBackend` (reads `onelens config show`).

### 4.3 MCP decoupling

**Before (today):** `ExportService` / plugin owns MCP child lifecycle.

**After:**

```bash
# Onboard registers once:
claude mcp add onelens -- onelens mcp serve

# Claude Code spawns stdio child per session, kills on exit.
# Plugin: not involved in MCP at all.
```

Optional warm-model daemon stays available for power users:

```bash
onelens daemon start          # keeps Qwen3 + mxbai loaded in RAM
onelens mcp serve --daemon    # MCP child connects to daemon for embed/rerank
```

Tradeoff:

| Mode | Cold start | RAM | When to use |
|---|---|---|---|
| stdio (default) | ~3s | freed between sessions | typical |
| stdio + daemon | ~50ms | ~2 GB resident | heavy interactive use |

### 4.3.1 MCP scope decision — project vs global

**Default = project-scope** (`<repo>/.mcp.json`, committable). Rationale: OneLens graphs are project-bound — graph name = project name, embeddings live in `~/.onelens/graphs/<project>`. MCP scope should match.

| Tool | Scope | Why |
|---|---|---|
| OneLens (proposed) | project | Graph is repo-scoped |
| GitNexus | global | Cross-repo MCP, no per-project state |
| Continue.dev | per-project `.continue/` | Repo-bound config |

**Override:** `onelens onboard --global` writes `~/.claude.json` user section.

**Idempotency caveat (Claude Code #8288):** `claude mcp add` lacks stable "already registered" exit code. Onboard implementation: parse `claude mcp list` JSON output → if `onelens` present, skip; else `add`. On parse failure, fall back to `remove` + `add`. Document this fragility.

**Upgrade UX:** Claude Code does NOT auto-respawn MCP servers when config changes. After `onelens upgrade` mutates anything, print:

```
✓ Upgraded onelens to 1.3.0
⚠ Restart Claude Code or run /mcp to reconnect.
```

### 4.4 Key + config storage

```
~/.onelens/
├── config.toml          # embedder, graph backend, host:port, paths
├── keys.json            # 0600, fallback only
├── venv/                # CLI deps
├── graphs/              # falkordblite data
└── exports/             # JSON exports
```

Resolution order at runtime: **env > OS keyring > file**. Env wins so CI/Docker overrides.

**Honest reality on keyring (research-validated):** Python `keyring` works on macOS Keychain + Windows Credential Manager. On **headless Linux / WSL / SSH-only boxes** without D-Bus + gnome-keyring, SecretService **fails silently**. Industry reality (gh, aws, gcloud, aider, Claude Code itself) = plaintext + `chmod 600` is the dominant pattern; keyring is "nice if available."

**OneLens implementation:**
1. Try `keyring.set_password()`. If it raises or returns no-backend, fall through.
2. Write to `~/.onelens/keys.json`, chmod 600. Print warning: `⚠ keyring unavailable — stored in ~/.onelens/keys.json (chmod 600). Use OP_API_KEY=... onelens ... for hardened setups.`
3. Document `op run -- onelens` (1Password CLI) and Bitwarden `bw` env-var injection in README. Don't hard-couple.

**Mirror gh's pattern:** expose `--insecure-storage` flag so user opts in explicitly to file fallback instead of failing the whole onboard.

```python
# onelens/config/secrets.py
KEYRING_SERVICE = "onelens"

def get_key(provider: str) -> str | None:
    if v := os.environ.get(f"{provider.upper()}_API_KEY"):
        return v
    try:
        if v := keyring.get_password(KEYRING_SERVICE, provider):
            return v
    except Exception:
        pass
    if FILE_PATH.exists():
        return json.loads(FILE_PATH.read_text()).get(provider)
    return None
```

### 4.5 MCP tool surface — security boundary

**Exposed as `@mcp.tool` (agent-callable):**
- `import_graph`, `delta_import`, `stats`, `query`, `search`, `impact`, `trace`, `entry_points`, `retrieve`, `mine`, `daemon_status`

**NOT exposed (CLI-only):**
- `config_set`, `config_get`, `config_show` — agent must never read/write API keys.
- `key_set`, `key_rotate`, `key_delete` — same.
- `install`, `uninstall`, `upgrade` — agent must not mutate venv.
- `setup`, `onboard`, `doctor` — interactive prompts incompatible with MCP.

Enforced by: those functions live in `onelens/cli_only/` and are imported only by `cli.py`, not `mcp_server.py`. CI guard: `grep -r "@mcp.tool" python/src/onelens/cli_only/` must be empty.

---

## 5. CLI surface

```
onelens onboard                                     # interactive per-project setup
onelens setup [--gpu|--cpu|--cloud=<provider>]       # install / reinstall deps
onelens doctor                                       # health check, exit 0/1
onelens config show [--json]                         # masked dump
onelens config embedder <local|openai|voyage|cohere>
onelens config key set <provider> [--source=keyring|file|env]
onelens config key rotate <provider>
onelens config key delete <provider>
onelens index [--headless] [--export <json>]
onelens mcp serve [--stdio|--daemon]
onelens daemon start|stop|status
onelens uninstall [--purge]
onelens upgrade
```

Existing commands (`import-graph`, `query`, `search`, `impact`, `trace`, `retrieve`, `stats`) unchanged.

## 6. File-level changes

### 6.1 New files

```
python/src/onelens/
├── cli_only/                       # never imported by mcp_server
│   ├── __init__.py
│   ├── onboard.py                  # interactive flow (rich prompts)
│   ├── setup.py                    # install deps, reused by onboard
│   ├── doctor.py                   # preflight (was: bits of PythonEnvManager)
│   ├── secrets.py                  # keyring/file/env resolution
│   ├── config.py                   # ~/.onelens/config.toml RW
│   └── installers/
│       ├── uv.py                   # auto-install uv (was Kotlin)
│       ├── gpu_stack.py            # onnxruntime-gpu + cuDNN
│       ├── falkor.py               # falkordblite vs falkordb decision
│       └── claude_mcp.py           # `claude mcp add onelens ...`
└── tests/cli_only/                 # mock prompts, validate flows

scripts/install.sh                  # curl-bash installer (uv + pipx + onelens)
docs/design/PLAN-onboard-cli.md     # this file
```

### 6.2 Modified files

```
python/pyproject.toml               # add: keyring, rich (already), tomli-w
python/src/onelens/cli_generated.py # regen via scripts/regen_cli.sh after mcp_server tools change
python/src/onelens/mcp_server.py    # remove cli_only imports; add @mcp.tool only for safe ops
plugin/.../PythonEnvManager.kt      # delete most; keep getOneLensCli() that just whichs `onelens`
plugin/.../actions/InstallSkillAction.kt  # delegate to `onelens config skill install`
plugin/.../export/ExportService.kt  # call `onelens index --export <json>` instead of cli_generated
docs/PROGRESS.md                    # add row: Onboard CLI ✅
CHANGELOG.md                        # Unreleased → Added: onboard CLI
docs/DECISIONS.md                   # ADR-NNN: CLI owns bootstrap, MCP independent of plugin
```

### 6.3 Deleted code

```
plugin/.../PythonEnvManager.kt      # ~400 LOC: installSemanticStack, installTensorrt,
                                    #          findUv, autoInstallUv, extractBundledSource,
                                    #          linkIntoLocalBin, detectLocalProvider helpers
plugin/.../resources/python/        # bundled Python source — now pulled from PyPI
```

---

## 7. Phasing

### Phase 1 — Extract setup (1 week)

- [ ] `cli_only/setup.py` mirrors `PythonEnvManager.installOneLens` + `installSemanticStack`
- [ ] `cli_only/installers/uv.py` mirrors `autoInstallUv`
- [ ] `cli_only/secrets.py` + `cli_only/config.py` (keyring + file + env)
- [ ] `onelens setup` command works standalone end-to-end
- [ ] `onelens doctor` reports all preflight checks
- [ ] CI: integration test on Linux + macOS GitHub runners

### Phase 2 — Onboard (1 week)

- [ ] `cli_only/onboard.py` interactive flow (Rich prompts)
- [ ] Embedder branch: local / openai / voyage / cohere / skip
- [ ] Key validation — call provider's tiniest endpoint, fail fast
- [ ] Storage choice: keyring / file / env
- [ ] `claude mcp add onelens -- onelens mcp serve` registration
- [ ] Skill copy to `~/.claude/skills/onelens/`
- [ ] First index hand-off (headless or "open IntelliJ")

### Phase 3 — Plugin slimdown (3 days)

- [ ] Plugin detects `onelens` on PATH; if missing, balloon → run installer
- [ ] Delete `PythonEnvManager` ~400 LOC
- [ ] Settings UI reads `onelens config show --json`
- [ ] InstallSkillAction shells out to `onelens config skill install`
- [ ] Smoke test: fresh IntelliJ + plugin + no global CLI → balloon → install → sync works

### Phase 4 — install.sh + PyPI publish (2 days)

- [ ] `scripts/install.sh` — uv + pipx + `onelens` from PyPI
- [ ] Publish `onelens` to PyPI (already on path; finalize package metadata)
- [ ] README install section rewritten
- [ ] Marketplace plugin description updated

### Phase 5 — Headless indexer (later, separate plan)

- [ ] `OneLensExportStarter : ApplicationStarter` (Kotlin)
- [ ] `onelens index --headless` shells into Qodana JVM Docker
- [ ] CI integration test on Spring Petclinic

---

## 8. Acceptance criteria

1. Fresh Ubuntu 24.04 box, no python, no uv, no docker:
   - `curl -LsSf https://onelens.dev/install.sh | sh` exits 0 in < 30s.
   - `cd petclinic && onelens onboard` produces a working graph + Claude Code MCP within 5 min (local backend) or 90s (cloud BYOK).
2. `onelens doctor` returns exit 0 on a healthy box, exit 1 with actionable fix instructions otherwise.
3. `claude mcp list` shows `onelens` after onboard. `claude mcp remove onelens` cleanly unregisters.
4. Killing IntelliJ does not break MCP — Claude Code can still call `impact` / `retrieve` / `query`.
5. `grep -r "@mcp.tool" python/src/onelens/cli_only/` returns empty (CI guard).
6. Plugin `PythonEnvManager` LOC drops by ≥ 350 lines.
7. `onelens config key set openai` validates the key against `https://api.openai.com/v1/models` before storing.
8. Stored key never appears in `idea.log`, `~/.onelens/*.log`, or any MCP tool result. CI grep guard.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Users on offline networks can't `curl install.sh` | Document `uv tool install onelens-X.Y.Z.tar.gz` offline path |
| `keyring` lacks backend on headless Linux / WSL (no D-Bus) | Confirmed real (research). Auto-fallback to `~/.onelens/keys.json` chmod 600 + warning. `--insecure-storage` flag for explicit opt-in. |
| Plugin shell-out latency on Windows | Cache `which` result; fall back to direct venv python on misses |
| Claude Code CLI not installed | Skip `claude mcp add`, print copy-paste command for manual register |
| PyPI publish blocks on name | Reserve `onelens` now; confirm before Phase 4 |
| Existing `~/.onelens/venv` from old plugin path | First-run `onelens doctor` migrates: copies config, leaves venv if compatible |
| `claude mcp add` idempotency unstable (#8288) | Parse `claude mcp list` JSON before add; fallback to remove+add. Pin to documented `claude` versions in `pyproject.toml` extras. |
| voyage-code-3 sole-vendor lock-in | Embedder interface = single config line. Add `nomic-embed-code` (open-weights) as escape hatch at Phase 2.5. |
| Cursor caches embeddings cloud-side by chunk hash → 92% reuse across team. OneLens re-embeds per dev. | Phase 2: deterministic chunk hashing already done (`method:<fqn>`). Phase 4 candidate: shared embedding cache (S3/Turbopuffer-like) — separate plan. |
| scip-java has NO Spring annotation indexing | Don't promise scip-java path as Spring-aware. If/when we add SCIP fallback, write own Spring layer on top of raw SCIP relations. |
| Qodana floor = $40/dev/mo, min 10 devs ($4,800/yr) | Don't recommend Qodana for paying customers. Headless-Spring story = own bytecode scanner (Phase B, separate plan) or stay PSI+Ultimate-license-on-CI-runner. |
| `uv tool install` requires uv on box | install.sh handles it. Document fallback `pipx install onelens` for users who refuse curl-bash. |

## 10. Open questions

- **`install.sh` host:** GitHub raw vs `onelens.dev` domain? (Domain implies branding cost.)
- **Should `onelens onboard` auto-run `onelens index`?** Or stop at "ready to index"? Lean: stop, let user decide (full index can be 20 min).
- **Voyage / Cohere worth shipping at Phase 2** or just OpenAI first? Lean: OpenAI only, add others on demand.
- **Daemon as systemd unit** for power users? Lean: yes, optional, off by default.
- **License key for hosted Spring-aware mode** (future)? Out of scope for this plan.

## 11. References

### Internal
- `plugin/src/main/kotlin/com/onelens/plugin/export/PythonEnvManager.kt` — current bootstrap to extract
- `python/src/onelens/mcp_server.py` — MCP tool source of truth
- `python/scripts/regen_cli.sh` — CLI regeneration after MCP tool list changes
- `docs/DECISIONS.md` — ADR-001 to ADR-current — aligns with "MCP server = source of truth for CLI"

### External (research-validated, Apr 2026)
- **uv installer** — https://astral.sh/uv/install.sh, https://docs.astral.sh/uv/getting-started/installation/
- **uv tool install** vs pipx — https://docs.bswen.com/blog/2026-03-05-uvx-vs-pipx/
- **curl|sh security spectrum** — https://spin.atomicobject.com/security-spectrum-curl-sh/
- **Claude Code MCP scopes** — https://code.claude.com/docs/en/mcp, https://www.developersdigest.tech/guides/mcp-installation-scopes
- **Claude Code MCP idempotency** — https://github.com/anthropics/claude-code/issues/8288
- **Python keyring** — https://pypi.org/project/keyring/
- **gh CLI keyring failure modes** — https://github.com/cli/cli/issues/8954
- **aider dotenv pattern** — https://aider.chat/docs/config/dotenv.html
- **Cursor codebase indexing** — https://cursor.com/docs/context/codebase-indexing
- **OpenAI embedding pricing** — https://costgoat.com/pricing/openai-embeddings
- **voyage-code-3 (CoIR 77.33 SOTA)** — https://blog.voyageai.com/2024/12/04/voyage-code-3/
- **Qodana JVM Docker (Phase 5 reference)** — https://www.jetbrains.com/help/qodana/qodana-jvm-docker-readme.html
- **Qodana pricing ($40/dev/mo floor)** — https://www.jetbrains.com/help/qodana/pricing.html
- **scip-java repo (active, no Spring layer)** — https://github.com/sourcegraph/scip-java
