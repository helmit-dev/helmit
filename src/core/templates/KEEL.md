# KEEL — project rules, gate commands, and architecture decisions (always loaded)

> Non-negotiable rules. The agent re-reads this every session.
> Keep it surgical: if removing a line wouldn't cause a mistake, cut it.
> Break the ADR log into its own file only when it hurts (~5–7 entries or
> this file past ~200 lines).

## Stack
<!-- filled by /arch — macro only -->
- Backend: <e.g., .NET 8 / Node 20 / Python 3.12>
- Frontend: <e.g., Vue 3 / React / none>
- Database: <e.g., PostgreSQL 16 / none>

## Commands (used by the deterministic gates — must be exact; mirrored in config.json by /arch)
- Test:  <e.g., dotnet test>
- Build: <e.g., dotnet build>
- Lint:  <e.g., dotnet format --verify-no-changes>
- Format: <optional auto-format command>

## Hard rules
- Clear, localized, directly verifiable requests may use ordinary edits and Git
  without CHG, task IDs or lifecycle records, even in source and tests. Use CHG
  when investigation, decisions, coordination or continuity need tracking;
  use deliveries for larger commitments. Judge impact, not file paths or size.
- Every logical commit passes the deterministic staged quick floor. A candidate
  that closes a task also passes its focused declared `verify:`; complete-suite
  proof belongs to explicit integration and delivery boundaries.
- Prefer a natural red reproduction for an observable defect. Refactors,
  documentation and new mechanisms use the most relevant green baseline,
  characterization, structural or behavior proof without fabricating failure.
  Evidence demonstrates the claimed result and discloses material limits.
- Focused proof observes the exact staged tree; complete proof observes the
  exact committed HEAD tree. Both run in a disposable local proof worktree so
  repository-relative mutations do not alter the user's checkout. This is not
  an OS security sandbox or authority for external access.
- Tests protect observable guarantees. Pin exact text only for public or
  machine-consumed interfaces; check agent policy semantically and remove a
  duplicate only when another case preserves the same independent failure mode.
- NEVER bypass the commit gate: no `git commit --no-verify`, no disabling hooks.
- Commits are coherent review checkpoints: a task may span several commits and
  one commit may close related tasks when all identities and proofs remain explicit.
- Never edit files under `.helmit/` except via the workflow commands.
  Single exception: `.helmit/INBOX.md` accepts appends at any moment (the
  corrections capture channel) — out-of-scope findings are registered there,
  never fixed inline.
<!-- project-specific hard rules go here; add a line whenever a structural
     mistake happens (harness engineering) -->

## Conventions
<!-- coding conventions, naming, error handling — filled by /arch (greenfield)
     or discovery (brownfield), grown one correction at a time.
     The first line below is the HARNESS DEFAULT and it is born here, not only
     in /arch: a convention seeded solely by a command reaches nobody whose
     KEEL predates it (REQ-257). Adjustable at the /arch gate — the default is
     the harness's, the convention is the project's. -->
- self-explanatory code — comments only where the code cannot speak; rationale
  lives in ADRs, never in comments
- <convention>

## Decisions (append-only ADR log — do NOT re-litigate; propose a NEW ADR to change one)
- ADR-001: <decision> — <date> — Reason: <why> — Do NOT revisit.

---
Built with HelmIt — helmit.dev
