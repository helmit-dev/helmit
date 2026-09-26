#!/usr/bin/env bash
# HelmIt — heartbeat: the per-session guardian beat (phase 19, REQ-157/REQ-158
# and the decision half of REQ-159; ADR-010).
#
# Anchor: optional recovery is PER SESSION/TASK. A native scheduler fires a
# cheap beat only after the user explicitly requests interruption recovery.
# The hook DECIDES; the skill ACTS. Normal work remains in the same active flow
# and waits on executor events — the beat never polls or supervises it. State is
# derived from run.jsonl + git + yolo.sh + the interactive executor lease.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   heartbeat.sh [beat] [--dry-run] [--quota-signature "<text>"]
# `beat` is the only command and the default. It never renews `lock.json` or an
# executor lease: recovery traffic is not evidence of interactive execution.
# In order, a beat:
#   1. COLLAPSES a burst (REQ-233): the harness cron only delivers a beat with
#      the REPL idle, so during a long turn the beats QUEUE and land ALL AT ONCE
#      when the turn ends (9 measured on 06/08, 15 on 18/08) — and each one
#      costs a turn. A beat arriving with a beat ALREADY PROCESSED less than
#      COLLAPSE_MIN minutes ago decides IDLE at once, reason burst-collapse, and
#      does nothing else: no mandate probe, no act, and IDLE is answered by the
#      skill with absolute silence (REQ-108). COLLAPSE_MIN is DERIVED from the
#      beat interval — a third of it, so 5 min at the default 15 — because at a
#      15 min cadence a beat landing inside that window is a queued one by
#      construction. The window is measured against the LAST RECORDED beat,
#      collapsed ones included, so a whole burst collapses end to end. A
#      collapsed beat is a NON-DECISION: it is recorded (the burst stays
#      measurable) but every derivation that reads DECISIONS — breaker streak,
#      backoff ladder, terminal-repeat guard — steps over it, otherwise a burst
#      after each RESUME would silently retire the breaker and a queued beat
#      after DONE would hide a cron removal that failed.
#   2. DECIDES, printing ONE stdout line `heartbeat: <DECISION> — <reason>`
#      and (not in --dry-run) appending a typed `beat` event to run.jsonl via
#      run-log.sh append (decision, reason, sha at beat time). The matrix, in
#      precedence order (the first match decides):
#        a. DONE           the mandate is no longer in force — yolo.sh status
#                          says off (reason no-mandate) or yolo.sh reap just
#                          harvested it (reason scope-fulfilled). The skill
#                          must remove the cron.
#        b. IDLE           honest stop: the last non-beat entry is
#                          session_stop{gate|awaiting_input} — a beat NEVER
#                          crosses a gate (REQ-090 lineage).
#                          reason typed-stop:<r>. `clean` is also typed and is
#                          never resumed: a live mandate forbids recording it,
#                          and a legacy/corrupt log carrying one stays parked.
#                          Only `interrupted` is candidate RESUME.
#        c. IDLE           work in flight in THIS session: last non-beat entry
#                          is not a stop and is FRESH (younger than the beat
#                          interval window) — the turn may still be finishing;
#                          reason in-flight. An OLD last entry is NOT death by
#                          itself (REQ-234): absence of a commit is the NORMAL
#                          state of a task in flight, and concluding otherwise
#                          reset every task longer than ~15 min — the guardian
#                          that exists to resume dead work stopped live work
#                          from finishing. So the beat asks for a SIGN OF LIFE
#                          of the executor before concluding: an open
#                          task_claimed (run-log.sh open-entry --all) is alive
#                          only with a FRESH executor lease for that exact task
#                          and session. The recurring beat shares task identity
#                          on Codex Desktop, so identity, Goal, pid, claim or
#                          lock heartbeat alone proves nothing: candidate IDLE,
#                          reason
#                          in-flight:executor-alive. It stays a CANDIDATE on
#                          purpose, so the breaker and the 24h floor below still
#                          see it and a signal that never expires cannot idle
#                          forever. No signal at all, or an expired one:
#                          candidate RESUME interrupted (the /next
#                          reconciliation resolves it). An EMPTY log is IDLE
#                          no-interruption: the normal route, never the beat,
#                          starts an eligible next act.
#        d. WAIT           quota: ONLY on the explicit --quota-signature the
#                          skill passes when the previous turn failed by limit
#                          (no fragile ambient detection). A parseable
#                          "resets H:MM(am|pm)" prints `WAIT until <iso>`
#                          (reset + 7 min, local clock) for the skill to
#                          schedule the one-shot; otherwise `WAIT backoff
#                          <min>` with the exponential ladder 5-10-20-40-60
#                          DERIVED from the trailing consecutive quota WAITs
#                          in run.jsonl. reason quota.
#        e. DISARM         breaker: 3 consecutive RESUME beats recorded with
#                          the SAME sha as the current HEAD (no new commit
#                          between them). reason breaker.
#        f. DISARM         floor: mandate in force but the trailing beats on
#                          the current HEAD span more than 24h — no commit in
#                          a whole day of beats. reason stale-24h.
#   4. TERMINAL-REPEAT GUARD (REQ-159): if this decision is DONE or DISARM and
#      the PREVIOUS beat recorded in the log already carried the SAME terminal
#      decision, the act that should have removed the cron did not happen.
#      stderr gets `heartbeat: ERROR — terminal decision repeated (<DECISION>);
#      the act that should have removed the cron FAILED` and the exit is 1 —
#      the ONLY non-zero exit of the decision contract. The skill treats it.
#
# PROGRESS is a new commit and only that: beats record the sha they saw, and a
# sha different from the current HEAD forgives breaker, backoff and floor.
# Two consecutive --dry-run executions are byte-identical: derivation is pure.
#
# Neighbours used BY CONTRACT (never reimplemented): yolo.sh status|reap ·
# run-log.sh append · run-log.sh open-entry --all (which claims are still in
# flight is ITS derivation, REQ-232 — a second reader of the WAL would drift).
# DETECTING is not EXPIRING, so the two modes consult different verbs: --dry-run
# reads the verdict off `status`, which reports a spent mandate as FULFILLED
# without writing anything (REQ-290); the normal mode runs `reap`, because the
# reap is what actually ends the mandate.
#
# Exit: 0 for every decision · 1 ONLY for the terminal-repeat guard ·
#       2 usage errors (outside the decision contract, like handoff.sh).
# Env: HELMIT_PYTHON            interpreter override (same contract as lock.sh)
#      HELMIT_BEAT_INTERVAL_MIN in-flight freshness window (default 15)
#      HELMIT_BEAT_COLLAPSE_MIN burst-collapse window (default: a third of the
#                               interval, so 5 at the default 15; 0 disables it)
#      HELMIT_BEAT_NOW          ISO-8601 UTC, testing only — freezes "now"
#      HELMIT_LOCK_STALE_SECS   lock staleness threshold (shared with lock.sh)
#      HELMIT_SESSION_ID / CLAUDE_CODE_SESSION_ID / CODEX_THREAD_ID /
#      CODEX_SESSION_ID / CLAUDE_SESSION_ID
#                               this session id (lock ownership and the
#                               liveness signal), in that precedence — the
#                               chain lock.sh defines and all four repeat
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "usage: heartbeat.sh [beat] [--dry-run] [--quota-signature \"<text>\"]" >&2
  exit 2
}

DRY=0
SIG=""
while [ $# -gt 0 ]; do
  case "$1" in
    beat) ;;
    --dry-run) DRY=1 ;;
    --quota-signature)
      shift
      [ $# -gt 0 ] || usage
      SIG="$1"
      ;;
    -h|--help)
      echo "usage: heartbeat.sh [beat] [--dry-run] [--quota-signature \"<text>\"]"
      exit 0
      ;;
    *) usage ;;
  esac
  shift || true
done

# Interpreter resolver — same contract as lock.sh/yolo.sh: fail open, loudly.
# A guardian that cannot think must stand still, not act: IDLE and exit 0.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt heartbeat SKIPPED — no python interpreter (python3/python/py) found; the beat cannot decide and does nothing." >&2
  echo "heartbeat: IDLE — no-interpreter"
  exit 0
fi

HB_ROOT="$ROOT" HB_HOOKS="$SELF_DIR" HB_DRY="$DRY" HB_SIG="$SIG" \
  exec "$PY_BIN" "$SELF_DIR/heartbeat.py" "$@"
