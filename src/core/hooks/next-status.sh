#!/usr/bin/env bash
# HelmIt — one compact, read-only routing snapshot for /next, handoff and board.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do
    command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "next-status: unavailable — no Python interpreter; inspect .helmit/STATE.md"
  exit 0
fi
NS_COMMAND="${1:-show}"
NS_ROOT="$ROOT" NS_HOOKS="$SELF_DIR" "$PY_BIN" "$SELF_DIR/next-status.py" "$@"
NS_RESULT=$?
if [ "$NS_RESULT" -eq 0 ] && [ "$NS_COMMAND" = "repair-state" ]; then
  CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
fi
exit "$NS_RESULT"
