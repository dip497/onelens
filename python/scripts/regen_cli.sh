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
src = re.sub(
    r"^# Modify this.*\nCLIENT_SPEC = StdioTransport\([^\n]*\)",
    "# In-process transport — no subprocess, no PATH dependency on `fastmcp` binary.\n"
    "from onelens.mcp_server import mcp as _server\n"
    "CLIENT_SPEC = _server",
    src,
    flags=re.MULTILINE,
)
# fastmcp generate-cli doesn't emit a `main` function — pyproject's
# `onelens = "onelens.cli_generated:main"` entry point needs it. Alias.
if "\nmain = app\n" not in src:
    src = src.rstrip() + "\n\nmain = app\n"
p.write_text(src)
print(f"Patched {p}")
PY
