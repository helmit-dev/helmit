import hashlib
import json
import os
import re
import sys

ROOT = os.environ.get("CC_ROOT") or os.getcwd()
SETUP = os.environ.get("CC_SETUP") or ""
FENCE = chr(96) * 3
START = "<!-- helmit:start -->"
END = "<!-- helmit:end -->"
LEASE = re.compile(r"<!--\s*helmit:start\s*-->.*?<!--\s*helmit:end\s*-->", re.S)
MARKER = re.compile(r"^.*helmit-lease-version:.*$\n?", re.M)
HOSTS = {
    "codex": ("AGENTS.md", "Codex", "CLAUDE.md"),
    "claude-code": ("CLAUDE.md", "Claude Code", "AGENTS.md"),
}


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def digest(text):
    return hashlib.sha256(MARKER.sub("", text).encode("utf-8")).hexdigest()


def reference():
    """Return the single lease written by /setup, or None without a verdict."""
    setup = read(SETUP)
    if setup is None:
        return None
    blocks = [b for b in re.findall(FENCE + r"[a-z]*\n(.*?)" + FENCE, setup, re.S)
              if START in b]
    if len(blocks) != 1:
        return None
    match = LEASE.search(blocks[0])
    return match.group(0) if match else None


def classify(name, want):
    """Classify a host file without writing it or inferring a boundary."""
    text = read(os.path.join(ROOT, name))
    if text is None:
        return {"file": name, "state": "missing", "outside_lease": False}
    starts, ends = text.count(START), text.count(END)
    match = LEASE.search(text) if starts == 1 and ends == 1 else None
    if starts != 1 or ends != 1:
        return {"file": name, "state": "markers_incomplete",
                "outside_lease": bool(text)}
    if match is None:
        return {"file": name, "state": "lease_missing", "outside_lease": True}
    lease = match.group(0)
    state = "current" if want and digest(lease) == digest(want) else "outdated"
    return {"file": name, "state": state, "lease": lease,
            "outside_lease": text[:match.start()] + text[match.end():] != ""}


def inspection(name):
    data = classify(name, reference())
    # The lease is deliberately not emitted. /env may compare it to the
    # reference, but no caller gets a channel that could copy user text.
    data.pop("lease", None)
    return data


def check(harness):
    if harness not in HOSTS:
        print("usage: context-contract.py check <codex|claude-code>", file=sys.stderr)
        return 2
    native, label, opposite = HOSTS[harness]
    want = reference()
    native_state = classify(native, want)
    other_state = classify(opposite, want)
    findings = []
    state = native_state["state"]
    if state == "missing":
        findings.append("%s: required by %s but missing — run /helmit:env" %
                        (native, label))
        if other_state["state"] != "missing":
            findings.append("%s: available only for assisted migration; its user content will not be copied — run /helmit:env" % opposite)
    elif state == "markers_incomplete":
        findings.append("%s: HelmIt lease markers incomplete — run /helmit:env" % native)
    elif state == "lease_missing":
        findings.append("%s: HelmIt leased section missing — run /helmit:env" % native)
    elif state == "outdated":
        findings.append("%s: leased HelmIt section outdated — run /helmit:env" % native)

    if (native_state["state"] == "current" and other_state["state"] == "current"
            and digest(classify(native, want)["lease"]) != digest(classify(opposite, want)["lease"])):
        findings.append("CLAUDE.md/AGENTS.md: HelmIt leased sections diverge — run /helmit:env")

    for finding in findings:
        print(finding)
    return 1 if findings else 0


def main(argv):
    if len(argv) == 2 and argv[0] == "inspect":
        print(json.dumps(inspection(argv[1]), sort_keys=True))
        return 0
    if len(argv) == 2 and argv[0] == "check":
        return check(argv[1])
    print("usage: context-contract.py {check <codex|claude-code>|inspect <CLAUDE.md|AGENTS.md>}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
