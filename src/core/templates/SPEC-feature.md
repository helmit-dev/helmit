# Delivery Spec — Phase <id>: <name>
status: draft            <!-- draft | approved — approve when it records authorized scope; pause only for a new material decision -->
approved-by: <!-- human | yolo — WHO authorized the delivery commitment, written together with status: approved (REQ-116) -->
parent: <phase id from ROADMAP.md>
anchor: <one line — why this phase exists / its intent>
covers: <REQ-IDs this phase is responsible for>

> Detailed, just-in-time (written when the phase starts, never earlier).
> EXACTLY these 6 sections — no more, no less.

## 1. Goals
<what must be true when this phase is done>

## 2. Out of scope
<what this phase will NOT do>

## 3. Constraints
<machine-relevant limits, first-class — not footnotes>

## 4. Prior decisions
<what is already decided and why — do not re-litigate; reference ADRs>

## 5. Requirements
> Each with its stable REQ-ID. New requirements discovered here are ADDED to
> `REQUIREMENTS.md` (never renumber existing ones).
- REQ-0XX — <requirement, binary and testable>

## 6. Acceptance criteria
> Binary, testable; Given/When/Then preferred. Every criterion must be
> provable by a test or explicitly flagged `[human]`. Cover every essential
> in-scope flow and each material failure or limit that changes its observable
> result; otherwise mark the behavior explicitly out of scope.
- Given <context>, when <action>, then <observable result>.

---

## Clarification record (only material decisions)
- Assumptions or hypotheses affecting scope or acceptance: <item and whether it
  is authorized or still pending evidence/decision, or none>
- Questions and answers that changed the commitment: <q → a, or none>

---
Built with HelmIt — helmit.dev
