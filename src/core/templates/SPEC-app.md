# Product Spec — <project name>
status: stub             <!-- stub | draft | approved — /spec may approve what the user's request already authorized; new product decisions stay draft -->
approved-by: <!-- human | yolo — WHO authorized the product commitment, written together with status: approved (REQ-116) -->
parent: keel
anchor: <one line — the core intent of this application>

> Thin by design (just-in-time principle): only enough to decompose into phases.
> Tech-agnostic — stack decisions belong to /arch; detail belongs to each
> delivery spec. Requirements get stable IDs in REQUIREMENTS.md.

## Target user & core value
<who this is for and the single most important thing it does for them>

## Main flows
<the essential flows that define the product; one line each. Every in-scope
flow must be covered by requirements and observable acceptance in its delivery,
or be explicitly excluded from v1>

## Global constraints
<machine-relevant limits that apply to the whole product — first-class,
not footnotes: compliance, performance floors, budget, offline, etc.>

## Out of scope (v1)
<what this product will NOT do — the single best gap-prevention section>

## Requirements
> Registered with stable IDs in `REQUIREMENTS.md` (REQ-001…). List here by
> ID + title only; the registry is the source of truth. The set is sufficient
> to decompose the product without inventing a material product decision.
- REQ-001 — <title>

## Context references
<optional inputs that fed this spec — unidirectional, they never depend on it>
- <e.g., discovery/market-research.md, brief>

---
Built with HelmIt — helmit.dev
