---
name: next
description: "Compact session resume and deterministic router. Reads one executable snapshot, explains the current position and either offers or continues the eligible act."
---

# /next

Resume a HelmIt project without making the user remember the lifecycle. This is
a safety net for a new session or lost context; every delivery skill also names
its own next act.

An explicit clear, localized, directly verifiable request may use `/implement`'s
direct-work guidance immediately. It does not require this resume protocol or a
new CHG merely because the roadmap or another task exists. Registered task work
still follows its current identity and proof; unresolved overlapping edits are
inspected before proceeding.

Under supervision, report the next eligible act and continue when the user's
request already authorizes it. Under an active mandate, keep the same live flow
running until its declared stopping point or a real gate.

## Preconditions

1. If `.helmit/` is absent, offer `/helmit:setup` and stop.
2. Run `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/next-status.sh" show` once.
   This is the canonical, read-only routing snapshot. Relay any non-`READY`
   verdict and use its `position`, `route`, `artifact`, `pending decision`,
   `proof`, and `advance when` fields. Do not independently parse STATE,
   ROADMAP, CHANGES, REQUIREMENTS, lock, mandate, drift, or reconciliation.
   When the snapshot reports remote synchronization debt, relay its branch,
   upstream, ahead, behind and oldest local-only commit with the next act. The
   comparison uses the local tracking ref and never implies a fetch, push, PR
   or merge.
3. Run `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/handoff.sh" render`. The content decides:
   RELAY only current narrative or concrete pendency and stay silent about handoffs
   when neither exists. A superseded handoff is history, not guidance.

Both calls are pure reads. The snapshot owns phase, dependency, route, open CHG,
legacy-correction compatibility, Inbox counts, and safety diagnostics. Handoff
reuses the same derivation and adds only temporal/narrative context.

## Interpret the verdict

- `READY`: the route is eligible. Continue if already authorized; otherwise
  offer the named skill/action in one sentence.
- `DECISION`: ask only for the material decision named by the snapshot. A
  mandate may answer only within its declared authority.
- `PAUSE`: preserve all work and explain the concrete concurrent executor,
  interrupted work, honest stop, or unknown lock. Never reset or discard.
- `BLOCKED`: name the unmet dependency or external prerequisite and the action
  that resolves it.
- `PROOF_FAILED`: open the named validation artifact, diagnose the failed
  command or requirement proof, and repair only within the authorized scope.

Advisory drift and a dirty worktree do not stop routing by themselves. Inspect
only the affected commitment or overlapping paths. Pause when a material
commitment is ambiguous, another executor is proven active, or the intended
edit conflicts with unknown work.

## Route semantics

The executable snapshot owns the state-to-route mapping. Public routes mean:

- `spec-product`: define the product commitment.
- `prepare` or `env`: complete only the preparation needed for execution.
- `spec-delivery`: define the next delivery commitment; an explicit future
  target is allowed and never activates execution by itself.
- `implement`: plan/adapt as needed, implement, verify focused behavior, and
  create logical reviewable commits. When the snapshot names an open CHG and
  `.helmit/CHANGES.md`, resume that localized correction before returning to
  the preserved delivery position.
- `ship`: run final configured quality and requirement proof, record the
  delivery milestone, and refresh the derived dashboard.
- `repair`: diagnose the recorded proof failure, then rerun the proof it names.
- `complete`: report that the current roadmap is closed; new work still needs
  authorization.

`chart` remains a compatibility alias/capability, not a routine approval stop.
`validate` remains an optional diagnostic, not a required lifecycle stage.
Legacy track metadata never changes routes, checks, or approval boundaries.

## Safety and authority

The snapshot has already run the read-only preflight for this routing boundary;
do not repeat it before the first write unless the tree changed meanwhile.
`CHANGED` is an advisory inventory; inspect overlapping targets and preserve
unrelated edits and the existing index. Only
`BLOCKED_CONCURRENT`, backed by a fresh lock and matching executor lease, is a
global safety stop.

At commit time, stage only intended paths or hunks, review the staged diff, and
run the declared focused verify plus the independent staged quick floor. Never
use `git add -A`, `--no-verify`, or a destructive cleanup. Files not named by a
plan are evidence to review, not foreign ownership that automatically blocks.

Pause for:

- a material product or architecture choice;
- an external, destructive, privileged, or public action without authority;
- proven concurrent execution or unresolved overlap;
- a failed deterministic proof that needs diagnosis.

Do not pause merely for planning detail, task count, phase reordering, advisory
drift, Inbox edits, dashboard generation, or compatible pre-existing changes.

## Mandate and continuity

The snapshot's mandate line is authoritative. If a mandate is in force, show
its scope and stopping point and immediately execute each eligible route in the
same live flow. Wait on active executors by events. Heartbeat only recovers an
unexpected interruption; it never supervises normal progress or replaces the
live chain.

Do not write a clean stop, terminal handoff, or terminal response while the
mandate is active and unfulfilled. A real gate records its truthful reason and
preserves the exact next action. When the stopping point is reached, let the
mandate owner expire it and report completion without extra ceremony.

## Inbox at useful boundaries

At a delivery boundary, mention open/unrouted counts from the snapshot in one
line. Triage remains optional unless the user asked for it; an urgent item may
be triaged at any time.

Read only the next batch with
`inbox-receipt.sh summary --limit 5`. Classify each item with the user as:

- direct execution for an authorized clear, localized, directly verifiable fix;
- limited CHG when restoration, maintenance, copy or configuration needs investigation, decisions, coordination or continuity recorded;
- backlog with an explicit destination;
- a new delivery when it creates durable behavior or a larger commitment.

A CHG is registered in `CHANGES.md` and never manufactures a requirement.
Direct work follows `/implement`'s direct-work guidance without a new task,
CHG or STATE transition, including labels in source and known-cause bug fixes.
Classify by meaning and impact, not file paths or line count. A resolved Inbox
item records its actual resolution; it does not need a CHG solely for closure.
After any Inbox write, run `inbox-receipt.sh maintain --limit 0`; it validates
the active structure and archives resolved history. Inbox edits are ordinary
tracked work and are never blocked merely because the Inbox was touched.

## Explicit repair only

A read-only snapshot may report `repair available` when STATE disagrees with
the artifacts. Explain the evidence first. Run
`next-status.sh repair-state` only when repair is authorized by the current
request or mandate. The repair operation publishes the dashboard itself; never
hide the repair inside `/next` or add a second render/check sequence.

If the snapshot reports ambiguous interrupted work, structural corruption, or
an unknown commit/lock result, load
`references/recovery.md` and follow only the matching branch. Do not load that
reference on the healthy path.

## Output

Use one compact paragraph in the project's language:

- where the project is;
- the exact next act and its artifact;
- the proof that will establish success;
- the criterion for advancing;
- any real gate, pending material decision, active mandate, or relevant Inbox
  count.

Do not narrate absent problems, enumerate internal hook calls, or restate the
whole lifecycle. A direct user command is allowed even if it targets future
work; `/next` gives direction and safety evidence, not permission.

## End of session

When the user explicitly says the session is ending, persist known decisions in
their owning artifacts first, run `state-retain.sh compact`, then run
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/session-close.sh" clean`. Ask one short
question about any decision not yet
recorded only after the handoff is durable; skip the question when unattended.
This procedure never fires between routes of an active mandate.
With an active mandate, continue to its stopping point rather than recording a
clean session end.

## Platform contract

Core behavior and snapshot fields are identical in Claude Code and Codex.
Adapters translate only skill invocation and event waiting. References such as
`/helmit:<skill>` use the Claude Code adapter's syntax; on Codex, use the skill
selector.
