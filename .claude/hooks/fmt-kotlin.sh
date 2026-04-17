#!/usr/bin/env bash
# PostToolUse hook: trigger ktlint format on edited .kt / .kts files if ktlint is on PATH.
set -u
path=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
if [[ "$path" == *.kt || "$path" == *.kts ]] && [[ -f "$path" ]]; then
  if command -v ktlint >/dev/null 2>&1; then
    ktlint --format "$path" 2>/dev/null || true
  fi
fi
exit 0
