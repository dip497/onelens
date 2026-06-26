#!/usr/bin/env bash
#
# onelens-headless.sh — one-shot headless OneLens on a no-IDE Linux server.
#
# Runs the *entire* verified flow with no GUI, no Docker, and no sudo — every
# artifact lands under $HOME:
#
#   preflight  → check JDK / network / disk
#   engine     → install the Python CLI + embedded graph DB (falkordblite)
#   plugin     → unpack the IntelliJ plugin SOURCE (Gradle downloads IU itself)
#   license    → place + persist your IntelliJ Ultimate license (see KEY TRICK)
#   export     → headless PSI export (Java/Spring) or Vue/JS (see CONTENT ROOT)
#   import     → load the export JSON into a falkordblite graph
#   verify     → sanity Cypher query
#
# This is the HEADLESS path. For day-to-day local use you do NOT need any of
# this — install the IDE plugin and use Tools → OneLens → Sync Graph (auto-sync
# on save). See docs/headless.md → "Headless vs the IDE".
#
# ─────────────────────────────────────────────────────────────────────────────
# LICENSE KEY TRICK (the bit that isn't obvious)
#
#   The Gradle path downloads a *real* IntelliJ IDEA Ultimate and runs it
#   headless. IDEA's LicenseManager fires even headless — "No valid license
#   found" → exit 7, BEFORE the export starter runs. So a license MUST be
#   present in the gradle sandbox config dir:
#
#       <plugin>/build/idea-sandbox/IU-<ver>/config/idea.key
#
#   Provide it via ONELENS_LICENSE_KEY=/path/to/idea.key (your activated key,
#   e.g. ~/.config/JetBrains/IntelliJIdea2026.1/idea.key on a licensed box).
#   COPY IT YOURSELF onto the server — it is a credential; this script never
#   fetches it across hosts.
#
#   Gotcha: an *account-tied* (JBA) license is re-validated online and IDEA
#   INVALIDATES the copied key after a single session. So this script keeps a
#   backup (idea.key.bak) and RESTORES it into the sandbox before EVERY export.
#   An expired key fails the same way — use your currently-active key.
#
#   ToS: a single-seat license is single-concurrent-use. Don't run your desktop
#   IDE while a server export runs.
#
# ─────────────────────────────────────────────────────────────────────────────
# CONTENT ROOT (non-JVM / Vue / JS / future Python-Go)
#
#   A Maven/Gradle project gets source roots from its build import, so its files
#   are indexable and the collectors see them. A directory-opened npm/Vue
#   project has NO content root → the scanner reports "scanned N files; 0 for
#   indexing" → collectors emit a SILENT 0-node export. Fix: give the project a
#   minimal .idea declaring it a web module with src/ as a source root. This
#   script generates it automatically with --frontend.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (override via env or flags) ──────────────────────────────────────
ONELENS_HOME="${ONELENS_HOME:-$HOME/.onelens}"
VENV="$ONELENS_HOME/venv"
PLUGIN_DIR="${ONELENS_PLUGIN_DIR:-$HOME/onelens-plugin}"     # unpacked plugin source
SRC_DIR="${ONELENS_SRC_DIR:-$HOME/onelens-src}"              # unpacked python source
EXPORT_DIR="${ONELENS_EXPORT_DIR:-$HOME/onelens-exports}"
PLATFORM="${ONELENS_PLATFORM:-IU-2025.1.3}"                  # must match gradle.properties
JDK_HOME="${ONELENS_JDK:-/usr/local/java}"                   # JDK for the target project (17+)
ONELENS_LICENSE_KEY="${ONELENS_LICENSE_KEY:-}"              # path to your idea.key (you place it)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
die()  { echo -e "${RED}✗${NC} $1" >&2; exit 1; }

# ── preflight ───────────────────────────────────────────────────────────────
preflight() {
  echo "── preflight ──"
  "$JDK_HOME/bin/java" -version >/dev/null 2>&1 \
    && ok "project JDK: $("$JDK_HOME/bin/java" -version 2>&1 | head -1)" \
    || die "no JDK at $JDK_HOME (set ONELENS_JDK=/path/to/jdk17+). Build JDK 21 is auto-provisioned by Gradle foojay."
  command -v git >/dev/null && ok "git present" || warn "git missing (delta export needs it)"
  for h in services.gradle.org cache-redirector.jetbrains.com repo.maven.apache.org; do
    timeout 5 bash -c "echo > /dev/tcp/$h/443" 2>/dev/null \
      && ok "reachable: $h" || warn "UNREACHABLE: $h (downloads/dep-resolution may fail)"
  done
  local free; free=$(df -BG --output=avail "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
  [ "${free:-0}" -ge 10 ] && ok "disk: ${free}G free" || warn "low disk (${free:-?}G); IU+deps need several GB"
}

# ── engine: python CLI + falkordblite ───────────────────────────────────────
engine() {
  echo "── engine (python, base / no semantic extras) ──"
  if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="$HOME/.local/bin:$PATH"
  [ -x "$VENV/bin/python" ] || uv venv "$VENV" --python 3.12
  uv pip install --python "$VENV/bin/python" -e "$SRC_DIR" >/dev/null
  # Regenerate the CLI if the committed artifact is broken (see regen_cli.sh).
  if ! "$VENV/bin/python" -c "import ast,sys; ast.parse(open('$SRC_DIR/src/onelens/cli_generated.py').read())" 2>/dev/null; then
    warn "cli_generated.py invalid — regenerating"
    (cd "$SRC_DIR" && FASTMCP="$VENV/bin/fastmcp" bash scripts/regen_cli.sh >/dev/null)
  fi
  "$VENV/bin/onelens" --version >/dev/null && ok "onelens CLI: $("$VENV/bin/onelens" --version)"
}

# ── license: place key into sandbox + keep a restorable backup ──────────────
license() {
  local cfg="$PLUGIN_DIR/build/idea-sandbox/$PLATFORM/config"
  mkdir -p "$cfg"
  if [ -n "$ONELENS_LICENSE_KEY" ] && [ -f "$ONELENS_LICENSE_KEY" ]; then
    cp "$ONELENS_LICENSE_KEY" "$ONELENS_HOME/idea.key.bak"
    ok "license backed up from $ONELENS_LICENSE_KEY"
  fi
  [ -f "$ONELENS_HOME/idea.key.bak" ] || die "no license. Place your idea.key and set ONELENS_LICENSE_KEY=/path/to/idea.key (see KEY TRICK in header)."
  # Restore before EVERY export — JBA keys self-invalidate after one session.
  cp "$ONELENS_HOME/idea.key.bak" "$cfg/idea.key"
  ok "license restored into sandbox ($cfg/idea.key)"
}

# ── content root for non-JVM projects (Vue/JS/…) ────────────────────────────
gen_idea() {
  local proj="$1"
  [ -f "$proj/.idea/modules.xml" ] && { ok ".idea already present ($proj)"; return; }
  mkdir -p "$proj/.idea"
  cat > "$proj/.idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/onelens.iml" filepath="$PROJECT_DIR$/.idea/onelens.iml" />
    </modules>
  </component>
</project>
XML
  cat > "$proj/.idea/onelens.iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module type="WEB_MODULE" version="4">
  <component name="NewModuleRootManager" inherit-compiler-output="true">
    <exclude-output />
    <content url="file://$MODULE_DIR$/..">
      <sourceFolder url="file://$MODULE_DIR$/../src" isTestSource="false" />
      <excludeFolder url="file://$MODULE_DIR$/../node_modules" />
      <excludeFolder url="file://$MODULE_DIR$/../dist" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
  ok "generated .idea content root for $proj (src/ as source, node_modules excluded)"
}

# ── export: headless PSI export ─────────────────────────────────────────────
# usage: export_project <project-dir> [--frontend]
export_project() {
  local proj="$1"; shift || true
  [ -d "$proj" ] || die "project not found: $proj"
  [ "${1:-}" = "--frontend" ] && gen_idea "$proj"
  license
  echo "── export: $proj ──"
  ( cd "$PLUGIN_DIR"
    export JAVA_HOME="$JDK_HOME" PATH="$JDK_HOME/bin:$PATH"
    # Isolated system dir per project — the shared index cache contaminates
    # across projects ("0 files for indexing" on a 2nd run). See docs/headless.md.
    export ONELENS_SYSTEM_DIR="$ONELENS_HOME/sys-$(basename "$proj")"
    # Generous gates: big Maven projects index slowly; resolve can take a while.
    export ONELENS_INDEX_TIMEOUT_SEC="${ONELENS_INDEX_TIMEOUT_SEC:-1200}"
    export ONELENS_RESOLVE_TIMEOUT_SEC="${ONELENS_RESOLVE_TIMEOUT_SEC:-2400}"
    ./gradlew headlessExport \
      -PonelensProject="$proj" \
      -PonelensOutput="$EXPORT_DIR" \
      -PonelensXmx="${ONELENS_XMX:-6g}" --console=plain
  )
  local json; json=$(ls -t "$EXPORT_DIR"/*-full-*.json | head -1)
  ok "export written: $json ($(du -h "$json" | cut -f1))"
  echo "$json"
}

# ── import: JSON → falkordblite graph ───────────────────────────────────────
# usage: import_graph <export.json> <graph-name>
import_graph() {
  local json="$1" graph="$2"
  echo "── import: $graph ──"
  export ONELENS_FORCE_LOCAL_CLIENT=1
  # NOTE: onelens_init json.loads() the --export-path arg (anyOf schema), so the
  # path must be JSON-ENCODED — wrap in inner double-quotes. Same for any string
  # arg with a nullable/union schema.
  "$VENV/bin/onelens" call-tool onelens_init \
    --export-path "\"$json\"" --graph "$graph" --backend falkordblite
  ok "imported into graph '$graph'"
}

# ── verify ──────────────────────────────────────────────────────────────────
verify() {
  local graph="$1"
  export ONELENS_FORCE_LOCAL_CLIENT=1
  echo "── verify: $graph ──"
  "$VENV/bin/onelens" call-tool onelens_query \
    --cypher "MATCH (n) RETURN count(n) AS nodes" --graph "$graph" --backend falkordblite
}

usage() {
  cat <<EOF
onelens-headless.sh — headless OneLens on a no-IDE server

  $0 preflight
  $0 engine
  $0 all <project-dir> <graph-name> [--frontend]      # full flow
  $0 export <project-dir> [--frontend]
  $0 import <export.json> <graph-name>
  $0 verify <graph-name>

Backend (Maven/Spring):   $0 all /opt/myapp-server     myapp
Frontend (Vue/npm):       $0 all /opt/myapp-frontend   myapp-frontend --frontend

Required: ONELENS_LICENSE_KEY=/path/to/your/idea.key (you place the key on the
server — it is a credential). See the KEY TRICK section at the top of this file.
EOF
}

# ── dispatch ────────────────────────────────────────────────────────────────
cmd="${1:-}"; shift || true
case "$cmd" in
  preflight) preflight ;;
  engine)    engine ;;
  export)    export_project "$@" >/dev/null ;;
  import)    import_graph "$@" ;;
  verify)    verify "$@" ;;
  all)
    proj="${1:?project dir}"; graph="${2:?graph name}"; flag="${3:-}"
    preflight; engine
    json=$(export_project "$proj" $flag | tail -1)
    import_graph "$json" "$graph"
    verify "$graph"
    ok "DONE — query: onelens call-tool onelens_query --cypher '<cypher>' --graph $graph --backend falkordblite"
    ;;
  *) usage; [ -z "$cmd" ] && exit 0 || exit 1 ;;
esac
