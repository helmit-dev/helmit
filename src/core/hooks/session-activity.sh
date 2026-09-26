#!/usr/bin/env bash
# HelmIt — short-lived evidence of host activity in this checkout, not task ownership.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -d "$ROOT/.helmit" ] || exit 0
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
SA_ROOT="$ROOT" SA_HOOKS="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/session-activity.py" "$@"
