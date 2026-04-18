#!/usr/bin/env bash
# OneLens static bundle — consumer side (multi-graph)
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

echo "[1/7] extract bundle..."
tar xzf "$BUNDLE" -C "$STAGE"
SRC="$STAGE/onelens-bundle"
[[ -d "$SRC" ]] || { echo "error: malformed bundle (no onelens-bundle/ dir)" >&2; exit 2; }
[[ -f "$SRC/manifest.json" ]] || { echo "error: missing manifest.json" >&2; exit 2; }

# parse manifest (supports schema v1 single-graph and v2 multi-graph)
read -r SCHEMA FALKOR_IMG GRAPHS_CSV CHROMA_CSV < <(python3 - "$SRC/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
schema = m.get("schema_version", 1)
if schema == 1:
    graphs = [m["graph"]]
    chroma = graphs if m.get("has_chroma") else []
else:
    graphs = m.get("graphs", [])
    chroma = m.get("chroma_graphs", [])
print(schema, m["falkor_image"], ",".join(graphs), ",".join(chroma))
PY
)
IFS=',' read -ra GRAPHS <<< "$GRAPHS_CSV"
IFS=',' read -ra CHROMA_GRAPHS <<< "${CHROMA_CSV:-}"

echo "    schema:        v$SCHEMA"
echo "    falkor image:  $FALKOR_IMG"
echo "    graphs:        ${GRAPHS[*]}"

echo ""
echo "!!! WARNING: restore overwrites ENTIRE falkor instance on container '$CONTAINER'."
echo "!!! All existing graphs on this falkor will be REPLACED by the bundle's RDB."
read -rp "continue? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "aborted."; exit 0; }

echo "[2/7] ensure falkor container exists..."
if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "    starting new container '$CONTAINER' from $FALKOR_IMG..."
  docker run -d --name "$CONTAINER" -p "$HOST_PORT:6379" -p 3001:3000 "$FALKOR_IMG" >/dev/null
  sleep 3
fi

echo "[3/7] stop falkor, load RDB, restart..."
docker stop "$CONTAINER" >/dev/null
docker cp "$SRC/dump.rdb" "$CONTAINER:/var/lib/falkordb/data/dump.rdb"
docker start "$CONTAINER" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" PING 2>/dev/null | grep -q PONG && break
  sleep 1
done

echo "[4/7] verify graphs loaded..."
LOADED="$(docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" GRAPH.LIST)"
for g in "${GRAPHS[@]}"; do
  if ! echo "$LOADED" | grep -qx "$g"; then
    echo "error: graph '$g' not found after RDB load" >&2
    exit 3
  fi
  echo "    ok: $g"
done

echo "[5/7] restore chroma embeddings..."
mkdir -p "$ONELENS_HOME/context"
if [[ "$SCHEMA" == "1" && -f "$SRC/chroma.tgz" ]]; then
  g="${GRAPHS[0]}"
  rm -rf "$ONELENS_HOME/context/$g"
  tar xzf "$SRC/chroma.tgz" -C "$ONELENS_HOME/context"
  echo "    -> $ONELENS_HOME/context/$g"
elif [[ -d "$SRC/chroma" ]]; then
  for g in "${CHROMA_GRAPHS[@]}"; do
    [[ -z "$g" ]] && continue
    tgz="$SRC/chroma/$g.tgz"
    if [[ ! -f "$tgz" ]]; then
      echo "    warn: missing $tgz — skip" >&2
      continue
    fi
    rm -rf "$ONELENS_HOME/context/$g"
    tar xzf "$tgz" -C "$ONELENS_HOME/context"
    echo "    -> $ONELENS_HOME/context/$g"
  done
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
  # Use the managed venv at ~/.onelens/venv — matches the plugin's
  # PythonEnvManager layout so both restore.sh and the IntelliJ plugin
  # target the same interpreter. A system-wide `pip install` was failing
  # on PEP 668 distros (Debian/Ubuntu 23.04+, Fedora 39+) with
  # "externally-managed-environment" — pip correctly refuses to write to
  # system site-packages there.
  VENV_DIR="$HOME/.onelens/venv"
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "    creating venv at $VENV_DIR"
    if command -v uv >/dev/null 2>&1; then
      uv venv "$VENV_DIR" >/dev/null
    else
      python3 -m venv "$VENV_DIR"
    fi
  fi
  echo "    installing ${WHL##*/}[context] into $VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade "${WHL}[context]"
  echo "    done — invoke as: $VENV_DIR/bin/onelens stats --graph <name>"
else
  echo "warn: no wheel in bundle — install onelens manually" >&2
fi

echo ""
echo "restore complete. verify:"
for g in "${GRAPHS[@]}"; do
  echo "  onelens stats --graph $g"
done
