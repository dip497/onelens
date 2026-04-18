#!/usr/bin/env bash
# OneLens static bundle — producer side
# Usage: ./bundle.sh <graph-name> [output-dir]
# Produces: <output-dir>/onelens-bundle-<graph>-<ts>.tgz
set -euo pipefail

GRAPH="${1:-}"
OUT_DIR="${2:-$PWD}"
CONTAINER="${ONELENS_FALKOR_CONTAINER:-falkordb}"
FALKOR_PORT="${ONELENS_FALKOR_PORT:-6379}"
ONELENS_HOME="${ONELENS_HOME:-$HOME/.onelens}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "$GRAPH" ]]; then
  echo "usage: $0 <graph-name> [output-dir]" >&2
  echo "available graphs:" >&2
  docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" GRAPH.LIST 2>&1 | sed 's/^/  /' >&2
  exit 1
fi

TS="$(date +%s)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
BUNDLE_DIR="$STAGE/onelens-bundle"
mkdir -p "$BUNDLE_DIR"

echo "[1/5] verify graph '$GRAPH' exists in falkor..."
if ! docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" GRAPH.LIST | grep -qx "$GRAPH"; then
  echo "error: graph '$GRAPH' not found in falkor" >&2
  exit 2
fi

echo "[2/5] BGSAVE + wait for RDB flush..."
docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" BGSAVE >/dev/null
LAST=0
for _ in $(seq 1 60); do
  STATUS="$(docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" LASTSAVE)"
  if [[ "$STATUS" != "$LAST" && "$LAST" != 0 ]]; then break; fi
  LAST="$STATUS"
  sleep 1
done
docker cp "$CONTAINER:/var/lib/falkordb/data/dump.rdb" "$BUNDLE_DIR/dump.rdb"
echo "    -> dump.rdb ($(du -h "$BUNDLE_DIR/dump.rdb" | cut -f1))"

echo "[3/5] pack chroma embeddings for '$GRAPH'..."
CHROMA_SRC="$ONELENS_HOME/context/$GRAPH"
if [[ ! -d "$CHROMA_SRC" ]]; then
  echo "warn: chroma dir missing at $CHROMA_SRC — skipping embeddings" >&2
else
  tar czf "$BUNDLE_DIR/chroma.tgz" -C "$ONELENS_HOME/context" "$GRAPH"
  echo "    -> chroma.tgz ($(du -h "$BUNDLE_DIR/chroma.tgz" | cut -f1))"
fi

echo "[4/5] build + stage onelens wheel..."
PYTHON_DIR="$REPO_ROOT/python"
if [[ -f "$PYTHON_DIR/pyproject.toml" ]]; then
  mkdir -p "$BUNDLE_DIR/wheel"
  python3 -m pip wheel --no-deps --wheel-dir "$BUNDLE_DIR/wheel" "$PYTHON_DIR" >/dev/null \
    || { echo "error: wheel build failed" >&2; exit 4; }
  WHL="$(ls "$BUNDLE_DIR/wheel"/onelens-*.whl | head -1)"
  echo "    -> $(basename "$WHL")"
else
  echo "warn: python/pyproject.toml missing — bundle won't be self-installable" >&2
fi

echo "[4b/5] copy skill..."
SKILL_SRC="$REPO_ROOT/skills/onelens/SKILL.md"
if [[ -f "$SKILL_SRC" ]]; then
  mkdir -p "$BUNDLE_DIR/skill"
  cp "$SKILL_SRC" "$BUNDLE_DIR/skill/SKILL.md"
  if [[ -d "$REPO_ROOT/skills/onelens/references" ]]; then
    cp -r "$REPO_ROOT/skills/onelens/references" "$BUNDLE_DIR/skill/"
  fi
else
  echo "warn: SKILL.md missing at $SKILL_SRC" >&2
fi

echo "[5/5] write manifest + archive..."
FALKOR_IMG="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")"
cat > "$BUNDLE_DIR/manifest.json" <<EOF
{
  "graph": "$GRAPH",
  "bundled_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "falkor_image": "$FALKOR_IMG",
  "producer": "$(whoami)@$(hostname)",
  "has_rdb": true,
  "has_chroma": $([[ -f "$BUNDLE_DIR/chroma.tgz" ]] && echo true || echo false),
  "has_skill": $([[ -f "$BUNDLE_DIR/skill/SKILL.md" ]] && echo true || echo false),
  "has_wheel": $([[ -d "$BUNDLE_DIR/wheel" ]] && echo true || echo false),
  "onelens_version": "$(grep '^version' "$REPO_ROOT/python/pyproject.toml" | head -1 | cut -d'"' -f2)"
}
EOF

OUT="$OUT_DIR/onelens-bundle-$GRAPH-$TS.tgz"
tar czf "$OUT" -C "$STAGE" onelens-bundle
echo ""
echo "bundle ready: $OUT ($(du -h "$OUT" | cut -f1))"
echo "ship this file + restore.sh to team."
