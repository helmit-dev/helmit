#!/usr/bin/env bash
# HelmIt — yolo: THE autonomy mandate, in one place (REQ-118).
#
# Anchor: before this, the mandate had two homes and neither owned it. The
# `yolo` field lived in the VERSIONED config.json — so a clone inherited
# somebody else's night — and the retired OS-scheduler arming file held a second
# copy that the skills did not read, which forced that layer to go and edit the
# config by hand for its scope to mean anything. Two sources for one decision is the same
# disease REQ-110 removed from the config; this hook is the single source that
# replaces both.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic, one line of output):
#   yolo.sh arm <off|phase|full> [--unattended] [--until <iso>]
#                                [--budget <n>] [--stop-at <point>]
#   yolo.sh status                 reads; never writes; always exit 0. It runs
#                                  the SAME fulfilled() check `reap` runs and
#                                  reports a spent mandate as FULFILLED instead
#                                  of `in force` — that is what lets a consumer
#                                  forbidden to write (session-start.sh, REQ-290)
#                                  ask the question here instead of copying the
#                                  rule.
#   yolo.sh expire [--reason <r>]  disarms; idempotent
#   yolo.sh reap                   expires a mandate whose scope is FULFILLED
#
# File: <root>/.helmit/yolo.json — LOCAL state, never versioned (it joins the
# lock, the run log, the handoff and the board in the .gitignore local-state
# block):
#   {"version","scope","stop_at","unattended","until","armed_at","budget_out"}
#   - scope      off | phase | full
#   - stop_at    the stopping point DERIVED at arming time: `ship:<phase>` for
#                phase — the phase is the FIRST OPEN row of the ROADMAP queue
#                (requires satisfied, status not shipped), never the
#                number inside the current position (at `shipped:N` that number
#                is a target already met — a mandate born fulfilled, REQ-156) —
#                and `ship:final` for full. Derived once, so a mandate cannot
#                silently follow the project into the next phase.
#   - unattended true only when the user was ASKED and said yes; the autopilot
#                is what acts on it.
#   - until      ISO-8601 UTC or null. OPTIONAL by design: it is an agenda
#                ceiling ("I need the machine at 9"), never the safety net.
#   - budget_out output-token ceiling, or null for NO ceiling.
#
# What `reap` decides, and how (this is the whole point of the hook — the
# mandate knows where it ends, so nobody has to remember to switch it off):
#   until in the past          => expired  (clock)
#   stop_at ship:final         => fulfilled when the position is `complete`
#   stop_at ship:<p>           => fulfilled at `shipped:<p>` — the VERB of the
#                                 stopping point decides, so `validated:<p>` is
#                                 still INSIDE the mandate (REQ-284) — or when
#                                 the position moved PAST <p> in the ROADMAP
#                                 order
#   anything else              => still in force, untouched
#
# Env: HELMIT_YOLO_NOW (ISO-8601 UTC, testing only — freezes "now").
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Interpreter resolver — same contract as commit-gate.sh/lock.sh.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt yolo SKIPPED — no python interpreter (python3/python/py) found; the mandate cannot be read, so approvals stay conversations." >&2
  exit 0
fi

export YL_ROOT="$ROOT"
export YL_SELF="$0"

exec "$PY_BIN" "$SELF_DIR/yolo.py" "$@"
