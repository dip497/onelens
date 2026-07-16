#!/usr/bin/env bash
# Regenerate onelens-palace CLI from the Palace MCP server.
# Post-processes the fastmcp 3.x output to:
#   1. Flatten tool commands from `call-tool` subcommand to top-level (match existing onelens CLI UX).
#   2. Rewrite app name/help to `onelens-palace`.
#   3. Pin the fastmcp stdio command to the venv binary (PATH-robust).
#
# Usage: bash scripts/regenerate-palace-cli.sh
# Prerequisite: activated or discoverable ~/.onelens/venv with `fastmcp` installed.

set -euo pipefail

VENV="${ONELENS_VENV:-$HOME/.onelens/venv}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_DIR="$REPO_ROOT/python"
OUT="$PY_DIR/src/onelens/palace/cli_palace_generated.py"

PATH="$VENV/bin:$PATH" "$VENV/bin/fastmcp" generate-cli \
  "$PY_DIR/src/onelens/palace/server.py" \
  --output "$OUT" --force --no-skill

# Flatten subcommand and rename app
sed -i 's|@call_tool_app\.command|@app.command|g' "$OUT"
sed -i 's|^app\.command(call_tool_app)$|# app.command(call_tool_app)  # flattened: tools are top-level|' "$OUT"
sed -i 's|cyclopts.App(name="server", help="CLI for server MCP server")|cyclopts.App(name="onelens-palace", help="OneLens Palace - MemPalace-shaped memory and facts over the code graph")|' "$OUT"

# Pin fastmcp transport to the venv binary so the CLI works under any PATH
sed -i "s|StdioTransport(command='fastmcp'|StdioTransport(command='$VENV/bin/fastmcp'|" "$OUT"

echo "OK  $(basename "$OUT") regenerated; 19 tools top-level; fastmcp pinned to $VENV/bin/fastmcp"
