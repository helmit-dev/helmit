#!/usr/bin/env bash
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
SR_COMMAND="${1:-}"
SR_ROOT="$ROOT" "$PY_BIN" "$SELF_DIR/state-retain.py" "$@"
SR_RESULT=$?
if [ "$SR_RESULT" -eq 0 ] && [ "$SR_COMMAND" = "compact" ]; then
  CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
fi
exit "$SR_RESULT"
