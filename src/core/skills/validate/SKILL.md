---
name: validate
description: "Optional compatibility alias for final delivery diagnosis. Runs or reuses the same complete proof used by ship, checks requirement coverage and acceptance, and leaves reusable evidence without adding a mandatory lifecycle stage."
---

# /validate

Diagnose whether a completed delivery is ready to ship. This is an optional
compatibility alias for teams that want to inspect final proof separately.
<code>/ship</code> performs the same validation itself, so the normal route
does not require this command.

## Preconditions

1. Run <code>bash "&lt;plugin&gt;/core/hooks/handoff.sh" render</code> and RELAY
   only what it prints. The content decides: actionable sections are surfaced;
   fixed core only means stay silent about handoffs.
2. Require the approved delivery SPEC and an executable CHART whose tasks are
   all complete. Open work routes to <code>/implement</code>.
3. Run <code>preflight.sh check</code> once. Changed files are advisory;
   proven concurrent execution or unresolved target overlap stops only the
   affected diagnosis.
4. Acquire <code>lock.sh acquire</code> before writing the diagnostic and run
   <code>lock.sh release</code> before returning.

## Process

### 1. Run the same final proof

Check registered spec drift for this delivery. Editorial or unrelated drift is
advisory; unresolved material drift routes to <code>/spec</code>.

Run:

    bash "<plugin>/core/hooks/quality-receipt.sh" validate --phase <id>

The hook reuses any passing complete-suite receipt bound to the exact current
product fingerprint and exact configured commands. Otherwise it runs the
configured test, build and lint commands once and records
<code>validate:&lt;id&gt;</code>. A focused task check cannot satisfy this
boundary.

The complete commands run together in the shared disposable proof worktree of
the exact committed HEAD tree. Repository-relative mutations disappear on
cleanup and the receipt records the tested tree. The mechanism reuses the local
toolchain and installs nothing; it does not contain absolute-path, network, or
external-service effects, which keep their normal authority boundaries.

### 2. Check the delivery contract

- Compare every REQ assigned to the delivery with <code>satisfies:</code> on
  completed tasks; historical <code>covers:</code> is equivalent and
  <code>supports:</code> never claims coverage.
- For every mapped REQ, call <code>quality-receipt.sh proof</code> with its
  required and provided levels. Structural &lt; mechanism &lt; behavior; human
  evidence is separate.
- Confirm that the mapped evidence demonstrates the promised result and carries
  any material limitation recorded in the existing SPEC, plan mapping, task, or
  review. A passing but irrelevant check remains insufficient. Human proof is
  reserved for judgment or access the agent cannot supply within scope.
- Evaluate every acceptance criterion as pass, fail, or <code>[human]</code>.
  Never invent a score or clear a human item.

### 3. Leave reusable diagnostic evidence

Write or refresh <code>VALIDATION.md</code> from the canonical template with
the receipt snapshot, suite result, coverage set, proof levels, acceptance and
precise failure route. Do not mark requirements proven or mark the delivery
shipped here; <code>/ship</code> owns the atomic closure.

An optional diagnostic does not require a standalone commit. If this command is
used as an explicit durable review point, stage only its intended artifacts and
make a normal logical commit. The receipt remains reusable because control-only
files do not change the product fingerprint.

Run <code>roadmap-status.sh</code> for compatibility. Its canonical write
publishes the dashboard automatically; do not ask the model to render or check
the projection separately. A passing diagnosis offers <code>/ship</code>; a failure
routes to <code>/implement</code>, <code>/chart</code>, or <code>/spec</code>
according to the failed contract.

## Lean guardrails

- This command diagnoses; it does not fix product code or create a second
  required approval.
- Reuse exact valid proof. Never run the same complete suite again merely
  because the user invoked <code>/ship</code> next.
- Preserve unrelated work and the existing index. Never bypass the Git floor.
- Close through <code>&lt;plugin&gt;/core/hooks/session-close.sh</code>: clean for
  a completed diagnostic, gate for a human criterion, awaiting_input after a
  direct question.

## Cross-platform note

The diagnostic uses repository files and deterministic hooks only, so the
contract is identical on Claude Code and Codex.

## Guidance footer

Report pass/fail, any human item, the reusable receipt scope and the exact next
route. Make clear that validation was optional and ship remains the milestone.
