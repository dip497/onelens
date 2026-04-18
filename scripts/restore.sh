#!/usr/bin/env bash
# OneLens static bundle — consumer side
# Usage: ./restore.sh <bundle.tgz>
# Prereqs: docker, python3 + pip (onelens wheel ships inside bundle)
set -euo pipefail

BUNDLE="${1:-}"
CONTAINER="${ONELENS_FALKOR_CONTAINER:-falkordb}"
HOST_PORT="${ONELENS_FALKOR_HOST_PORT:-17532}"
FALKOR_PORT="${ONELENS_FALKOR_PORT:-6379}"
ONELENS_HOME="${ONELENS_HOME:-$HOME/.onelens}"
SKILL_HOME="${ONELENS_SKILL_HOME:-$HOME/.claude/skills/onelens}"

if [[ -z "$BUNDLE" || ! -f "$BUNDLE" ]]; then
  echo "usage: $0 <bundle.tgz>" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "[1/6] extract bundle..."
tar xzf "$BUNDLE" -C "$STAGE"
SRC="$STAGE/onelens-bundle"
[[ -d "$SRC" ]] || { echo "error: malformed bundle (no onelens-bundle/ dir)" >&2; exit 2; }
[[ -f "$SRC/manifest.json" ]] || { echo "error: missing manifest.json" >&2; exit 2; }

GRAPH="$(python3 -c "import json; print(json.load(open('$SRC/manifest.json'))['graph'])")"
FALKOR_IMG="$(python3 -c "import json; print(json.load(open('$SRC/manifest.json'))['falkor_image'])")"
echo "    graph:         $GRAPH"
echo "    falkor image:  $FALKOR_IMG"

echo ""
echo "!!! WARNING: restore overwrites ENTIRE falkor instance on container '$CONTAINER'."
echo "!!! All existing graphs on this falkor will be REPLACED by the bundle."
read -rp "continue? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "aborted."; exit 0; }

echo "[2/6] ensure falkor container exists..."
if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "    starting new container '$CONTAINER' from $FALKOR_IMG..."
  docker run -d --name "$CONTAINER" -p "$HOST_PORT:6379" -p 3001:3000 "$FALKOR_IMG" >/dev/null
  sleep 3
fi

echo "[3/6] stop falkor, load RDB, restart..."
docker stop "$CONTAINER" >/dev/null
docker cp "$SRC/dump.rdb" "$CONTAINER:/var/lib/falkordb/data/dump.rdb"
docker start "$CONTAINER" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" PING 2>/dev/null | grep -q PONG && break
  sleep 1
done

echo "[4/6] verify graph loaded..."
if ! docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" GRAPH.LIST | grep -qx "$GRAPH"; then
  echo "error: graph '$GRAPH' not found after RDB load" >&2
  exit 3
fi

echo "[5/6] restore chroma embeddings..."
if [[ -f "$SRC/chroma.tgz" ]]; then
  mkdir -p "$ONELENS_HOME/context"
  rm -rf "$ONELENS_HOME/context/$GRAPH"
  tar xzf "$SRC/chroma.tgz" -C "$ONELENS_HOME/context"
  echo "    -> $ONELENS_HOME/context/$GRAPH"
else
  echo "    (no chroma in bundle — semantic search will be empty)"
fi

echo "[6/7] install skill..."
if [[ -f "$SRC/skill/SKILL.md" ]]; then
  mkdir -p "$SKILL_HOME"
  cp "$SRC/skill/SKILL.md" "$SKILL_HOME/"
  [[ -d "$SRC/skill/references" ]] && cp -r "$SRC/skill/references" "$SKILL_HOME/"
  echo "    -> $SKILL_HOME"
else
  echo "    (no skill in bundle — skip)"
fi

echo "[7/7] install onelens wheel..."
WHL="$(ls "$SRC"/wheel/onelens-*.whl 2>/dev/null | head -1 || true)"
if [[ -n "$WHL" ]]; then
  if command -v onelens >/dev/null 2>&1; then
    echo "    onelens already on PATH — upgrading from bundled wheel"
    python3 -m pip install --upgrade "${WHL}[context]"
  else
    echo "    installing ${WHL##*/}[context] (user site)"
    python3 -m pip install --user "${WHL}[context]"
    echo "    NOTE: ensure ~/.local/bin is on PATH"
  fi
else
  echo "warn: no wheel in bundle — install onelens manually" >&2
fi

echo ""
echo "restore complete. verify:"
echo "  onelens stats --graph $GRAPH"
echo "  onelens retrieve --query 'auth flow' --graph $GRAPH"
