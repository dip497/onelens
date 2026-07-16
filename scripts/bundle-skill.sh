#!/usr/bin/env bash
# Bundle the OneLens skill as a shareable tarball.
# Usage: ./scripts/bundle-skill.sh [output-dir]
#   Default output-dir: ./build/

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/build}"
mkdir -p "$OUT_DIR"

STAMP=$(date -u +%Y%m%d-%H%M%S)
BUNDLE="$OUT_DIR/onelens-skill-${STAMP}.tgz"
LATEST="$OUT_DIR/onelens-skill-latest.tgz"

cd "$ROOT/skills"
if [ ! -d onelens ]; then
  echo "error: skills/onelens/ not found at $ROOT/skills" >&2
  exit 1
fi

tar --exclude='*.pyc' --exclude='__pycache__' \
    -czf "$BUNDLE" onelens/

# Overwrite "latest" pointer. Devs curl-install from this URL.
cp "$BUNDLE" "$LATEST"

echo "Bundle:    $BUNDLE"
echo "Latest ->  $LATEST"
echo
echo "Contents:"
tar -tzf "$BUNDLE" | head -15
echo "  (…$(tar -tzf "$BUNDLE" | wc -l) entries total)"
