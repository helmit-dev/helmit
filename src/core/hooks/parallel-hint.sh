#!/usr/bin/env bash
# HelmIt — parallel-hint: does this test runner have a known parallel form?
#
# Anchor: /arch (REQ-198) and /env (REQ-199) need the SAME runner table. Spelled
# out in two prose skills it would rot in two directions, which is the disease
# REQ-110 and REQ-188 already treated: the knowledge lives in ONE deterministic
# hook and the skills stay thin shells that call it.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic, at most ONE line):
#   parallel-hint.sh suggest --command "<test command>"
#       recognized runner with no parallel form yet:
#         parallel-hint: <runner> — <suggested command> (<what it changes>)
#       recognized runner that is ALREADY parallel:
#         parallel-hint: <runner> — already parallel (<flag>); nothing to propose
#       unknown runner, or an empty command: NOTHING on stdout
#   exit 0 ALWAYS. This is an informer, never a gate; only a USAGE error exits 2.
#
# The table, deliberately small — five runners whose parallel form is common
# knowledge and has been stable for years:
#   pytest   -> -n auto           (pytest-xdist)
#   jest     -> --maxWorkers=50%
#   go test  -> -p 4
#   cargo    -> cargo nextest run (cargo-nextest)
#   vitest   -> --pool=threads
# Growing that list is a decision, not a reflex: every entry is a claim this
# hook makes about somebody else's project, and a wrong claim costs more than
# silence. Anything outside the table is answered with silence, on purpose.
#
# THE HONEST LIMIT, stated where nobody can miss it: this hook reads a STRING.
# It does not know whether the plugin behind the flag is installed (pytest-xdist
# and cargo-nextest may well be absent), how many cores the machine has, or
# whether the suite even survives running out of order — shared fixtures, one
# database, fixed ports. So the output is a PROPOSAL for a human to confirm,
# never a command to run on its own. The test command belongs to the PROJECT:
# the boundary REQ-112 held when it OFFERED `git rm --cached` instead of
# running it is the same boundary here.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Interpreter resolver — same contract as commit-gate.sh/yolo.sh.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
# No interpreter means no hint. An informer that cannot inform says nothing and
# gets out of the way: stdout stays empty and the caller keeps its old behavior.
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  exit 0
fi

PARALLEL_HINT_DIR="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/parallel-hint.py" "$@"
