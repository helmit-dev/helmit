---
name: chart
description: "Prepares or refreshes an executable delivery plan with outcome tasks, requirement links, focused proof, and optional execution hints. Compatible planning alias; implementation can perform the same planning inline."
---

# /chart

Prepare the executable plan for one approved delivery spec. This is a reusable
planning capability and a compatibility alias: `/implement` performs the same
work when no usable plan exists. Planning is part of delivery, not a routine
human-approval stage.

The public concept is a **plan**. The persisted filename remains `CHART.md`, and
`status: approved` remains the compatibility value meaning **executable**. It
does not claim that a human reviewed the task decomposition.

## Preconditions

1. Read the resume context with
   `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/handoff.sh" render` and RELAY only
   what it prints. The content decides: actionable sections are surfaced;
   fixed core only means stay silent about handoffs.
2. `.helmit/`, the target approved delivery `SPEC.md`, KEEL commands and
   `config.json.commands` must exist. A future approved delivery may be planned
   and parked without changing the currently active delivery.
3. Before the first write, run
   `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/preflight.sh" check` once. `CHANGED`
   is advisory. `BLOCKED_CONCURRENT` stops only the affected operation when a
   fresh lock plus matching executor lease proves concurrent execution.
4. Acquire `lock.sh acquire` before writing and always run `lock.sh release`
   before returning. Preserve unrelated edits and the existing index.

## Process

### 1. Understand the delivery

- Read KEEL, REQUIREMENTS, ROADMAP and the target SPEC.
- Refresh and use the optional repo map when available. If it is unavailable,
  inspect only the code needed to understand the affected behavior.
- Confirm required product foundations exist or are planned. Pause only for a
  newly discovered material product or architecture decision; technical
  decomposition and task count are agent responsibility.

### 2. Build outcome tasks

Use `core/templates/CHART.md`. For every task record:

- stable id `<delivery>.<n>` and a one-line `anchor`;
- exactly one `satisfies:` or `supports:` relation;
- a focused `verify:` that can prove the complete outcome;
- optional `files:` with likely paths, as an observation only.

A task is a coherent outcome slice, not a commit-sized unit or a clean-context
agent assignment. Use as many tasks as make the result understandable. Split a
delivery only when its product scope should be independently delivered, not
because an internal count crossed a threshold.

Map every delivery REQ to at least one `satisfies:` task and classify its
required/provided proof as `structural`, `mechanism`, `behavior`, or `human`.
Executable evidence orders structural < mechanism < behavior; human evidence is
separate. A behavioral requirement backed only by text matching is a planning
gap.

Choose how the proof becomes informative, without adding a field to the task:

- For an observable defect with a deterministic reproduction, prefer recording
  the natural red result before the fix and retaining the green regression.
- For behavior-preserving refactoring, establish a green baseline and preserve
  or strengthen characterization; never manufacture a failure.
- For documentation or schema changes, use structural proof when structure is
  the promise. For a new mechanism, require mechanism or behavior evidence
  according to the user-visible claim.

The mapped check must demonstrate the promised result, not merely execute
successfully. Put a material limitation in the existing SPEC acceptance,
mapping, or task wording instead of creating a proof ledger or mandatory field.

### 3. Add execution hints only when useful

- Name independent candidates only when parallel work is likely to shorten the
  path without introducing integration overhead.
- Suggest a disposable worktree only when isolation materially improves safety
  or experiment quality.
- Name an integration boundary only for a real dependency convergence or a
  risk increase that merits the complete configured proof.

These are hints, not mandatory waves. `/implement` may adapt them when the code
reveals a better route. `files:` never grants ownership and drift never blocks.

### 4. Make the plan executable

- Write or update `CHART.md` with `status: approved` and `prepared-by: agent`.
  Preserve historical `approved-by:` values when editing an older chart; do not
  fabricate one for a plan produced by the agent.
- If this is the active delivery, update STATE to `chart-approved:<id>` for
  persisted compatibility and run `roadmap-status.sh`. A parked future plan
  leaves the active STATE unchanged.
- Run deterministic structural checks for the plan. Do not run the complete
  product suite merely because planning changed.
- Stage only intended plan/state paths, review the staged diff, and commit the
  planning change when it is a useful durable checkpoint. No separate human
  approval is required unless planning exposed a material decision.
- Report the resulting tasks, proof and material assumptions, then offer or
  continue `/implement` according to the active autonomy mandate.

## Lean guardrails

- Do not write product code in this skill.
- Do not stop for task count, technical reordering, optional parallelism, or
  plan wording.
- Do not make `files:` a fence and do not infer parallel safety from it alone.
- Prefer behavior proof over assertions that freeze skill prose or command
  order when the order is not itself the product contract.
- Never weaken a check, inject a temporary defect, or demand a failing run only
  to manufacture red/green history.
- Persist new scope, durable decisions and user choices in their canonical
  owner immediately. Capture out-of-scope findings in INBOX and continue.
- Before returning, append a typed `session_stop`: `clean` when planning is
  complete, `gate` for a material human decision, or `awaiting_input` after a
  direct question. A missing stop remains the interruption signal.

## Cross-platform note

Planning uses repository files and deterministic hooks only. Parallel agents
and worktrees are optional implementation mechanisms, so this skill behaves the
same on Claude Code and Codex. On Codex, invoke the skill through its selector.

## Guidance footer

Before returning control, say where the delivery now stands, identify the next
material action, and offer to implement it. Do not add an approval ceremony to
an already executable plan.
