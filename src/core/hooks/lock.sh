#!/usr/bin/env bash
# HelmIt — lock: mutual exclusion PER WORKING TREE (phase 14, REQ-091).
#
# Anchor: two agent sessions in the SAME repo trample each other SILENTLY —
# one rewrites .helmit/STATE.md under the other and nobody notices. And on a
# naive remedy ("does the holder still exist?") would block the whole night: on a
# quota stall the REPL does NOT die: it returns to a live, idle prompt still
# holding the lock. Hence liveness here is the HEARTBEAT, never "the pid exists".
# The mirror image is just as wrong and cost a whole phase to see: "the pid does
# NOT exist" is not death either, because the harness hands each Bash call its own
# short-lived shell, so every recorded pid is born dying (REQ-231).
#
# Contract (ADR-001: bash + python3 stdlib; deterministic):
#   lock.sh acquire [--session <id>] [--force]   acquire (only the commands
#                                                that WRITE should call it)
#   lock.sh release [--session <id>] [--force]   release; idempotent
#   lock.sh status  [--session <id>]             readable state; always exit 0
#   lock.sh heartbeat [--session <id>]           beats the heartbeat of the own lock
#
# File: <root>/.helmit/lock.json
#   {"pid","host","session","acquired_at","heartbeat_at","version"} — dates in
#   ISO-8601 UTC. root = $CLAUDE_PROJECT_DIR, falling back to cwd.
#
# States and exits of `acquire` (the matrix that matters). Read it top down: the
# HEARTBEAT decides first and the pid only refines an already EXPIRED one.
#   no lock                            => 0  acquires (O_CREAT|O_EXCL: atomic)
#   same pid/session                   => 0  re-entrant (just beats the heartbeat)
#   FRESH heartbeat, ANY pid           => 3  live session working — a DEAD pid
#                                            does NOT override a fresh heartbeat
#                                            (REQ-231)
#   EXPIRED heartbeat + same host
#     + provably DEAD pid              => 0  ORPHAN recovered WITHOUT ASKING
#   EXPIRED heartbeat, owner alive
#     or unknowable                    => 2  does not take it: EXPLAINS who/since
#                                            when/last heartbeat, and OFFERS
#                                            the unlock (`--force`)
#   different host                     => decided by the heartbeat ALONE (2 or 3),
#                                         because the pid cannot be checked
#   --force                            => 0  takeover in any state
# No state requires hand-editing a file: `--force` resolves all of them.
#
# `release` is deliberately MORE tolerant than `acquire`, and only there: it also
# yields to a caller whose recorded owner is a dead process of this host, whatever
# the heartbeat says. See owner_gone() for why refusing there would strand every
# lock under its own holder.
#
# THE SESSION-ID CHAIN, defined here and repeated verbatim by run-log.sh,
# heartbeat.sh and commit-gate.sh (the four share no file that could hold it):
#
#   HELMIT_SESSION_ID -> CLAUDE_CODE_SESSION_ID -> CODEX_THREAD_ID
#   -> CODEX_SESSION_ID -> CLAUDE_SESSION_ID -> none
#
# CLAUDE_CODE_SESSION_ID is the variable the harness actually exports (measured
# in a live session, 18/08). The chain used to jump straight from the override
# to CLAUDE_SESSION_ID, which no harness sets, so EVERY reader resolved to
# nothing in the field: locks had no owner to renew, claims carried no session
# and the liveness signal of REQ-234 never existed. The override stays FIRST
# because the suite and any wrapper need a way to name a session that is not
# theirs; CLAUDE_SESSION_ID stays LAST so an environment that only has it keeps
# working. CODEX_THREAD_ID identifies the durable Desktop task, so it wins over
# CODEX_SESSION_ID when both are present; the latter remains a usable fallback
# for Codex invocations that expose no thread. NONE of them set remains legal
# and every consumer falls back to what it did before: the id is additive,
# never a precondition.
#
# The chain must be IDENTICAL in all four: whoever STAMPS a session and whoever
# READS it have to resolve the same way, or every record looks like it belongs
# to somebody else, which is worse than the inert chain it replaced.
#
# Env: HELMIT_LOCK_STALE_SECS (heartbeat threshold, default 900s = 15min),
#      HELMIT_LOCK_PID (pid of the OWNER; default = the caller of the script),
#      HELMIT_SESSION_ID / CLAUDE_CODE_SESSION_ID / CODEX_THREAD_ID /
#      CODEX_SESSION_ID / CLAUDE_SESSION_ID
#      (default session id, in that precedence — the chain above).
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Interpreter resolver — same contract as commit-gate.sh/metrics.sh.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt lock SKIPPED — no python interpreter (python3/python/py) found; concurrent sessions will NOT be detected." >&2
  exit 0
fi

# The recorded pid is the pid of the CALLER (the REPL/session), not of this
# ephemeral process, which dies at the end of the call and would orphan every lock.
export LK_ROOT="$ROOT"
export LK_SELF="$0"
export LK_PID="${HELMIT_LOCK_PID:-$PPID}"
export LK_STALE="${HELMIT_LOCK_STALE_SECS:-900}"
export LK_SESSION="${HELMIT_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-${CLAUDE_SESSION_ID:-}}}}}"

exec "$PY_BIN" "$SELF_DIR/lock.py" "$@"
