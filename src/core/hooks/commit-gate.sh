#!/usr/bin/env bash
# HelmIt commit gate — layer 1 of the layered defense (PreToolUse hook).
#
# The shell owns only the runtime boundary mandated by ADR-014: resolve Python
# at invocation time and fail open, loudly, when it is absent. The gate policy
# and all observable decisions live in the sibling Python body.
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

if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt gate SKIPPED — no python interpreter (python3/python/py) found. Install python3 to enable the commit gate." >&2
  exit 0
fi

export CG_SELF_DIR="$SELF_DIR"
exec "$PY_BIN" "$SELF_DIR/commit-gate.py" "$@"
