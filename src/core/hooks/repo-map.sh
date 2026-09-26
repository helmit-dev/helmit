#!/usr/bin/env bash
# HelmIt repo map — deterministic, OPTIONAL code-map layer (REQ-045, ADR-009).
# Extracts symbol definitions/references via tree-sitter and renders a
# budget-capped map of the repository. ZERO tokens: no LLM, no network.
#
# The ONLY optional dependency is `tree-sitter-language-pack` (+ tree-sitter):
# absent => {"available": false, ...} on stdout, exit 0, and every consumer
# (/arch, /chart, /implement) falls back to today's behavior. The commit gate
# and the hooks NEVER touch this layer (ADR-001 stays the core rule).
#
# Usage:
#   repo-map.sh scan [<project-dir>] [--budget <chars>]
#       Renders the map on stdout (text). Unavailable => JSON + exit 0.
#   repo-map.sh refresh [<project-dir>] [--budget <chars>]
#       Re-parses only what changed (REQ-046), persists .helmit/map/ and prints.
#       This is the GENERATION command, so it leaves a `map_refreshed` record —
#       see record_refresh().
#   repo-map.sh check [<project-dir>]
#       absent | stale | fresh, by sha1 fingerprint — no parsing.
#   repo-map.sh show [<project-dir>] [--files <a,b,c> | --symbol <name>]
#       Prints the PERSISTED map; never regenerates. This is the consumption
#       command (/implement injects from it, REQ-130), so it is the one that
#       leaves a `map_shown` record in .helmit/run.jsonl — see record_show().
#       With --files it answers a DIRECTED query instead (REQ-271): the entries
#       of exactly those paths, read from the fingerprints.json the refresh
#       persists under the map directory, independent of the ranking and NEVER
#       capped by the budget — the cap governs the whole-repo view, and applying
#       it to a selection asked for by name is the very failure this query
#       exists to remove. The flag takes a comma-separated list and may repeat;
#       paths are relative to the project root. A path the base holds without
#       symbols is declared as such, a path the base does not hold is named as
#       missing: the map never hides a file it was asked about. The base on disk
#       is all it needs, so it answers with the optional library ABSENT.
#       With --symbol it answers the OTHER directed query (REQ-272): where that
#       name is DEFINED — file, line and kind, out of the same base's `defs`.
#       The match is EXACT, never a substring: `grep` already answers the
#       question about mentions, and answering it again with the same fog is
#       what the query exists NOT to do. A name defined in N files lists the N
#       definitions; a name nothing defines is said so in one line, exit 0. Same
#       base, so the same two properties hold: no budget, and the library ABSENT.
#       The two queries are two questions — asking both at once is a usage error.
#
# Env:
#   HELMIT_MAP=off   kill-switch: ABSOLUTE, and no longer a synonym for "lib
#                    absent" — since REQ-271 the absent library is CONDITIONAL
#                    (a directed query reads the base the refresh left on disk
#                    and parses nothing, so it crosses), while this switch stops
#                    every mode, directed queries included. On purpose: the eval
#                    measures map-on vs map-off, and a channel that survived the
#                    switch would be measuring neither.
#   HELMIT_PYTHON    interpreter override (same contract as the other hooks).
#   HELMIT_QUERIES   override the queries dir (tests).
#
# Design (docs/research-brownfield.md, Adendo 10/07/2026):
#   file -> language by extension -> parser -> .scm query (vendored from
#   Aider, Apache-2.0, see core/queries/NOTICE.md) -> def/ref tags ->
#   ranking = defs + refs received (pluggable; PageRank-stdlib is the
#   documented upgrade path) -> two-layer render under a char budget.
#   Per-file silent fallback: no parser/query => file listed by name only.

set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
QUERIES_DIR="${HELMIT_QUERIES:-$SELF_DIR/../queries/tree-sitter}"

PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  # Isolated HelmIt venv first (created by /env — never touches the system
  # python; PEP 668-safe). Then the usual interpreter fallback.
  HV="${HELMIT_VENV:-$HOME/.helmit/venv}"
  if [ -x "$HV/bin/python3" ] \
     && "$HV/bin/python3" -c "import tree_sitter, tree_sitter_language_pack" >/dev/null 2>&1; then
    PY_BIN="$HV/bin/python3"
  else
    for cand in python3 python py; do
      if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
    done
  fi
fi

unavailable() { # $1 = reason
  printf '{"available": false, "reason": "%s"}\n' "$1"
  exit 0
}

# A wrong command line is NOT an unavailable layer. Fail-open covers an absent
# base and an absent library — states of the world the caller cannot fix from
# the command line — and answering bad syntax with `{"available": false}` would
# hand a silent JSON to somebody who mistyped a query.
usage_error() { # $1 = the single line the caller gets
  echo "repo-map.sh: $1" >&2
  exit 2
}

CMD="${1:-scan}"
case "$CMD" in scan|refresh|show|check) shift || true ;; *) CMD="scan" ;; esac

# Parsed BEFORE any availability gate: the refusal of a bad query has to reach
# the caller whatever the state of the optional layer, and a directed query is
# exactly what decides whether the missing library still matters below.
PROJ=""
BUDGET=4000
FILES=""
SYMBOL=""
HAS_FILES=0
HAS_SYMBOL=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --budget|--files|--symbol)
      [ "$#" -ge 2 ] || usage_error "$1 takes a value"
      case "$1" in
        --budget) BUDGET="$2" ;;
        --files)  FILES="$FILES,$2"; HAS_FILES=1 ;;
        --symbol) SYMBOL="$2"; HAS_SYMBOL=1 ;;
      esac
      shift 2
      ;;
    *)
      [ -n "$PROJ" ] || PROJ="$1"
      shift
      ;;
  esac
done
PROJ="${PROJ:-$PWD}"

if [ "$HAS_FILES" -eq 1 ] && [ "$HAS_SYMBOL" -eq 1 ]; then
  usage_error "--files and --symbol are two different questions: ask one at a time"
fi
if [ "$HAS_FILES" -eq 1 ] && [ -z "${FILES//[, ]/}" ]; then
  usage_error "--files takes at least one path, relative to the project root"
fi
if [ "$HAS_SYMBOL" -eq 1 ] && [ -z "${SYMBOL// /}" ]; then
  usage_error "--symbol takes the name to look for"
fi

DIRECTED=0
[ "$CMD" = "show" ] && { [ "$HAS_FILES" -eq 1 ] || [ "$HAS_SYMBOL" -eq 1 ]; } \
  && DIRECTED=1

[ "${HELMIT_MAP:-on}" = "off" ] && unavailable "disabled (HELMIT_MAP=off)"
[ -n "$PY_BIN" ] && command -v "$PY_BIN" >/dev/null 2>&1 || unavailable "no-python"
if ! "$PY_BIN" -c "import tree_sitter, tree_sitter_language_pack" >/dev/null 2>&1; then
  # A directed query READS the base the refresh left on disk and parses nothing,
  # so the absent library may not silence it (REQ-271). Every mode that DOES
  # parse still falls back to today's behavior.
  [ "$DIRECTED" -eq 1 ] || unavailable "lib-absent"
fi
[ -d "$PROJ" ] || { echo "repo-map.sh: not a directory: $PROJ" >&2; exit 1; }

# The run-log lives BESIDE this hook, so it is resolved from SELF_DIR and never
# from QUERIES_DIR: HELMIT_QUERIES relocates the queries in the suite, and a path
# derived from it would silently stop finding the writer exactly under test.
# Absent/broken is a supported state — see record().
export RM_RUNLOG="$SELF_DIR/run-log.sh"

exec "$PY_BIN" "$SELF_DIR/repo-map.py" "$CMD" "$PROJ" "$QUERIES_DIR" "$BUDGET" "$FILES" "$SYMBOL"
