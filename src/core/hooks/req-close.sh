#!/usr/bin/env bash
# HelmIt — req-close: close a numbered phase after its full-suite proof.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   req-close.sh --phase <id> [--dry-run] [--project <path>]
# Explicit phase closure is a ship gate and exits 2 when deterministic proof is
# incomplete.
#
# What it does NOT do, on purpose:
#   - it never touches the git INDEX (no `git add` inside anybody's commit): the
#     index decides what the user's next commit says, and that is their act
#     (REQ-112). The column is correct at most ONE pass later, and always in the
#     conservative direction — `todo` while already proven, never the reverse.
#   - it promotes only after every planned task is complete and a matching
#     full-suite receipt covers the candidate.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
DRY=0
PHASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --project) shift; ROOT="${1:-$ROOT}" ;;
    --phase) shift; PHASE="${1:-}" ;;
    --dry-run) DRY=1 ;;
    -h|--help)
      echo "usage: req-close.sh --phase <id> [--dry-run] [--project <path>]"; exit 0 ;;
    *) echo "req-close: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift || true
done

if [ -z "$PHASE" ]; then
  echo "req-close: --phase is required" >&2
  exit 2
fi

PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0

RC_REQS="$ROOT/.helmit/REQUIREMENTS.md"
[ -f "$RC_REQS" ] || exit 0

# The commit messages are the evidence. Read them once here.
RC_LOG="$(git -C "$ROOT" log --format='%h%x1f%B%x1e' 2>/dev/null || true)"

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
RC_MATCH=0
if QR_ROOT="$ROOT" bash "$SELF_DIR/quality-receipt.sh" match >/dev/null 2>&1; then
  RC_MATCH=1
fi

RC_ROOT="$ROOT" RC_REQS="$RC_REQS" RC_DRY="$DRY" RC_LOG="$RC_LOG" RC_PHASE="$PHASE" RC_MATCH="$RC_MATCH" \
  "$PY_BIN" "$SELF_DIR/req-close.py" "$@"
RC_RESULT=$?
if [ "$RC_RESULT" -eq 0 ] && [ "$DRY" -eq 0 ]; then
  IR_ROOT="$ROOT" IR_SANITY="$SELF_DIR/sanity.sh" \
    "$PY_BIN" "$SELF_DIR/inbox-receipt.py" archive
  CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
fi
exit "$RC_RESULT"
