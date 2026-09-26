#!/usr/bin/env bash
# Resolve a HelmIt skill from the active Codex plugin cache.  This is advisory:
# Codex owns the locator it placed in an already-open task.
set -u

name="${1:-}"
advertised="${2:-}"
[ -n "$name" ] || { echo "usage: resolve-skill.sh <skill> [advertised-path]" >&2; exit 2; }

cache="${CODEX_HOME:-$HOME/.codex}/plugins/cache/helmit/helmit"
best=""
if [ -d "$cache" ]; then
  while IFS= read -r candidate; do
    best="$candidate"
  done < <(find "$cache" -path "*/core/skills/$name/SKILL.md" -type f 2>/dev/null | sort)
fi

[ -n "$best" ] || { echo "codex-skill: no active HelmIt skill '$name' found; refresh the plugin or start a new task." >&2; exit 3; }
if [ -n "$advertised" ] && [ "$advertised" != "$best" ]; then
  echo "codex-skill: stale locator '$advertised'; using active '$best'" >&2
fi
printf '%s\n' "$best"
