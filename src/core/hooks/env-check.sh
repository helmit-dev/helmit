#!/usr/bin/env bash
# HelmIt — env-check: the cheap, deterministic half of /env as code (phase 15,
# REQ-206).
#
# Why this exists: the staleness detections lived only as prose in env/SKILL.md,
# so they ran when a human remembered to run /helmit:env — and the artifacts the
# plugin update never touches (the leased block, the pre-commit floor, the
# .gitignore local-state block) aged in silence in every installed project.
# This hook is those detections as code, cheap enough for a session trigger.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   env-check.sh check   (default) run the cheap /env checks and print REAL
#                        pendencies, one per line, as
#                          <artifact>: <state> — run /helmit:env
#                        Exit 0 ALWAYS — it informs, it never gates. No
#                        pendency: stdout EMPTY, absolute silence (REQ-108),
#                        and two consecutive runs are byte-identical.
#
# The four checks — REUSED from env/SKILL.md, never a second source of the
# same truth (REQ-110). Reference copies are the plugin's own, resolved from
# this script's location; the verdict is a CONTENT HASH, never a version:
#   1. leased section of CLAUDE.md/AGENTS.md — SHA-256 of the block between
#      <!-- helmit:start --> and <!-- helmit:end -->, the helmit-lease-version
#      line stripped, against the block setup/SKILL.md writes.
#   2. pre-commit floor — SHA-256 of the HelmIt gate with the
#      helmit-pre-commit-version line stripped, against core/hooks/pre-commit.
#      WHICH file carries the gate depends on the layout (REQ-210): direct
#      install → .git/hooks/pre-commit itself. CHAINED install (setup's chain
#      offer, or a pre-commit.com project) → .git/hooks/pre-commit is a
#      DISPATCHER, the USER's file, invoking the verbatim copy
#      .git/hooks/helmit-pre-commit by path — there the verdict hashes the
#      COPY, never the dispatcher, whose body diverges from the reference
#      FOREVER by construction (the permanent false positive that bit in the
#      field, 04/08). Only judged when the hashed file is identifiably
#      HelmIt-derived: a foreign hook the user chose to keep is their call,
#      not a pendency (accusing it every session is the REQ-108 fatigue).
#   3. .gitignore local-state block (REQ-127) — SHA-256 of the BODY between
#      # helmit:local-state:start / :end, against the block /setup writes.
#   4. tracked local state (REQ-112) — `git ls-files` over the paths of that
#      same block (derived, never hand-copied): every hit is machine-local
#      state living in the project history.
# An ABSENT artifact or block is NOT reported here: with no boundary to hash
# there is no cheap verdict, and that case belongs to the /env conversation.
#
# Plus ONE check that is not a hash (REQ-208): `helmit_version` of the project
# config against the plugin's own version. The version REPORTS, it never
# decides: a gap adds one line declaring the DEEP toolchain check due in /env
# (the only thing a version gap means), even with every hash above in good
# shape — and it changes no verdict. Equal versions, field absent, unreadable
# JSON: not one word (fail-open). Writing the field back is /env's act, after
# the deep check — never this hook's, which stays a pure read.
#
# And ONE check over the SHAPE of the config (REQ-209): a top-level key of the
# project's config.json that LEFT the plugin's template gets one line naming it
# and routing to /env for the migration offer. A field removed from the
# template dies only for whoever installs tomorrow — in every project already
# installed it stays behind and LIES (the REQ-118 `yolo` removal is the live
# case: an agent read the leftover and assumed a mandate nobody gave, 02/08).
# The legal key set is the template's top-level keys — since REQ-214 the
# template is the single source of the format (artifact_language included) —
# PLUS, as DELIBERATE redundancy, the keys the /setup wizard itself persists,
# DERIVED from setup/SKILL.md (same discipline as check 4, never a hand-copied
# allowlist): the net for the next key the wizard gains before the template. `$`-prefixed keys ($schema_note,
# $enums) are the file's documentation-of-itself convention and are ignored.
# The REMOVAL is never this hook's: /env offers it, with the reason, under
# explicit confirmation.
#
# This hook only DETECTS: every fix is /env's offer, under explicit user
# confirmation — hence every line ends pointing there.
#
# PURE READ (REQ-091): writes nothing, mutates no mtime, and `git ls-files`
# only reads the index. Fail-open EVERYWHERE: no .helmit/, no git, no python,
# unreadable reference copies — silence, exit 0. A session trigger calls this
# in every project the user opens, so a failure here must cost nothing.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

usage() {
  echo "usage: env-check.sh [check]" >&2
  exit 2
}

CMD="${1:-check}"
[ "$CMD" = "check" ] || usage

# Not a HelmIt project: silence (a session trigger fires in EVERY project).
[ -d "$ROOT/.helmit" ] || exit 0

# Reference copies live in the plugin itself, resolved from this script's own
# location like the sibling hooks do (session-start.sh, reconcile.sh).
SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
[ -n "$SELF_DIR" ] || exit 0

# Interpreter resolver — same contract as sanity.sh/handoff.sh, minus the
# warning: this is a session trigger, so no interpreter degrades to silence.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  exit 0
fi

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
EC_ROOT="$ROOT" EC_SETUP="$SELF_DIR/../skills/setup/SKILL.md" EC_PRE="$SELF_DIR/pre-commit" \
  EC_TPL="$SELF_DIR/../templates/config.json" EC_PLUGIN="$SELF_DIR/../../.claude-plugin/plugin.json" \
  exec "$PY_BIN" "$SELF_DIR/env-check.py" "$@"
