#!/usr/bin/env bash
# HelmIt metrics hot capture — PostToolUse + Stop hook (REQ-037).
# One script, dispatched by the `hook_event_name` field of the stdin payload:
#   PostToolUse (matcher Bash): after a `git commit` command, append one line
#     to .helmit/metrics.jsonl attributing the session's token delta to the
#     task id parsed from the last commit message ("[<phase>.<task>").
#     No task pattern in the message => task/phase null, still recorded.
#   Stop: append the session residue (task null, source "stop"). Having no task
#     to be attributed by, the residue INHERITS the current phase from the
#     `workflow:` field of STATE.md ("phase_source":"state") — the reading a
#     human would give that residue, and without it the record is mostly
#     phase-less: measured on this repo on 06/08/2026, 6 of 41 lines carried a
#     phase and the board's consumption-by-phase chart covered ~20% of the
#     spend. CAVEAT, CARRIED IN THE DATA: a session residue can straddle a
#     phase boundary, so an inherited phase is an APPROXIMATE attribution and
#     never a measurement. "phase_source":"commit" is the exact one (parsed
#     from the commit message) and a STATE with no phase in its workflow
#     (`env-ready`, `complete`) leaves both fields null, as before.
# The durable line also carries what the parent transcript records about each
# subagent — resolved model and real duration — and the CROSS-CHECK of the
# token figure that comes with it (REQ-227). CAVEAT DECLARED IN THE DATA, not
# only here: that figure is the subagent's FINAL CONTEXT, never the sum of its
# session. The two quantities confer each other and never substitute one
# another, so what is stored is a floor comparison — a collected sum below the
# reported context means the collector stopped seeing a class of line, while a
# sum above it is the normal state and means nothing. Divergence beyond the
# declared tolerance is REPORTED by `metrics.sh agg`, never silent.
# Never double-counts: the last recorded cursor for THIS session is fed back
# into `metrics.sh scan --since-cursor`, and a zero delta writes NO line.
#
# FAIL-OPEN ABSOLUTE: metrics must never disturb the flow. Any failure
# (no interpreter, no transcript, malformed JSON, missing metrics.sh) is a
# silent exit 0 — at most one discreet stderr line. This script NEVER exits
# non-zero.
set -u

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0

# Interpreter resolver — same contract as commit-gate.sh / metrics.sh:
# HELMIT_PYTHON wins, else the first of python3/python/py on PATH.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "HelmIt metrics: skipped (no python interpreter)." >&2
  exit 0
fi

METRICS_COLLECT_DIR="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/metrics-collect.py" "$@"
