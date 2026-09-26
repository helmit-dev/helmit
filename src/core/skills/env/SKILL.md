---
name: env
description: "Checks the environment against the stack and quality commands recorded during preparation. Installs, remote repositories, authentication, and system changes always require explicit confirmation."
---

# /env

Run AFTER /arch: the stack determines the required tools. Checking "is tool X
installed?" needs no AI — it is deterministic. Guiding the user to close the
gap is the conversational part.

---

## Working-tree safety (ADR-018)

Before the first write, lock, claim, executor dispatch or expensive gate, run
`bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/preflight.sh" check` once. `READY`
means no changes were observed. `CHANGED <paths>` is advisory: inspect Git
status, the staged and unstaged diffs, and every target already modified; it
never blocks merely because the worktree is dirty. `BLOCKED_CONCURRENT` stops
only when a fresh lock and matching fresh executor lease prove another executor
is active in this checkout.

Preserve unrelated edits and the existing index. Continue through compatible,
understood changes in a target file; pause only the affected operation for an
unresolved overlap or unknown intent. Before commit, review the staged diff and
stage only the intended paths or hunks—never `git add -A`. Do not repeat the
global preflight at staging or commit; the task verify and independent Git floor
judge the selected content.

---

## Preconditions (declarative gates — block if unmet)

1. `STATE.md` workflow is `arch-approved` (or later re-run) — KEEL Stack and
   Commands are filled. If not → route to `/helmit:arch`. STOP.

---

## Process

### 1. Build the required-tools list from KEEL
- From the Stack + Commands: runtime(s), package manager, test/build/lint
  tools, DB client/server if applicable, `git`.
- Check only tools required by the recorded stack and commands. Legacy track
  metadata never adds or removes tools and never changes readiness.

### 2. Check, deterministically
- **When the deep toolchain check runs (REQ-208): the version gap is the
  trigger, and the ONLY one.** Read `helmit_version` from `.helmit/config.json`
  and the plugin version from
  `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` — the same two fields the
  session trigger (`env-check.sh`) reads when it prints the one-line reminder
  that routes here. EQUAL → the toolchain of this very plugin version was
  already verified once: SKIP the per-tool sweep below, say nothing about
  versions (REQ-108), and keep every content-hash detection further down
  running unchanged. DIFFERENT, or the field absent → run the per-tool sweep,
  and when it completes UPDATE `helmit_version` in `.helmit/config.json` to
  the plugin version, declaring the write in the readiness report. That is the
  ONE automatic write this skill performs (phase 15, assumption 2): the field
  is HelmIt's own metadata — the last version whose toolchain this project
  verified — not a user artifact, and writing it is what makes the deep check
  run ONCE per version jump instead of once per session. The jump itself is
  REPORTING material (`helmit_version: 0.0.16 seen, plugin is 0.0.25`) and
  NEVER the verdict: no offer fires and nothing is declared stale because the
  versions differ — the version decides WHEN to check, the content decides IF
  anything is said.
- **Orphan top-level keys of `config.json` — the migration route for a removed
  field (REQ-209).** The session trigger (`env-check.sh`, check 6) compares
  the TOP-LEVEL keys of the project's `.helmit/config.json` against the
  plugin's own `templates/config.json` and prints one line per key that LEFT
  the template (`config.json: orphan top-level key "<k>" — removed from the
  template; run /helmit:env to migrate`). WHY it matters: a field removed from
  the template dies only for whoever installs tomorrow — in the project
  already installed it stays behind and LIES to whoever reads it. Here that
  line becomes an OFFER: name the orphan key WITH THE REASON — which REQ
  removed it and where the data lives now — and offer to delete exactly that
  key from `.helmit/config.json`, touching no other line. Execute ONLY on
  explicit user confirmation (permission boundary, step 4) — NEVER silently
  and NEVER as a side effect of the readiness report: the config is the
  user's project contract, and the hook that detects is a PURE READ.
  The KNOWN REASONS live HERE, in this list — the hook only detects, the
  story belongs to this conversation:
  - `yolo` — removed by REQ-118; the mandate lives in `.helmit/yolo.json`,
    local state written only by `core/hooks/yolo.sh` (read it via
    `yolo.sh status`). The leftover is not inert: an agent that reads it
    assumes a mandate nobody gave (field report, 02/08) — which is what makes
    this migration worth interrupting for.
  A key NOT in this list gets the GENERIC offer: name the key, say the
  current template does not carry it, and offer the removal WITHOUT inventing
  a reason — never fabricate which REQ removed it or where the data went.
  NOT orphans, never accused: keys the /setup wizard itself persists
  (`artifact_language` — in the template since REQ-214, so the template is
  the primary source; the hook still derives the wizard keys from
  setup/SKILL.md as declared redundancy, the net for the next key the wizard
  gains before the template) — and `$`-prefixed keys
  (`$schema_note`, `$enums`), the file's documentation-of-itself convention.
  A REFUSAL is respected for the rest of the SESSION: do not re-offer the
  same key in this session, do not re-ask, do not "just check" — the REQ-108
  fatigue rule the other offers already follow. No cross-session memory here
  on purpose: an orphan key is a one-time migration, and the single line the
  next session prints is the reminder it deserves, not a nag.
- Also verify the SAFETY FLOOR: `.git/hooks/pre-commit` installed (by /setup).
  It is the self-contained staged quick floor; `config.json.commands` belong
  to the full-suite boundaries and are checked separately as environment
  readiness. If the floor is missing, fixing it is part of the gap.
- **How staleness is decided, for EVERY check below — CONTENT HASH, never
  version.** Compare the SHA-256 of the NORMALIZED BODY of the installed
  artifact against the same hash of the plugin's own reference copy, where
  NORMALIZED means "with the version-marker line stripped out". Equal hashes →
  NO offer and no report, however far apart the two version markers are.
  Different hashes → the offer, even when the two version markers agree. The
  version is REPORTING material (installed vs plugin, what changed) and NEVER
  the verdict.
  WHY this is not a detail: `scripts/dev-sync.sh` rewrites those markers on
  EVERY release, so a version comparison declares every project in the world
  stale at every bump, with the bytes identical. The cost is not the needless
  reapply — it is FALSE-POSITIVE FATIGUE: an offer that shows up with nothing
  changed teaches the user to refuse on reflex, and that reflex then swallows
  the one offer that mattered. A guard that cries wolf gets itself disabled.
  Corollary, so nobody chases it: when the body matches and only the marker is
  old, the stale marker is HARMLESS — leave it; the next real content change
  carries the new version in with it. Any future /env detection inherits this
  rule: compare what the artifact SAYS, not what it is labelled.
- If the floor IS installed, check it is up to date BY CONTENT: hash the body of
  `.git/hooks/pre-commit` and the body of the plugin's own copy at
  `${CLAUDE_PLUGIN_ROOT}/core/hooks/pre-commit`, both with the
  `# helmit-pre-commit-version:` line stripped, and compare the two hashes.
  Equal → the floor is current; say nothing, offer nothing. That holds for a
  pre-marker install too: a copy carrying no marker line at all, whose body
  still matches, IS current, and reinstalling it would buy the user nothing but
  noise. Different → REPORT the divergence (installed vs plugin version, plus
  what changed in the body) and OFFER to reinstall: copy the plugin's file over
  `.git/hooks/pre-commit` and `chmod +x` it. Execute ONLY on explicit user
  confirmation (permission boundary, step 4) — never silently.

  CHAINED LAYOUT (REQ-210) — decide WHICH file to hash before hashing anything.
  When a pre-commit hook already existed at install time, /setup's chain offer
  (or a framework like pre-commit.com) leaves `.git/hooks/pre-commit` as a
  DISPATCHER — the USER's file — that invokes HelmIt's verbatim copy at
  `.git/hooks/helmit-pre-commit` by path. In that layout the content hash above
  is taken over the VERBATIM COPY, never the dispatcher: the dispatcher's body
  differs from the plugin's reference BY CONSTRUCTION, so hashing it declares
  the floor stale forever — the permanent false positive REQ-108 exists to
  prevent, and it bit in the field (a pre-commit.com project, 04/08, where
  accepting the "fix" would have clobbered the dispatcher and taken the user's
  own hooks out of the commit path). Copy up to date → the floor is current;
  say nothing, whatever the dispatcher looks like. Copy stale → report and
  offer to refresh THE COPY (`.git/hooks/helmit-pre-commit`), touching the
  dispatcher on no account. A dispatcher that references no HelmIt copy is the
  user's own floor: not judged, not a pendency.

  HARD RULE of the reinstall offer, in EVERY layout: the reinstallation NEVER
  overwrites a hook that contains more than the HelmIt gate. If
  `.git/hooks/pre-commit` carries anything beyond the plugin's own gate body —
  a dispatcher, a user edit, another tool's hook — the offer is confined to the
  verbatim copy; for the hook itself, REPORT the layout you found and delegate
  the decision to the human: fixing a dispatcher is the user's act, never the
  agent's (ADR-007 — the git floor is the user's guarantee; HelmIt does not
  edit what it does not own).

- Also verify the `.gitignore` hygiene floor, BY CONTENT and never by presence
  (REQ-127): hash the BODY between `# helmit:local-state:start` and
  `# helmit:local-state:end` in the project's root `.gitignore` and compare it
  against the same hash of the block /setup writes (step 6). This is the SAME
  rule the other two floors already follow — the leased block and the pre-commit
  floor — and it was the only one left detecting by the MARKER LINE.
  - Marker ABSENT — a project onboarded before the block existed, or a repo with
    no `.gitignore` at all → REPORT and OFFER the whole block.
  - Marker PRESENT, hashes DIFFER → REPORT and OFFER to bring the block up to
    date. This is the case presence-detection declared healthy: marker there,
    block INCOMPLETE, verdict green. It is not hypothetical — REQ-118 added
    `.helmit/yolo.json` as the sixth line, so EVERY project onboarded before
    that carries a stale block, and the cost is concrete: one distracted
    `git add -A` commits the mandate, and whoever clones the repo inherits an
    ARMED yolo — exactly what `/helmit:yolo` promises never happens ("cloning a
    project must never hand somebody an agent that has stopped asking"). It
    happened AGAIN with REQ-170 and `.helmit/dashboard.html`: the board is
    rewritten whole on every render, so a project on the older block has a
    40 KB derived file churning in `git status` — this is not a one-off, it is
    what the block does for a living, and it is why the verdict must come from
    the BODY.
  - Hashes EQUAL → the block is current: no report, no offer.

  Name in the report which machine-local paths are currently UNIGNORED and what
  that costs: machine state in `git status`, an execution log committed by a
  distracted `git add -A`, `run.jsonl` in conflict between machines. The paths
  are NOT re-listed here on purpose — the block /setup writes is the single
  source, and this skill reads it instead of keeping a hand-copy that drifts
  (that hand-copy is why REQ-118's sixth line needed three separate edits).
  Then OFFER the fix — append or update the block exactly as /setup writes it,
  touching no other line. Execute ONLY on explicit user confirmation (permission
  boundary, step 4) — NEVER silently and NEVER as a side effect of the readiness
  report. The rest of `.helmit/` stays versioned; never propose ignoring
  `.helmit/` wholesale.
- The OTHER HALF of that floor, for the project already IN the bad state:
  `.gitignore` DOES NOT UNTRACK anything. A path already in the git index keeps
  showing up in `git status` forever, block or no block — so the project that
  most needs the fix is exactly the one the block alone never reaches. DETECT it
  with one deterministic command:

```sh
git ls-files -- .helmit/map/ .helmit/proof-worktrees/ '.helmit/*.jsonl' .helmit/lock.json .helmit/executor-lease.json .helmit/session-activity/ .helmit/yolo.json .helmit/HANDOFF.md .helmit/dashboard.html .helmit/quality-receipt.json
```

  Every path it prints is machine-local state living in the project history.
  REPORT them by name and OFFER `git rm --cached <path>` for each: it drops the
  path from the INDEX and leaves the file untouched on disk. NEVER run it
  silently and NEVER commit the removal — the index decides what the next commit
  says about the user's project, so the removal AND its commit are the user's
  act, on explicit confirmation (permission boundary, step 4). Say so when
  offering: a staged removal sits there waiting for a commit that belongs to
  them. Nothing to report when the command prints nothing.
  The generalization is the point, and it binds every /env detection, present
  and future: ask whether it repairs the project ALREADY in the bad state, or
  only the one that has not reached it yet.
- **RE-OFFER the parallel form of the test command, ONCE (REQ-199).** REQ-198
  put the lever where the command is BORN: /arch PROPOSES the parallel form at
  the moment `commands.test` is decided, and never writes it alone. That lever
  reaches only a project configured AFTER it — which is the item above all over
  again: the repair has to reach whoever is ALREADY in the bad state, and here
  that is whoever pays a serial suite on every single run. So ask the SAME
  question about the command this project already carries, through the SAME
  hook and the same runner table — the knowledge lives in ONE place and both
  skills are thin shells over it:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/parallel-hint.sh" suggest --command "<config.json commands.test>"
```

  Read `commands.test` from `config.json` and pass it VERBATIM. The hook prints
  AT MOST one line and always exits 0 — an informer, never a gate: nothing it
  says can block, delay or fail /env.
  - **A proposal came back** (`parallel-hint: <runner> — <suggested command>
    (<what it changes>)`) → REPORT the divergence — the command in force, the
    suggested one, and in ONE line what changes — then OFFER the swap. Execute
    ONLY on explicit user confirmation (permission boundary, step 4) — NEVER
    silently and NEVER as a side effect of the readiness report. The OK writes
    the parallel form into `config.json.commands.test` AND into the KEEL
    Commands line, which have to keep matching. State the honest limit in the
    same breath, exactly as /arch does — the reasoning is REQ-198's and is not
    repeated here: the hook reads a STRING, so it cannot know whether
    pytest-xdist or cargo-nextest is installed on this machine, how many cores
    it has, or whether this suite survives running out of order (shared
    fixtures, one database, fixed ports). A proposal to judge, never a verified
    fact.
  - **The hook said nothing** — runner outside its table, empty command, no
    interpreter — or it answered `already parallel (...); nothing to propose`
    → SILENCE, absolute: no line in the readiness report, no "nothing to
    suggest here" reassurance. Same REQ-108 rule the detections above follow:
    say nothing when there is no real pendency.
  - **ONCE: the refusal is respected on every later run.** This half decides
    whether the item helps or becomes the very fatigue REQ-108 fights — an
    offer that returns on every /env is a nag, and a nag teaches the reflex
    refusal that then swallows the offer that mattered. So the NO is RECORDED
    the moment it is given: append ONE line to `.helmit/env.jsonl` with a
    single `>>`, never rewriting the file:

```json
{"ts":"<ISO-8601 UTC>","event":"parallel_hint_declined","command":"<commands.test, verbatim>","suggested":"<the command that was offered>"}
```

    and READ that file BEFORE speaking: a `parallel_hint_declined` record whose
    `command` equals the CURRENT `commands.test`, byte for byte, is a NO
    already given — say NOTHING, do not re-ask, do not re-explain, do not
    "just check if you changed your mind". No record, or a record for a command
    that is no longer the one in force, and the offer is live again ONCE.
    Deciding by the command STRING is the REQ-108 rule applied here: the
    verdict comes from the CONTENT the user judged, never from a date or a
    counter. The three decisions behind the mechanism, written down because
    every cheaper variant is wrong in a way that only shows up later:
    - NOT "the command is still serial, so the user must have refused": a project
      nobody ever asked and a project that answered no are byte-identical, so
      the offer would come back forever. That IS the nag.
    - NOT a field in `config.json`: that file is the VERSIONED contract, and
      every field in it needs a reader in the framework (REQ-110). "This
      checkout was already asked" is not a term of the project contract, and
      versioning it would push one person's answer onto everyone who clones.
    - `.helmit/env.jsonl` and NOT a new `.helmit/<name>.json` precisely because
      `.helmit/*.jsonl` is ALREADY one line of the local-state block /setup
      writes and ALREADY inside the tracked-state detection above: the file
      inherits both floors by construction, instead of being hand-copied into
      two lists that drift apart — the drift REQ-127 documents. Append-only,
      because one `>>` cannot corrupt what is already in the file, while a
      read-modify-write of a JSON object can.
    The price, stated so nobody finds it later as a bug: the memory is per
    CHECKOUT. A teammate who clones the repo is asked once on that machine, and
    so is this user after a fresh clone. That is what it costs to keep one
    machine's answer out of a versioned contract, and one question per checkout
    is the floor of the fatigue, not the fatigue itself.
  - The YES needs no memory of its own: accepting makes `commands.test`
    parallel, and from then on the hook answers `nothing to propose` by itself,
    forever. Only the NO has to be remembered.
  - The test command belongs to the PROJECT: /env OFFERS and NEVER writes it
    alone — the same boundary the item above holds when it offers the removal
    from the index instead of running it (REQ-112). The one thing /env writes
    by itself here is the record of the user's own NO, which is machine-local
    state and not the project contract.
- **Retired-autopilot residue detection (REQ-162).** The OS-scheduler autopilot
  layer was RETIRED by ADR-010 (the guardian is now a session-scoped heartbeat
  on the harness-native cron), but machines armed before the retirement still
  carry its residues — and a leftover scheduler entry re-decides its own disarm
  forever. DETECT, read-only and best-effort, the three residue kinds:
  - (a) **OS-scheduler entries** named `com.helmit.autopilot.*`, on the CURRENT
    platform only:
    - macOS (launchd): `launchctl list | grep com.helmit.autopilot` plus plists
      matching `~/Library/LaunchAgents/com.helmit.autopilot.*.plist`;
    - Linux (systemd user): `systemctl --user list-unit-files
      'com.helmit.autopilot.*'` plus unit files matching
      `~/.config/systemd/user/com.helmit.autopilot.*` (`.timer`/`.service`);
    - Windows (Git Bash/WSL): `schtasks /Query | grep com.helmit.autopilot`
      (use `schtasks.exe` under WSL).
    A tool missing or erroring is NOT a finding — skip that probe silently.
  - (b) **The stable shim** `~/.helmit/ops/tick.sh` (the file the entries used
    to point at), including a leftover `~/.helmit/ops/` tree around it.
  - (c) **Project arming files**: `.helmit/autopilot.json` and
    `.helmit/power.json` in THIS project (also check whether git tracks them —
    tracked residues need `git rm --cached` on top of the delete).
  For each residue FOUND: report it by name and OFFER the removal with the
  reason — "the OS-scheduler autopilot was retired by ADR-010; this entry
  re-decides its own disarm forever" — and the exact removal command
  (`launchctl bootout gui/$(id -u)` + `rm` of the plist; `systemctl --user
  disable --now` + `rm` of the units; `schtasks /Delete /TN <name>`; `rm` for
  the shim and the project files). Execute ONLY on explicit user confirmation
  (permission boundary, step 4) — NEVER silently, never as a side effect of
  the readiness report. Nothing found → absolute silence: no line in the
  report, no reassurance (REQ-108); unattended resumption today is
  `/helmit:heartbeat`, and this detection exists only to bury the old layer.

- Also verify the LEASED SECTION of the host context file (`CLAUDE.md` /
  `AGENTS.md`, written by /setup step 4) is UP TO DATE, BY CONTENT: hash the
  project's `<!-- helmit:start -->` … `<!-- helmit:end -->` block and the
  plugin's own copy of the block at
  `${CLAUDE_PLUGIN_ROOT}/core/skills/setup/SKILL.md`, both with the
  `helmit-lease-version:` line stripped, and compare the two hashes. WHY this
  item exists:
  /setup runs ONCE per project and refuses to run again, so with nobody checking
  the block, every improvement to it dies in every project that already exists —
  and that block is the only text ALWAYS loaded in a fresh session (it is what
  tells the agent that `.helmit/INBOX.md` is this project's capture/triage
  channel and not e-mail). Equal hashes → the block is current: no report, no
  offer, whatever the two markers say. If the hashes differ — a marker-less
  block included, whenever its body is the one that diverged — REPORT the
  divergence: installed version × plugin version, plus what changed that
  matters. Then OFFER the refresh, and execute ONLY on explicit user
  confirmation (permission boundary, step 4) — NEVER silently and NEVER as a
  side effect of the readiness report.
- The refresh REPLACES ONLY what is BETWEEN the markers, and nothing else:
  everything the user wrote OUTSIDE `<!-- helmit:start -->` /
  `<!-- helmit:end -->` is preserved byte for byte, in place — no reordering, no
  reflow, no dedup, no "while I am here" cleanup, and the file's own leading and
  trailing bytes stay as they are. Running the refresh twice must leave the file
  byte-identical. If both context files exist, refresh both, same content.
- If the block is ABSENT, or only ONE of the two markers survives (the user
  edited the section by hand), do NOT guess and do NOT re-inject blindly: there
  is no reliable boundary to replace. REPORT exactly what you found and ask the
  user how to proceed — the host context file belongs to the user (#43).
- Before a route is allowed, the native context contract is checked: Claude
  Code requires `CLAUDE.md`; Codex requires `AGENTS.md`. A missing native file,
  incomplete markers, missing lease, stale lease, or divergent leases routes to
  `/env` and blocks autonomous continuation. This check is read-only.
- For a missing native file, inspect the opposite harness file only to classify
  it. Its HelmIt lease is compared to the plugin reference and may be proposed
  for the new native file. Show general, portable rules as candidates for an
  explicit migration. NEVER copy content outside the lease automatically:
  harness syntax, hooks, permissions, skills and all user text remain owned by
  their original file. When both files exist, refresh only their marker-bounded
  leases with the identical reference block; preserve all external bytes.

### 2b. Optional repo-map layer (ADR-009 — offered, never assumed)
- Gate FIRST — the map only deserves a word when there IS code to map. One
  deterministic command, exit 0 = the project HAS code:

```sh
git ls-files | grep -Ev '^\.helmit/' | grep -Eiq '\.(py|js|jsx|ts|tsx|cs|go|rb|java|rs|c|h|cpp|cc|hpp|php|swift|kt|scala|ex|exs|el|ml|lua|r|jl|zig|sh|bash)$'
```

  Those extensions ARE the `EXT_LANG` table of `core/hooks/repo-map.sh`, so the
  question asked is the real one: would the map find a single symbol to extract?
  Docs, config and `.helmit/` fall out by construction — not mappable. Nothing
  tracked yet (or no git repo yet) counts as NO code.
- NO code (greenfield just scaffolded): SKIP this whole item — do not run the
  availability check, do not report the map as absent, do not offer the install,
  and never record it as a gap or a blocker. With nothing to map, the absence is
  not a pendency, and announcing it turns a non-issue into a chore the user
  cannot even do. Say nothing here: the offer comes back on its own on the next
  /env, once there is code (and /chart is where the map is BORN on demand).
- WITH code — availability check: run
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/repo-map.sh" check` — the script
  resolves the ISOLATED HelmIt venv (`~/.helmit/venv`) by itself. If it
  reports `"available": false`, OFFER the optional install in one line with
  the declared cost (~4.7 MB, ~1.5 s, pre-built wheels on the 6 mainstream
  platforms — no compiler):
  `python3 -m venv ~/.helmit/venv && ~/.helmit/venv/bin/pip install tree-sitter tree-sitter-language-pack`
  ISOLATED by design: never installs into the system/user python (PEP 668
  safe), shared across the user's projects, fully removable with
  `rm -rf ~/.helmit/venv`. Explain the gain (deterministic code map for
  discovery, /chart and /implement) and that WITHOUT it everything works
  identically (fail-open). Install ONLY on explicit confirmation (step 4
  boundary). Platforms without a wheel: graceful absence — do not guide
  source compilation.

### 3. Report the gap — one clear table
`tool | required | installed? | version` — then list exactly what is missing.

### 4. Guide the setup (permission boundary — NON-NEGOTIABLE, #20)
- Read-only checks: free.
- Local `git init`: may be OFFERED and, on confirmation, executed.
- EVERYTHING below requires EXPLICIT user confirmation, EACH time, and is
  NEVER run silently:
  - installing software / downloading or executing installers
  - creating a REMOTE repository (e.g. GitHub)
  - authenticating (logins, tokens)
  - changing system settings
  For these: PREPARE the exact command/steps, show them, and ask the user to
  confirm or run them themselves. NEVER enter credentials on the user's
  behalf.

### 5. Re-check and close
- After the user acts, re-run the deterministic checks. When everything
  required is present, advance `STATE.md` → `env-ready` **ONLY IF the current
  position is EARLIER than it** (REQ-129) — `setup-done`, `spec-app-draft`,
  `spec-app-approved`, `arch-draft`, `arch-approved`. This skill declares itself
  re-runnable in precondition 1 ("or later re-run"), so running it on a project
  well past setup is NORMAL USE, and the unconditional write REGRESSES the
  position: measured in the field on a project sitting at `shipped:1c`, where
  the agent REFUSED and explained why. That refusal is what makes the case
  serious — the skill said otherwise, and an obedient agent would have corrupted
  the ONE field `/next` routes from.
- Position EQUAL to or LATER than `env-ready` → DO NOT TOUCH the field, and say
  so in the report: environment re-checked, position preserved at `<current>`.
- The rule generalizes to every re-runnable skill: a position field is
  MONOTONIC, and a step that can legitimately run twice must never write a
  position it did not compute from the current one.
- If the user chooses to proceed with a known gap (their call), record the
  gap as a blocker in `STATE.md` — visible, not forgotten.

---

## Session safety — /env only READS (REQ-091)
- /env produces no product artifact of its own, so it never takes the tree
  lock. The repairs it OFFERS are the exception that proves the rule: the
  pre-commit floor, the `.gitignore` block, the leased section and the REQ-199
  swap of `commands.test` are all written only WITH the OK, and they are the
  user's act, not this skill producing an artifact. When the lock is held by a
  live holder, say so with the offer and let the user decide. Run
  `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/lock.sh" status` and REPORT it in the
  readiness table: free, or held (who, since when, last heartbeat). A live
  holder is a warning to the user, not a block on /env.
- Same read-only posture for anything the environment has ARMED (the yolo
  mandate and the heartbeat guardian): report what is armed and how to turn it
  off; changing it belongs to the command that owns it, never to /env.
- Concretely: if `bash "${CLAUDE_PLUGIN_ROOT}/core/hooks/yolo.sh" status`
  reports a mandate in force, the readiness report says ARMED, with which
  scope and where it stops, and ends the line with `/helmit:yolo off`.
  Never arm, disarm or edit it here.

## Lean guardrails
- Check only what the STACK requires — no "nice to have" tool inflation.
- The readiness report is short: the table + the gap + the next action.
- Do not loop without progress. Continue an in-scope repair while evidence
  changes; pause when the same failure repeats without progress or needs a
  user or external decision.

## Cross-platform note (adapter contract)
- Pure core: shell checks + `.helmit/` reads/writes. The required-tools list
  comes from KEEL (core). Identical on Claude Code and Codex.
- `${CLAUDE_PLUGIN_ROOT}` resolves on both platforms: Claude Code sets it
  natively; Codex exports `PLUGIN_ROOT` plus `CLAUDE_PLUGIN_ROOT` for
  compatibility (see `adapters/codex/README.md`).
- Command references like `/helmit:<cmd>` use the Claude Code adapter's syntax; on Codex, invoke the skill via the `$` selector or `/skills` (see `adapters/codex/README.md`).

## Guidance footer (MANDATORY — every HelmIt command ends with this)
Before returning control, ALWAYS:
1. Update the `workflow:` field in `STATE.md` to the new position — SUBJECT TO
   THE MONOTONICITY RULE of step 5 (REQ-129). On a re-run of an advanced
   project the correct action is to write NOTHING and say the position was
   preserved.
2. Tell the user, in the language from `config.json`, where they now are and
   continue to the next delivery definition when it is already authorized.
   On a re-run, preserve the current position and use `/helmit:next` to derive
   the active delivery; never branch on legacy track metadata.
