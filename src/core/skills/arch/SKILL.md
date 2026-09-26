---
name: arch
description: "Records macro architecture and exact quality commands during preparation. Observed brownfield facts are adopted without ceremony; only new material tradeoffs require a user decision."
---

# /arch

Decide ONLY macro architecture: stack, data store, layer boundaries, and the
EXACT test/build/lint commands the deterministic gates depend on.
Component-level design stays just-in-time in each phase's /chart.

This step is what UNLOCKS the gates: the commit gate cannot run before the
commands exist.

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

1. `.helmit/SPEC.md` exists with `status: approved`. If not → route to
   `/helmit:spec`. STOP.
2. `KEEL.md` Stack/Commands are EMPTY. If already filled → STOP and report
   (never silently overwrite an architecture decision; changing one is a new
   ADR proposed to the user, not an overwrite).

---

## Mode routing (deterministic — no interpretation)

- **Greenfield** (no source files; /setup recorded greenfield) → the guided
  interview below (steps 1–6). You DECIDE the conventions.
- **Brownfield** (source files exist; /setup recorded brownfield) → the
  **Discovery mode** section below. The agent DETECTS conventions from the real
  code and records observed facts directly. It asks only where competing
  interpretations or a new architecture decision would change the commitment.
- **Trivial repo** (discover.sh reports `meta.trivial: true`, <5 files) →
  route to the greenfield interview; discovery ceremony is not worth it.

---

## Process

### 1. Pre-detect, deterministically (#48D)
- Read existing manifests (`package.json`, `pyproject.toml`, `*.csproj`,
  `go.mod`, ...) to pre-populate stack candidates — file reads, not guessing.
  Brownfield: what exists IS the starting point; confirm rather than propose.

### 2. Walk the tradeoffs (guided by `checklists/tradeoffs-checklist.md`)
- For each unresolved checklist item RELEVANT to this spec: present viable
  options with consequences and a recommendation, then let the user decide.
- Prefer the boring, well-supported choice unless the spec demands otherwise.
- If a decision can be deferred without blocking Phase 0, DEFER it
  (just-in-time; see the checklist's defer list).
- Scale depth by the uncertainty and impact of the current architecture choice,
  never by the legacy project track. Do not ask about facts already established
  by the codebase or the user's explicit request.

### 3. Record, at MACRO level only
KEEL.md is ALWAYS written in English, regardless of
`config.json.artifact_language` — it is an agent-facing instruction file, the
single exception to the artifact-language rule (per the KEEL-English rule).
Write into `KEEL.md`:
- **Stack** section — language/runtime, framework(s), data store(s).
- **Commands** section — the EXACT `test`, `build`, `lint` (and optional
  `format`) commands. REQUIRED: the gates depend on these being runnable.
- **Conventions** section — SEED the harness default convention:
  `self-explanatory code — comments only where the code cannot speak;
  rationale lives in ADRs, never in comments`. This default is ADJUSTABLE at
  this command's own gate (step 6): the default is the harness's, the
  convention is the project's — the user replaces it there with the project's
  own comment policy and that choice is the record, not a deviation. It is
  seeded because executors receive the rationale ready-made (the chart's
  `anchor:`) and, with no stated destination, it lands as ADR-sized comment
  headers in the implementation.
- **Decisions (ADR)** — append one line per significant choice:
  `ADR-00X: <decision> — <date> — Reason: <why> — Do NOT revisit.`

**`test`: PROPOSE the parallel form, never write it alone (REQ-198).** The
moment `commands.test` is decided is the one place where a slow suite is cheap
and permanent to fix — a harness that only ever CHARGES the cost it multiplies
never helps at the origin. So, with the command chosen and BEFORE writing it,
ask the hook whether that runner has a known parallel form:
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/parallel-hint.sh" suggest --command "<the chosen test command>"`
- The hook prints AT MOST one line and always exits 0. It is an informer, not
  a gate: nothing it says can block this step.
- **A proposal came back** (`parallel-hint: <runner> — <suggested command> (<what
  it changes>)`) → PRESENT it to the user: the suggested command, and in ONE
  line what it changes. Then ASK.
- ONLY the user's explicit confirmation writes `commands.test` in the parallel
  form; silence, a shrug or an unanswered question do not.
  A refusal is a FINAL answer: record the command exactly as the user chose it,
  do not re-ask, do not insist, do not bring it back later in this run.
- **The hook said nothing** (runner not in its table, empty command, no
  interpreter) → say NOTHING. Fail-open: no proposal, no mention, no "nothing
  to suggest here" reassurance — zero noise (the REQ-108 rule: silence when
  there is no real pendency). Same treatment for the line that reports the
  command is ALREADY parallel: there is nothing to propose, so there is
  nothing to say.
- **State the honest limit in the same breath as the proposal.** The hook
  reads a STRING: it does not know whether the plugin behind the flag is
  installed (pytest-xdist, cargo-nextest may well be absent on this machine),
  how many cores there are, or whether this suite survives running out of
  order — shared fixtures, one database, fixed ports. That is exactly why the
  decision is the user's, every time; do not present the suggestion as
  verified, present it as a proposal to judge.
- The test command belongs to the PROJECT. Writing the parallel form without
  confirmation would be the same boundary violation REQ-112 avoided when /env
  OFFERS `git rm --cached` and never runs it.

**`format`: PREFER the per-file form (REQ-102).** Write `commands.format` with
the `{file}` placeholder — `prettier --write {file}`, `black {file}`,
`dotnet format --include {file}` — so the PostToolUse hook can only ever touch
the file just edited. A project-wide command (`prettier --write .`) formats the
WHOLE repository, `.helmit/` included, on every single edit: it rewrites the
project contract (`STATE.md` is parsed deterministically, `REQUIREMENTS.md` and
`ROADMAP.md` are tables, `config.json` is read key by key by the gate scripts).
If the project-wide form is what the user wants anyway:
- WARN in ONE line: "project-wide format command: auto-format will be SKIPPED
  until `.helmit/` is excluded from the formatter";
- then lease the `helmit:format-ignore` block in the formatter's ignore file —
  same mechanism as `/setup` step 7 (marker-detected, create or append,
  idempotent, never reorder the user's lines);
- if the formatter's exclusion mechanism is not one HelmIt recognizes, say so
  and record the pendency (KEEL Commands note + `.helmit/INBOX.md`); the user
  can exclude `.helmit/` by other means and set `commands.format_guard` to
  `declared`.
Never leave this implicit: a project-wide `format` with no declared protection
means auto-format is OFF (the hook skips it and warns), and the user must hear
that from /arch, not discover it later.

Then MIRROR the commands into `config.json.commands` (machine-readable — the
hook scripts read config.json, never parse markdown). KEEL and config MUST
match; KEEL is for humans and the agent, config is for the gate scripts.

### 4. Validate the commands ACTUALLY run
- Execute each command once (greenfield: they may legitimately fail on an
  empty project — what must succeed is the tool being found and runnable).
- A command that cannot be found/run is not a gate — fix it now, or record it
  as pending and BLOCK /implement until it works.
- EXCEPTION: never validate a project-wide `format` command by EXECUTING it —
  that single run is exactly the damage REQ-102 exists to prevent. Check the
  tool is reachable instead (`command -v <tool>`).

### 5. Re-run the archetype classification
- With the stack known, confirm against `checklists/archetype-checklist.md`
  which foundations Phase 0 MUST include (DB → schema/migrations; auth →
  identity model; multi-layer → API contracts). Update ROADMAP Phase 0 scope
  notes if a mandatory foundation is missing — surface it, never silently.

### 6. Decision boundary and provenance
- Present only new material architecture decisions not already authorized.
  Pause for those decisions unless an active mandate covers them. Observed
  brownfield facts and exact commands discovered from the repository do not
  create an item-by-item approval ceremony.
- Once required authority is present: advance `STATE.md` → `arch-approved` **ONLY IF the current
  position is EARLIER than it** (REQ-152; the rule is REQ-129, which fixed the
  same defect in /env) — `setup-done`, `spec-app-draft`, `spec-app-approved`,
  `arch-draft`. Next: `/helmit:env`. Before authority: `arch-draft`, under the
  same condition.
- Position EQUAL to or LATER than `arch-approved` — any later phase value:
  `env-ready`, `spec-feature-*`, `chart-*`, `implementing:*`, `implemented:*`,
  `validated:*`, `shipped:*`, `complete` — → DO NOT TOUCH the field. A re-run
  of /arch on an advanced project (ADR revision, brownfield discovery on a
  live codebase) records its result — the new ADR line, the KEEL update —
  WITHOUT rewriting the position, and says so in the report: architecture
  recorded, position preserved at `<current>`. The position field is
  MONOTONIC (the REQ-129 rule for every re-runnable skill): an unconditional
  write here REGRESSES the ONE field `/next` routes from.
- **Record WHO authorized it (REQ-116):** write `approved-by: human` or
  `approved-by: yolo` in the KEEL header, in the same edit that approves. A
  stack chosen without a person reading it is exactly the kind of decision the
  user will want to find later. In brownfield discovery, `human` may record the
  user's explicit request to prepare the existing repository; new choices still
  require direct authority or an eligible mandate.

---

## Discovery mode (brownfield — detect facts, decide gaps)

Discovery reports what the code IS; it is not an oracle about what it SHOULD
be. Established repository facts are recorded without a confirmation loop.
Ambiguity, architectural debt, or a proposed change is surfaced because it can
alter the commitment, not because every detected line needs approval.

### D1. Deterministic scan (zero LLM, zero tokens)
- Run `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/discover.sh" scan` — factual
  candidates for stack, test/build/lint commands and conventions, EVERY item
  with its evidence (the file that sustains it). If `meta.trivial: true`,
  route to the greenfield interview and stop here.

### D1.5 Repo map (optional deterministic layer — ADR-009, fail-open)
- Run `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/repo-map.sh" refresh`. If it
  reports `"available": false` (lib absent or `HELMIT_MAP=off`), SKIP this
  step silently and proceed exactly as before — NEVER install here (/env
  owns installation, behind explicit consent).
- With the map present: symbols + references of the whole codebase, ranked,
  at zero token cost — persisted in `.helmit/map/` (incremental refresh).

### D2. Selective reading of key files (model tier: `fast`)
- Read ONLY the files the scan flagged as evidence (bounded: skip >100KB) to
  resolve ambiguities (e.g. two test commands detected — which is canonical?).
- When the map exists, the reading is GUIDED by it: prioritize its top-ranked
  files — they are where the codebase's conventions actually live.
- NEVER load the whole repository into context; never read files the scan
  did not point to. Directed scan is the contract (REQ-040).
- `config.json.model_profiles.discovery` maps this step to the cheap tier;
  the tier→model mapping belongs to the ADAPTER (core only knows tiers).

### D3. Synthesize the KEEL draft (model tier: `default`)
- Write `KEEL.md` with `status: draft`: each detected statement carries its
  evidence path and an open marker. Content rule (Anthropic criterion,
  verified): include ONLY what the agent cannot infer from the code
  (commands, diverging conventions, gotchas); NO file-by-file descriptions;
  for each line ask "would removing it cause a mistake?" — if not, cut.
- Synthesis and interpretation stay on the `default` tier (weak models get
  confused interpreting maps — Aider's documented caveat).
- Nothing is invented: a statement without evidence is not "detected" — it
  becomes a `gap` for the human to decide (as in greenfield).
- When the map exists, CODE conventions become detectable with evidence
  (layering, naming patterns, where the logic lives — cite file:line from
  the map); without it, stick to what D1/D2 evidenced.

### D4. Resolve only ambiguous facts and new decisions
- Record evidenced stack, commands, and conventions directly. Present a compact
  summary so the user can correct it, but do not stop for confirmation of each
  line.
- Ask only when evidence conflicts, a gap blocks the declared commands, or the
  desired architecture differs from observed code. Debt is captured in Inbox
  only when it matters to the current work or the user asks; discovery does not
  manufacture an upfront backlog.
- Apply the per-line pruning criterion of D3 before writing.
- A `format` command DETECTED in the codebase follows the step-3 rule when it
  is mirrored: prefer the `{file}` form; project-wide → warn in one line and
  lease the `helmit:format-ignore` block. The DETECTED `test` command follows
  the step-3 parallel proposal the same way (REQ-198) — propose once, write
  only on explicit confirmation, stay silent when the hook says nothing.
- The KEEL becomes final when its required stack and commands are evidenced and
  every material ambiguity affecting the current delivery is resolved. A gap
  unrelated to current work is recorded without blocking preparation.

### D5. Rejoin the common flow
- Validate the confirmed commands actually run (step 4 above), re-run the
  archetype check (step 5) and close at the decision boundary (step 6).
- **Post-discovery operating model** (research: unanimous change-driven):
  a brownfield project SKIPS questions about product behavior that already
  exists (the system is the implicit baseline); the ROADMAP is born
  EMPTY and grows on demand — a new delivery uses a delivery /spec; a clear,
  localized, directly verifiable fix uses ordinary edits and Git. Use CHG when
  investigation or continuity needs tracking, and a phase for a larger commitment.
  Discovery debts NEVER become an upfront backlog.

---

## Lean guardrails
- No separate architecture document — output lives in KEEL.md (#16, respects
  the file-kit rule #3).
- No component-level design, no diagrams-for-the-sake-of-it, no personas.
- ADRs are one line each, append-only. Their job is to stop re-litigation.
- Only decide what Phase 0 needs; defer everything else.

## Session safety (tree lock + typed stop — REQ-090/REQ-091)
This command WRITES. Both steps are mandatory, in this order.
- **Acquire the lock before the first write:**
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" acquire`. Exit 0 → proceed.
  Exit 2 → a stale holder: show what the hook printed (who, since when, last
  heartbeat) and OFFER `--force`; never hand-edit the lock file. Exit 3 →
  another session is live in this tree: STOP and say so. Always
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" release` before returning
  control.
- **Record the TYPED stop as the last thing you do:**
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append session_stop reason=<r>`
  — `r` = `clean` when the command finished, `gate` when it stopped at a human
  material-decision boundary, `awaiting_input` when
  it asked the user something and is waiting. A MISSING `session_stop` means
  `interrupted`, and `interrupted` is the ONLY reason a resume may act on
  (REQ-090): a wrong reason either crosses a human gate or strands a real crash.

## Cross-platform note (adapter contract)
- Pure core: reads/writes `.helmit/` files and runs shell commands to
  validate. Identical on Claude Code and Codex.
- Discovery: `discover.sh` is bash+python3 stdlib (ADR-001) and
  `${CLAUDE_PLUGIN_ROOT}` resolves on both platforms (Codex exports it).
  The `model_profiles` tier→model mapping (D2 fast / D3 default) is the
  ADAPTER's job; sequential execution is the universal fallback.
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer (MANDATORY — every HelmIt command ends with this)
Before returning control, ALWAYS:
1. Update the `workflow:` field in `STATE.md` to the new position — SUBJECT TO
   THE MONOTONICITY RULE of step 6 (REQ-152). On a re-run of a project already
   past `arch-approved` the correct action is to write NOTHING and say the
   position was preserved.
2. Tell the user, in the language from `config.json`, where they now are.
   Continue directly into `/helmit:env` when no material decision or external
   action is pending; do not return merely to make the user invoke the next
   preparation capability.
