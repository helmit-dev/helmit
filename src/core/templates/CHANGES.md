# Changes Ledger
parent: keel

> Repository-wide ledger for limited changes. Identity comes only from this
> versioned file: `CHG-001`, `CHG-002`, and so on. Each identity is append-only;
> its state may move from `open` to `done`, but an ID is never reused.

| id | kind | origin | intent | task | paths | verify | inbox | status |
|----|------|--------|--------|------|-------|--------|-------|--------|

<!-- status: open | done -->

---
Built with HelmIt — helmit.dev
