#!/usr/bin/env bash
# HelmIt — roadmap-status: the ROADMAP status column gets a WRITER (REQ-265).
#
# Anchor: the ROADMAP template declares six status values — todo | spec |
# planned | implementing | validated | shipped — and the sweep of the six skills
# that touch the artifact found TWO writers: /spec creates the row as `todo` and
# /ship writes `shipped`. The four intermediate values had no writer at all, so
# the column the whole routing reads was maintained by hand. Measured in this
# repo on 2026-08-20: of 29 rows, 24 `shipped` and 5 `todo` — and phase 6, whose
# SPEC.md and CHART.md are both `approved` on disk, still said `todo`.
#
# The derivation reads the ARTIFACTS, never the `workflow:` field of STATE.md
# (REQ-266). That is not a style preference: the ROADMAP is the RECOVERY source
# for when that field is missing, and a deriver that consults the field it
# exists to replace recovers nothing. The circularity would only show up on the
# day of the accident.
#
# The derivation is MONOTONIC (REQ-267): it only ever moves a row FORWARD in the
# enum order. Deriving from zero would demote to `todo` every `shipped` row whose
# phase no longer has a directory under `phases/` — in this repo, phases 0 to 5 on
# the very first run. The single regression allowed is `validated` ->
# `implementing`, and only when the VALIDATION.md of that phase says
# `result: failed`: the artifact that granted the level is the same one taking it
# back, so the row is not being second-guessed by an absence.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   roadmap-status.sh [--dry-run] [--project <path>]
#   roadmap-status.sh mark <phase> <status> [--dry-run] [--project <path>]
# One line per cell changed; SILENT when nothing changes (REQ-204); atomic write
# (tmp + os.replace); always exit 0 — writing a ledger must never break the
# command that called it.
#
# `mark` writes the cell it is told to write, with no derivation, and it is the
# ONLY way `shipped` ever reaches the column: /ship calls it at the milestone.
# It refuses a phase with no row instead of inventing one — this hook writes a
# cell, never a roadmap.
#
# What it does NOT do, on purpose:
#   - it never touches the git INDEX: what the next commit says is the user's
#     act (REQ-112).
#   - it writes ONE cell, the last one: the rest of the row — anchor, requires,
#     covers, and the row ORDER, which is the user's priority — is never ours.
#   - it never derives `shipped`: there is no ship artifact on disk, and the row
#     is the only durable record of that fact, so a `shipped` row is left
#     byte-identical here.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
DRY=0
MODE=derive
MARK_PHASE=""
MARK_STATUS=""

# Subcommand first, like `yolo.sh arm`: what follows it are two operands, and
# whatever comes after them is parsed as flags by the same loop as always.
if [ "${1-}" = "mark" ]; then
  MODE=mark
  shift
  MARK_PHASE="${1-}"; [ $# -gt 0 ] && shift
  MARK_STATUS="${1-}"; [ $# -gt 0 ] && shift
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --project) shift; ROOT="${1:-$ROOT}" ;;
    --dry-run) DRY=1 ;;
    -h|--help)
      echo "usage: roadmap-status.sh [--dry-run] [--project <path>]"
      echo "       roadmap-status.sh mark <phase> <status> [--dry-run] [--project <path>]"
      exit 0 ;;
    *) echo "roadmap-status: unknown argument: $1" >&2; exit 0 ;;
  esac
  shift || true
done

if [ "$MODE" = mark ] && { [ -z "$MARK_PHASE" ] || [ -z "$MARK_STATUS" ]; }; then
  echo "roadmap-status: mark needs a phase and a status: mark <phase> <status>" >&2
  exit 0
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

RS_ROADMAP="$ROOT/.helmit/ROADMAP.md"
[ -f "$RS_ROADMAP" ] || exit 0

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
RS_ROOT="$ROOT" RS_ROADMAP="$RS_ROADMAP" RS_DRY="$DRY" \
RS_MODE="$MODE" RS_PHASE="$MARK_PHASE" RS_STATUS="$MARK_STATUS" \
  "$PY_BIN" "$SELF_DIR/roadmap-status.py" "$@"
RS_RESULT=$?
if [ "$RS_RESULT" -eq 0 ] && [ "$DRY" -eq 0 ]; then
  CLAUDE_PROJECT_DIR="$ROOT" bash "$SELF_DIR/dashboard.sh" publish --project "$ROOT" >/dev/null 2>&1 || true
fi
exit "$RS_RESULT"
