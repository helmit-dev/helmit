#!/usr/bin/env bash
# HelmIt brownfield discovery core — deterministic layer-1 scan (REQ-040/043).
# Zero LLM, zero network, bash + python3 stdlib only (ADR-001). The AGENT
# interprets and the HUMAN confirms (gate item a item) — this script only
# reports what is OBSERVABLE, each item with the file that evidences it.
#
# Usage:
#   discover.sh scan [<project-dir>]
#       One JSON document on stdout:
#       {"stack":[{"value","evidence"}...],
#        "commands":{"test":[{"value","evidence"}...],"build":[...],"lint":[...]},
#        "conventions":[{"value","evidence"}...],
#        "meta":{"trivial":bool,"tracked_files":N}}
#
# Directed scan by design (research 2026-07-10, docs/research-brownfield.md):
# manifests, lockfiles, CI, Makefile, config files — NEVER the whole tree,
# never file contents beyond bounded reads (100KB cap per file).

set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "discover.sh: no python interpreter (python3/python/py) found" >&2
  exit 0
fi

DISCOVER_DIR="$SELF_DIR" exec "$PY_BIN" "$SELF_DIR/discover.py" "$@"
