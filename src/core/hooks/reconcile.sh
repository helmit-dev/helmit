#!/usr/bin/env bash
# HelmIt — reconcile: decide how to resume in-flight work (REQ-089/REQ-090).
set -u
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/reconcile.py" ] || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || { echo FORWARD; echo "python3 missing — reconcile is a no-op (fail-open on read)"; exit 0; }
RC_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}" RC_HOOKS="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/reconcile.py" "$@"
