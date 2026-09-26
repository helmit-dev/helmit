---
name: uninstall
description: "Removes HelmIt from THIS project: leased section out of CLAUDE.md/AGENTS.md, pre-commit hook removed, and asks before deleting .helmit/ (default: keep). Run BEFORE the native plugin uninstall."
---

# /uninstall

Undo what `/helmit:setup` did to this project. The plugin's own uninstall
(`/plugin uninstall` / `codex plugin uninstall`) only removes the plugin from
the machine cache — it never touches the project. This skill is the
project-side cleanup, so run it FIRST.

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

## Preconditions
1. Something to clean exists: `.helmit/`, the leased section, or our
   pre-commit hook. If none → report "nothing to uninstall". STOP.

---

## Process

### 1. Remove the leased section (surgical)
- In `CLAUDE.md` AND `AGENTS.md` (whichever exist): delete EXACTLY the block
  from `<!-- helmit:start -->` through `<!-- helmit:end -->` (inclusive).
- NEVER touch anything outside the markers — the rest of the file belongs to
  the host harness (#43). If the file becomes empty, ask before deleting it.

### 2. Remove the git pre-commit floor (only if it is ours)
- Check `.git/hooks/pre-commit` for the HelmIt marker line (the installed
  script identifies itself). Ours → remove (or restore the chained original
  if /setup chained one). Not ours / user-modified → show it and ask.

### 2b. The resumption guardian needs no cleanup (offer the mandate's)
- The heartbeat guardian is a SESSION cron: it dies with the session by
  construction, so there is no OS scheduler entry, no shim and no arming
  file to hunt down — nothing of it lives on the machine.
- If `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" status` reports a
  mandate in force, OFFER `/helmit:yolo off` before concluding — an
  uninstall that leaves a mandate armed leaves a promise nobody will keep.

### 3. Ask about `.helmit/` (DESTRUCTIVE — explicit confirmation, default NO)
- `.helmit/` holds the user's specs, charts, state, and verification history.
- Ask ONE clear question: keep it (default — everything remains readable as
  plain markdown) or delete it permanently. Only delete on an explicit yes.

### 4. Point to the native uninstall (the package side)
- Tell the user to now remove the plugin itself:
  - Claude Code: `claude plugin uninstall helmit` — use the CLI (the TUI
    uninstall path is known-unreliable, #43).
  - Codex: `codex plugin uninstall helmit`.
- Note: after uninstall, any kept `.helmit/` is inert data — reinstalling the
  plugin and running `/helmit:next` picks the project right back up.

### 5. Report
- What was removed, what was kept, and the one native command left to run.

---

## Lean guardrails
- Surgical edits only: markers in/out, nothing else.
- `.helmit/` deletion: explicit yes required; when in doubt, keep.
- No "cleanup" beyond what /setup created — do not touch the user's git
  config, other hooks, or unrelated files.

## Session safety (tree lock + typed stop — REQ-090/REQ-091)
This command WRITES. Both steps are mandatory, in this order — while `.helmit/`
still exists (if the user chooses to delete it in step 3, that deletion is the
end of the line: nothing left to lock or log, and nothing left to resume).
- **Acquire the lock before the first write:**
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" acquire`. Exit 0 → proceed.
  Exit 2 → a stale holder: show what the hook printed (who, since when, last
  heartbeat) and OFFER `--force`; never hand-edit the lock file. Exit 3 →
  another session is live in this tree: STOP and say so — removing HelmIt under
  a live writer is how half-uninstalls happen. Always
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" release` before returning
  control.
- **Record the TYPED stop as the last thing you do** (unless `.helmit/` was
  deleted):
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/run-log.sh" append session_stop reason=<r>`
  — `r` = `clean` when the removal finished, `gate` when it stopped at a human
  gate, `awaiting_input` when it asked the destructive question and is waiting.
  A MISSING `session_stop` means `interrupted`, and `interrupted` is the ONLY
  reason a resume may act on (REQ-090): a wrong reason either crosses a human
  gate or strands a real crash.

## Cross-platform note (adapter contract)
- Pure core: file edits in the project. WHICH host files exist (CLAUDE.md /
  AGENTS.md) varies; the marker contract is identical on both platforms.
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer
This command ends the workflow — no next step is offered. Confirm, in the
language from `config.json` (while it still exists), that the project-side
removal is complete and only the native plugin uninstall remains.
