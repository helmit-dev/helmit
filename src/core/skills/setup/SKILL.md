---
name: setup
description: "Prepares a project for HelmIt: scaffolds .helmit/, installs the leased instructions and Git floor, then continues into product, architecture, and environment work as needed. Never overwrites an existing .helmit/."
---

# /setup

Configure HelmIt for THIS project. Installing the plugin (`/plugin install`) put
the commands on the machine; /setup wires the project: the `.helmit/` kit, the
leased section in the host context file, and the git safety floor.

/setup owns scaffolding and starts one continuous preparation flow. Product
definition, architecture, and environment remain separate capabilities, but the
user does not need to remember or invoke each command between eligible steps.

---

## Working-tree safety (ADR-018)

Check the preconditions below directly before scaffolding. Inspect Git status
and warn about existing work without blocking or rewriting it. If a target such
as `AGENTS.md`, `CLAUDE.md`, or the pre-commit hook already contains changes,
inspect and preserve those changes while applying only the setup-owned block.
Pause only for an unresolved overlap or unknown intent.

Before commit, review the staged diff and stage only the scaffold and leased
blocks created by this setup—never `git add -A`. Preserve the existing index
and every unrelated file. Setup creates no task claim or executor lease.

---

## Preconditions (declarative gates — block if unmet)

1. `.helmit/` does NOT exist. If it exists → STOP and report ("already
   initialized — use `/helmit:next` to resume"). Never overwrite; migration
   between HelmIt versions is a separate, explicit command (#43).
2. `git` is available on PATH. If the directory is not a git repository,
   OFFER `git init` (local action — run on confirmation). A repo is required:
   the workflow anchors tracking to commits.
3. If the working tree has uncommitted changes, warn (do not block).

---

## Process

### 1. Detect, deterministically (no LLM guessing — #48D)
- Project type: read the manifests that exist (`package.json`,
  `pyproject.toml`, `go.mod`, `*.csproj`/`*.sln`, `Cargo.toml`, `composer.json`,
  ...). Do NOT assume Node. No manifest + no source files → greenfield.
- Greenfield vs brownfield: source files already present = brownfield.

### 2. Ask the essentials (as FEW questions as possible)
- **Language** for user-facing communication (default: the language the user
  is writing in). Persist as `config.json.language`.
- **Artifact language** for the prose of the USER's artifacts —
  SPEC/ROADMAP/CHART/VALIDATION (default: same as `language`).
  Persist as `config.json.artifact_language`. Note: `KEEL.md` is ALWAYS
  English regardless — it is agent-facing.
- Report the detected project type and correct it only if the user supplies
  contrary information; a factual detection does not require confirmation.
- Ask only when a language choice is genuinely unknown. Defaults inferred from
  the request need no duplicate confirmation.
- Keep `config.json.track` at its compatible default. Track is descriptive
  context for older projects and never selects steps, approvals, or proof.
- Brownfield: record the detection in `STATE.md` (notes) — downstream routing
  depends on it: the product /spec becomes a THIN baseline declaration
  (no interview about what already exists; ROADMAP born EMPTY, grows on
  demand) and `/arch` runs its **Discovery mode** (KEEL facts detected from
  the real code; only ambiguous or new decisions return to the user).

### 3. Scaffold `.helmit/` from the plugin templates (`core/templates/`)
Create:
- `KEEL.md` (placeholders — filled by /arch)
- `SPEC.md` from the SPEC-app template — it already ships with
  **`status: stub`** (the marker /spec uses for deterministic level
  detection); no manual status edit needed
- `ROADMAP.md` from its template (also ships with `status: stub`),
  `REQUIREMENTS.md` (registry born empty — header only)
- `CHANGES.md` from its template (the repository-wide monotonic ledger for
  limited `CHG-NNN` work; identity is allocated from this versioned file)
- `INBOX.md` from its template (the capture and triage channel:
  bugs/improvements found out-of-scope land here; `/next` offers triage)
- `STATE.md` with `workflow: setup-done` and the compatible track noted as
  descriptive context only
- `config.json` from the template, with the wizard's answers: persist BOTH
  `language` and `artifact_language`, and STRIP every top-level key starting
  with `$` (e.g. `$schema_note`, `$enums`) — schema documentation lives only
  in the plugin's template; the user's config is values-only
- `phases/` with a `.gitkeep` inside (empty directories are not versionable by
  git)

### 4. Inject the leased section into the host context file
- Target: the current platform's context file — `CLAUDE.md` (Claude Code) or
  `AGENTS.md` (Codex). Create the native file if it does not exist. If both
  exist in the repo, inject the SAME lease into both. A pre-existing file from
  the opposite harness is evidence for `/env` assisted migration, never a
  reason to copy its user rules into the native file automatically.
- The section is EXACTLY the block between the markers below. If markers are
  already present, replace only their content. NEVER touch anything outside
  the markers — the file belongs to the host harness (#43).
- Write it VERBATIM, `helmit-lease-version:` line included. That marker mirrors
  the plugin version exactly like `helmit-pre-commit-version:` does for the git
  floor, and it is the block's whole LIFECYCLE: /setup runs once per project, so
  the marker is what lets `/env` notice a stale block later and OFFER the
  refresh. Without it, every later improvement to this text would die in every
  project that already exists.
- The block is the ONLY text loaded in every fresh session, so it must name the
  harness concepts a new session cannot otherwise guess — starting with the
  capture channel: bare "inbox" reads as e-mail to any agent.
- It is also the only place a rule can reach EVERY door. The autonomy mandate
  is the case that proves it: a user asks for yolo in the middle of `/spec`,
  `/chart` or `/next` just as often as in `/implement`, and a rule written
  inside one skill does not exist for the others (REQ-118). Hence the yolo line
  below is not a courtesy — it is the only reason the request is honoured
  wherever it arrives.

```markdown
<!-- helmit:start -->
<!-- helmit-lease-version: 0.0.90 -->
## HelmIt (workflow harness)
This project uses HelmIt — a lean SDD harness with deterministic gates.
- ALWAYS read `.helmit/KEEL.md` at session start: project rules, the exact
  test/build/lint gate commands, and architecture decisions (ADRs).
- The project's position lives in `.helmit/STATE.md`. To resume or get
  oriented, run `/helmit:next` — the only command you need to remember.
- Also at session start, read `.helmit/HANDOFF.md` if present — the previous
  session's handoff (narrative resume context); the derived facts come from
  `bash <plugin>/core/hooks/handoff.sh render`.
- Capture and triage channel: `.helmit/INBOX.md`. In THIS project "inbox" and
  "triage" ALWAYS mean that file — never e-mail: bugs and improvements found
  out of scope are captured there, and `/helmit:next` offers the triage.
- Autonomy is a MANDATE, and it has a door. If the user asks to skip approvals
  ("go yolo", "yolo full", "stop asking me until the phase is done"), run
  `/helmit:yolo phase|full` BEFORE continuing — in ANY command. That is what
  arms it; a sentence on its own arms nothing. `/helmit:yolo status` says what
  is in force, `off` ends it, and it expires by itself when its scope is done.
- Under an active mandate, the orchestrator keeps eligible work in the same
  live flow and waits on executor events. Heartbeat only recovers an unexpected
  interruption; it never polls or supervises normal progress.
- `.helmit/` is managed by the `/helmit:*` commands. Do not edit it by hand.
- Commit gate: every logical commit MUST pass the staged quick floor; a
  candidate that closes a task also passes its declared `verify:`. Never use
  `--no-verify` or bypass hooks.
<!-- helmit:end -->
```

### 5. Install the git pre-commit floor
- Copy the plugin's `core/hooks/pre-commit` into `.git/hooks/pre-commit`
  (make it executable). It checks the staged diff plus shell, Python and JSON
  syntax. It is self-contained and never runs the product's test/build/lint
  commands; those belong to wave, validation and ship boundaries.
- If a pre-commit hook already exists, do not clobber it: show it to the user
  and ask whether to chain or skip. Chaining MATERIALIZES the canonical chained
  layout (REQ-210) — the exact shape `/env` and `env-check.sh` already
  recognize; never improvise another:
  1. Copy the plugin's `core/hooks/pre-commit` VERBATIM to
     `.git/hooks/helmit-pre-commit` and `chmod +x` it. The copy is where the
     gate lives in this layout — env-check hashes IT, never the dispatcher.
  2. Move the user's existing hook aside unchanged:
     `.git/hooks/pre-commit` → `.git/hooks/pre-commit.user` (byte-for-byte —
     it is the "chained original" /uninstall restores).
  3. Write `.git/hooks/pre-commit` as this short DISPATCHER, `chmod +x`:

```bash
#!/usr/bin/env bash
# HelmIt /setup dispatcher — the pre-existing hook runs first, then the
# HelmIt gate. Either failing blocks the commit.
"$(dirname "$0")/pre-commit.user" "$@" || exit 1
exec "$(dirname "$0")/helmit-pre-commit" "$@"
```

  The dispatcher references the verbatim copy BY PATH: the `/helmit-pre-commit`
  token in its body is the discriminator env-check's check 2 uses to tell the
  chained layout from a direct install. Keep both hook names exactly as
  written — rename either and the floor's verdict silently degrades.

### 6. Write the HelmIt local-state block into `.gitignore`
- Target: `.gitignore` at the REPO ROOT (next to `.git/`). Create it if it does
  not exist. Like the host context file, this file belongs to the user: HelmIt
  leases ONE delimited block inside it and owns nothing else (#43).
- The block is EXACTLY this, markers included:

```text
# helmit:local-state:start
# HelmIt local machine state — machine-local, never shared, never versioned.
# Everything ELSE under .helmit/ (SPEC.md, ROADMAP.md, REQUIREMENTS.md,
# STATE.md, KEEL.md, config.json, phases/) IS the project contract and MUST
# stay versioned — that contract is the reason HelmIt exists.
.helmit/map/
.helmit/proof-worktrees/
.helmit/*.jsonl
.helmit/lock.json
.helmit/executor-lease.json
.helmit/session-activity/
.helmit/yolo.json
.helmit/HANDOFF.md
.helmit/dashboard.html
.helmit/quality-receipt.json
# helmit:local-state:end
```

- IDEMPOTENT, detected by the marker line `# helmit:local-state:start`:
  - marker already present → DONE. Do not duplicate it, do not rewrite it, do
    not reorder it.
  - no `.gitignore` → create it containing exactly the block.
  - `.gitignore` exists without the marker → APPEND the block at the END of the
    file. Every pre-existing line stays byte-for-byte identical: no reordering,
    no dedup, no "while I am here" cleanup.
  - Running /setup twice must leave `.gitignore` byte-identical. That is the
    whole acceptance test.
- WHY each entry is machine-local: `map/` is a rebuildable cache;
  `proof-worktrees/` contains short-lived exact Git trees used to keep proof
  mutations out of the user's checkout and is recovered or removed after use;
  `*.jsonl` is
  the hot log (`run.jsonl`, `metrics.jsonl`) — versioned, it conflicts on every
  run from a second machine; `lock.json` carries the PID and ABSOLUTE path of
  ONE machine, which are meaningless and actively misleading anywhere else.
  `executor-lease.json` carries the short-lived liveness proof of one
  interactive executor on one checkout; versioning it makes another machine
  appear active and makes the preflight classify its own required lease as
  foreign work.
  `session-activity/` carries short-lived per-session host signals for this
  checkout; it does not belong to the shared project contract.
  `yolo.json` is there for a different and
  sharper reason: it is an autonomy MANDATE, and a mandate one person granted
  for one night must never be inherited by whoever clones the repository —
  cloning a project must never hand somebody an agent that has stopped asking.
  `HANDOFF.md` is the session handoff — the narrative half of resumption; the
  facts are derived at read time, so what the file carries is one machine's
  one-moment thinking, meaningless in someone else's clone.
  `dashboard.html` is the project board and is DERIVED whole: `dashboard.sh
  render` rebuilds it from the versioned contract plus the local logs, so
  committing it stores a second, aging copy of facts the repo already carries —
  and a 40 KB generated file rewritten on every render conflicts between
  machines exactly like the logs it reads.
- Never ignore `.helmit/` wholesale, and never widen the block on your own. If
  the user's file already ignores `.helmit/` entirely, do NOT rewrite their
  line: report it and let them decide — the versioned contract is the point of
  the harness.

### 7. Write the HelmIt format-ignore block into the formatter's ignore file
- WHY: a project-wide format command (`prettier --write .`, `eslint --fix .`,
  `black .`) reaches `.helmit/` and rewrites the project contract on EVERY file
  edit — `STATE.md` is parsed deterministically by `/next`, `REQUIREMENTS.md`
  and `ROADMAP.md` are tables, and the gate scripts read `config.json` key by
  key. The PostToolUse auto-format hook therefore REFUSES to run a project-wide
  command until the project declares `.helmit/` out of the formatter's reach
  (REQ-102). Leasing this block is what keeps auto-format working.
- Detect the formatter from what EXISTS (step 1 manifests + config files), never
  by guessing. Target file per formatter:
  - prettier (`.prettierrc*`, `prettier` key/dependency in `package.json`) →
    `.prettierignore`
  - eslint with `.eslintrc*` → `.eslintignore`; stylelint → `.stylelintignore`;
    biome → `.biomeignore`
  - eslint FLAT config (`eslint.config.js|mjs|cjs`) or black/ruff
    (`pyproject.toml`, `ruff.toml`, `setup.cfg`) → the exclusion is a KEY, not a
    line: add `.helmit` to the EXISTING `ignores`/`extend-exclude` value (e.g.
    `[tool.black] extend-exclude = '/(\.helmit)/'`) and say so in the report.
    Never rewrite the user's config beyond that one entry.
- For the line-based files, the block is EXACTLY this, markers included:

```text
# helmit:format-ignore:start
# HelmIt workflow contract — written ONLY by the /helmit:* commands.
# A project-wide formatter must never rewrite it: STATE.md is parsed
# deterministically, REQUIREMENTS.md and ROADMAP.md are tables, and the gate
# scripts read config.json key by key.
.helmit/
# helmit:format-ignore:end
```

- IDEMPOTENT, same lease mechanism as step 6, detected by the marker line
  `# helmit:format-ignore:start`:
  - marker already present → DONE. Do not duplicate it, do not rewrite it, do
    not reorder it.
  - ignore file absent → create it containing exactly the block.
  - ignore file exists without the marker → APPEND the block at the END. Every
    pre-existing line stays byte-for-byte identical: no reordering, no dedup.
  - Running /setup twice must leave the file byte-identical.
- `.gitignore` does NOT count as protection here: step 6 keeps the `.helmit/`
  contract VERSIONED on purpose, and eslint does not read it anyway.
- NO formatter detected (greenfield is the normal case — `/arch` has not chosen
  the commands yet) → write nothing and SAY it: "no formatter detected; `/arch`
  will write `commands.format` and lease this block if the command is
  project-wide". The degradation is always ANNOUNCED, never silent.
- Formatter detected but its exclusion mechanism is none of the above → report
  it in one line: keep `commands.format` in the `{file}` form, or exclude
  `.helmit/` by other means and set `config.json.commands.format_guard` to
  `declared`.

### 8. Report
- One short summary: what was created, where the leased section went, hook
  installed or skipped, `.gitignore` block written or already present,
  format-ignore block written / already present / not applicable. The first
  session start publishes the initial dashboard projection automatically; no
  separate render step belongs in setup. Then the guidance footer.

---

## Lean guardrails
- Minimal interaction: detect first and ask only for an unknown language or a
  decision that changes the product, architecture, permissions, or external state.
- Write NOTHING outside `.helmit/`, the leased section markers,
  `.git/hooks/pre-commit`, and the leased block in the root `.gitignore`.
- No product content, no phases, no tasks, no stack decisions.

## Session safety (tree lock + typed stop — REQ-090/REQ-091)
This command WRITES. Both steps are mandatory, in this order — from the moment
`.helmit/` exists (before that there is nowhere to write the lock or the log,
and that is fine: acquire right after scaffolding, log from then on).
- **Acquire the lock before the first write:**
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" acquire`. Exit 0 → proceed.
  Exit 2 → a stale holder: show what the hook printed (who, since when, last
  heartbeat) and OFFER `--force`; never hand-edit the lock file. Exit 3 →
  another session is live in this tree: STOP and say so. Always
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" release` before returning
  control.
- **Record the TYPED stop as the last thing you do:**
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append session_stop reason=<r>`
  — `r` = `clean` when onboarding finished, `gate` when it stopped at a human
  gate, `awaiting_input` when it asked the user something and is waiting. A
  MISSING `session_stop` means `interrupted`, and `interrupted` is the ONLY
  reason a resume may act on (REQ-090): a wrong reason either crosses a human
  gate or strands a real crash.

## Cross-platform note (adapter contract)
- WHICH host file receives the leased section (CLAUDE.md vs AGENTS.md) is the
  adapter's only variation. Scaffold, config, and pre-commit floor are core
  and identical on Claude Code and Codex.
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer (MANDATORY — every HelmIt command ends with this)
Before returning control, ALWAYS:
1. Update the `workflow:` field in `STATE.md` to the new position (`setup-done`).
2. Continue the same preparation flow with product definition, architecture,
   and environment checks while each next act is authorized. Pause only for a
   material decision or external action; otherwise report the final preparation
   result and the next delivery, without making the user invoke three commands.
