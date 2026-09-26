#!/usr/bin/env bash
# HelmIt — local remote synchronization status. Reads Git refs; never fetches.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do
    command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  printf '%s\n' '{"available":false,"reason":"no-python","tracking":"local-ref"}'
  exit 0
fi

REMOTE_ROOT="$ROOT" exec "$PY_BIN" "$SELF_DIR/remote-status.py" "$@"
