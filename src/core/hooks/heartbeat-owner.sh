#!/usr/bin/env bash
# HelmIt — heartbeat owner: records and verifies Codex automation ownership.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
HO_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}" exec "$PY_BIN" "$SELF_DIR/heartbeat-owner.py" "$@"
