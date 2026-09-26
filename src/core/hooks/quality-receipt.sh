#!/usr/bin/env bash
# HelmIt — quality receipt: record and match proof against a product snapshot.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0

ROOT="${QR_ROOT:-${CLAUDE_PROJECT_DIR:-$(pwd)}}"
QR_COMMAND="${1:-}"
QR_ROOT="$ROOT" "$PY_BIN" "$SELF_DIR/quality-receipt.py" "$@"
QR_RESULT=$?
case "$QR_COMMAND" in
  record|integration|ship|validate)
    if [ "$QR_RESULT" -eq 0 ]; then
      CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
    fi
    ;;
esac
exit "$QR_RESULT"
