#!/usr/bin/env bash
# PreToolUse guard — refuses Write / Edit operations that introduce
# client-specific names into the repo. Keeps OneLens public-push ready
# at all times instead of relying on a grep sweep before release.
#
# Hook input on stdin is the JSON envelope Claude Code passes for a
# tool invocation:
#   { "tool": "Edit", "input": { "file_path": "...", "old_string": "...", "new_string": "..." } }
#   { "tool": "Write", "input": { "file_path": "...", "content": "..." } }
#
# We only care about the `file_path` and the content being written.
# If any configured forbidden pattern matches, we exit non-zero with a
# message on stderr — Claude Code surfaces that as a rejection.
#
# Forbidden list lives in `.claude/hooks/client-names.txt`. One pattern
# per line, `#` for comments, blank lines ignored. Patterns are
# case-insensitive substrings (not regex) so entries stay obvious.
# Widen the list any time a new client name shows up in review.

set -euo pipefail

FORBIDDEN_FILE="$(dirname "$0")/client-names.txt"
if [[ ! -f "$FORBIDDEN_FILE" ]]; then
  # No list configured = no-op (don't block legitimate edits on a broken setup).
  exit 0
fi

# Read the hook envelope from stdin.
payload="$(cat -)"

# Extract the tool name; skip anything other than Write / Edit variants.
tool="$(printf '%s' "$payload" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool",""))' 2>/dev/null || true)"
case "$tool" in
  Write|Edit|NotebookEdit) ;;
  *) exit 0 ;;
esac

# Pull file_path + payload content into separate variables. For Edit we check
# `new_string`; for Write we check `content`.
file_path="$(printf '%s' "$payload" | python3 -c '
import sys, json
data = json.load(sys.stdin)
print(data.get("input", {}).get("file_path", ""))
' 2>/dev/null || true)"

content="$(printf '%s' "$payload" | python3 -c '
import sys, json
data = json.load(sys.stdin)
inp = data.get("input", {})
# Concatenate every string field that represents content going into the file.
parts = []
for key in ("content", "new_string", "new_source"):
    v = inp.get(key)
    if isinstance(v, str):
        parts.append(v)
print("\n".join(parts))
' 2>/dev/null || true)"

# Nothing to scan (e.g. deletes, metadata-only edits) — allow.
if [[ -z "${content// /}" && -z "${file_path}" ]]; then
  exit 0
fi

# Scan line-by-line against each forbidden pattern. Bail at the first hit so
# the error message stays readable.
combined="${file_path}\n${content}"
while IFS= read -r pattern || [[ -n "$pattern" ]]; do
  # Skip comments and blanks.
  case "$pattern" in
    '' | '#'*) continue ;;
  esac
  if printf '%b' "$combined" | grep -qiF -- "$pattern"; then
    {
      echo "OneLens client-name guard: blocked."
      echo "Forbidden substring detected: '$pattern'"
      echo "File: ${file_path:-(stdin)}"
      echo "Rewrite references generically (e.g. 'a large Vue 3 repo',"
      echo "'the reference Java backend'). The full block list lives in"
      echo ".claude/hooks/client-names.txt — edit that file only if you"
      echo "intend to add or retire a block term."
    } >&2
    exit 2
  fi
done < "$FORBIDDEN_FILE"

exit 0
