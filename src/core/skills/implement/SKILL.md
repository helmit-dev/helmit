---
name: implement
description: "Plans when needed, implements delivery outcomes directly by default, records logical commits, and proves completed tasks. Delegation, worktrees, and integration boundaries are optional risk-based tools."
---

# /implement

Implement an approved delivery. Planning is the first implementation activity
when the persisted `CHART.md` is absent, draft, incomplete, or stale. `/chart`
exposes that same planning capability separately; it is not a required prior
stage.

Direct work in the current checkout is the normal path. Delegation, parallel
execution and disposable worktrees are tools selected only when independence,
isolation or measured wall-clock benefit justifies their coordination cost.

## Preconditions

1. Render resume context with
   `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/handoff.sh" render` and RELAY only
   what it prints. The content decides: actionable sections are surfaced;
   fixed core only means stay silent about handoffs.
2. Run `commit-transaction.sh recover` before claiming work and before retrying
   a commit. `UNKNOWN_LOCK` preserves the lock and stops the affected commit.
3. For a delivery, the approved SPEC, KEEL commands and commit floor must exist.
   An open CHG instead requires its canonical ledger row and declared focused
   proof; it preserves the delivery STATE and needs no SPEC or CHART. Track
   never changes the workflow or proof.
4. Run `preflight.sh check` once before the first write. `CHANGED` is advisory:
   inspect the status and target diffs, preserve unrelated edits, and continue
   when overlap is understood. `BLOCKED_CONCURRENT` stops only when a fresh
   lock and matching executor lease prove conflicting execution.
5. Acquire `lock.sh acquire` before writing and run `lock.sh release` before
   returning.

These checks remain under YOLO. A mandate carries eligible human decisions; it
does not bypass deterministic proof, external authority or destructive safety.

## Process

### 0. Resume an open localized correction

When the routing snapshot names one open CHG, work from that row before the
preserved delivery position. Its task identity, intent, observed paths and
focused verify are the complete execution contract; do not manufacture a SPEC,
requirement, chart, phase, or STATE transition.

Implement the correction directly and run its declared proof. If durable scope
appears, run `change.sh classify --kind <kind> --stage in-flight`, preserve the
work and route the new commitment to `/spec`. Otherwise, run a fresh
`change.sh snapshot`, then
`change.sh prepare-close --base <base> --ledger <ledger> --id <CHG-NNN>`.
Change only that row from `open` to `done`, stage the intended paths plus
`.helmit/CHANGES.md`, review the staged diff and validate it with
`change.sh candidate --id <CHG-NNN> --subject <canonical-subject>`.

Land the normal protected commit, then run `change.sh recover --id <CHG-NNN>`
to record its proof idempotently. The CHG writer publishes the dashboard; after
the row closes, the next snapshot returns to the untouched delivery position.
Release the lock and record the typed clean stop last. An Inbox-linked CHG also
closes exactly its linked item in the same candidate.

### 1. Prepare or adapt the executable plan

Read KEEL, REQUIREMENTS, ROADMAP, the delivery SPEC and any existing CHART. If
the plan cannot guide implementation, create or adapt it using the `/chart`
contract: outcome tasks with stable identity, `satisfies:`/`supports:`, focused
`verify:`, requirement-to-test mapping, and optional execution hints. Persist
`status: approved` and `prepared-by: agent` as the compatibility representation
of an executable plan. Do not stop for routine plan approval, task count or
technical reordering. Pause only for a material product/architecture choice or
authority the user has not supplied.

Refresh the optional repo map before relying on it. If unavailable, inspect the
relevant code directly. Treat `files:` as a likely-impact observation: it may
help navigation, staging and recovery, but it never defines ownership and
drift never blocks a task or commit.

### 2. Choose the simplest execution shape

- Work directly when one agent can safely make progress in the current
  checkout. This is the default.
- Delegate only work that is genuinely independent and when the host and user
  authorization allow it. Keep orchestration in the current flow and wait for
  executor events; heartbeat is only interruption recovery.
- Use a disposable worktree when an experiment, risky change or concurrent
  edit materially benefits from isolation. Never create one merely because a
  plan has several tasks.
- Integrate sequentially when work converges on shared behavior. Resolve actual
  overlap from the diff, not from a declared-file ownership rule.

If delegation is used, give the executor only the outcome, anchor, relation,
proof contract and relevant KEEL context. The orchestrator owns STATE, WAL,
integration and commits. An executor never writes machine-local `.helmit/`
state. Remove any disposable worktree after its result is integrated.

### 3. Execute and checkpoint logically

Before starting an outcome, record:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append task_claimed task=<task> files=<observed,paths>
```

Omit `files=` when genuinely unknown. Inspect before editing and keep changes
focused. When an observable defect has a deterministic reproduction, prefer to
run it first and preserve the relevant red result before correcting it; the
passing regression becomes part of the task proof. A behavior-preserving
refactor starts from a green baseline and preserves or strengthens
characterization. Documentation and new mechanisms use the structural,
mechanism, or behavior check that matches their promise. Never weaken a check or
introduce a temporary defect merely to create a red run.

A logical commit is a coherent, reviewable green checkpoint. It may be:

- one of several commits for a larger task; or
- one commit that completes closely related tasks.

Every source/test commit carries each associated stable task and requirement
relation in its subject, for example:

```text
feat(auth): introduce token parsing [3.1 supports: REQ-012]
feat(auth): complete login [3.1 satisfies: REQ-012] [3.2 satisfies: REQ-013]
```

Before a commit, stage only intended paths or hunks and review the staged diff.
Wrap the attempt with `commit-transaction.sh start <task-set>` and
`commit-transaction.sh landed <task-set> <commit>`. After every landed logical
commit record:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append commit_checkpoint tasks=<comma,separated> commit=<hash> proof=<quick-floor|task-verify|integration>
```

An intermediate commit leaves the task unticked. The PreToolUse gate resolves
all referenced tasks and applies the staged quick floor, but it runs a task's
final `verify:` only when that same candidate changes the task marker to `[x]`.
The independent Git pre-commit floor repeats whitespace and staged shell,
Python and JSON syntax checks. Never use `--no-verify`.

### 4. Complete tasks only with complete proof

When the whole task outcome is present:

1. Run or prepare its declared focused `verify:` against the candidate. Confirm
   that it demonstrates the requested result, not only that the command exits
   zero. Record any material limitation in the existing task, mapping, SPEC, or
   final review; do not create a separate proof ledger.
2. Change its marker to `[x]` and update the compatible STATE position in the
   same closing candidate.
3. Reference every completed task in the commit subject. The commit gate runs
   each distinct final verify once; a shared command is deduplicated.
4. After the commit lands, append one record per completed task:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append task_committed task=<task> commit=<hash> verify_result=passed
```

Several records may point to the same coherent commit. Compare actual commit
paths with any `files:` hints and record meaningful drift in the delivery
report or `files_drift=`; it remains observational.

The commit gate materializes the exact staged tree under the ignored local
`.helmit/proof-worktrees/` area and runs every distinct final `verify:` in that
disposable Git worktree. Tracked unstaged and untracked files are absent;
repository-relative writes disappear during cleanup, while the original index
and checkout remain unchanged. Failure to prepare, verify, or clean the exact
candidate blocks completion. The sandbox reuses the authorized local toolchain;
it installs nothing and is not an OS security boundary. Absolute paths, parent
traversal, network and external services retain their ordinary authority and
side-effect rules.

If a final verify fails, keep the task open, fix within bounded attempts and
retry. Stop only when the failure needs a material user decision or external
change. A timeout is not a failed verdict: inspect the staged state and use
commit recovery before retrying.

### 5. Prove integration where dependency or risk changes

Do not run the complete configured suite after every task group or historical
wave. Create an integration boundary only when previously independent changes
converge, a risky cross-cutting contract changes, or proceeding would make a
failure materially harder to localize. Record why, then run exactly once:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/quality-receipt.sh" integration --phase <id> --reason <stable-slug>
```

The hook runs the complete configured `test`, `build`, and `lint` commands in
order inside one disposable worktree of the exact committed HEAD tree and binds
the receipt to that tree and its Git-object product fingerprint. Relative build
outputs never alter the current checkout. Failure blocks only work that depends
on that integration result. Unrelated safe work may continue. Final delivery
proof and closure remain `/ship`'s responsibility.

### 6. Finish or continue (REQ-314)

Keep eligible implementation in the same active turn. When delegated work is
live, use the host's event-driven wait (`wait_threads` on Codex) and resume on a
completion or attention event. Do not return a terminal response while
authorized work remains live. Heartbeat never polls or supervises normal
implementation; it only recovers an unexpected interruption.

After a real task transition, update its canonical task record and compact
STATE, then call the deterministic ROADMAP writer last. That writer publishes
the derived dashboard in the same local operation; do not add a model-driven
render/check sequence.
Dashboard failure is advisory and visible, while the successful task result
remains valid. Name the next route, artifact, applicable gate or deterministic
proof, and advance only when that named proof or decision criterion is
satisfied. Do not maintain duplicate status prose.

After all delivery tasks are complete, run
`delivery-report.sh --session <current-session>` and relay its output as the
single implementation report derived from Git and WAL. Under an eligible
mandate, continue immediately to the next authorized action; otherwise offer
`/ship`.

## Lean guardrails

- Deterministic gates judge candidate content; advisory metadata does not.
- Do not manufacture tasks, commits, waves or worktrees merely to satisfy a
  ceremony. Preserve stable identities and auditable requirement relations.
- Prefer behavior evidence over tests that freeze wording, internal command
  order or a particular agent mechanism.
- Do not transfer a check or inspection to the user when it can be completed by
  the agent within the authorized scope. Human proof is for judgment or access
  that automation genuinely cannot provide.
- Persist new scope, durable design decisions and user choices immediately in
  their canonical owner. Capture out-of-scope findings in INBOX and continue.
- Use bounded retries. Never discard unrelated work, replace the index, or
  bypass a hook.
- Append the typed `session_stop` last: `clean` at a completed stopping point,
  `gate` for a material human decision, `awaiting_input` after asking, and no
  record when the session was genuinely interrupted.

## Cross-platform note

The contract is stable identities, logical commits, focused completion proof,
the independent Git floor and risk-based integration proof. Claude Code and
Codex may offer different delegation or worktree mechanisms; absence of either
does not degrade the normal direct path.

## Guidance footer

Before returning control, state the completed outcomes and proof, the current
delivery position, and the next material action. Offer to continue; do not
insert a chart approval or wave boundary that the result does not need.
