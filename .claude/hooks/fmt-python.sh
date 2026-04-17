#!/usr/bin/env bash
set -u
path=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
if [[ "$path" == *.py && -f "$path" ]]; then
  if command -v ruff >/dev/null 2>&1; then
    ruff format "$path" 2>/dev/null || true
    ruff check --fix-only "$path" 2>/dev/null || true
  fi
fi
exit 0
