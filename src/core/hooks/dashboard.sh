#!/usr/bin/env bash
# HelmIt — dashboard: the project board, DERIVED (phase 20, REQ-168/REQ-169).
#
# Anchor: the number had to be true before it could be pretty (tasks 20.1-20.3
# fixed the collector). This is the visual follow-up of a project, generated
# from the artifacts that are already deterministic in `.helmit/` — never a
# second source of truth. Like `handoff.sh render`, it DERIVES everything on
# every call; the only thing it writes is its own output file, which is
# regenerable and disposable.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; offline):
#   dashboard.sh render [--project <path>]
#       Writes `<project>/.helmit/dashboard.html` and prints its path.
#   dashboard.sh publish [--project <path>]
#       Publishes only when the derived snapshot changed.
#   dashboard.sh ensure [--project <path>]
#       Repairs an absent/stale projection, otherwise reports FRESH.
#   dashboard.sh summary [--project <path>] [--phase <id>]
#   dashboard.sh freshness [--project <path>]
#       Compares the embedded source fingerprint with the live sources.
#   dashboard.sh stale [--project <path>] is a compatibility alias.
#       Prints the PHASE REPORT as text and writes nothing. Same sources, same
#       parsing, another surface: a generated file nobody is told about does not
#       exist for the user, so the end of a phase gets a report ON THE SCREEN
#       (tasks and commits, requirements proven and still to prove, tokens per
#       model, session durations) and the board's path is PROMOTED as the last
#       line, as a `file://` URL. Without `--phase` the phase is DERIVED, in
#       this order: `STATE.md`'s `workflow:` field, the single row the ROADMAP
#       marks `implementing`, the last phase that has a CHART.
#
# The output is ONE SELF-SUFFICIENT FILE (REQ-168): CSS and JS are inline, and
# the page references NO external resource at all — no CDN, no remote font, no
# image, no link/script/img/iframe tag of any kind. Double-clicking the file
# opens a working board with no server and no network. The write is ATOMIC
# (tmp file in the SAME dir, then rename), so a reader never sees half a page.
#
# The board has NINE permanent blocks, each derived from canonical sources
# (REQ-169/REQ-471), plus the optional map block:
#   presence  <- lock.json + executor-lease.json + run.jsonl
#   phases    <- .helmit/ROADMAP.md          (markdown table of phases)
#   tasks     <- .helmit/phases/<id>/CHART.md (`- [ ]` / `- [x]` task lines)
#   reqs      <- .helmit/REQUIREMENTS.md     (markdown table of REQ rows)
#   tests     <- .helmit/run.jsonl           (`gate_run` records of the suite)
#   tokens    <- .helmit/metrics.jsonl       (`models` breakdown + `phase`/`task`)
#   time      <- .helmit/run.jsonl           (spans between paired events)
#   timeline  <- .helmit/run.jsonl           (the same spans, by day)
#   map       <- .helmit/run.jsonl + .helmit/map/ (the OPTIONAL layer)
# The map block is the only CONDITIONAL one (REQ-252): a project with no
# `.helmit/map/` and no map event in the log renders WITHOUT it, byte for
# byte the board it rendered before. The repo map is the project's one
# optional dependency (ADR-009), and a board that grew a hole where it is
# missing would be that dependency becoming a gate through the back door.
# metrics.jsonl is read DIRECTLY, never through `metrics.sh agg`: that command
# ends in a frozen JSON line locked by an exact-equality fixture, and a reader
# hanging off it would make the board hostage to another command's output
# format. The `models` key was born in REQ-167, so lines written BEFORE it have
# no breakdown: those are NEVER attributed to a model (that would invent data)
# — they are counted and declared, exactly as `metrics.sh agg` declares them.
#
# NO AI SCORES, of any kind (KEEL hard rule): every figure on the page is a
# count, a sum or a date taken from an artifact. Nothing is judged or graded.
#
# Language: the page PROSE follows `config.json.artifact_language`, like every
# other user artifact. The translations live in the sibling file
# `dashboard-i18n.json` (data, not code) and English is the built-in default,
# so a missing or malformed overlay degrades to an English board instead of
# breaking. Structural keys, enum values (`shipped`, `covered`, `proven`) and
# every identifier stay English, machine-read as they are everywhere else.
#
# Reliability: absolutely fail-open — a board is an aid, never a gate. A
# missing or malformed source does not break the render: its block states that
# there is no data and every other block still renders. Exit 0 on every data
# path; exit 2 only on usage errors.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
# The script's OWN directory: hooks are called from anywhere, worktrees
# included, by absolute or relative path — $PWD is never the answer.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
CMD=""
PHASE=""
USAGE="usage: dashboard.sh {render|publish|ensure|summary|freshness|stale} [--project <path>] [--phase <id>]"
while [ $# -gt 0 ]; do
  case "$1" in
    render) CMD="render" ;;
    publish) CMD="publish" ;;
    ensure) CMD="ensure" ;;
    summary) CMD="summary" ;;
    freshness) CMD="freshness" ;;
    stale)   CMD="stale" ;;
    --project) shift; ROOT="${1:-$ROOT}" ;;
    --phase) shift; PHASE="${1:-}" ;;
    -h|--help)
      echo "$USAGE"; exit 0 ;;
    *) echo "dashboard: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift || true
done
if [ -z "$CMD" ]; then
  echo "$USAGE" >&2; exit 2
fi

# Interpreter resolver — same contract as commit-gate.sh/metrics.sh:
# HELMIT_PYTHON wins, else the first of python3/python/py on PATH.
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "WARNING: HelmIt dashboard SKIPPED — no python interpreter (python3/python/py) found." >&2
  exit 0
fi

if [ ! -d "$ROOT/.helmit" ]; then
  echo "dashboard: no .helmit/ in $ROOT — not a HelmIt project, nothing to render"
  exit 0
fi

DASH_ROOT="$ROOT" DASH_DIR="$SELF_DIR" \
DASH_CMD="$CMD" DASH_PHASE="$PHASE" \
  exec "$PY_BIN" "$SELF_DIR/dashboard.py" "$@"
