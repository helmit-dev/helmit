#!/usr/bin/env bash
# HelmIt — executor lease: records fresh interactive activity for an open task claim.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
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

LEASE_ROOT="$ROOT" LEASE_HOOKS="$SELF_DIR" \
  exec "$PY_BIN" "$SELF_DIR/executor-lease.py" "$@"
