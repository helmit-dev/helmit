# Plan — Delivery <id>: <name>
status: approved         <!-- compatibility value: executable plan, not a human-approval gate -->
prepared-by: agent
approved-by: <!-- optional historical compatibility: human | yolo -->
parent: <roadmap delivery id>
anchor: <one line — why this delivery exists / its intended outcome>
requires: <delivery ids, or "none">
satisfies: <REQ-IDs this delivery is responsible for>
promoted_from: <prior artifact id, if promoted — else omit>

## Foundation checks
- Product shape: <classification from KEEL/stack>
- Required foundations present or planned: <yes — list | N/A>

## Tasks
<!-- Tasks are complete outcome slices, not commit-sized or agent-sized units.
     A task may use several logical commits; one coherent commit may close
     related tasks. Every task keeps a stable identity, requirement relation
     and focused final verify. `files:` is an optional planning observation,
     never an ownership boundary or a commit gate. -->
- [ ] <id>.1 <outcome>  · anchor: <why>  · satisfies: REQ-00X  · verify: <focused proof>  · files: <likely paths, optional>
- [ ] <id>.2 <enabling outcome>  · anchor: <why>  · supports: REQ-00Y  · verify: <focused proof>

<!-- markers: [ ] todo · [>] in-progress · [x] done · [blocked: reason]
     Tick a task only when its whole outcome and final verify are complete.
     The closing logical commit carries the tick and corresponding STATE
     transition. Earlier logical commits retain the same task identity but do
     not claim completion. A human-only criterion records its review reason. -->

## Execution hints (optional)
- Independent candidates: <task ids that may benefit from parallel execution>
- Integration boundaries: <dependency or risk boundary and why it merits a complete proof>
- Isolation hints: <task ids that may benefit from a disposable worktree>

## Requirement → test mapping
- REQ-00X → task <id>.1 → test <name> · required: behavior · provides: behavior
- REQ-00Y → task <id>.2 → test <name> · required: mechanism · provides: mechanism
<!-- Proof levels: structural | mechanism | behavior | human.
     structural proves an instruction/schema; mechanism executes the producer;
     behavior observes the user-facing result; human is reserved for judgment
     automation cannot make. Higher executable evidence satisfies lower levels;
     human is separate and is never inferred. Prefer a natural red reproduction
     for an observable defect and retain its green regression. A preserving
     refactor starts from a green baseline; documentation and new mechanisms use
     the level their promise needs. Never fabricate a failure. Record a material
     limitation in the existing task, mapping or SPEC, not in a new ledger. -->
- Coverage: all delivery REQs mapped? <yes | list orphans>

---
Built with HelmIt — helmit.dev
