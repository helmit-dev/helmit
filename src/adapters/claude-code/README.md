# Claude Code adapter

The core (`src/core/`) speaks contract; this adapter speaks mechanism. Anything
Claude-Code-specific lives here or is explicitly annotated in the skills'
"Cross-platform note (adapter contract)" sections.

## What this adapter provides

- **Plugin manifest**: `src/.claude-plugin/plugin.json` (plugin root = `src/`,
  shared with the Codex manifest side by side — ADR-002).
- **Hooks**: `adapters/claude-code/hooks.json` —
  - `SessionStart` on `startup|resume` → `core/hooks/session-start.sh`
    (REQ-138: replays `handoff.sh render` as `additionalContext`, ONLY when
    the render carries real pendency — a clean project stays silent, REQ-108).
    Matcher rationale (JSON carries no comments): `clear`, `compact` and
    `fork` are IN-conversation transitions — replaying a handoff there would
    be noise, not resumption. Never runs test/build/lint; absolutely
    fail-open (exit 0 on every path — it informs, never blocks).
  - `PreToolUse` on `Bash` → `core/hooks/commit-gate.sh` (runs a task commit's
    chart `verify:` once plus staged quick guards; strong: not disableable by
    the agent).
  - `PostToolUse` on `Write|Edit` first runs `core/hooks/executor-lease.sh
    renew`: only an existing open claim for this interactive session can be
    renewed. It then runs `core/hooks/inbox-receipt.sh`, which emits the real
    `sanity.sh check` result after an INBOX write, and
    `core/hooks/auto-format.sh`. A heartbeat beat is Bash, not `Write|Edit`, so
    it never renews or manufactures this lease. Claude Code executes configured hooks without
    the Codex-style per-user Trust confirmation; the skill's explicit receipt
    remains the cross-platform floor if the native event is unavailable.
- **Environment variables**: `CLAUDE_PLUGIN_ROOT` (plugin root) and
  `CLAUDE_PROJECT_DIR` (project dir, available to hooks).
- **Skill invocation**: plugin skills become namespaced slash commands —
  `/helmit:<cmd>` (e.g. `/helmit:next`). This is the canonical written syntax
  used throughout the core skills and templates.
- **Leased section**: `/helmit:setup` injects the HelmIt section into
  `CLAUDE.md` (marker-delimited; removed by `/helmit:uninstall`).
- **Subagents**: when `/helmit:implement` selects optional delegation for truly
  independent work, Claude Code supplies clean-context executors through the
  **Task tool**. Direct execution remains the normal path.
- **Install flow**: `/plugin marketplace add <repo>` then
  `/plugin install helmit` (marketplace file: `.claude-plugin/marketplace.json`
  at the repo root — legacy location). Uninstall: `claude plugin uninstall
  helmit` (CLI; the TUI path is known-unreliable).

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
| install flow | `/plugin marketplace add` + `/plugin install` | `codex plugin marketplace add` + `/plugins` UI | to-validate-3.5/3.6 |
| interactive executor lease (REQ-397) | `PostToolUse(Write\|Edit)` renews only a matching open claim; beats do not match | `PostToolUse(apply_patch)` renews only a matching open claim; beats do not match | fixture-tested |
| token metrics capture | `PostToolUse(Bash)`+`Stop` hooks parse session transcript (dedup by requestId, subagents/ summed) | same hooks parse rollout `token_count` events; requires user hook Trust — cold reconciliation (`metrics.sh reconcile`) covers untrusted/missed sessions | validated (fixtures) / to-validate-4.5 (Codex) |
| session-start handoff trigger (REQ-138) | `SessionStart` hook, matcher `startup\|resume`; stdout JSON `hookSpecificOutput.additionalContext` enters the model context | `SessionStart` hook, matcher `^(startup\|resume)$` (sources: startup/resume/clear/compact; no fork); same JSON `additionalContext` shape; plugin hooks require user Trust | validated (fixtures) / to-validate (Codex live, docs checked 2026-08-03) |

Status legend: **validated** = proven on both platforms (or harness-independent);
**to-validate-3.5/3.6** = mechanism defined from official docs, live Codex
validation pending in tasks 3.5/3.6; **phase-6** = mechanism deferred to the
`/implement` execution phase.

## OTEL alternative (teams)

Claude Code can export `claude_code.token.usage` / `claude_code.cost.usage`
via OpenTelemetry (`CLAUDE_CODE_ENABLE_TELEMETRY=1`), with the
`query_source` attribute (`main` | `subagent`) — an alternative for
organizational aggregation. HelmIt's own mechanism is local-first and
per-task (`.helmit/metrics.jsonl`); the two coexist.
