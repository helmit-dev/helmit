# Architecture Tradeoffs Checklist (consulted by /arch)

> Purpose: ensure macro architecture decisions are made deliberately, not by
> default. No personas — this file IS the "Architect knowledge", versioned.
> Extend whenever a missed tradeoff causes rework (harness engineering).
> For each relevant item: present 2–3 viable options with pros/cons, recommend
> one, let the user decide, log the choice as an ADR in KEEL.md.

## Data
- Relational vs document vs key-value — driven by the data shape in the spec.
- Single store vs multiple — avoid multiple without a clear reason.
- Migration strategy from day 1 (the Phase 0 foundation depends on it).

## Application shape
- Monolith vs services — default to monolith unless the spec forces otherwise.
- Sync vs async/queue — only introduce a queue if a requirement needs it.
- Layer boundaries (e.g., API / domain / data) — define before Phase 0.

## Interface / delivery
- API style (REST / GraphQL / RPC) — and contract-first if multi-layer.
- Server-rendered vs SPA vs API-only.

## Cross-cutting (decide only what Phase 0 needs)
- AuthN/AuthZ approach (if the app has auth).
- Config/secrets strategy.
- Logging/observability baseline.
- Test strategy + the EXACT test/build/lint commands (REQUIRED — the
  deterministic gates depend on them; written to KEEL.md AND config.json).

## Defer list (do NOT decide now unless Phase 0 is blocked)
- Caching layers, scaling/HA topology, advanced infra — revisit per phase
  when needed (just-in-time).
