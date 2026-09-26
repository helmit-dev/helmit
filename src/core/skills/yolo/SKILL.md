---
name: yolo
description: "The autonomy mandate: arms how far the agent may go without asking (off | phase | full), optionally records explicit interruption recovery, reports what is in force, and expires on fulfillment."
---

# /yolo

How far may the agent go before it asks you again? That answer is the MANDATE,
and this command is its explicit door. Everything it does is a thin shell over
`core/hooks/yolo.sh`, which owns the writing, the reading and the expiry — so
the answer is a fact on disk, not an impression somebody formed from a sentence
three hours ago.

The mandate is ONE thing with three dimensions:

| dimension | what it decides | default |
|---|---|---|
| `scope` | how far: `off` (every gate is a conversation) · `phase` (auto-approve through this delivery's unified `/ship`) · `full` (chain deliveries through the final one) · `until <phase>` (chain deliveries and stop after THAT one) | `off` |
| `until` | the LATEST it may run — an agenda ceiling ("I need the machine at 9"), never the safety net | none |
| `unattended` | whether a native heartbeat may recover a real interruption | off unless explicitly requested |

It lives in `.helmit/yolo.json`, which is LOCAL state and never versioned: a
mandate must not be inherited by a clone. Whoever clones the repo starts
supervised, always.

The orchestrator owns the live flow. While the mandate is in force and its
`stop_at` is not fulfilled, it executes every eligible act in the same active
turn, using an event-driven wait when an executor is still working. It does
not return a terminal response between acts and does not delegate normal
continuation to a periodic automation. The heartbeat is a recovery-only
watchdog for a real interruption, not the engine of YOLO.

On Codex Desktop, a Goal is optional continuity evidence, not a prerequisite
for an active YOLO flow. Observe `get_goal` before ending a turn when a Goal
already exists, but Goal absence or an unavailable Goal never changes the
HelmIt route. Never call `create_goal`, replace, complete or cancel a Goal
unless the user made an explicit request for that mutation; YOLO is not that
authority.

---

## Working-tree safety (ADR-018)

Before the first write, lock, claim, executor dispatch or expensive gate, run
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/preflight.sh" check` once. `READY`
means no changes were observed. `CHANGED <paths>` is advisory: inspect Git
status, the staged and unstaged diffs, and every target already modified; it
never blocks merely because the worktree is dirty. `BLOCKED_CONCURRENT` stops
only when a fresh lock and matching fresh executor lease prove another executor
is active in this checkout.

Preserve unrelated edits and the existing index. Continue through compatible,
understood changes in a target file; pause only the affected operation for an
unresolved overlap or unknown intent. Before commit, review the staged diff and
stage only the intended paths or hunks—never `git add -A`. Do not repeat the
global preflight at staging or commit; the task verify and independent Git floor
judge the selected content.

---

## Preconditions (declarative gates — block if unmet)

1. `.helmit/` exists. If not → route to `/helmit:setup`. STOP.
2. Argument is `off` | `phase` | `full` | `until <phase>` | `status`. No argument → `status`. `until` REQUIRES a phase id, and that id must be an OPEN row of `ROADMAP.md` — a target that is already shipped arms a
   mandate born fulfilled, and one that does not exist arms a mandate
   with nowhere to stop. Refuse either, naming the open rows.
3. `off` and `status` never refuse: they are idempotent and safe on a project
   that never armed anything. A disarm that can fail is a disarm nobody trusts.

---

## Process

### `status` — what is in force right now (default)
Run `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" status` and report its
line in the language from `config.json`. Nothing else: the hook's answer IS
the state.

### `off` — disarm
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" expire --reason disarmed`.
Then say, in one line, that approvals are conversations again — and, in the
SAME response, take the guardian down with the mandate: instruct
`/helmit:heartbeat off` so the session beat cron is removed (CronDelete,
removal verified). Ask about neither — `off` never asks — because a guardian
still beating for a mandate that no longer exists is exactly the half-state
this command exists to prevent.

### `phase` | `full` | `until <phase>` — arm

#### 0. Optional pre-spec decision scan (REQ-317)
Before arming a scope that can reach a `/spec`, read the current ROADMAP,
REQUIREMENTS, KEEL and relevant INBOX route. Surface ONLY choices with durable
high impact: public contract, data, security/autonomy, recurring cost,
compatibility, cross-platform parity, or priority. For each, give a concise
recommendation and the assumption behind it. Use the native multiple-choice
question control when the harness offers it, with the recommendation first;
otherwise present closed alternatives plus an open response in plain text.

This scan is consultative, never a gate. If the user declines, is unavailable,
or has already asked for YOLO, record the recommendation as an explicit
hypothesis in the spec's Clarification record (or INBOX before a target spec
exists) and arm the mandate normally. Silence is not authority for a material
choice: continue independent investigation and drafting, and let only an
eligible mandate scope authorize the dependent commitment. Do not manufacture
low-impact questions just to use the scan or re-confirm prior decisions.

#### 1. Record explicit recovery intent

Do not ask about availability by default. An ordinary yolo request authorizes
continuous work in the current flow and arms WITHOUT `--unattended`; it does
not create a periodic guardian.

Use `--unattended` only when the user explicitly asks to recover automatically
after an interruption, says they are leaving and wants work to resume, or
directly asks for heartbeat. In that same response, invoke the heartbeat skill
without a second confirmation. State once that its default interval is about
15 minutes and the machine must remain awake (sleep pauses delivery).

Do not infer recovery consent from scope, clock time, or a generic request for
autonomy. If the wording makes recovery intent materially ambiguous, ask one
short question; otherwise proceed with the attended default. On a host without
a native task/session scheduler, keep the mandate but declare that automatic
recovery is unavailable there. Never emulate it with a shell loop or OS job.

`until` is OPTIONAL and is NOT a second question. Ask nothing about it; pass
`--until` only when the user named a time themselves ("until 7am", "before my
meeting"). Its default — none — means "it ends when it ends", and what
guarantees an end is the fulfilled scope, the breaker and the honest gate, not
a clock.

#### 2. Arm through the hook, never by hand
```
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" arm <phase|full> \
     [--unattended] [--until <iso8601 UTC>] [--budget <output tokens>]
```
and, for the in-between case, `until <phase>` is `full` carrying an explicit
stopping point:
```
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" arm full --stop-at ship:<phase> \
     [--unattended] [--until <iso8601 UTC>] [--budget <output tokens>]
```
The hook derives `stop_at` from the position at THIS moment (`ship:<phase>` for
`phase`, `ship:final` for `full`), or takes the one `--stop-at` names, and
prints one line. Hand-editing `.helmit/yolo.json` is not the interface — if the
hook cannot arm it, that is a bug to report, not a file to fix.

WHAT `until` DOES, and it is worth saying plainly because it is NOT a list of
phases: the mandate stores ONE stopping point and nothing else. It never picks
which phases run — the router does that, in the ROADMAP order READ AT EACH
CHECK, never from a copy frozen at arming time. So a queue reordered, a phase
inserted in the middle or a phase created later all keep working: they are just
more work before the stopping point arrives. Measured on 19/08 with a target of
`ship:27`: the mandate held through `implemented:28`, `shipped:28`,
`shipped:26` and `implementing:27`, and expired exactly at `shipped:27`.

The one edge that is NOT benign, and the hook now closes it: if the target
phase is REMOVED from the ROADMAP, the mandate has no stopping point left —
`reap` expires it and says so, instead of letting it run to `complete` and
carry the queue's last phase, which is typically the public release (REQ-264).

`--budget` is a COST ceiling, optional, and only meaningful to someone paying
per token; omit it and there is no ceiling. It is not a safety mechanism.
When optional recovery is armed, its breaker stops repeated resumptions that
produce no commit.

#### 3. DECLARE what was armed
Say, in one short paragraph: the scope in plain words, where it stops, whether
it resumes unattended, and that `/helmit:yolo off` ends it at any time. A
mandate that is armed and invisible is how a night surprises someone.

---

## The rules that make this a mandate and not a setting

- **The conversation ARMS it, and this command is the deterministic door.**
  "implement phase 3 in yolo", "carry on in yolo full", "stop asking me until
  the phase is done" — any of those, said in ANY command, means: call
  `/helmit:yolo <scope>` BEFORE continuing. The rule lives in the leased block
  of `CLAUDE.md`/`AGENTS.md` because that is the only text every session loads,
  so the request is honoured at whatever door it arrives.
- **It EXPIRES on its own, and the VERB of the stopping point decides.** `reap`
  compares the stored `stop_at` with the position in `STATE.md`. A `phase`
  mandate stores `ship:<phase>`, and `ship:` means SHIPPED: it is over at
  `shipped:<phase>` and NOT at an optional `validated:<phase>` diagnostic.
  Final proof and closure now belong to the same `/ship` act, so there is no
  routine approval or idle window between them. Three other things also end it: the project
  reaching `complete`, the project moving PAST that phase in the ROADMAP order,
  and the phase disappearing from the ROADMAP altogether — a stopping point
  that vanished leaves no scope to go on holding. A `full` mandate stores
  `ship:final`, which is over at `complete` and at nothing else. An explicit
  `--until` is an agenda ceiling on top of all of that: once the timestamp has
  passed the mandate is over wherever the project stands. `/helmit:next` runs
  `reap` on every call, so an expired mandate never survives into a session
  that did not ask for it. The user never has to remember to switch anything
  off.
- **A sentence now beats the file, in BOTH directions.** Asking for yolo in a
  project that says `off` arms it; asking to be consulted in a project that
  says `phase` disarms it. The file records a mandate; it never outranks the
  person giving one.
- **Every skill with an approval gate reads the mandate AT THE GATE**, never at
  the start of the command — otherwise a mandate armed mid-conversation does
  not exist for the command already running.
- **An uncovered human gate ends the mandate.** When a skill reaches a human
  decision the mandate did not authorize and no autonomous route remains, it
  expires the mandate with reason `human gate` and removes the session guardian
  through the adapter. The pending decision stays recorded; deterministic
  failures and intermediate phases with an eligible route do not end it.
- **Deterministic gates never switch off.** The commit gate (test/build/lint)
  runs in every mode. The mandate skips APPROVALS, never PROOF.

> **Honest limit, stated so nobody over-trusts it.** Recognising the sentence is
> still prose: no platform hook can tell "I want yolo" from "what is yolo?".
> But the failure is SAFE — without a call there is no mandate, and the agent
> keeps stopping at the gates.

---

## Lean guardrails
- Do not ask about `unattended` routinely. The safe default is attended;
  explicit recovery intent is consent for the guardian and needs no second ask.
- The hook owns the file. This skill never writes `.helmit/yolo.json` directly.
- Creates NOTHING outside the project or the session. The guardian
  `/helmit:heartbeat` arms is a session cron that dies with the session — no
  OS scheduler entry, no arming file.
- `off` never fails and never asks. Disarming is not a negotiation.

## Session safety (tree lock + typed stop — REQ-090/REQ-091)
- Arming and disarming WRITE local state, not product artifacts: no tree lock
  is taken (the lock guards the artifacts `/implement` and friends rewrite).
  Report `lock.sh status` only if the user is about to start work.
- Record the typed stop last: `bash
  "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append session_stop reason=<r>`
  — `clean` when the arm/disarm finished, `awaiting_input` while the
  unattended question is on the table. A missing `session_stop` means
  `interrupted`, and only `interrupted` may be auto-resumed. Exception: when a
  narrative handoff closes the session, append the `clean` stop FIRST and
  write the handoff as the session's LAST write — the ORDER CONTRACT in
  `core/hooks/handoff.sh` (REQ-149).

## Cross-platform note (adapter contract)
- Pure core: `.helmit/` plus `yolo.sh`. No platform primitive; identical on
  Claude Code and Codex.
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer (MANDATORY — every HelmIt command ends with this)
Before returning control, ALWAYS:
1. Leave `STATE.md` untouched — arming changes no workflow position; the work
   the mandate authorizes is what moves it.
2. Tell the user, in the language from `config.json`, what is in force now and
   how it ends (by fulfilled scope, or `/helmit:yolo off`). Then offer the next
   workflow step exactly as `/helmit:next` would.
