---
name: ship
description: "Verifies and closes one delivery in a single milestone: exact reusable full-suite proof, requirement coverage, binary acceptance, proven REQs, roadmap/state update, dashboard, and optional PR. Never merges."
---

# /ship

Verify and close one delivery. Ship owns the final validation; running
<code>/validate</code> first is optional. “Shipped” means the promised outcome
has exact passing evidence and the local milestone is recorded. It never means
merged.

## Preconditions

1. Run <code>bash "&lt;plugin&gt;/core/hooks/handoff.sh" render</code> and RELAY
   only what it prints. The content decides: actionable sections are surfaced;
   fixed core only means stay silent about handoffs.
2. Run <code>commit-transaction.sh recover</code>. Unknown lock ownership
   preserves the lock and stops the affected commit.
3. Require an approved delivery SPEC, an executable CHART, and every planned
   task complete. Open tasks route to <code>/implement</code>.
4. Run <code>preflight.sh check</code> once. Changed files are advisory;
   proven concurrent execution or unresolved overlap stops only the affected
   closure.
5. Acquire <code>lock.sh acquire</code> before writes and always run
   <code>lock.sh release</code> before returning.

After the delivery id is known and the lock is acquired, expose ship as the
operational activity <code>ship.&lt;id&gt;</code>:

    bash "<plugin>/core/hooks/run-log.sh" append task_claimed task=ship.<id>
    bash "<plugin>/core/hooks/executor-lease.sh" renew --task ship.<id>

This presence identity is not a CHART task and never counts as implementation
time. On successful closure append <code>task_committed</code> with
<code>verify_result=passed</code>; on a controlled failed closure append it with
<code>verify_result=failed</code>. A human gate keeps the claim open and records
<code>awaiting_input</code>, so the dashboard presents the pause rather than
inventing completion. Release the lock only after the final presence transition.

Deterministic proof remains mandatory under every autonomy mandate.

## Process

### 1. Validate the current candidate

Check registered source drift for this delivery. Editorial or unrelated drift
is advisory. Unresolved material drift routes to <code>/spec</code>.

Build set A from REQs assigned to the delivery and set B from
<code>satisfies:</code> on completed tasks. Historical <code>covers:</code>
counts as satisfies; <code>supports:</code> does not. A − B must be empty.

For each mapping, run <code>quality-receipt.sh proof</code> with its required
and provided levels. Structural &lt; mechanism &lt; behavior; human proof is
separate. Missing, failing or insufficient mapped evidence routes to
<code>/implement</code> or <code>/chart</code> according to the gap.

Also review whether the evidence actually demonstrates the promised result and
whether a material limitation is preserved in the existing SPEC, plan mapping,
task, or validation review. Exit zero alone is not acceptance. Do not assign an
agent-completable check to the user; human proof remains for judgment or access
automation cannot provide.

Evaluate every acceptance criterion as pass, fail or <code>[human]</code>.
Never self-grade or clear a human item. An unresolved human criterion pauses
this closure even under YOLO, preserves the candidate, expires only the
fulfilled/blocked mandate scope, and records <code>session_stop reason=gate</code>.

### 2. Run or reuse final complete proof

Run exactly once:

    bash "<plugin>/core/hooks/quality-receipt.sh" ship --phase <id>

The hook reuses any passing validate, integration or ship receipt only when its
product fingerprint and exact configured command list still match. Otherwise it
runs configured test, build and lint once and records
<code>ship:&lt;id&gt;</code>. Never execute those commands separately at this
boundary. A red or interrupted run leaves the delivery open and routes to
<code>/implement</code>.

The configured commands share one disposable proof worktree of the exact
committed HEAD tree. Repository-relative mutations are removed with it; the
receipt names the tested tree and the original checkout and index stay intact.
This reuses the authorized local toolchain without installing dependencies. It
is not an OS sandbox: absolute paths, network, and external-service effects keep
their normal authorization and safety boundaries.

### 3. Record validation and close atomically

Write <code>VALIDATION.md</code> from the canonical template with the receipt,
coverage sets, proof levels, binary acceptance, any human review and precise
failure routing. This artifact is the final scoreboard whether validation was
invoked separately or only through ship.

With a passing matching receipt, run:

    bash "<plugin>/core/hooks/req-close.sh" --phase <id>

The command deterministically promotes only this delivery's covered REQs and
closes explicitly linked Inbox items. Set STATE to
<code>shipped:&lt;id&gt;</code> or <code>complete</code> when no eligible delivery
remains, then make the ROADMAP transition last:

    bash "<plugin>/core/hooks/roadmap-status.sh" mark <id> shipped

That hook is the only writer of the shipped cell and publishes one consistent
dashboard snapshot containing the requirement, Inbox, STATE and ROADMAP changes.

Stage only VALIDATION, REQUIREMENTS, ROADMAP, STATE and any Inbox change that
these operations actually produced. Review the staged diff and make one normal
milestone commit under the independent Git floor. Unrelated changes and
legitimate unrelated Inbox edits remain outside the candidate.

### 4. Report the current local view

The canonical requirement and ROADMAP writers publish the dashboard
automatically and atomically. Do not add a model-driven render/check sequence.
An open local board notices the replacement within a few seconds and preserves
its reading state. Dashboard failure is visible but does not undo a valid
milestone; the next session repairs an absent or stale projection.

Run <code>delivery-report.sh --phase &lt;id&gt;</code> and relay its output.
Report task outcomes, all logical commits, proven requirements and the final
receipt without reconstructing a second report by hand. Metrics are optional
observations, never a gate.

### 5. Optional PR and route forward

Run <code>remote-status.sh show</code> and relay its local tracking ref facts: branch,
upstream, ahead, behind and the oldest local-only commit. State explicitly that
the comparison does not fetch and may be older than the server. When work is
only local, recommend the action consistent with <code>branch_mode</code> and
<code>ship.create_pr</code>, then ask the human to choose synchronization or
deferral. Create or push only after that explicit remote-action authority;
never merge, in any mode. A deferral is recorded before returning:

    bash "<plugin>/core/hooks/run-log.sh" append remote_sync_deferred branch=<branch> upstream=<upstream> ahead=<n> behind=<n> head=<sha>

The debt remains visible through <code>/next</code> while the local comparison
still reports ahead or behind. A missing upstream is reported as an unresolved
comparison, never treated as synchronized.

Read the live autonomy mandate after closure:

- phase scope completes after this delivery ships and then expires;
- full scope immediately starts the next eligible delivery in the same active
  flow until its target is reached;
- no mandate returns control with the next delivery or project completion.

Do not emit a terminal intermediate response or <code>session_stop=clean</code>
while authorized full-scope work remains. Heartbeat is recovery-only and never
supervises normal cross-delivery progress.

## Lean guardrails

- Ship is one verification-and-closure milestone, not a second validation run.
- Reuse exact valid evidence; rerun only proof invalidated by product or command
  changes.
- No scores, release ceremony, version bump or changelog unless requested.
- Preserve existing work and index selections. Never bypass hooks.
- Close the session last through <code>&lt;plugin&gt;/core/hooks/session-close.sh</code>: clean only at
  the authorized stopping point, gate for a human decision, awaiting_input
  after a direct question.

## Cross-platform note

Local proof and milestone mutation are repository operations shared by Claude
Code and Codex. PR tooling differs by host; the authority boundary and the
never-merge rule do not.

## Guidance footer

Report the delivered outcome, exact final proof, dashboard path, any remaining
human decision, and the next eligible action. Do not tell the user to run a
second validation step.
