#!/usr/bin/env bash
# HelmIt — spec-sync: deterministic reconciliation between the SOURCES of a
# spec (files the /spec distilled requirements from, e.g. the repo's PRD.md)
# and the internal record (.helmit/REQUIREMENTS.md). Closes the structural
# nos degraus de realismo da eval (fase 11, corr:2026-07-19 / REQ-072): o
# record was the only source of truth and NOTHING checked it against the
# world — a spec edited externally (round D2), or a demand that arrived in the
# exact interrupted act (round E2), vanished silently.
#
# Contract (ADR-001: bash + python3 stdlib; deterministic; fail-open):
#   spec-sync.sh record <spec-rel> [<file>...]    writes/updates the hashes of
#                                                 the spec sources; with NO file
#                                                 it DEREGISTERS that spec
#                                                 (REQ-256). An append-only HelmIt
#                                                 artifact (*.jsonl, INBOX.md,
#                                                 STATE.md) is REFUSED as a source:
#                                                 its hash moves on every write, so
#                                                 it would drift forever.
#                                                 the spec's sources (called by
#                                                 /spec ao finalizar)
#   spec-sync.sh check [--spec <spec-rel>]        compares registered sources
#                                                 vs disk; with --spec, only
#                                                 that spec's sources are read:
#                                                 exit 0 = em sincronia (ou
#                                                 nada registrado — fail-open)
#                                                 exit 1 = DRIFT (prints one
#                                                 line per divergent source)
#                                                 a vanished source is drift too
#                                                 (never silent)
# Ledger: .helmit/spec-sources.json (managed by the product, not by the
# user). No ledger, or an unreadable one => check is a no-op exiting 0 with a
# warning on stderr (loud fail-open: old behaviour preserved, never blocks a
# project that does not use the feature).
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LEDGER="$ROOT/.helmit/spec-sources.json"

die() { echo "error: $*" >&2; exit 2; }
usage() { echo "usage: spec-sync.sh {record <spec-rel> <file>... | check [--spec <spec-rel>]}" >&2; exit 2; }

command -v python3 >/dev/null 2>&1 || { echo "aviso: python3 ausente — spec-sync vira no-op (fail-open)" >&2; exit 0; }

SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 0
PY_BIN=""
if [ -n "${HELMIT_PYTHON:-}" ]; then
  PY_BIN="$HELMIT_PYTHON"
else
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY_BIN="$cand"; break; fi
  done
fi
if [ -z "$PY_BIN" ] || ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "aviso: python3 ausente — spec-sync vira no-op (fail-open)" >&2
  exit 0
fi
SS_ROOT="$ROOT" SS_LEDGER="$LEDGER" exec "$PY_BIN" "$SELF_DIR/spec-sync.py" "$@"
