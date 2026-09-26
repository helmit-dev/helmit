#!/usr/bin/env bash
# HelmIt — session-start: relay a relevant handoff into session context (REQ-138).
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -d "$ROOT/.helmit" ] || exit 0
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/session-start.py" ] || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
HS_ROOT="$ROOT" HS_DIR="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/session-start.py" "$@"
