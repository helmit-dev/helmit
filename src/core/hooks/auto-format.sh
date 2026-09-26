#!/usr/bin/env bash
# HelmIt auto-format — PostToolUse hook. Formatting is NEVER a gate: this
# script always exits 0 (a formatter problem must not block the agent).
# Runs the project's format command after a file edit, while keeping `.helmit/`
# out of a project-wide formatter's reach (REQ-102).

set -u

# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Interpreter resolver: HELMIT_PYTHON (verbatim; also the test hook) wins,
# else the first of python3/python/py on PATH.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi

# Formatting is never a gate: with no interpreter, exit silently (no noise).
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0

# The body receives the original hook payload through this exported contract.
AF_INPUT="$(cat 2>/dev/null || true)"
export AF_INPUT

exec "$PY_BIN" "$SELF_DIR/auto-format.py" "$@"
