#!/usr/bin/env bash
# HelmIt — run proof in an exact disposable Git tree.
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
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || {
  echo "error: proof-sandbox: no Python interpreter" >&2
  exit 2
}

ROOT="${PS_ROOT:-${CLAUDE_PROJECT_DIR:-$(pwd)}}"
PS_ROOT="$ROOT" "$PY_BIN" "$SELF_DIR/proof-sandbox.py" "$@"
