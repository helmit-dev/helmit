#!/usr/bin/env bash
# HelmIt — change: allocate and revalidate repository-wide CHG identities.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
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

export CHG_ROOT="$ROOT"
CHG_COMMAND="${1:-}"
"$PY_BIN" "$SELF_DIR/change.py" "$@"
CHG_RESULT=$?
case "$CHG_COMMAND" in
  allocate|open|expand-paths|recover)
    if [ "$CHG_RESULT" -eq 0 ]; then
      CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
    fi
    ;;
esac
exit "$CHG_RESULT"
