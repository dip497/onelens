#!/usr/bin/env bash
# Bootstraps the OneLens MCP + skill static server on the target VM.
# Runs idempotently. Expects SNAP_TGZ, WHEEL, SKILL_TGZ in ~/onelens-drop/
# (scp'd by the deploy script from the operator's laptop).

set -euo pipefail

HOME_DIR="/home/$USER"
DROP="$HOME_DIR/onelens-drop"
VENV="$HOME_DIR/.onelens/venv"
BUNDLES="$HOME_DIR/.onelens/bundles"
STATIC_DIR="$HOME_DIR/onelens-static"

mkdir -p "$HOME_DIR/.onelens/graphs" "$BUNDLES" "$STATIC_DIR"

# 1. uv (if missing)
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME_DIR/.local/bin:$PATH"
fi
hash -r

# 2. venv + onelens install
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV" --python 3.12
fi
# uv venv omits pip — use uv pip for installs.
VIRTUAL_ENV="$VENV" uv pip install --upgrade "$DROP"/onelens-*.whl >/dev/null

# 3. Drop snapshot bundle + skill bundle where they belong
cp -v "$DROP"/onelens-snapshot-*.tgz "$BUNDLES"/
cp -v "$DROP"/onelens-snapshot-*.tgz.sha256 "$BUNDLES"/ 2>/dev/null || true
cp -v "$DROP"/onelens-skill-latest.tgz "$STATIC_DIR"/
cp -v "$DROP"/install-skill.sh "$STATIC_DIR"/ 2>/dev/null || true

# 4. Pull + promote the snapshot so live graph = @tag state
GRAPH=$(ls "$BUNDLES"/onelens-snapshot-*.tgz | head -1 \
        | sed -E 's|.*onelens-snapshot-(.*)-[^-]+\.tgz|\1|')
TAG=$(ls "$BUNDLES"/onelens-snapshot-*.tgz | head -1 \
      | sed -E 's|.*onelens-snapshot-.*-([^-]+)\.tgz|\1|')
echo "Detected: graph=$GRAPH tag=$TAG"

"$VENV/bin/onelens" call-tool onelens_snapshots_pull \
  --graph "$GRAPH" --tag "$TAG" --repo local >/dev/null
"$VENV/bin/onelens" call-tool onelens_snapshot_promote \
  --graph "$GRAPH" --tag "$TAG" \
  --commit-sha '"67d687514f798faaf809eeec4e48ab8acf28fb58"' | tail -5

# 5. Verify live graph works
echo "--- onelens_status ---"
"$VENV/bin/onelens" call-tool onelens_status --graph "$GRAPH" | \
  python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); print("nodes:", d.get("total_nodes"), "edges:", d.get("total_edges"))'

echo
echo "Bootstrap complete. Next:"
echo "  1. sudo systemctl enable --now onelens-mcp.service"
echo "  2. sudo systemctl enable --now onelens-skill-static.service"
echo "  (Unit files land via separate sudo step.)"
