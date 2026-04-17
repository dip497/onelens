#!/usr/bin/env bash
# Stop hook — remind to update CHANGELOG.md when source code has changed
# but CHANGELOG.md has not. Runs on session stop. Never blocks.
set -u
if ! command -v git >/dev/null 2>&1; then exit 0; fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then exit 0; fi
changed=$(git status --porcelain 2>/dev/null | awk '{print $2}')
if echo "$changed" | grep -qE '^(python/src|plugin/src|skills/)' \
   && ! echo "$changed" | grep -q '^CHANGELOG\.md$'; then
  cat >&2 <<EOF
NOTE: source files changed in this session but CHANGELOG.md is not
      modified. If this is a user-visible change, add an entry under
      [Unreleased] in CHANGELOG.md.
EOF
fi
exit 0
