# Inbox — bugs, friction, improvement ideas
parent: keel

> Capture channel for anything found OUTSIDE the current task's scope — a bug,
> an improvement, a friction point — by the user OR the agent. Capturing is
> NOT deciding: append the item and return to the task at hand; never fix an
> out-of-scope finding inline (it breaks atomic commits and traceability).
> This is the ONE `.helmit/` artifact that may be appended to at any moment.
>
> `/next` OFFERS triage at phase boundaries (or whenever the user asks).
> Each item gets exactly one destination, gated by the user:
> 1. limited CHG — maintenance, copy, configuration, or a bounded restoration
>    recorded in `CHANGES.md`, with one task and its focused proof;
> 2. Backlog — valid but deferred, destination noted;
> 3. new ROADMAP phase — gated edit, for big items or a correlated batch.
> Nothing leaves silently: an item only closes with its resolution written.
>
> Item format:
> `- [ ] YYYY-MM-DD · <where: skill/command/code area> · <what happened / what was expected>`
>
> Triage keeps the same item in a canonical, machine-checkable form:
> - open capture (under `## Inbox`): `- [ ] YYYY-MM-DD · <area> · <description>`;
> - routed phase (still under `## Inbox` until resolved):
>   `- [ ] [TRIADO -> FASE N / REQ-N,REQ-M] YYYY-MM-DD · <area> · <description>`; a numbered phase must list its exact REQs. A linked CHG closes its source item in the same useful commit instead of creating another routed-item grammar.
> - deferred work (under `## Backlog`): `- [ ] [BACKLOG -> <destination>] YYYY-MM-DD · <area> · <description>`;
> - resolved item (transiently under `## Closed`): `- [x] [FECHADO -> <REQ/commit or discard reason>] YYYY-MM-DD · <area> · <description>`.
>   `inbox-receipt.sh archive` moves it byte-for-byte to the versioned
>   `.helmit/history/INBOX-<year>.md`; ordinary reads never load that history.
>
> After every write that touches this file, run `sanity.sh check` and relay its
> receipt before continuing. The hook is reinforcement; this explicit receipt
> remains mandatory when a platform has no trusted post-write hook.
>
> Triage runs `inbox-receipt.sh summary --limit <n>` and reads the actionable
> batch, not the whole file or history: report open/routed/unrouted/backlog
> counts first, then read only the selected open items plus any linked
> context needed for a decision. After each batch, state what remains without a
> destination and invite complete triage. Use native multiple-choice with the
> recommended option first when available; otherwise give closed alternatives
> and an open response.

## Inbox

<!-- - [ ] 2026-08-22 · core/skills/next · example open capture -->

## Backlog

<!-- - [ ] [BACKLOG -> post-v1] 2026-08-22 · core/templates/INBOX · example deferred item -->

## Closed

<!-- Resolved items are archived after the write. Historical lookup is explicit:
     inbox-receipt.sh history --find <REQ, CHG, date, or text>. -->

---
Built with HelmIt — helmit.dev
