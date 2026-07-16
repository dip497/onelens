#!/usr/bin/env bash
#
# OneLens installer — sets up the Python CLI + builds the IntelliJ plugin
# for headless export. One command, zero manual steps.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   # or: bash install.sh
#
# What it does:
#   1. Installs the onelens Python package (pip or uv)
#   2. Builds the IntelliJ plugin ZIP (for headless export)
#   3. Starts FalkorDB (Docker) or falls back to embedded falkordblite
#   4. Verifies the installation with a smoke test
#
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        OneLens Installer                  ║"
echo "║  Code Knowledge Graph for Java + Vue 3   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Python CLI ──────────────────────────────────────────────
#
# Default = base install (NO semantic extras). The structural graph
# (impact / trace / query / search) works out of the box via embedded
# falkordblite, with zero external accounts. Semantic `retrieve` is opt-in:
#
#   ONELENS_WITH_CONTEXT=local  ./install.sh   # account-free ONNX embedder (~1GB, CPU-OK)
#   ONELENS_WITH_CONTEXT=modal  ./install.sh   # Modal-backed embedder (needs a Modal token)
#
# We deliberately do NOT pull `[context]` by default — it drags in the Modal
# client, which is useless without a Modal account and surprises self-hosted
# installs.
case "${ONELENS_WITH_CONTEXT:-}" in
    local) PKG="onelens[context-local]"; info "Semantic: local ONNX embedder (account-free)" ;;
    modal) PKG="onelens[context]";       info "Semantic: Modal backend (needs ONELENS token)" ;;
    "")    PKG="onelens";                 info "Base install (no semantic extras — set ONELENS_WITH_CONTEXT=local to add)" ;;
    *)     fail "ONELENS_WITH_CONTEXT must be 'local', 'modal', or unset (got '${ONELENS_WITH_CONTEXT}')" ;;
esac

if command -v uv &>/dev/null; then
    info "Found uv — installing $PKG via uv"
    uv tool install "$PKG" 2>/dev/null || uv pip install --system "$PKG"
elif command -v pip3 &>/dev/null; then
    info "Found pip — installing $PKG"
    pip3 install "$PKG"
elif command -v pip &>/dev/null; then
    info "Found pip — installing $PKG"
    pip install "$PKG"
else
    warn "No pip/uv found — installing uv first"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.local/bin/env" 2>/dev/null || true
    uv tool install "$PKG" || fail "Could not install onelens via uv"
fi

# Verify
if command -v onelens &>/dev/null; then
    info "onelens CLI installed: $(onelens --version 2>/dev/null || echo 'OK')"
else
    # Try the venv path (plugin installs there)
    if [ -x "$HOME/.onelens/venv/bin/onelens" ]; then
        export PATH="$HOME/.onelens/venv/bin:$PATH"
        info "onelens CLI at ~/.onelens/venv/bin/onelens"
    else
        warn "onelens CLI not on PATH — add ~/.local/bin or ~/.onelens/venv/bin to PATH"
    fi
fi

# ── 2. IntelliJ plugin (for headless export) ──────────────────

PLUGIN_DIR="${ONELENS_PLUGIN_DIR:-}"

if [ -z "$PLUGIN_DIR" ]; then
    # Try to find the git repo
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/plugin/build.gradle.kts" ]; then
        PLUGIN_DIR="$SCRIPT_DIR/plugin"
    elif [ -d "$HOME/.onelens/plugin" ]; then
        PLUGIN_DIR="$HOME/.onelens/plugin"
    fi
fi

if [ -n "$PLUGIN_DIR" ] && [ -f "$PLUGIN_DIR/build.gradle.kts" ]; then
    info "Building IntelliJ plugin at $PLUGIN_DIR..."
    (cd "$PLUGIN_DIR" && ./gradlew buildPlugin --console=plain -q 2>/dev/null) && \
        info "Plugin built: $(ls $PLUGIN_DIR/build/distributions/*.zip 2>/dev/null | head -1)" || \
        warn "Plugin build skipped (Gradle not available or network issue)"
else
    warn "Plugin source not found — headless export needs the plugin built from source."
    warn "Clone the repo and run: cd plugin && ./gradlew buildPlugin"
fi

# ── 3. FalkorDB ───────────────────────────────────────────────

if command -v docker &>/dev/null; then
    if ! docker ps --filter name=falkordb --format "{{.Names}}" | grep -q falkordb; then
        info "Starting FalkorDB container..."
        docker run -d --name falkordb -p 17532:6379 -p 3001:3000 falkordb/falkordb:latest >/dev/null 2>&1 && \
            info "FalkorDB running at localhost:17532 (browser: http://localhost:3001)" || \
            warn "Could not start FalkorDB — using embedded falkordblite instead"
    else
        info "FalkorDB already running"
    fi
else
    info "Docker not found — will use embedded falkordblite (no server needed)"
fi

# ── 4. Smoke test ─────────────────────────────────────────────

echo ""
if command -v onelens &>/dev/null || [ -x "$HOME/.onelens/venv/bin/onelens" ]; then
    ONELENS="${ONELENS:-onelens}"
    [ -x "$HOME/.onelens/venv/bin/onelens" ] && ONELENS="$HOME/.onelens/venv/bin/onelens"

    info "Running smoke test..."
    $ONELENS call-tool onelens_status --graph _smoke_test 2>/dev/null && \
        info "CLI is working" || warn "CLI smoke test failed (may need PATH setup)"
fi

# ── Done ──────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  OneLens is ready!                        ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  Sync a project:                         ║"
echo "║    onelens call-tool onelens_import \\   ║"
echo "║      --export-path <export.json> \\      ║"
echo "║      --graph myproject                  ║"
echo "║                                          ║"
echo "║  Headless export:                        ║"
echo "║    cd plugin && ./gradlew headlessExport \\║"
echo "║      -PonelensProject=/path/to/project   ║"
echo "║                                          ║"
echo "║  Query:                                  ║"
echo "║    onelens call-tool onelens_search \\   ║"
echo "║      --term 'UserService' --graph myproj ║"
echo "║                                          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
