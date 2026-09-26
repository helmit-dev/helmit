#!/usr/bin/env bash
# HelmIt — handoff: derive and write the resume artifact (REQ-131–REQ-135).
# ORDER CONTRACT (REQ-149): append the typed stop FIRST; the narrative handoff is the session's LAST write.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SELF_DIR/handoff.py" ] || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: handoff ${1:-} SKIPPED — no python interpreter (python3/python/py) found." >&2
  exit 0
fi
HD_ROOT="$ROOT" HD_DIR="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/handoff.py" "$@"
