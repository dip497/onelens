#!/usr/bin/env bash
# Install the OneLens skill into ~/.claude/skills/onelens/.
# Typical usage for end users:
#   curl -sSL http://<vm>:8766/onelens-skill-latest.tgz | tar -xzf - -C ~/.claude/skills/
# Or with this script:
#   ONELENS_SKILL_URL=http://<vm>:8766/onelens-skill-latest.tgz ./install-skill.sh

set -euo pipefail

URL="${ONELENS_SKILL_URL:-http://onelens.example.local:8766/onelens-skill-latest.tgz}"
DEST="${HOME}/.claude/skills"

mkdir -p "$DEST"

# Remove any prior install so stale reference files don't linger.
rm -rf "$DEST/onelens"

echo "Fetching $URL…"
curl -sSL --fail "$URL" | tar -xzf - -C "$DEST"

echo "Installed:"
find "$DEST/onelens" -maxdepth 2 -type f | sort
echo
echo "Ensure your ~/.claude/settings.json has the OneLens MCP server:"
cat <<'JSON'
{
  "mcpServers": {
    "onelens": {
      "type": "http",
      "url": "http://onelens.example.local:8765/mcp"
    }
  }
}
JSON
