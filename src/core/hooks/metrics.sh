#!/usr/bin/env bash
# HelmIt metrics core — deterministic, offline token accounting (REQ-036/038).
# Reads what the platforms already write (transcripts); never calls a network.
#
# Subcommands:
#   metrics.sh scan <transcript.jsonl> [--since-cursor <cursor>]
#       One JSON line: {"platform","model","models","model_variants",
#       "input_tokens","output_tokens","cache_read_tokens",
#       "cache_creation_tokens","cursor"}.
#       "models" is the per-model-id breakdown (REQ-167):
#       {"<model id>": {"input_tokens","output_tokens","cache_read_tokens",
#       "cache_creation_tokens"}} — same four keys as the top level, so the
#       buckets always sum back to the totals. "model" stays as it was (the
#       last non-synthetic model id seen) for consumers written before it.
#       "model_variants" is the window-variant dimension (REQ-228):
#       {"<base model id>": ["<variant>", ...]}. `claude-opus-5[1m]` is the 1M
#       context variant of `claude-opus-5` and is PRICED APART, but the bucket
#       ids come from `message.model`, which drops the suffix — the resolved id
#       lives only in `toolUseResult.resolvedModel` (verified on this repo's
#       own transcripts, 18/08/2026). Keeping the variant here lets whoever
#       prices later tell a 1M session from a standard one; the buckets and
#       their sums are untouched. It is OBSERVED over the whole transcript,
#       never sliced by the cursor: a category cannot be double-counted the way
#       a token can, and the residue of a session that spent nothing new since
#       the last capture would otherwise lose the variant. A dimension, never a
#       per-token split — pricing stays out of scope.
#       "subagents" is the per-subagent dimension read from the SECOND source of
#       truth (REQ-227): the parent transcript carries one `toolUseResult` per
#       subagent the orchestrator launched, and that record is the only place
#       the RESOLVED model of that subagent and its real duration exist at all —
#       the token buckets know model ids, never who ran for how long.
#       {"<agent id>": {"model","duration_ms","final_context_tokens"}}, observed
#       over the whole transcript for the same reason model_variants is.
#       "cross_check" confronts that record against what THIS collector summed
#       for the same agents: two independent paths to one fact is how a
#       collector regression is found without waiting for a field to vanish.
#       CAVEAT THAT RIDES IN THE DATA, because the whole reading depends on it:
#       `totalTokens` is the subagent's FINAL CONTEXT, never the sum of its
#       session. The two quantities CONFER each other and never substitute one
#       another, so the check is a FLOOR and never a proximity test — the final
#       context is one of the terms the collector sums, which makes
#       `collected >= reported` structural, and only a sum BELOW it (beyond
#       CROSS_CHECK_TOLERANCE) is a finding. Measured on this repo's own
#       transcripts (18/08/2026, 64 subagents): zero violations, with
#       collected/reported from 7.8x to 130x — which is also why a proximity
#       test would be nonsense. Only agents this scan actually summed are
#       confronted: one the cursor already counted belongs to another window and
#       would otherwise be reported as divergent for having been counted right.
#       THE FLEET IS ONLY SUMMED ONCE IT STOPPED WRITING (REQ-239). The
#       collector fires on ORCHESTRATOR events, so it routinely opens the file
#       of a subagent that is STILL RUNNING: it used to sum that partial and
#       write the agent into the cursor, and the spend that agent had after
#       that instant was never counted again. Measured on this repo
#       (18/08/2026): 9 of 12 agents read in flight, 17,079,801 tokens counted
#       against 37,744,872 real — 54.7% of the fleet lost, 87.4% on the worst
#       agent, and unrecoverable, since the id was already in the cursor. An
#       agent with no stop record is now NOT summed AND NOT written to the
#       cursor, so the next sweep reads it whole, once: delay is not loss.
#       A STOPPED AGENT CAN BE RESUMED (REQ-240) — SendMessage wakes it and it
#       spends again. Counted at its first stop and named in the cursor, that
#       new spend was frozen exactly as before: neither the hot rule (which only
#       asks for A stop record) nor the cold complement (which only sums agents
#       MISSING from the record) ever reopens a file already counted. Measured
#       here on 18/08/2026: 36 of 221 (session, agent) pairs were notified of a
#       stop more than once. So the cursor entry is VERSIONED by the stop it was
#       counted at: a later stop no longer matches it, the file is read again,
#       and what is summed is that whole read MINUS the same read over the
#       prefix already counted — growth only, per model bucket too. Recounting
#       would be worse than the freeze. The generation is also what keeps "do
#       not read what still changes" in force: an agent resumed and RUNNING has
#       no new stop record yet and is left alone, like one that never stopped.
#       The two stop records, both measured on real transcripts (18/08/2026,
#       115 agents over 11 sessions):
#         synchronous  — the Task `toolUseResult` carries `totalTokens` and
#                        `totalDurationMs`; the launch record of an async agent
#                        (status `async_launched`) carries neither.
#         asynchronous — a `<task-notification>` naming the agent in
#                        `<task-id>` and carrying a `<status>` (completed,
#                        failed, killed and stopped were observed, all
#                        terminal; a notification with NO status is a Monitor
#                        event about something else entirely). This is the ONLY
#                        stop record a BACKGROUND agent leaves on the parent
#                        transcript: of the 115 agents, ZERO carried both
#                        shapes, and one whole session of 16 background agents
#                        carried none of the first.
#       PLATFORM BOUNDARY, verified 18/08/2026: the rule lives in scan_claude
#       because only claude-code accumulates one FILE PER SUBAGENT. Codex
#       writes no per-subagent record and takes the session total as
#       `c_in - b_in`, a design immune to this class by construction, and no
#       parallel wave has ever run there (parity is phase 6). When Codex gains
#       parallel waves the question must be RE-VERIFIED against its real
#       format, never inherited from here (ADR-010).
#       Platform is detected by CONTENT: any token_count event => codex,
#       otherwise claude-code. With --since-cursor only the delta since that
#       cursor is counted; without it the whole transcript is summed.
#   metrics.sh agg [--file <metrics.jsonl>] [--phase <id>] [--task <id>.N] [--project]
#       Phase ids may be digit-led alphanumerics (e.g. 3c) — REQ-151.
#       Human-readable totals (including a per-platform, a per-model and a
#       window-variant breakdown) + one final JSON line {"input_tokens",
#       "output_tokens","cache_read_tokens","cache_creation_tokens","lines"}
#       for the scope. Lines whose "phase_source" is "state" inherited the
#       phase from STATE.md rather than from a commit message (REQ-225), and
#       the report says so: a session residue can straddle a phase boundary,
#       so that attribution is approximate and never a measurement.
#       The cross-check of the second source is reported here too (REQ-227),
#       carrying the caveat with it: divergence above the declared threshold is
#       PRINTED, never silent, and what is compared is a FLOOR between two
#       quantities that confer each other, not two spellings of one.
#   metrics.sh reconcile [--claude-dir <dir>] [--codex-dir <dir>] [--file <f>]
#       Cold reconciliation: scans transcript dirs (defaults:
#       ~/.claude/projects/<cwd-slug>/ and ~/.codex/sessions/), finds sessions
#       with NO line in metrics.jsonl and appends {"source":"reconcile"} lines.
#       The claude sweep is the union of the transcripts in <claude-dir> and the
#       BACKGROUND sessions that only ever wrote a subagent fleet (REQ-226):
#       listing the dir alone misses a session whose parent transcript never
#       landed there, and with it the whole fleet — precisely the spend the cold
#       path exists to recover.
#       A session that ALREADY has lines is COMPLETED, never recounted
#       (REQ-239): the agents its own cursors prove were counted stay out and
#       only the ones missing from the record are summed, so a session
#       abandoned in the middle of a wave — whose running agents the hot sweep
#       deliberately left for later — still lands whole. A session whose lines
#       cannot say what was counted (no cursor, or not a claude one) is skipped
#       entirely, as it always was: with no proof of what was counted, nothing
#       is completed. The cold sweep sums whatever is on disk BECAUSE it assumes
#       the sessions it walks are dead — a ghost session has no parent transcript
#       and therefore no stop record to wait for, so waiting would lose its whole
#       fleet. That assumption is now CHECKED instead of declared (REQ-241): a
#       session the write-ahead log still holds an OPEN CLAIM for is skipped,
#       with the reason printed. It used to be swept like any other, and summing
#       a fleet in flight is exactly the partial read the hot side stopped doing.
#       The signal is per session and fail-open: no run-log.sh, no log, no open
#       claim, or a claim that cannot name its session (REQ-234) leaves the sweep
#       running as it always did.
#
# Formats (inspected live 2026-07-09):
#   claude-code: <dir>/<session-id>.jsonl, one JSON per line; assistant lines
#     carry message.usage AND message.model — the model id is per message, so
#     the breakdown is exact for a session that switches models mid-run and for
#     subagents on a different model than the main session (REQ-167).
#     CRITICAL: one assistant message is flushed once per
#     streamed content block — 2..6 lines sharing the same message.id AND the
#     same requestId (strictly 1:1 on real data), each carrying a CUMULATIVE
#     usage snapshot: only output_tokens grows, and the chunk carrying
#     `stop_reason` holds the final count. That chunk is NOT reliably the last
#     LINE of its requestId, and 3% of the messages never carry one at all, so
#     dedup by requestId keeping the LAST occurrence (REQ-166) — which never
#     consults `stop_reason`, and that is precisely where its robustness comes
#     from. Keeping the first undercounts output ~12x; summing every line
#     inflates input/cache instead.
#     REFUSED (REQ-244), in the ADR-012 spirit — the alternative, the reason and
#     the numbers, so the next reader does not re-propose it: make the line
#     cursor WAIT for the end of a streaming message (stop before it, read it
#     whole in the next window, the way the fleet waits for a stop record,
#     REQ-239) and retire the straddle subtraction (REQ-229) with it. The end
#     signal it would ride on does not exist. Measured 19/08/2026 over the real
#     transcripts of this project (29 parent + 121 subagent files, ~9.27k
#     messages):
#       3.0% of the messages (274) NEVER carry `stop_reason`, and 263 of them
#         are provably finished (a different requestId follows). A cursor
#         waiting for the signal freezes on those: ~1.0M cache_read tokens never
#         counted, 10 of the 11 files affected being SUBAGENT files, which never
#         grow again once the agent stopped.
#       27.6% of the messages (2557) carry lines of the SAME requestId AFTER the
#         chunk with `stop_reason`, and in 100% of them those lines are PURE
#         duplicates of the snapshot. A cursor parked on the marked chunk is
#         therefore INSIDE the message, and with no REQ-229 subtraction the next
#         window re-adds the whole snapshot — a recount, the one thing this file
#         forbids.
#       No field marks the final line: over 5445 adjacent chunk pairs the only
#         differences are uuid, parentUuid, timestamp, content, stop_reason and
#         usage. There is no other signal to switch to either.
#     The only end signal append-only data does supply is a LATER message, and
#     waiting for it costs the last message of every file (~22M cache_read
#     here). The guard being dropped costs nothing against that: of 902 real
#     cursors checked against their own transcripts, ZERO ever landed inside a
#     message. REQ-239 does not transport — a subagent stop record is an
#     OUT-OF-BAND, unambiguous event on the parent transcript, while
#     `stop_reason` is in-band and does not mark the end. Frozen by
#     "metrics-stop-reason-is-not-an-end-marker".
#     Subagents, two roots (both same format, isSidechain:true), always summed
#     together with the main session:
#       interactive: <dir>/<session-id>/subagents/agent-*.jsonl
#       background:  <tmp>/claude-<uid>/<project-slug>/<session-id>/tasks/*.output
#     Background sessions write ONLY to the tasks/ root for most agents, so
#     ignoring it under-counts a phase by the whole subagent fleet (REQ-165).
#   codex: rollout-<ts>-<uuid>.jsonl; event_msg/token_count events whose
#     info.total_token_usage is CUMULATIVE => session total = LAST event.
#     The counter is session-wide and carries NO model tag, so a per-model
#     breakdown is only derivable when the session declared a single model
#     (turn_context/session_meta): then the whole delta is that model's. With
#     two or more declared models "models" is left EMPTY rather than guessed.
#
# Cursor formats (opaque strings; version-prefixed):
#   claude:v2:<lines-counted>:<last-request-id>:<input,output,cache_read,
#     cache_creation ALREADY COUNTED for that request id>:<agent entry,...>
#   claude:v1:<lines-counted>:<last-request-id>:<agent entry,...>  (still read)
#   codex:v1:<last-token_count-line-idx>:<input>:<cached>:<output>
#
#   An AGENT ENTRY is `<agent id>#<stop generation>@<lines summed>` (REQ-240):
#   how many stops the parent transcript recorded for that agent when it was
#   counted, and how far into its file the count went. A BARE id is an entry
#   written before this existed: it proves the agent was counted and cannot say
#   how far, so it stays SEALED (never read again) — the behaviour it had when it
#   was written, and the only one that cannot recount. The entry rides INSIDE the
#   v2 (and v1) agent list on purpose, instead of a v3 field: a build that
#   predates it reads an unknown agent id and re-counts one agent, where a
#   version it cannot parse would make it re-count the whole session.
#
# v1 simplifications (documented by design):
#   - reconcile never re-reads the PARENT transcript of a session that has any
#     existing line (source hook|stop|reconcile) => never double-counts, may
#     under-count a session that kept running after its last hook line. Its
#     FLEET is the exception (REQ-239): agents missing from the record are
#     summed, one by one, because a session can be abandoned with agents the
#     hot sweep was still waiting on.
#   - reconcile skips zero-usage sessions (no noise lines).
#   - claude delta scan guards only the LAST requestId against duplicate lines
#     straddling the cursor boundary (duplicates are adjacent in practice). The
#     guard SUBTRACTS what the cursor says was already counted for that id
#     (REQ-229) instead of dropping its lines: usage is cumulative and only the
#     final chunk carries the message's whole output, so a cursor written
#     mid-stream would otherwise lose that output for good. A v1 cursor carries
#     no usage and still skips the id whole — never double-counting, which is
#     what v1 optimized for.
#   - metrics NEVER break anything: malformed JSON lines are ignored, missing
#     files yield empty results, and every data-path failure exits 0.
set -u

# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# Interpreter resolver — same contract as commit-gate.sh: HELMIT_PYTHON wins,
# else the first of python3/python/py on PATH. No interpreter => skip loudly,
# exit 0 (metrics must never block a hook chain).
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt metrics SKIPPED — no python interpreter (python3/python/py) found." >&2
  exit 0
fi

# The claims the write-ahead log still has OPEN — the work this project says is
# IN FLIGHT — handed to the reader below in the environment, the same idiom
# reconcile.sh uses: the log is ALWAYS read through run-log.sh, which is the one
# implementation of what OPEN means, and the shell is the half that already
# resolves its siblings. Only the COLD path asks (REQ-241): the hot
# scan fires on every tool call and must not spawn anything. Fail-open by
# construction — no sibling script, no log, no open claim, all give the empty
# string, and the sweep then runs exactly as it always did.
HELMIT_OPEN_CLAIMS=""
if [ "${1:-}" = "reconcile" ]; then
  RUNLOG="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/run-log.sh"
  if [ -f "$RUNLOG" ]; then
    HELMIT_OPEN_CLAIMS="$(bash "$RUNLOG" open-entry --all 2>/dev/null)" \
      || HELMIT_OPEN_CLAIMS=""
  fi
fi
export HELMIT_OPEN_CLAIMS

exec "$PY_BIN" "$SELF_DIR/metrics.py" "$@"
