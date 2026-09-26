# Codex adapter

The core (`src/core/`) speaks contract; this adapter speaks mechanism. Anything
Codex-specific lives here or is explicitly annotated in the skills'
"Cross-platform note (adapter contract)" sections.

## What this adapter provides

- **Plugin manifest**: `src/.codex-plugin/plugin.json` (plugin root = `src/`,
  shared with the Claude Code manifest side by side — ADR-002).
- **Hooks**: `adapters/codex/hooks.json` —
  - `PreToolUse` on `^Bash$` → `core/hooks/commit-gate.sh` (runs a task
    commit's chart `verify:` once plus staged quick guards). Codex declares
    `PreToolUse` a **guardrail**: simple shell
    only, and the USER can disable it via `/hooks`. It is therefore
    best-effort reinforcement. Its timeout is 600 seconds: expiration is not
    a verify verdict and a staged commit must be retried with the real gate.
    The git pre-commit floor is the OFFICIAL
    commit-gate guarantee (ADR-007).
  - A canonical `task_claimed` creates the first executor lease only after a
    matching lock is owned. `PostToolUse` on `^apply_patch$` renews that lease;
    `PostToolUse` on `^Bash$` renews it for interactive shell activity, while
    excluding `heartbeat.sh` and `heartbeat-owner.sh` recovery probes. Each
    renewal also beats the matching lock, and neither a foreign lock nor a
    closed claim can be renewed. The edit hook then runs
    `core/hooks/inbox-receipt.sh`, which emits the real `sanity.sh check`
    result after an INBOX write, and `core/hooks/auto-format.sh`. Codex hook
    Trust is required for these hooks. A
    trusted `PreToolUse` may reject a simple shell action, while this
    post-write receipt confirms what was actually written; the skill repeats
    the receipt explicitly when Trust is absent or disabled.
  - `SessionStart` on `^(startup|resume|clear)$` → `core/hooks/session-start.sh`
    (REQ-138). VERDICT (docs checked 2026-08-03, official Codex hooks
    reference — developers.openai.com/codex/hooks): Codex DOES have a
    `SessionStart` lifecycle event, with matcher source values `startup`,
    `resume`, `clear`, `compact` (no `fork`), and JSON stdout with
    `additionalContext` added as extra developer context (default cap ~2500
    tokens, tunable via `additionalContextLimit`). Wired for
    `startup|resume|clear` — a session that just LOST its context via
    `clear` is the handoff use case (REQ-150); `compact` stays out (the
    summary preserves the relevant context, replaying the handoff there
    would be noise). Plugin-bundled hooks
    require user hook Trust (like the metrics hooks): without Trust the
    trigger simply never fires — nothing is blocked, and the leased block
    (REQ-136) and skill preconditions (REQ-137) remain the Codex reach
    layers. Live Codex validation of the exact JSON wrapper is pending
    (to-validate).
    This hook deliberately **does not schedule beats**: a lifecycle hook can
    restore the mandate/handoff context, but it cannot be presented as a
    recurring executor.
  - **Heartbeat (Codex Desktop)**: the native primitive is a `heartbeat`
    automation attached to the current local thread. It is a recovery-only
    watchdog: it never performs normal progress polling and never supervises
    an executor or substitutes for an active orchestrator. The agent arms it through
    the Desktop `automation_update` contract with `targetThreadId` equal to
    `CODEX_THREAD_ID`; it records the returned identity with
    `heartbeat-owner.sh` and can subsequently observe, pause or
    delete only that same automation after ownership verification. Missing target or identity
    refuses to arm; there is no standalone/global fallback. The
    automation delivers a follow-up turn to this thread, where the prompt runs
    `core/hooks/heartbeat.sh beat` and obeys its decision. It is not a plugin
    hook, a shell loop, or an OS cron. The Codex **CLI** still has no such
    primitive: `/heartbeat on` must refuse there rather than promise unattended
    resumption. SessionStart above is recovery context for either case, not an
    implicit arming action.
    Before the core hook decides `RESUME`, the automation reads no project
    artifacts or progress; `IDLE` is silent and never invokes `/helmit:next`.
    A live executor is followed inside the orchestrator's same active turn
    through an event-driven wait (`wait_threads`), not through heartbeat turns.
  - **Goal continuity (Codex Desktop)**: an agent with a live HelmIt mandate
    observes the current task through `get_goal` before treating a turn as
    terminal. `goal-owner.sh status` reports only an explicitly supplied Goal
    identity for the current `CODEX_THREAD_ID`; missing Goal is diagnostic,
    never a block. `create_goal`, completion and replacement require the
    user's explicit request. A Goal is optional continuity evidence, not a
    prerequisite, executor, scheduler or authority to cross HelmIt gates.
- **Environment variables**: Codex exports `PLUGIN_ROOT`, plus
  `CLAUDE_PLUGIN_ROOT` for compatibility — core skills that reference
  `${CLAUDE_PLUGIN_ROOT}` resolve on both platforms. Hooks receive the
  project dir as the `cwd` field of the stdin JSON payload (no
  `CLAUDE_PROJECT_DIR` env var; the gate has a fallback — task 3.1).
- **Skill invocation**: there is NO `/helmit:<cmd>` slash-command syntax on
  Codex. The same SKILL.md files are invoked via the **`$` selector** (type
  `$` and pick the skill), via the `/skills` list, or implicitly when the
  request matches the skill's description. Wherever core files write
  `/helmit:<cmd>`, read it as "the skill named `<cmd>`" and invoke it through
  the selector.
- **Leased section**: `/helmit:setup` injects the HelmIt section into
  `AGENTS.md` (marker-delimited; removed by `/helmit:uninstall`).
- **Subagents**: Codex has its own native subagent primitive (not the Task
  tool); the `/implement` wave mechanism is validated in Phase 6.
- **Install flow**: `codex plugin marketplace add <repo>` then
  `codex plugin add helmit@helmit`. Uninstall: `codex plugin remove
  helmit@helmit`.
- **Plugin refresh and task boundary (REQ-324..326)**: Codex development uses
  `scripts/dev-sync.sh --codex-home /absolute/isolated/path`. The target is
  mandatory: the script refuses the normal `~/.codex`, then verifies before
  any bump that the target contains exactly one enabled `helmit@helmit` sourced
  from this repository. Only then it runs `env CODEX_HOME=<target> codex plugin
  remove helmit@helmit --json`, followed by `env CODEX_HOME=<target> codex
  plugin add helmit@helmit --json`, and verifies the added version from JSON.
  If removal or addition fails, it names that stage and prints a recovery
  command carrying the same target. A refresh changes the cached plugin files,
  not the skill locators already captured by an open Codex task. Before a
  HelmIt route acts, use `resolve-skill.sh <name>
  [advertised-path]`: it verifies and prints the active cache copy, warns when
  it replaced a stale locator, and stops when no active copy exists. It never
  copies or mutates cache files. Codex still owns the original UI locator.
  Start a new task after a successful refresh when practical; do not reuse a
  stale skill locator or copy a different cache directory into its place.
  Start a new task after a successful refresh. Do not reuse a
  stale skill locator and do not copy a different cache directory into its place.

## Name-collision mitigation (skill selector)

If two installed skills share the same `name`, BOTH appear in the Codex `$`
selector. Decided policy (Phase 3 clarification gate) — NO manual prefix in
the skill `name` (it would break the Claude Code namespace:
`/helmit:helmit-spec`). Mitigation order:

1. **Plugin namespace**, if Codex applies one to plugin skills (validated in
   task 3.5).
2. **Descriptions carry the "HelmIt" trigger word**, so the right skill is
   picked by description match.
3. **Manual `name` prefix only as a last resort**, if 1 and 2 prove
   insufficient.

## Parity mapping (contract → mechanism)

| contract | Claude Code mechanism | Codex mechanism | status |
| --- | --- | --- | --- |
| commands/skills invocation | namespaced slash command `/helmit:<cmd>` | `$` selector, `/skills` list, or implicit by description (no slash-command syntax) | to-validate-3.5/3.6 |
| commit-gate reinforcement | `PreToolUse` runs task `verify:` once plus staged quick guards (strong, agent cannot disable) | same policy in a user-disableable simple-shell guardrail | to-validate-3.5/3.6 |
| git floor (commit gate guarantee) | `.git/hooks/pre-commit` runs only the independent staged quick floor; never the product suite (ADR-007) | same file, same installer — harness-independent | validated |
| project-dir resolution (hooks) | `CLAUDE_PROJECT_DIR` env var | `cwd` field in the hook's stdin JSON (gate has a fallback — task 3.1, fixture-tested) | to-validate-3.5/3.6 |
| plugin manifest | `src/.claude-plugin/plugin.json` | `src/.codex-plugin/plugin.json` (same plugin root `src/`) | to-validate-3.5/3.6 |
| marketplace | `.claude-plugin/marketplace.json` (repo root, legacy) | `.agents/plugins/marketplace.json` (repo root, new) | to-validate-3.5/3.6 |
| leased section | `CLAUDE.md` | `AGENTS.md` | to-validate-3.5/3.6 |
| subagents / waves | Task tool (clean-context subagent per task) | Codex-native subagent primitive | phase-6 |
| install flow | `/plugin marketplace add` + `/plugin install` | `codex plugin marketplace add` + `codex plugin add helmit@helmit` | to-validate-3.5/3.6 |
| plugin refresh and task boundary (REQ-324..326) | `scripts/dev-sync.sh` re-syncs the cache (`claude plugin update helmit@helmit`) | remove/add with `--json`, verify version, then start a new task; no stale-locator fallback | fixture-tested |
| token metrics capture | `PostToolUse(Bash)`+`Stop` hooks parse session transcript (dedup by requestId, subagents/ summed) | same hooks parse rollout `token_count` events; requires user hook Trust — cold reconciliation (`metrics.sh reconcile`) covers untrusted/missed sessions | validated (fixtures) / to-validate-4.5 (Codex) |
| session-start handoff trigger (REQ-138) | `SessionStart` hook, matcher `startup\|resume`; stdout JSON `hookSpecificOutput.additionalContext` enters the model context | `SessionStart` hook, matcher `^(startup\|resume)$` (sources: startup/resume/clear/compact; no fork); same JSON `additionalContext` shape; plugin hooks require user Trust | validated (fixtures) / to-validate (Codex live, docs checked 2026-08-03) |
| lock identity (REQ-330) | `HELMIT_SESSION_ID`, then native Claude session id | `HELMIT_SESSION_ID`, then `CODEX_THREAD_ID` (durable task identity; `CODEX_SESSION_ID` fallback) | fixture-tested across separate hook calls |
| interactive executor lease (REQ-397) | claim start plus `PostToolUse(Write\|Edit, Bash)` renew a matching claim and lock; recovery probes are excluded | claim start plus `PostToolUse(apply_patch, Bash)` renew a matching claim and lock; recovery probes are excluded | fixture-tested |
| optional interruption recovery — heartbeat | an explicitly requested session-native cron fires the cheap beat; normal work stays in the live event-driven flow | **Codex Desktop:** one native `heartbeat` automation carries `targetThreadId=CODEX_THREAD_ID`; its `automation_id` is WAL-owned and verified before arm/observe/disarm/beat/clear, so A can only act on A. Beats never renew execution liveness. **Codex CLI:** no scheduler, so arming refuses. SessionStart restores context; it does not schedule. | Desktop contract verified structurally / CLI declared-gap |

Status legend: **validated** = proven on both platforms (or harness-independent);
**to-validate-3.5/3.6** = mechanism defined from official docs, live Codex
validation pending in tasks 3.5/3.6; **phase-6** = mechanism deferred to the
`/implement` execution phase; **declared-gap** = the platform lacks the
primitive and the skill declares it (never emulated with sleep loops or
background shells).

## Metrics & hook trust

The metrics hooks require user hook Trust, like any Codex hook. Without
Trust nothing is lost: `metrics.sh reconcile` sweeps the rollout files and
back-fills `.helmit/metrics.jsonl` at read time — metrics are never a gate.

The same Trust requirement covers the immediate INBOX receipt. `/env` reports
whether HelmIt hooks are configured, disabled, awaiting Trust, or operational;
until operational, the user should enable/trust them through Codex `/hooks`.
The portable skill receipt still runs after an INBOX write, so the artifact is
never accepted as healthy merely because the native reinforcement is absent.

## OTEL alternative (teams)

Claude Code can export `claude_code.token.usage` / `claude_code.cost.usage`
via OpenTelemetry (`CLAUDE_CODE_ENABLE_TELEMETRY=1`), with the
`query_source` attribute (`main` | `subagent`) — an alternative for
organizational aggregation. HelmIt's own mechanism is local-first and
per-task (`.helmit/metrics.jsonl`); the two coexist.
