# Archetype Checklist (consulted by /chart; classification fed by /arch)

> Purpose: ensure structural foundations are never skipped.
> Extend this file whenever the agent misses a foundation (harness engineering:
> every structural mistake becomes a permanent line here).

## If the app has a DATABASE
A "Phase 0 — Foundation" MUST exist before any feature phase, covering:
- Data model / schema definition
- Migration strategy
- Connection / pooling configuration
- Test data seed

## If the app has AUTHENTICATION
- An auth foundation MUST precede any protected endpoint.
- Define: identity model, token strategy, session/refresh policy.

## If the app is MULTI-LAYER (backend + frontend)
- API contracts MUST be defined before the frontend consumes them.

## If the app has EXTERNAL INTEGRATIONS
- Define: credentials handling, failure/retry policy, sandbox vs prod config,
  before any feature depends on the integration.

## General foundation (Phase 0) usually includes
- Project scaffold + build/test/lint commands wired (the gates depend on them)
- Basic CI (lint + test on push)
- Config / secrets strategy
