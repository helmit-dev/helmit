#!/usr/bin/env bash
# HelmIt — run-log: append-only work-in-flight log (REQ-088). Events include
# "map_shown" and "map_refreshed".
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/run-log.py" ] || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
RL_ROOT="$ROOT" RL_PID="${HELMIT_PID:-${PPID:-0}}" RL_SESSION="${HELMIT_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-${CLAUDE_SESSION_ID:-}}}}}" exec "$PY_BIN" "$SELF_DIR/run-log.py" "$@"
