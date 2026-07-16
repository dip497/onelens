#!/usr/bin/env bash
# OneLens static bundle — producer side (multi-graph)
# Usage: ./bundle.sh <graph1> [graph2 ...] [--out <dir>]
#        ./bundle.sh --all [--out <dir>]
# Produces: <out-dir>/onelens-bundle-<ts>.tgz
set -euo pipefail

CONTAINER="${ONELENS_FALKOR_CONTAINER:-falkordb}"
FALKOR_PORT="${ONELENS_FALKOR_PORT:-6379}"
ONELENS_HOME="${ONELENS_HOME:-$HOME/.onelens}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OUT_DIR="$PWD"
ALL=0
GRAPHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    --out) OUT_DIR="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 <graph1> [graph2 ...] [--out <dir>]"
      echo "       $0 --all [--out <dir>]"
      exit 0 ;;
    *) GRAPHS+=("$1"); shift ;;
  esac
done

LIST_RAW="$(docker exec "$CONTAINER" redis-cli -p "$FALKOR_PORT" GRAPH.LIST)"
mapfile -t AVAILABLE < <(echo "$LIST_RAW")

if [[ $ALL -eq 1 ]]; then
  GRAPHS=("${AVAILABLE[@]}")
fi

if [[ ${#GRAPHS[@]} -eq 0 ]]; then
  echo "usage: $0 <graph1> [graph2 ...] | --all [--out <dir>]" >&2
  echo "available graphs:" >&2
  printf '  %s\n' "${AVAILABLE[@]}" >&2
  exit 1
fi

# verify all requested graphs exist
for g in "${GRAPHS[@]}"; do
  found=0
  for a in "${AVAILABLE[@]}"; do [[ "$a" == "$g" ]] && found=1 && break; done
  if [[ $found -eq 0 ]]; then
    echo "error: graph '$g' not found in falkor" >&2
    echo "available:" >&2
    printf '  %s\n' "${AVAILABLE[@]}" >&2
    exit 2
  fi
done

TS="$(date +%s)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
BUNDLE_DIR="$STAGE/onelens-bundle"
mkdir -p "$BUNDLE_DIR"

echo "[1/5] graphs to bundle: ${GRAPHS[*]}"

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

echo "[3/5] pack chroma embeddings per graph..."
mkdir -p "$BUNDLE_DIR/chroma"
CHROMA_GRAPHS=()
for g in "${GRAPHS[@]}"; do
  src="$ONELENS_HOME/context/$g"
  if [[ ! -d "$src" ]]; then
    echo "    warn: chroma dir missing for '$g' at $src — skipping" >&2
    continue
  fi
  tar czf "$BUNDLE_DIR/chroma/$g.tgz" -C "$ONELENS_HOME/context" "$g"
  echo "    -> chroma/$g.tgz ($(du -h "$BUNDLE_DIR/chroma/$g.tgz" | cut -f1))"
  CHROMA_GRAPHS+=("$g")
done

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
GRAPHS_JSON="$(printf '"%s",' "${GRAPHS[@]}" | sed 's/,$//')"
CHROMA_JSON="$(printf '"%s",' "${CHROMA_GRAPHS[@]}" | sed 's/,$//')"
cat > "$BUNDLE_DIR/manifest.json" <<EOF
{
  "schema_version": 2,
  "graphs": [${GRAPHS_JSON}],
  "chroma_graphs": [${CHROMA_JSON}],
  "bundled_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "falkor_image": "$FALKOR_IMG",
  "producer": "$(whoami)@$(hostname)",
  "has_rdb": true,
  "has_skill": $([[ -f "$BUNDLE_DIR/skill/SKILL.md" ]] && echo true || echo false),
  "has_wheel": $([[ -d "$BUNDLE_DIR/wheel" ]] && echo true || echo false),
  "onelens_version": "$(grep '^version' "$REPO_ROOT/python/pyproject.toml" | head -1 | cut -d'"' -f2)"
}
EOF

if [[ ${#GRAPHS[@]} -eq 1 ]]; then
  OUT="$OUT_DIR/onelens-bundle-${GRAPHS[0]}-$TS.tgz"
else
  OUT="$OUT_DIR/onelens-bundle-multi-$TS.tgz"
fi
tar czf "$OUT" -C "$STAGE" onelens-bundle
echo ""
echo "bundle ready: $OUT ($(du -h "$OUT" | cut -f1))"
echo "graphs: ${GRAPHS[*]}"
echo "ship this file + restore.sh to team."
