import hashlib, json, os, sys

ROOT = os.environ.get("SS_ROOT") or os.getcwd()
LEDGER = os.environ.get("SS_LEDGER") or os.path.join(ROOT, ".helmit", "spec-sources.json")
USAGE = "usage: spec-sync.sh {record <spec-rel> <file>... | check [--spec <spec-rel>]}"

def usage():
    print(USAGE, file=sys.stderr)
    return 2

def record(argv):
    if not argv:
        return usage()
    spec, sources = argv[0], argv[1:]
    if not os.path.isdir(os.path.join(ROOT, ".helmit")):
        print("error: .helmit/ does not exist in %s" % ROOT, file=sys.stderr)
        return 2
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = []
    entries = [e for e in data if e.get("spec") != spec]
    for rel in sources:
        base = os.path.basename(rel)
        if rel.endswith(".jsonl") or (rel.replace("\\", "/").startswith(".helmit/") and base in ("INBOX.md", "STATE.md")):
            print("error: %s is an append-only HelmIt artifact, not a document: its hash changes on every write, so registering it as a source would report DRIFT forever (REQ-256)" % rel, file=sys.stderr)
            return 2
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            print("error: source not found: %s" % rel, file=sys.stderr)
            return 2
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        entries.append({"spec": spec, "path": rel, "sha256": digest})
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted(entries, key=lambda e: (e["spec"], e["path"])), fh, indent=2)
        fh.write("\n")
    os.replace(tmp, LEDGER)
    if sources:
        print("spec-sync: %d fonte(s) registradas para %s" % (len(sources), spec))
    else:
        print("spec-sync: fontes de %s DESREGISTRADAS (nada a conferir para essa spec a partir de agora)" % spec)
    return 0

def check(argv):
    if argv and (len(argv) != 2 or argv[0] != "--spec" or not argv[1]):
        return usage()
    spec_filter = argv[1] if argv else ""
    if not os.path.isfile(LEDGER):
        print("spec-sync: sem fontes registradas — nada a conferir (fail-open)", file=sys.stderr)
        return 0
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        print("spec-sync: unreadable ledger — no-op (fail-open)", file=sys.stderr)
        return 0
    drift = []
    for e in sorted(data, key=lambda e: (e.get("spec", ""), e.get("path", ""))):
        if spec_filter and e.get("spec") != spec_filter:
            continue
        rel, want = e.get("path"), e.get("sha256")
        path = os.path.join(ROOT, rel or "")
        if not rel or not want:
            continue
        if not os.path.isfile(path):
            drift.append("DRIFT %s (source of %s): file is GONE" % (rel, e.get("spec")))
            continue
        with open(path, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        if got != want:
            drift.append("DRIFT %s (source of %s): content changed since the last sync" % (rel, e.get("spec")))
    for line in drift:
        print("ADVISORY_" + line)
    return 0

def main(argv):
    if not argv:
        return usage()
    if argv[0] == "record":
        return record(argv[1:])
    if argv[0] == "check":
        return check(argv[1:])
    return usage()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
