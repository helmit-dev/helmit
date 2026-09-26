#!/usr/bin/env bash
# HelmIt — sanity: structural verifier for the .helmit/ artifacts (phase 18,
# REQ-145; guards REQ-144's field-comment budget and REQ-201's table shape).
#
# Why this exists: the commit gate runs test/build/lint over CODE, so a
# structurally destroyed .helmit/ (hundreds of lines inserted mid-sentence,
# dozens of duplicated items, two `## Backlog` headers) sails through green.
# Nothing looked at the SHAPE of the artifacts the handoff derives from —
# this hook is that look.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   sanity.sh check   (default) examine the project's .helmit/ artifacts and
#                     print STRUCTURAL findings, one per line, as
#                       <file>:<line>: <description>
#                     Exit 0 ALWAYS — it warns, it never gates (same
#                     philosophy as the handoff size warning). No finding:
#                     stdout EMPTY, absolute silence (REQ-108).
#   sanity.sh summary print only total findings grouped by artifact. This is
#                     the bounded read used by /next; it never hides the full
#                     `check` required immediately after structured writes.
#
# v1 detections (CLOSED list, decided at the spec gate):
#   a. duplicated canonical header — in INBOX.md, `## Inbox` / `## Backlog` /
#      `## Closed` appearing more than once (whole-line match).
#   b. exact duplicated item — in INBOX.md, byte-identical `- [ ]`/`- [x]`
#      lines appearing 2+ times (the second occurrence onward is reported).
#   c. canonical section order and presence — INBOX.md contains Inbox ->
#      Backlog -> Closed, exactly once each.
#   d. item grammar/destination — every checkbox belongs to one canonical
#      section and uses that section's template grammar.
#   e. field HTML comment over 10 lines — in STATE.md, a `<!-- ... -->`
#      opened on the same line as a `- <name>: <value>` field and closing
#      MORE than 10 lines later (counted from the field line to the `-->`
#      line, inclusive) is a finding naming the field; exactly 10 is silence.
#
# AMENDED ONCE, on purpose (REQ-201, user's triage of 2026-08-15): the list was
# closed against scope creep, not against evidence. A manual promotion wrote a
# DOUBLED PIPE into a REQ row (`| 21 || proven |`), the `phase` cell came out
# empty, and the board reported "0 of 0 proven" with five proven REQs sitting in
# the table — damage of exactly the shape this hook exists to see, in the two
# files the whole traceability chain hangs from. So the list gains one item:
#   f. broken anchor cell in a REQUIREMENTS.md / ROADMAP.md data row. The row is
#      read FROM THE ENDS — id in the FIRST cell, phase (REQUIREMENTS) or covers
#      (ROADMAP) in the PENULTIMATE, status in the LAST — the same indexing the
#      board's `parse_requirements` already does. A finding is raised when an
#      anchor cell is EMPTY, or when `status` falls outside its enum
#      (REQUIREMENTS: todo | covered | proven | retired; ROADMAP: todo | spec | planned |
#      implementing | validated | shipped).
#      Counting cells is FORBIDDEN here, not merely avoided: 7 legitimate rows of
#      this repo's REQUIREMENTS.md carry a pipe inside the prose (`off | phase |
#      full`), so a count-based guard would flag correct rows and be switched off
#      in its first week (REQ-108). Reading from the ends is immune to it,
#      because a pipe in the prose only ever grows the MIDDLE.
#
# PURE READ (REQ-091): writes nothing, mutates no mtime under .helmit/, and
# two consecutive runs over unchanged inputs are byte-identical.
# Fail-open: a missing artifact (INBOX.md, STATE.md, REQUIREMENTS.md,
# ROADMAP.md) is silence; a missing .helmit/ gets one stderr note. Exit 0 on
# every path except usage errors (exit 2).
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

usage() {
  echo "usage: sanity.sh [check|summary]" >&2
  exit 2
}

CMD="${1:-check}"
case "$CMD" in check|summary) ;; *) usage ;; esac

if [ ! -d "$ROOT/.helmit" ]; then
  echo "sanity check: no .helmit/ in $ROOT — not a HelmIt project, nothing to verify" >&2
  exit 0
fi

# Interpreter resolver — same contract as handoff.sh/lock.sh. A read-only aid:
# with no interpreter it degrades loudly and exits 0.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: sanity check SKIPPED — no python interpreter (python3/python/py) found." >&2
  exit 0
fi

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
SN_ROOT="$ROOT" SN_MODE="$CMD" exec "$PY_BIN" "$SELF_DIR/sanity.py" "$@"
