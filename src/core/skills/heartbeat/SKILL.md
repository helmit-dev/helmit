---
name: heartbeat
description: "Optional interruption recovery for an unattended mandate. on arms one task-owned native beat, off disarms idempotently, and status reports. It never drives normal progress."
---

# /heartbeat

Heartbeat is an optional recovery path for a real interruption. Normal work
continues in the same active flow and waits for executor events; a recurring
beat must never poll progress, supervise a live executor, or renew execution
liveness.

The portable hook `core/hooks/heartbeat.sh` derives one decision from the run
log, Git position, mandate and executor lease. The adapter owns scheduling.
There is no project arming file and no background shell loop.

## Commands

- `on [interval]` — arm recovery, 15 minutes by default.
- `off` — remove recovery without changing the mandate.
- `status` — report mandate, latest decision and owned automation.

Before the first project write, run `preflight.sh check` once. A dirty tree is
advisory. Only proven concurrent execution blocks the affected operation. If
executor evidence is incomplete, suspend automatic recovery; do not block
manual work or guess that nobody is active.

## `on`

Arm only when all of these facts hold:

1. `yolo.sh reap`, then `yolo.sh status`, shows an in-force mandate with
   `unattended: true`. That value is explicit prior consent for recovery.
2. `config.json` declares non-empty test, build and lint commands.
3. This host has a task/session-native scheduling primitive.

Refuse with the missing fact and its remedy. Do not ask another confirmation:
the yolo command records the user's recovery choice. Ordinary yolo without an
explicit recovery request remains attended and does not arm heartbeat.

Create exactly one recurring primitive for this task:

- Claude Code: its session-native cron.
- Codex Desktop: a native `heartbeat` automation targeting the current local
  task, created through `automation_update` with `targetThreadId` equal to
  `CODEX_THREAD_ID`.
- Codex CLI: refuse and declare that no native scheduler exists.

Never emulate the primitive with `sleep`, an OS scheduler, a background shell,
or a standalone/global task.

Immediately register the returned automation id with:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/heartbeat-owner.sh" arm <automation_id>
```

Arming is idempotent for the same automation and task. If another automation
already owns the task, remove the attempted automation and refuse; never leave
two recovery loops attached to one task.

Report the interval, that the machine must remain awake, and that the user can
disable recovery with the heartbeat command or disable autonomy and recovery
together with the yolo command.

## Beat contract

The automation prompt does only this cheap probe before any project reading:

1. `heartbeat-owner.sh verify <automation_id>`; a refusal ends the beat.
2. `heartbeat.sh beat`; act literally on its single decision line.

The beat itself must not touch `lock.json`, create or renew an executor lease,
load the workflow, inspect the dashboard, or infer progress. Decisions mean:

- `IDLE` — absolute silence. Do not load the next route.
- `RESUME` — invoke the next skill in this same task under the existing
  mandate. Typed `gate`, `awaiting_input`, and `clean` stops never reach here.
- `WAIT until <iso>` — arrange one native one-shot at that time; keep the
  recurring recovery beat.
- `WAIT backoff <min>` — take no extra action; the recurring beat is enough.
- `DONE` or `DISARM` — remove the recurring and pending one-shot primitives,
  verify removal, then clear ownership. A repeated terminal decision means
  cleanup failed and must be reported, not hidden.

An old in-flight claim resumes only when the executor lease is definitively
inactive. A fresh matching lease means `IDLE`; malformed or unavailable
activity evidence also means `IDLE` with an uncertainty reason. Uncertainty
stops only automatic recovery.

## `off`

Verify identity, remove the owned recurring and pending one-shot primitives,
verify removal, then run `heartbeat-owner.sh clear <automation_id>`. Cleanup is
idempotent: already absent is success. Never delete another task's automation.

Do not ask to disarm the mandate. Report whether autonomy remains active; the
user may disable it separately with the yolo command.

## `status`

Read only and report:

- `yolo.sh status` in plain language;
- the newest `beat` entry in `.helmit/run.jsonl`;
- whether the current task has one native automation whose id passes
  `heartbeat-owner.sh verify`.

Project state alone never proves that an automation exists.

## Continuity and safety

- Same-turn work uses event-driven executor waits. Heartbeat is not its engine.
- `DONE`, `DISARM`, explicit `off`, mandate expiry and final cleanup remove the
  owned automation and verify that removal.
- A live Codex Goal can preserve platform continuity, but its absence does not
  change the HelmIt route. Never create, replace, complete or cancel a Goal
  unless the user explicitly requested that mutation.
- The scheduler belongs to the task/session; project A never resumes project B.
- Typed stops follow the ordering contract in `handoff.sh`; do not duplicate
  that algorithm here.

Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax;
on Codex, invoke the skill through the `$` selector or `/skills` as documented
by the Codex adapter.

## Guidance footer

Leave `STATE.md` unchanged. Report whether recovery is armed, its interval and
how to disable it, then offer the same next workflow step the router derives.
