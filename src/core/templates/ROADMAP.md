# Roadmap — <project name>
status: stub             <!-- stub | draft | approved — approved with the product commitment already authorized by the user -->
parent: spec-app

> The phase decomposition of the product spec. Thin: each phase gets its
> detailed delivery spec just-in-time (/spec when the phase starts) — never here.
> Phase ordering respects `requires:`; /next and /chart enforce it.

## Phases

| id | name | anchor (why it exists) | requires | covers (REQ) | status |
|----|------|------------------------|----------|--------------|--------|
| 0 | Foundation | <transversal foundations: schema, config, CI> | none | REQ-... | todo |
| 1 | <name> | <one line of intent> | 0 | REQ-... | todo |

<!-- status: todo | spec | planned | implementing | validated | shipped
     (mirrors the phase-scoped workflow enum in STATE.md) -->

## Notes
- Phase 0 — Foundation MUST exist if the app has a database, auth, or multiple
  layers (see archetype-checklist.md).
- Promotions/demotions keep their trail: a promoted artifact carries
  `promoted_from:`; historical tasks without a phase may point `parent: keel`.
- BROWNFIELD projects: the roadmap is born EMPTY (the existing system is the
  implicit baseline — never decompose what already works). Phases enter on
  demand: a delivery /spec adds a row when its scope is authorized; localized
  CHGs live in `CHANGES.md` and never appear here.

---
Built with HelmIt — helmit.dev
