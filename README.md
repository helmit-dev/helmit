# HelmIt

English | [Português (Brasil)](README.pt-BR.md)

**A lean harness for agentic software development that uses Spec-Driven
Development (SDD) as a practical working discipline.** HelmIt keeps project
intent, progress, decisions, and proof in the repository so work can continue
across sessions without depending on one conversation's memory.

## What HelmIt helps you do

HelmIt gives a coding agent enough structure to carry a software delivery from
an expected outcome to a verified result without turning every change into a
large specification exercise.

- **Proportional specification.** A clear correction stays small. A delivery
  receives the detail needed to implement it without inventing product
  behavior.
- **Repository-backed continuity.** Requirements, decisions, current position,
  and pending work remain available when you change sessions, agents, or
  machines.
- **Deterministic protection.** Every logical commit crosses an independent
  staged quick floor. Completing tasks run focused proof, and delivery closure
  runs or reuses the complete configured test, build, and lint proof.
- **Visible authority boundaries.** The agent continues through routine
  implementation choices. Material product decisions and external actions
  remain yours.
- **One shared core.** Claude Code and Codex use the same skills, templates,
  hooks, and project artifacts, with platform-specific invocation where needed.

The core uses Bash and the Python standard library. It requires no database,
cloud service, or background runtime.

## The command to remember

```text
/helmit:next
```

`next` reads the project's recorded position, explains where the work is, and
identifies the eligible next action. In Codex, select the corresponding
`helmit:next` skill with `$`, `/skills`, or the Skills interface.

The normal path is:

| Outcome | Command | What establishes success |
|---|---|---|
| Prepare the repository | `/helmit:setup` | HelmIt files and the Git commit floor are installed |
| Define the product or delivery | `/helmit:spec` | The authorized outcome and acceptance are explicit |
| Record architecture and quality commands | `/helmit:arch` | Stack facts and exact checks are recorded |
| Check the working environment | `/helmit:env` | Required local tools are ready |
| Plan and implement | `/helmit:implement` | Logical commits and focused task proof pass |
| Close the delivery | `/helmit:ship` | Coverage, acceptance, and complete final proof pass |

`chart` remains available when you want planning as a separate view.
`validate` remains available when you want to inspect final readiness before
ship. Neither is a mandatory lifecycle stage.

Small maintenance and copy corrections use a bounded `CHG-NNN` record instead
of manufacturing a new requirement or delivery phase.

## Install

HelmIt installs from this repository as a native plugin. Register the catalog,
then install the qualified plugin name.

### Claude Code

```text
/plugin marketplace add helmit-dev/helmit
/plugin install helmit@helmit
```

### Codex

```text
codex plugin marketplace add helmit-dev/helmit
codex plugin add helmit@helmit
```

### Ask your agent to install it

You can also request the installation in plain language:

> **Claude Code:** "Install the HelmIt plugin for me. Add the
> `helmit-dev/helmit` marketplace, install `helmit@helmit`, and confirm that the
> plugin is installed."

> **Codex Desktop or CLI:** "Install the HelmIt plugin for me. Register the
> `helmit-dev/helmit` marketplace, install `helmit@helmit`, and confirm the
> installed version."

Review any actions the client asks you to authorize during installation.

Always use `helmit@helmit`. If several marketplaces are registered, an
unqualified plugin name is ambiguous. Codex presents plugin hooks as untrusted
on first installation so you can review and enable them.

## Start in a project

In Claude Code:

```text
/helmit:setup
/helmit:next
```

In Codex CLI or the IDE extension, select `helmit:setup` and `helmit:next` with
`$` or `/skills`. In Codex Desktop, select them from Skills.

`setup` prepares the project once. After that, `next` is the safe entry point
when you return to the project or change sessions.

## What stays visible

HelmIt records its working context under `.helmit/` in the project using it.
The local `.helmit/dashboard.html` summarizes the roadmap, requirements,
changes, Inbox, validation, and current position without requiring a server.

The dashboard is a projection of repository artifacts. The files remain the
source of truth, and deterministic writers refresh the dashboard when those
artifacts change.

## Greenfield and brownfield projects

For a new project, HelmIt helps define the product, architecture, quality
commands, and first delivery.

For an existing project, HelmIt treats working behavior as the baseline. It
detects observable stack and command facts from the repository, records gaps
honestly, and asks only about conflicts, missing required checks, or desired
architecture changes. It does not require the team to rewrite the existing
system as a specification before useful work can begin.

## Autonomy without weaker proof

`/helmit:yolo phase` and `/helmit:yolo full` let you authorize a wider span of
work without repeated approval prompts. They do not disable the commit floor,
focused verification, final proof, or external-action boundaries.

An optional heartbeat can recover an unexpectedly interrupted unattended run
on hosts with a native scheduling mechanism. It is not the normal supervisor
for active work.

## Documentation

- [Install and get started](https://helmit.dev/en/guides/getting-started/)
- [Understand the process](https://helmit.dev/en/guides/flows/)
- [Follow a delivery from spec to ship](https://helmit.dev/en/guides/phase-lifecycle/)
- [Understand tests and delivery proof](https://helmit.dev/en/guides/testing/)
- [Use autonomy modes](https://helmit.dev/en/guides/autonomy/)
- [Compare platform behavior](https://helmit.dev/en/guides/platforms/)
- [Troubleshoot common situations](https://helmit.dev/en/guides/troubleshooting/)
- [Portuguese documentation](https://helmit.dev/pt-br/)

## License

HelmIt is released under the [MIT License](LICENSE).
