#!/usr/bin/env bash
# HelmIt — inbox receipt: post-write structural receipt for INBOX.md edits.
# Reinforcement only: invalid or unreadable hook payloads never block a write.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
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

IR_INPUT=""
if [ "$#" -eq 0 ]; then
  IR_INPUT="$(cat 2>/dev/null || true)"
fi
export IR_INPUT IR_ROOT="$ROOT" IR_SANITY="$SELF_DIR/sanity.sh"
IR_COMMAND="${1:-post-write}"
"$PY_BIN" "$SELF_DIR/inbox-receipt.py" "$@"
IR_RESULT=$?
case "$IR_COMMAND" in
  post-write|maintain|archive)
    if [ "$IR_RESULT" -eq 0 ]; then
      CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
    fi
    ;;
esac
exit "$IR_RESULT"
