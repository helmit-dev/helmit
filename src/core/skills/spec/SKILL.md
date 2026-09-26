---
name: spec
description: "Defines the product or a concrete delivery with detail proportional to uncertainty and impact. Uses a short CHG for localized corrections, preserves stable requirements, and asks only about material decisions."
---

# /spec

Define the result before implementation. Reuse what the user and repository
already establish; ask only when missing information can change scope,
acceptance, authority, or a material product decision.

When a numbered phase absorbs an Inbox item, replace its triage prefix with
`[TRIADO -> FASE <id> / REQ-001,REQ-002]`, listing the exact REQs registered
for that capture.  Never infer this link from prose; a legacy phase-only prefix
stays unlinked and is never eligible for automatic closure.

---

## Direct work before level detection

A clear, localized and directly verifiable request can be executed directly
through the direct-work guidance in `/implement`, without creating a CHG, spec,
task or phase. Labels in source, cache ignores and known-cause bug fixes can
qualify. Judge meaning, uncertainty and impact, not paths or line counts.
Use CHG when bounded work needs investigation, decisions, coordination or
continuity recorded; use a delivery for a new material product commitment.
For direct work, skip level detection and lifecycle artifact/stop writers below.
Keep ordinary Git checks, authorization and unrelated work intact.

## Transparent level and target

Begin by naming: (i) the detected level (**PRODUCT** or **DELIVERY**),
(ii) the concrete target (e.g. "Phase 1 — <name>"), (iii) WHY — the state
that determined it (e.g. "SPEC.md is `approved`, Phase 1 has no spec yet"),
and (iv) that an explicit product or phase target overrides the default.
The stored names `application` and `feature` remain compatible aliases; do not
make the user learn them.

## Level detection (deterministic, by state — with explicit override)

- `.helmit/SPEC.md` has `status: stub` → **PRODUCT** level.
- `status: draft` → resume the PRODUCT level and resolve its material decision.
- `status: approved` → **DELIVERY** level, for the next phase per ROADMAP order
  (first phase whose `requires:` are satisfied and has no approved spec yet).
- **OVERRIDE:** if the user explicitly asks for a level or target out of order
  ("revise the product spec", "spec delivery X"), honor the request over the
  state-based default. Do not set an approved spec back to `draft` from a hash
  or editorial change alone; first inspect whether the commitment changed.

## Working-tree safety (ADR-018)

Before the first write, lock or expensive gate, run
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/preflight.sh" check` once. `READY`
means no changes were observed. `CHANGED <paths>` is advisory: inspect Git
status, the staged and unstaged diffs, and every target already modified; it
never blocks merely because a draft or unrelated file exists.
`BLOCKED_CONCURRENT` stops only when a fresh lock and matching fresh executor
lease prove another executor is active in this checkout.

Preserve unrelated edits and the existing index. A prior draft is resume
context found from the requested target and current artifacts, not an ownership
verdict. Continue through compatible, understood changes; pause only the
affected operation for an unresolved overlap or unknown intent. Before commit,
review the staged diff and stage only intended paths or hunks—never `git add -A`.
Do not repeat the global preflight at staging or commit; named semantic checks
remain below until their separate replacement in stage A.

---

## Preconditions (declarative gates — block if unmet)

Resume context first (REQ-137): run
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/handoff.sh" render` and RELAY it — the
content decides: surface any pendency/handoff sections it prints; fixed core
only → stay silent about handoffs (REQ-108). Pure read, never a gate.

1. `.helmit/` exists → else route to `/helmit:setup`. STOP.
2. DELIVERY level only: product spec `status: approved`; `/arch` completed
   (`arch-approved` or later — delivery specs must not contradict the stack).
   For the state-derived target, every `requires:` phase must be
   `shipped`/`validated`; otherwise STOP and name exactly what is missing.
   For a target the user named explicitly, unmet dependencies and out-of-order
   priority are WARNINGS, never a veto: state the consequence and honor the
   target. The user owns that sequencing decision; HelmIt advises it.

## Optional pre-spec decision scan (REQ-317)

Before interviewing, inspect the active ROADMAP entry, KEEL, REQUIREMENTS and
relevant INBOX route for choices with durable high impact: public contract,
data, security/autonomy, recurring cost, compatibility, cross-platform parity,
or priority. Present only those choices, each with a recommendation and its
assumption. Prefer the harness-native multiple-choice question control with the
recommendation first; when unavailable, offer closed alternatives and an open
response in text.

The scan is consultative, never a gate: it never blocks independent discovery
or drafting. No answer — including an unattended YOLO run — means record the
recommendation as an explicit hypothesis in the Clarification record, never as
authority for a material product choice. Continue the unaffected scope; keep
only the dependent commitment draft until the user or an eligible active
mandate authorizes it. Do not inflate the scan into a generic discovery
interview or ask low-impact questions.

## Proportional investigation and sufficiency

Investigate only until the requested result is safe to commit and possible to
verify. Depth follows uncertainty and impact, not a required question count,
form, or exhaustive catalogue:

1. Resolve facts before asking for decisions. Inspect the request, repository,
   running behavior, cited sources and prior artifacts; never ask the user for
   information the available evidence can establish.
2. Classify every remaining gap:
   - a repository or domain fact → inspect the best available source;
   - a routine technical choice → leave it to `/arch`, planning or implementation;
   - a material product choice → ask the user, or use an eligible active mandate;
   - empirical uncertainty → run the smallest useful experiment and keep only
     the commitment that depends on its result pending.
3. For material choices, expose only the current independent frontier. Ask in
   short rounds; defer dependent questions until their premise is decided.
   Give a recommendation when useful and state whether it rests on evidence,
   an assumption, or remaining uncertainty. The user retains the scope choice:
   a recommendation or plausible default never authorizes one alternative when
   the alternatives change observable behavior. Do not infer the subject, data
   field, or boundary semantics of a new rule merely from its shorthand name.
4. Before finalizing, trace every essential in-scope flow to requirements and
   observable acceptance, or mark it explicitly out of scope. Inspect actors
   and permissions, starting and ending states, business rules and data,
   failures and limits, and interactions with other flows only where they can
   change an observable result. If this pass exposes omitted material behavior,
   return to investigation and update the artifacts.

The sufficiency exit is behavioral: the authorized slice can be implemented
without inventing a material product decision, and every essential outcome can
be verified. A clear, bounded request may satisfy this with zero questions. A
vague product idea may require several small decision rounds. Do not turn this
into a new lifecycle stage or a second approval gate.

---

## Localized correction (CHG)

When maintenance, copy, configuration, or a limited restoration needs structured
tracking beyond direct execution, keep it out of the delivery roadmap.
Run `change.sh classify --kind <kind>`; a durable security, data, public-contract,
mandatory-accessibility, or acceptance commitment routes to a delivery instead.

For an eligible CHG:

1. Run `change.sh snapshot`, then pass its `base`, `ledger`, and `next_id` to
   `change.sh open` with the kind, origin, concise intent, observed paths and one
   focused `verify:` command. The writer creates the canonical `CHG-NNN.1` row
   in the worktree without an intermediate commit.
2. Continue directly through `/implement` with the CHG identity and proof. Do
   not create a SPEC, requirement, chart, phase, or STATE transition. If durable
   scope appears in flight, preserve the work and route that commitment to a
   delivery.

An Inbox-linked CHG also closes exactly its linked item in the same candidate.
Paths discovered later are added only through `change.sh expand-paths` with
explicit human authorization; an observed path list is never global ownership.

---

## PRODUCT level (`application` compatibility)

### 1. Resolve only missing product decisions
Cover: target user, core value, main flows, global constraints, what is
explicitly OUT of scope for v1. Read `discovery/*` context if present (#22 —
inputs flow forward; the spec cites them, never the reverse).
- **Brownfield project** (recorded by /setup): do NOT interview about what
  already exists — the running system is the implicit baseline. Write a THIN
  spec (evolution goal + out of scope only) and a ROADMAP born EMPTY (phases
  enter on demand when a later delivery spec records authorized scope). The
  requirement registry starts empty.

### 2. Write the artifacts (from the plugin templates, `core/templates/`)
Prose of these artifacts is written in `config.json.artifact_language`;
structural keys, field names and enum values stay English.
- If the spec distills FILE(S) (a PRD, discovery docs), record them as sources
  after writing: `bash "<plugin>/core/hooks/spec-sync.sh" record SPEC.md
  <file>...` — same advisory drift contract as the delivery level (REQ-072).
- `SPEC.md` (SPEC-app template) — thin: only enough to decompose. NO
  implementation/tech-stack detail (that is /arch's job).
- `REQUIREMENTS.md` — register every requirement with a **stable ID**
  (`REQ-001`, ...). IDs are never renumbered or reused. This registry anchors
  the traceability chain REQ → task (`covers:`) → test (#37).
- `ROADMAP.md` — phase decomposition: each phase with `anchor`, `requires:`,
  and the REQ-IDs it covers. ALWAYS include "Phase 0 — Foundation" if the app
  has a database, auth, or multiple layers (archetype-checklist.md).

### 3. Preserve track only as compatibility context
- Do not ask the user to classify this project as `micro`, `standard`, or
  `full`. Existing values remain readable descriptive context; they never
  select steps, approval gates, or proof. New projects keep the template default
  without turning it into a workflow decision.
- Do not create a flat chart here. Tracked corrections use the CHG route; deliveries
  use the same proportional definition and planning flow in every project.

### 4. Record the commitment and continue preparation
- When the artifact only records scope already explicit in the user's request,
  set `status: approved` with `approved-by: human` in the same edit; this records
  real authority and does not ask for a duplicate OK.
- If drafting exposes a new material product choice, write `status: draft`,
  set `STATE.md` to `spec-app-draft`, present only that choice, and wait. An
  active mandate may authorize it as `approved-by: yolo`; proof remains required.
- On approval, set SPEC and ROADMAP to `approved`, advance to
  `spec-app-approved`, and continue preparation through `/arch` and `/env`
  without returning merely to request the next command.

At the draft boundary, leave the draft visible in the worktree and present it
for the human gate. A later session resumes by reading the target artifacts and
their diff; no ownership verdict or draft-only commit is required.

After authority is present, write the approval fields in SPEC and ROADMAP and
`workflow: spec-app-approved` in STATE. Run the normal deterministic writers, stage the related
artifacts explicitly, review the staged diff and create one ordinary approval
commit. Existing unrelated work and other legitimate Inbox edits remain
outside that snapshot unless deliberately selected.

---

## DELIVERY level (`feature` compatibility)

### 1. Resolve only missing delivery decisions
Read the app spec, the roadmap entry (its `anchor` and REQ-IDs), and KEEL
(stack + ADRs — prior decisions are constraints, not suggestions).

### 2. Write `.helmit/phases/<id>/SPEC.md` (SPEC-feature template)
EXACTLY the 6 sections: Goals · Out of scope · Constraints · Prior decisions ·
Requirements · Acceptance criteria (binary, testable, Given/When/Then
preferred). New requirements discovered here are APPENDED to
`REQUIREMENTS.md` with new stable IDs — never renumber existing ones.
Prose is written in `config.json.artifact_language`; structural keys, field
names and enum values stay English — new REQs in REQUIREMENTS.md follow the
same rule. Appends and edits to `REQUIREMENTS.md`/`ROADMAP.md` anchor on a
verified header and position, never a first text match — canonical procedure
in `/next` (REQ-146).
- **Record spec sources (REQ-072):** if the requirements were distilled from
  FILE(S) — a PRD in the repo, a client brief, discovery docs — register them:
  `bash "<plugin>/core/hooks/spec-sync.sh" record phases/<id>/SPEC.md <file>...`
  From then on `/next` and `/validate` detect out-of-flow edits to those files
  (drift) and route back here only when impact analysis finds a material
  commitment change. Conversational-only specs
  have no sources to record — skip, zero behavior change. Re-record after every
  approved revision (the new hash is the new baseline).
- **Approved historical revision (REQ-401):** after the human explicitly
  authorizes a revision of one or more already-approved delivery specs, re-record
  their sources when applicable, update only the correlated requirement text,
  stage the intended artifacts explicitly and review their staged diff. Commit
  the revision normally; a conversational clarification never needs fabricated
  source drift or a special checkpoint.

### 3. Record the commitment and route planning
- When the delivery spec faithfully records an explicit authorized request,
  write `status: approved` and `approved-by: human` together without asking for
  another confirmation. A newly discovered material choice keeps it draft at
  `spec-feature-draft:<id>` until the user or active mandate authorizes it.
- State-derived target: after authority → `spec-feature-approved:<id>`. The
  compatible next route remains `/helmit:chart` until BRB.2 incorporates
  planning into `/implement`.
- Explicit future/out-of-order target: keep `STATE.md` byte-identical while
  drafting and approving. The approved SPEC and its `spec` ROADMAP row are
  parked until ROADMAP order makes that phase current; the user's current
  workflow remains active.
- **Commit a new delivery spec after authorization:** run the ROADMAP transition
  below, stage SPEC, ROADMAP, STATE and only the correlated REQUIREMENTS/source
  registry/Inbox edits that actually occurred, then review the staged diff and
  create one ordinary approval commit. For an explicit future/out-of-order
  target, keep STATE byte-identical; parking is a user-owned scheduling choice,
  not a special checkpoint mode.
- **Expand the active phase while its chart is still draft:** preserve every
  existing requirement, phase identity, dependency, chart task and historical
  line; append only the newly approved requirements to SPEC and REQUIREMENTS,
  and add their exact ROADMAP and CHART mappings. Keep STATE at
  `chart-draft:<id>`. Confirm that the chart remains draft and no task is marked
  `[x]`/`[>]`; stage SPEC, REQUIREMENTS, ROADMAP and CHART explicitly, review
  the staged diff and create one ordinary expansion commit. Return to
  `/helmit:chart` for compatible planning. Never route an already
  started chart through this expansion path.
- **The ROADMAP row follows the artifact — PRIMARY trigger (REQ-268):** run
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/roadmap-status.sh"` (adapter note:
  `PLUGIN_ROOT` on Codex) as the approval lands. It derives the status column
  from the phase artifacts on disk (`spec`, here), only ever forward, and is
  SILENT when nothing moved. `/next` re-runs it as a net; a column that waits
  for the net is wrong for everyone who reads it meanwhile.

---

## Material-decision boundary and provenance
1. Reuse the request, product spec, repository facts, prior decisions, and
   existing acceptance before asking anything.
2. Ask only a question whose answer can materially change scope, observable
   acceptance, compatibility, cost, authority, or destructive/external effect.
   There is no minimum question count and no confirmation of established facts.
3. Record only assumptions, hypotheses and answers that changed or delimit the
   commitment. A hypothesis is evidence to investigate, not approval of a
   material choice. `none` is a valid clarification record.
4. When a new material decision remains, stop only that delivery and preserve
   unrelated work. Otherwise finalize and continue in the already authorized flow.
5. An active mandate may carry an eligible decision; read it at the boundary
   with `yolo.sh status`. Deterministic proof is unchanged.
6. **Record WHO authorized it (REQ-116).** Whatever sets `status: approved`
   also writes `approved-by: human` or `approved-by: yolo` in the same edit.
   `human` may refer to the explicit request that already authorized the exact
   commitment; `yolo` means no person reviewed that artifact.

> Principle: a gap that becomes a test criterion stops being a gap.

---

## Lean guardrails
- Do NOT produce charts or tasks; planning belongs to the planning/execution
  capability; only corrections needing structured tracking use CHG.
- Do NOT put tech detail in a product spec; do NOT re-litigate ADRs in a
  delivery spec.
- Thin product spec and detailed delivery specs. Recommend just-in-time to reduce
  waterfall planning and drift, but never turn that recommendation into a
  prohibition: an explicit user request may spec and park a future phase.
- Requirements must be binary and testable; a requirement that cannot fail a
  test is not a requirement yet — rewrite it.
- Design decisions and user choices surfacing in the conversation are
  persisted ON THE SPOT, per the canonical capture rule in `/implement`
  (REQ-141). Session-closing phrases fire the end-of-session procedure
  canonical in `/next` immediately (REQ-142).

## Session safety (tree lock + typed stop — REQ-090/REQ-091)
This command WRITES. Both steps are mandatory, in this order.
- **Acquire the lock before the first write:**
  `bash "<plugin>/core/hooks/lock.sh" acquire`. Exit 0 → proceed. Exit 2 → a
  stale holder: show what the hook printed (who, since when, last heartbeat)
  and OFFER `--force`; never hand-edit the lock file. Exit 3 → another session
  is live in this tree: STOP and say so. Always
  `bash "<plugin>/core/hooks/lock.sh" release` before returning control.
- **Record the TYPED stop as the last thing you do:**
  `bash "<plugin>/core/hooks/run-log.sh" append session_stop reason=<r>` —
  `r` = `clean` when the command finished, `gate` when it stopped at a human
  material-decision boundary, `awaiting_input` when
  it asked the user something and is waiting. A MISSING `session_stop` means
  `interrupted`, and `interrupted` is the ONLY reason a resume may act on
  (REQ-090): a wrong reason either crosses a human gate or strands a real crash.

## Cross-platform note (adapter contract)
- Pure core: reads/writes `.helmit/` only. No platform primitive. Identical
  on Claude Code and Codex.
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer (MANDATORY — every HelmIt command ends with this)
Before returning control, ALWAYS:
1. Update the `workflow:` field in `STATE.md` to the new position.
2. Tell the user, in the language from `config.json`, where they now are and
   continue the eligible preparation or planning act already authorized. Pause
   only at a material decision or external-authority boundary.
