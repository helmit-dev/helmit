#!/usr/bin/env bash
# HelmIt — context contract. A platform adapter calls this before it routes
# /next, heartbeat or YOLO, so a legacy opposite-harness file cannot silently
# impersonate the native session context. Pure read; exit 1 means no autonomy.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$(pwd)}}"
CMD="${1:-check}"
HARNESS="${2:-${HELMIT_HARNESS:-}}"

case "$CMD" in
  check)
    case "$HARNESS" in codex|claude-code) ;; *)
      echo "usage: context-contract.sh check <codex|claude-code>" >&2; exit 2 ;;
    esac ;;
  inspect)
    [ -n "${2:-}" ] || { echo "usage: context-contract.sh inspect <CLAUDE.md|AGENTS.md>" >&2; exit 2; }
    HARNESS="$2" ;;
  *) echo "usage: context-contract.sh {check <codex|claude-code>|inspect <CLAUDE.md|AGENTS.md>}" >&2; exit 2 ;;
esac

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
PY_BIN="${HELMIT_PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  for cand in python3 python py; do command -v "$cand" >/dev/null 2>&1 && { PY_BIN="$cand"; break; }; done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0
CC_ROOT="$ROOT" CC_SETUP="$SELF_DIR/../skills/setup/SKILL.md" \
  exec "$PY_BIN" "$SELF_DIR/context-contract.py" "$CMD" "$HARNESS"
