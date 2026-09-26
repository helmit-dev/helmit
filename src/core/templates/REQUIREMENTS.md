# Requirements Registry
parent: spec-app

> Stable requirement IDs — the anchor of the traceability chain
> `REQ → task that satisfies it (CHART.md satisfies:) → test that proves it (/ship)`.
> Written by /spec (product level); extended by /spec (delivery level).
> IDs are NEVER renumbered or reused. Coverage is checked by set comparison,
> not judgment: a REQ no task covers is an orphan = a detected gap.

| id | requirement (binary, testable) | phase | status |
|----|--------------------------------|-------|--------|

<!-- status: todo | covered (a ticked task claims it) | proven (mapped test passes)
     proven is written by /ship on a passing delivery — it owns final closure.
     phase is a ROADMAP delivery id. A localized CHG restores an existing
     commitment and is tracked in CHANGES.md rather than manufacturing a REQ. -->

---
Built with HelmIt — helmit.dev
