# Validation — Phase <id>: <name>
date: <iso-date>
result: passed | failed | passed-with-human-items

> Written by /ship, or prepared by the optional /validate diagnostic. A
> scoreboard, not a report — details live in test output and Git. Every check
> is binary; no scores, no partial credit.

## 1. Snapshot receipt
- scope: validate:<phase> | implement:<phase>:integration:<reason> | ship:<phase> · commit: <hash> · tree: <hash> · receipt: pass|fail · match: pass|fail

## 2. Suite
- test: pass|fail · build: pass|fail · lint: pass|fail

## 3. Requirement coverage (set check)
- Phase REQs: [REQ-...]
- Covered by ticked tasks: [REQ-...]
- Orphans: none | [REQ-...]   <!-- fail if any -->

## 4. REQ → test proof
- REQ-00X → test <name> → pass|fail|missing · required: behavior · provides: behavior · level: pass|fail
<!-- one line per REQ; a covers: declaration without a passing test at the
     required proof level is a claim, not proof -->

## 5. Acceptance checklist
- [x|✗] <criterion>            <!-- binary -->
- [human] <criterion>          <!-- needs human eyes — never self-graded -->

## 6. Human review
- none | <criterion explicitly cleared by the user>

## Failures & routing
- <what failed> → route: /implement (code) | /chart (charting gap) | /spec (spec problem)

---
Built with HelmIt — helmit.dev
