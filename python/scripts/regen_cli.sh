#!/usr/bin/env bash
# Regenerate cli_generated.py from mcp_server.py and patch CLIENT_SPEC to
# in-process FastMCPTransport. fastmcp has no flag for this (confirmed against
# docs + repo); manual patch is the official pattern, so we automate it here.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=src/onelens/cli_generated.py

FASTMCP="${FASTMCP:-$HOME/.onelens/venv/bin/fastmcp}"
if [[ ! -x "$FASTMCP" ]]; then
  FASTMCP="$(command -v fastmcp || true)"
fi
[[ -n "$FASTMCP" ]] || { echo "fastmcp not found; set FASTMCP=/path/to/fastmcp" >&2; exit 1; }
export PATH="$(dirname "$FASTMCP"):$PATH"
"$FASTMCP" generate-cli src/onelens/mcp_server.py --output "$OUT" -f

python - <<'PY'
import pathlib, re
p = pathlib.Path("src/onelens/cli_generated.py")
src = p.read_text()
src = re.sub(
    r"from fastmcp\.client\.transports import StdioTransport\n",
    "",
    src,
)

# Inject `os`, `socket`, `Path` imports at the top alongside `import json`.
# generate-cli emits a small fixed import block; just rewrite it.
src = re.sub(
    r"^import json\nimport sys\n",
    "import json\nimport os\nimport socket\nimport sys\nfrom pathlib import Path\n",
    src,
    count=1,
    flags=re.MULTILINE,
)

# Replace the fastmcp-emitted CLIENT_SPEC stanza with our resolver block.
# generate-cli emits a comment line `# Modify this...` followed by
# `CLIENT_SPEC = StdioTransport(...)`. Swap that for the in-process fallback
# import + the per-call resolver helpers.
RESOLVER_BLOCK = """\
# In-process transport — fallback when no warm MCP daemon is reachable.
# When a daemon is up (plugin auto-spawn / `onelens daemon start` /
# `onelens mcp serve`), `_resolve_client_spec()` returns the HTTP URL of
# that daemon and the warm embedder + reranker get reused (~200 ms calls
# vs ~22-30 s cold load per invocation).
from onelens.mcp_server import mcp as _server

_PORT_FILE = Path.home() / ".onelens" / "mcp.port"


def _read_mcp_port() -> int | None:
    \"\"\"Read `~/.onelens/mcp.port`. Written by `mcp_server.py::_write_port_atomic`
    whenever the MCP server boots — regardless of who launched it.\"\"\"
    try:
        text = _PORT_FILE.read_text().strip()
        port = int(text)
    except (FileNotFoundError, ValueError, OSError):
        return None
    if not (1 <= port <= 65535):
        return None
    return port


def _probe_reachable(port: int, timeout: float = 0.2) -> bool:
    \"\"\"TCP connect probe, ~5 ms when up, hard-fail in `timeout` when down.\"\"\"
    try:
        with socket.create_connection((\"127.0.0.1\", port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_client_spec():
    \"\"\"Pick the right transport for this CLI invocation.

    Resolved per call (not at import) so a daemon started mid-session is
    picked up on the next invocation without restart. `Client(url_str)`
    auto-infers `StreamableHttpTransport` for `http://` URLs (FastMCP
    v2.3.0+ behavior); `Client(_server)` uses in-process `FastMCPTransport`.

    `ONELENS_FORCE_LOCAL_CLIENT=1` forces the in-process path even when
    a daemon is up — useful for cold-load benchmarks and air-gapped CI
    that must not touch the network stack.
    \"\"\"
    if os.environ.get(\"ONELENS_FORCE_LOCAL_CLIENT\") == \"1\":
        return _server
    port = _read_mcp_port()
    if port and _probe_reachable(port):
        return f\"http://127.0.0.1:{port}/mcp/\"
    return _server


# Backward-compat: kept for any external code that referenced this name.
# New callsites should call `_resolve_client_spec()` directly.
CLIENT_SPEC = _server"""

src = re.sub(
    r"^# Modify this.*\nCLIENT_SPEC = StdioTransport\([^\n]*\)",
    RESOLVER_BLOCK,
    src,
    flags=re.MULTILINE,
)

# Rewrite all `Client(CLIENT_SPEC)` callsites to use the per-call resolver.
src = src.replace("Client(CLIENT_SPEC)", "Client(_resolve_client_spec())")

# fastmcp generate-cli doesn't emit a `main` function — pyproject's
# `onelens = "onelens.cli_generated:main"` entry point needs it. Alias.
if "\nmain = app\n" not in src:
    src = src.rstrip() + "\n\nmain = app\n"

# Fail-loud invariants — if a future fastmcp release changes its emitted
# stanza shape, the regex above silently no-ops and we'd ship a CLI that
# still imports StdioTransport (cold-load-every-call regression). Verify
# every required transformation actually landed and exit non-zero
# otherwise so CI catches it before merge.
required_markers = [
    ("def _resolve_client_spec",
     "resolver helper missing — RESOLVER_BLOCK substitution didn't fire "
     "(fastmcp likely changed its CLIENT_SPEC emission stanza; update the "
     "regex above to match the new shape)"),
    ("Client(_resolve_client_spec())",
     "callsites still reference CLIENT_SPEC directly — replace step "
     "didn't fire on at least one Client(CLIENT_SPEC) occurrence"),
    ("from onelens.mcp_server import mcp as _server",
     "in-process fallback import missing"),
    ("import socket",
     "stdlib socket import missing — TCP probe in _probe_reachable would "
     "raise NameError at runtime"),
]
errors = [msg for marker, msg in required_markers if marker not in src]
if "Client(CLIENT_SPEC)" in src:
    errors.append(
        "Client(CLIENT_SPEC) still present — the str.replace() to "
        "_resolve_client_spec() didn't fire on every callsite"
    )
if "StdioTransport(" in src:
    errors.append(
        "StdioTransport(...) still present in output — fastmcp emission "
        "changed and the in-process patch didn't match"
    )
if errors:
    import sys
    sys.stderr.write("regen_cli.sh: post-generation patch FAILED:\n")
    for e in errors:
        sys.stderr.write(f"  - {e}\n")
    sys.exit(1)

p.write_text(src)
print(f"Patched {p}")
PY
