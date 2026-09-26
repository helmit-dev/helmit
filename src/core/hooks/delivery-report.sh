#!/usr/bin/env bash
# HelmIt — delivery-report: derive delivered tasks from the run log, task artifacts and Git.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/delivery-report.py" ] || exit 0

PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do
    command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }
  done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0

DR_ROOT="$ROOT" exec "$PY_BIN" "$SELF_DIR/delivery-report.py" "$@"
