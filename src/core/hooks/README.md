Deterministic hooks packaged with the plugin. Every one of them is bash +
python3 stdlib (ADR-001/ADR-005), offline, and safe to call twice — the agent
calls them; none of them calls an agent.

`commit-transaction.sh` / `commit-transaction.py` records `commit_started` before a commit and
`commit_landed` after it. Its recovery classifier preserves every unknown lock;
it never removes an `index.lock`: a dead recorder and an unchanged index do
not prove ownership of a Git writer's lock. Git resolves the effective index
and lock paths, including linked worktrees and `GIT_INDEX_FILE`; an existing
lock takes precedence over safe-retry or landed classifications.

## Formatter filename templates

`auto-format` binds `{file}` as filename data for ordinary command arguments,
including quoted arguments, prefixes, command chains, pipes and redirects.
Literal `bash`/`sh`/`dash`/`zsh`/`ksh` `-c` programs are handled recursively;
`$(...)` has its own quoting context. For example, `python3 format.py {file}`,
`python3 -m black "{file}"` and `bash -c 'formatter "{file}"'` preserve one
filename argument even when the filename contains shell characters.

The template is trusted project configuration, not a general shell sanitizer.
The formatter itself must consume filenames as data. Substituting `{file}` into
executable source for `eval`, Python/Node/Perl/Ruby/PHP code flags, or an awk
program is unsupported and skipped with a warning; pass the filename as a
separate argument instead. Dynamic nested shell source, implicit shell stdin,
and templates combining `{file}` with heredocs, backticks, arithmetic or process
substitution are also skipped. These restrictions prevent interpreting filename
bytes as code and do not change the project-wide formatter protection checks.

## The shape of a hook (ADR-014)

A hook is a PAIR: a thin shell `<hook>.sh` and its body `<hook>.py`, side by
side in this directory. Python inside a heredoc is a STRING to every tool that
reads code — the repo map, the linter, `grep` — and the body in a file of its
own is what makes it code again. Nothing changes for whoever calls it: a hook
is still `bash <hook>.sh <args>`.

The shell is the half that a shebang cannot replace, and it keeps exactly three
jobs: choose the interpreter at run time, fail open when there is none, and
mount the environment the body reads. The body is plain python: **no shebang
and no execute bit** — whoever picks the interpreter is the shell, and a
shebang invites the `bad interpreter` that job 2 exists to prevent.

Canonical skeleton. Copy it verbatim; `<hook>` is the only part that varies:

```bash
#!/usr/bin/env bash
# HelmIt — <hook>: <what it does, in one line>.
set -u

# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
# Fail open: no interpreter, no hook — never an error in a project that may
# not even be a HelmIt one.
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || exit 0

# ... argument parsing and the exported variables the body reads ...

exec "$PY_BIN" "$SELF_DIR/<hook>.py" "$@"
```

Two notes for whoever converts a hook that already exists:

- What the heredoc received as `"$PY_BIN" - <args>` the body receives as
  `"$PY_BIN" "$SELF_DIR/<hook>.py" <args>`: `sys.argv[1:]` is unchanged, only
  `argv[0]` stops being `-` and becomes the file path.
- A hook that needs the OPTIONAL tree-sitter library probes the /env venv
  before the plain interpreter (see `repo-map.sh`). That probe is the declared
  exception, not part of the skeleton — a hook that does not need the library
  must not inherit it.

### Legitimate variations of the shell

The skeleton is the DEFAULT, never a mould. The phase-27 conversions met four
shapes that depart from it and kept every one of them VERBATIM, because the
hook already behaved that way — and the principle behind that decision is the
one to carry into the next conversion: **identical observable behavior beats
"copy the skeleton"**. A conversion moves WHERE the python lives; it must not
change what the caller sees. So a hook that already spoke goes on speaking, and
one that already answered JSON goes on answering JSON. The four below are
LEGITIMATE — recognise them instead of "fixing" a hook to fit the mould, and
when none of them applies, the skeleton is still the answer.

1. **Fail-open that SPEAKS.** `dashboard.sh`, `metrics.sh`, `lock.sh` and
   `yolo.sh` print `WARNING: <hook> SKIPPED — no python interpreter ...` on
   stderr and then `exit 0`, instead of the skeleton's silent
   `|| exit 0`. Use it when the silence would be MISREAD: `lock.sh` adds that
   concurrent sessions will NOT be detected, `yolo.sh` that the mandate cannot
   be read, so approvals stay conversations. The exit code stays 0 and stdout
   stays clean — the hook still fails open; only the silence is dropped.

2. **`exec` with an environment PREFIX.** `heartbeat.sh`
   (`HB_ROOT=... HB_HOOKS=... HB_DRY=... HB_SIG=...`) and `dashboard.sh`
   (`DASH_ROOT=... DASH_DIR=... DASH_CMD=... DASH_PHASE=...`) hand the body its
   context through the environment. That is job 3 — mounting the environment —
   done explicitly: the shell has ALREADY parsed the command line, so the body
   reads named variables instead of parsing `sys.argv` a second time, and the
   arguments may be consumed in bash rather than forwarded. The prefix is where
   the contract between the two halves is written down, in one place.

3. **Fail-open that answers JSON on STDOUT.** `repo-map.sh` declines through
   `unavailable()`, which prints `{"available": false, "reason": "..."}` and
   exits 0. That is the CALLER'S contract, not taste: every consumer of this
   hook parses JSON, so an empty stdout would reach it as a parse error dressed
   up as a fail-open. Whatever shape a hook answers in when it works is the
   shape it owes when it declines.

4. **A gate of several STAGES, with an exception for a directed query.** Still
   `repo-map.sh`: `HELMIT_MAP=off` and `no-python` decline ABSOLUTELY, while
   `lib-absent` declines CONDITIONALLY — a directed query (`--files` or
   `--symbol` on `show`) crosses it, because reading the base the last refresh
   left on disk parses nothing and needs no library (REQ-271). A malformed
   command line is NOT one of the stages: it exits 2 with a message on stderr,
   because bad syntax is something the caller can fix and a silent
   `{"available": false}` would hide it. `dashboard.sh` carries a second stage
   of its own, placed AFTER the interpreter is resolved: no `.helmit/` in the
   project means there is nothing to render, so it says so on stdout and
   exits 0.

One line per script, and a guard in the suite compares this list with the
directory (`hooks-readme-matches-directory`): a hook without a line, or a line
without a hook, fails. A README that lies about its own inventory is drift
coming in through the front door. A `<hook>.py` body gets NO line of its own —
nobody calls it — it is declared ON its shell's line, which is how this
inventory counts the pair instead of half of it.

| script | what it does |
|---|---|
| `commit-gate.sh` | Commit checkpoint gate: resolves the task from the commit subject, runs its chart `verify:`, then applies staged quick guards (PreToolUse layer). Body: `commit-gate.py`. |
| `proof-sandbox.sh` | Materializes the exact staged or HEAD tree in a disposable local worktree, runs proof there, and recovers abandoned owned sandboxes without touching the user's checkout. Body: `proof-sandbox.py`. |
| `pre-commit` | The independent git floor: staged whitespace plus shell/Python/JSON syntax, copied into `.git/hooks/`; it never runs the product suite (ADR-003/ADR-007). |
| `auto-format.sh` | Runs the project's format command after edits, and refuses a project-wide one that would rewrite `.helmit/` (REQ-102). Body: `auto-format.py`. |
| `sanity.sh` | Structural verifier for the `.helmit/` artifacts. Body: `sanity.py`. |
| `inbox-receipt.sh` | Selective active-Inbox summary plus lossless annual archive of resolved items; post-write receipt remains fail-open. Body: `inbox-receipt.py`. |
| `state-retain.sh` | Compacts STATE to current operational facts and exposes a bounded resume summary without dropping unresolved decisions. Body: `state-retain.py`. |
| `run-log.sh` | Write-ahead log of work IN FLIGHT — the only thing that survives the death it describes. Body: `run-log.py`. |
| `commit-transaction.sh` | Provenance for a Git commit attempt and conservative recovery that preserves every Git index lock. Body: `commit-transaction.py`. |
| `reconcile.sh` | Decides what to do about in-flight work on return: forward, reconcile, or an honest stop. Body: `reconcile.py`. |
| `lock.sh` | Mutual exclusion per working tree, with liveness by HEARTBEAT (never "the pid exists"). Body: `lock.py`. |
| `change.sh` | Allocates repository-wide monotonic `CHG-NNN` identities from the versioned `CHANGES.md` ledger under lock and revalidates candidates before commit. Body: `change.py`. |
| `handoff.sh` | The resume artifact: renders the derived facts, keeps the written half honest. Body: `handoff.py`. |
| `next-status.sh` | Compact read-only routing snapshot shared by `/next`, handoff and dashboard; STATE repair is an explicit subcommand. Body: `next-status.py`. |
| `remote-status.sh` | Reports local branch/upstream divergence and the oldest local-only commit without fetching or mutating Git. Body: `remote-status.py`. |
| `session-close.sh` | Canonical typed session close: stop first, then a minimal current STATE-derived handoff after a clean stop. Body: `session-close.py`. |
| `session-start.sh` | Fires the handoff at session start. Body: `session-start.py`. |
| `context-contract.sh` | Checks the native `CLAUDE.md`/`AGENTS.md` lease before an adapter routes autonomous work; it only classifies the opposite harness file for assisted `/env` migration. Body: `context-contract.py`. |
| `env-check.sh` | The cheap /env staleness detections as code: real pendencies one per line, absolute silence when there is nothing (REQ-206). Body: `env-check.py`. |
| `heartbeat.sh` | The per-session guardian beat: decides whether to resume, and acts on it. Body: `heartbeat.py`. |
| `executor-lease.sh` | Records an expiring interactive-activity lease and verifies it against an open task claim; heartbeat beats only read it. Body: `executor-lease.py`. |
| `session-activity.sh` | Records a short-lived, checkout-local host event per session without claiming a task or lock. Body: `session-activity.py`. |
| `preflight.sh` | Read-only, one-shot working-tree diagnostic: clean, changed paths, or a conflicting executor proved by fresh lock+lease. It never owns artifacts, stages, or commits. Body: `preflight.py`. |
| `heartbeat-owner.sh` | Records and verifies the Codex Desktop automation owner against the current task before any heartbeat lifecycle act. Body: `heartbeat-owner.py`. |
| `goal-owner.sh` | Reports the current Codex task Goal fail-open and refuses a Goal whose declared owner is another task. Body: `goal-owner.py`. |
| `yolo.sh` | THE autonomy mandate — arms, reports, expires and reaps it (REQ-118). Body: `yolo.py`. |
| `req-close.sh` | Closes a numbered phase after every planned task and its matching full-suite receipt prove the phase requirements. Body: `req-close.py`. |
| `roadmap-status.sh` | The ROADMAP status column, DERIVED from the phase artifacts on disk — never from the `workflow:` field it exists to recover (REQ-265/REQ-266). Body: `roadmap-status.py`. |
| `metrics.sh` | Token accounting core: parse, aggregate, reconcile. Body: `metrics.py`. |
| `metrics-collect.sh` | Hot capture of token usage (PostToolUse + Stop). Body: `metrics-collect.py`. |
| `dashboard.sh` | The project board, DERIVED from the artifacts; renders to a single static HTML file. Body: `dashboard.py`. |
| `dashboard-i18n.json` | The board's prose overlay per language — how a hook speaks the user's language without holding pt-BR inline (ADR-013). |
| `spec-sync.sh` | Reconciles a spec against the SOURCES it was written from, and reports drift. Body: `spec-sync.py`. |
| `repo-map.sh` | The optional deterministic code map (tree-sitter, fail-open, ADR-009). Body: `repo-map.py`. |
| `discover.sh` | Brownfield discovery: deterministic layer-1 scan of an existing codebase. Body: `discover.py`. |
| `parallel-hint.sh` | The runner table, in one place: has this test command a known parallel form? Proposes it for a human to confirm, never runs it (REQ-198/REQ-199). Body: `parallel-hint.py`. |
| `quality-receipt.sh` | Runs complete proof through the shared HEAD sandbox, records evidence against the exact tree and product fingerprint, and decides whether it still matches. Body: `quality-receipt.py`. |
| `delivery-report.sh` | Derives the on-screen delivery report from committed-task WAL events, task artifacts and reachable Git commits. Body: `delivery-report.py`. |
