import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time


USAGE = """usage:
  change.sh snapshot
  change.sh classify --kind <kind> [--stage before|in-flight]
  change.sh allocate --expected-base <sha> --expected-ledger <sha256> \\
    --expected-id <CHG-NNN> --kind <kind> --origin <text> --intent <text> \\
    --paths <csv> --verify <command> [--inbox <reference>]
  change.sh open --expected-base <sha> --expected-ledger <sha256> \\
    --expected-id <CHG-NNN> --kind <kind> --origin <text> --intent <text> \\
    --paths <csv> --verify <command> [--inbox <reference>]
  change.sh expand-paths --approved-by human --expected-base <sha> \\
    --expected-ledger <sha256> --id <CHG-NNN> --paths <csv>
  change.sh revalidate --base <sha> --ledger <sha256> --id <CHG-NNN>
  change.sh prepare-close --base <sha> --ledger <sha256> --id <CHG-NNN>
  change.sh candidate --id <CHG-NNN> --subject <subject>
  change.sh recover --id <CHG-NNN>
"""

ROOT = os.path.abspath(os.environ.get("CHG_ROOT") or os.getcwd())
HELMIT_DIR = os.path.join(ROOT, ".helmit")
LEDGER = os.path.join(HELMIT_DIR, "CHANGES.md")
MUTEX = os.path.join(HELMIT_DIR, ".changes.allocate.lock")
ID_RE = re.compile(r"^CHG-([0-9]{3,})$")
ROW_RE = re.compile(r"^\| (CHG-([0-9]{3,})) \|")
LIMITED_KINDS = {"maintenance", "copy", "configuration", "limited-restoration"}
DURABLE_KINDS = {
    "security", "data", "public-contract", "mandatory-accessibility",
    "durable-acceptance",
}


def fail(message, code=1):
    sys.stderr.write("change: %s\n" % message)
    raise SystemExit(code)


def git(*args):
    result = subprocess.run(
        ["git", "-C", ROOT] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "git %s failed" % " ".join(args))
    return result.stdout.strip()


def require_ledger():
    if not os.path.isfile(LEDGER):
        fail(".helmit/CHANGES.md is missing; initialize it from the HelmIt template")
    tracked = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "--error-unmatch", ".helmit/CHANGES.md"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if tracked.returncode != 0:
        fail(".helmit/CHANGES.md is not versioned")


def read_ledger():
    require_ledger()
    with open(LEDGER, "rb") as stream:
        raw = stream.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(".helmit/CHANGES.md is not valid UTF-8: %s" % exc)
    ids = []
    numbers = []
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        ids.append(match.group(1))
        numbers.append(int(match.group(2)))
    if len(ids) != len(set(ids)):
        fail(".helmit/CHANGES.md contains a duplicate CHG identity")
    if numbers != sorted(numbers) or any(
        current <= previous for previous, current in zip(numbers, numbers[1:])
    ):
        fail(".helmit/CHANGES.md identities are not strictly monotonic")
    return raw, text, ids, numbers


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def next_id(numbers):
    number = (numbers[-1] if numbers else 0) + 1
    return "CHG-%0*d" % (max(3, len(str(number))), number)


def state():
    raw, _text, ids, numbers = read_ledger()
    return {
        "base": git("rev-parse", "HEAD"),
        "ledger": digest(raw),
        "next_id": next_id(numbers),
        "count": len(ids),
    }


class LedgerLock:
    def __enter__(self):
        deadline = time.monotonic() + 15.0
        while True:
            try:
                os.mkdir(MUTEX, 0o700)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    fail("timed out waiting for the CHANGES ledger lock")
                time.sleep(0.01)
        try:
            with open(os.path.join(MUTEX, "owner"), "w", encoding="ascii") as owner:
                owner.write(str(os.getpid()) + "\n")
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, _kind, _value, _traceback):
        try:
            os.unlink(os.path.join(MUTEX, "owner"))
        except FileNotFoundError:
            pass
        try:
            os.rmdir(MUTEX)
        except FileNotFoundError:
            pass


def parse_options(args, allowed, required):
    values = {}
    index = 0
    while index < len(args):
        name = args[index]
        if name not in allowed:
            fail("unknown option %s\n%s" % (name, USAGE), 2)
        if index + 1 >= len(args):
            fail("%s requires a value\n%s" % (name, USAGE), 2)
        if name in values:
            fail("%s was provided more than once" % name, 2)
        values[name] = args[index + 1]
        index += 2
    missing = [name for name in required if not values.get(name)]
    if missing:
        fail("missing required option(s): %s\n%s" % (", ".join(missing), USAGE), 2)
    return values


def cell(value):
    return " ".join(value.replace("\\", "\\\\").replace("|", "\\|").splitlines()).strip()


def uncell(value):
    result = []
    escaped = False
    for character in value:
        if escaped:
            result.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        else:
            result.append(character)
    if escaped:
        result.append("\\")
    return "".join(result)


def row_cells(line):
    if not line.startswith("|") or not line.endswith("|"):
        return []
    fields = []
    current = []
    escaped = False
    for character in line[1:-1]:
        if escaped:
            current.extend(("\\", character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            fields.append(uncell("".join(current).strip()))
            current = []
        else:
            current.append(character)
    fields.append(uncell("".join(current).strip()))
    return fields


def ledger_rows(text):
    rows = {}
    for line in text.splitlines():
        fields = row_cells(line)
        if len(fields) == 9 and ID_RE.fullmatch(fields[0]):
            if fields[0] in rows:
                fail(".helmit/CHANGES.md contains a duplicate CHG identity")
            rows[fields[0]] = {key: value for key, value in zip(
                ("id", "kind", "origin", "intent", "task", "paths", "verify", "inbox", "status"),
                fields,
            )}
    return rows


def require_row(text, identity, status=None):
    row = ledger_rows(text).get(identity)
    if row is None:
        fail("CHANGES has no entry for %s" % identity)
    if row["task"] != identity + ".1":
        fail("CHANGES task for %s is not canonical" % identity)
    if status is not None and row["status"] != status:
        fail("CHANGES entry %s must be %s" % (identity, status))
    return row


def declared_paths(row):
    return valid_paths(row["paths"])


def valid_paths(value):
    paths = {item.strip() for item in value.split(",") if item.strip()}
    if not paths or any(path.startswith("/") or path in (".", "..")
                        or ".." in path.split("/") for path in paths):
        fail("CHANGES has invalid declared paths")
    return paths


def render_row(row):
    return "| " + " | ".join(cell(row[key]) for key in (
        "id", "kind", "origin", "intent", "task", "paths", "verify",
        "inbox", "status")) + " |"


def replace_row(text, identity, row):
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        fields = row_cells(stripped)
        if fields and fields[0] == identity:
            lines[index] = render_row(row) + line[len(stripped):]
            return "".join(lines)
    fail("CHANGES has no entry for %s" % identity)


def canonical_subject(row):
    return "fix(chg): %s [%s]" % (row["intent"], row["task"])


def git_bytes(spec):
    result = subprocess.run(
        ["git", "-C", ROOT, "show", spec],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def git_text(spec):
    raw = git_bytes(spec)
    if raw is None:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("%s is not valid UTF-8" % spec)


def changed_paths(staged=False):
    command = ["git", "-C", ROOT, "diff"]
    if staged:
        command.append("--cached")
    command.extend(("--name-only", "-z"))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        fail("could not inspect the Git candidate")
    paths = {os.fsdecode(item) for item in result.stdout.split(b"\0") if item}
    if not staged:
        untracked = subprocess.run(
            ["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if untracked.returncode != 0:
            fail("could not inspect untracked candidate paths")
        paths |= {os.fsdecode(item) for item in untracked.stdout.split(b"\0") if item}
    return paths


def classify_kind(kind, stage):
    if stage not in ("before", "in-flight"):
        fail("--stage must be before or in-flight", 2)
    if kind in LIMITED_KINDS:
        return {"kind": kind, "route": "CHG", "stage": stage}
    if kind in DURABLE_KINDS:
        if stage == "in-flight":
            fail(
                "durable scope discovered in-flight: stop the current CHG and route "
                "to /helmit:spec and a phase; never create a REQ mid-implementation",
                3,
            )
        fail(
            "CHG refused for durable scope: route to /helmit:spec and a phase "
            "before implementation",
            3,
        )
    fail("unknown change kind %s" % kind, 2)


def require_configuration_endpoint_proof(paths, verify):
    """A configuration CHG must make every changed endpoint visible to proof.

    Generic suite selectors can remain useful alongside this check, but they
    cannot stand in for exercising the real files named by the correction.
    Requiring the literal paths keeps the contract transparent and lets the
    command delegate the actual comparison to any executable the project owns.
    """
    endpoints = valid_paths(paths)
    missing = sorted(path for path in endpoints if path not in verify)
    if missing:
        fail("configuration verify must exercise every declared path; missing: %s"
             % ",".join(missing), 2)


def write_entry(text, values, identity):
    marker = "\n<!-- status: open | done -->"
    if text.count(marker) != 1:
        fail(".helmit/CHANGES.md is missing its unique status marker")
    row = "| {id} | {kind} | {origin} | {intent} | {task} | {paths} | {verify} | {inbox} | open |".format(
        id=identity,
        kind=cell(values["--kind"]),
        origin=cell(values["--origin"]),
        intent=cell(values["--intent"]),
        task=identity + ".1",
        paths=cell(values["--paths"]),
        verify=cell(values["--verify"]),
        inbox=cell(values.get("--inbox", "-")),
    )
    updated = text.replace(marker, "\n" + row + marker)
    fd, temporary = tempfile.mkstemp(prefix=".CHANGES.", dir=HELMIT_DIR)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, LEDGER)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return updated.encode("utf-8")


def write_ledger(text):
    fd, temporary = tempfile.mkstemp(prefix=".CHANGES.", dir=HELMIT_DIR)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, LEDGER)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return text.encode("utf-8")


def snapshot(args):
    if args:
        fail("snapshot accepts no options\n%s" % USAGE, 2)
    with LedgerLock():
        print(json.dumps(state(), sort_keys=True))


def classify(args):
    values = parse_options(args, {"--kind", "--stage"}, {"--kind"})
    result = classify_kind(values["--kind"], values.get("--stage", "before"))
    print(json.dumps(result, sort_keys=True))


def allocate(args, emit=True, acquire_lock=True):
    allowed = {
        "--expected-base",
        "--expected-ledger",
        "--expected-id",
        "--kind",
        "--origin",
        "--intent",
        "--paths",
        "--verify",
        "--inbox",
    }
    required = allowed - {"--inbox"}
    values = parse_options(args, allowed, required)
    classify_kind(values["--kind"], "before")
    if not ID_RE.fullmatch(values["--expected-id"]):
        fail("--expected-id must be canonical CHG-NNN", 2)
    for name in ("--origin", "--intent", "--paths", "--verify"):
        if not cell(values[name]):
            fail("%s must not be blank" % name, 2)
    if values["--kind"] == "configuration":
        require_configuration_endpoint_proof(values["--paths"], values["--verify"])

    def write():
        current = state()
        stale = []
        comparisons = (
            ("base", "--expected-base", "base"),
            ("ledger", "--expected-ledger", "ledger"),
            ("identity", "--expected-id", "next_id"),
        )
        for reason, option, key in comparisons:
            if values[option] != current[key]:
                stale.append(reason)
        identity = current["next_id"]
        raw, text, ids, _numbers = read_ledger()
        if identity in ids:
            fail("refusing to overwrite existing identity %s" % identity)
        new_raw = write_entry(text, values, identity)
        result = {
            "base": current["base"],
            "id": identity,
            "ledger": digest(new_raw),
            "reallocated": bool(stale),
            "stale": stale,
            "task": identity + ".1",
        }
        if emit:
            print(json.dumps(result, sort_keys=True))
        return result, raw

    if acquire_lock:
        with LedgerLock():
            return write()
    return write()


def open_change(args):
    with LedgerLock():
        result, _previous_raw = allocate(args, emit=False, acquire_lock=False)
    print(json.dumps(result, sort_keys=True))


def expand_paths(args):
    values = parse_options(args, {
        "--approved-by", "--expected-base", "--expected-ledger", "--id", "--paths",
    }, {"--approved-by", "--expected-base", "--expected-ledger", "--id", "--paths"})
    if values["--approved-by"] != "human":
        fail("expand-paths requires --approved-by human", 2)
    identity = values["--id"]
    if not ID_RE.fullmatch(identity):
        fail("--id must be canonical CHG-NNN", 2)
    additions = valid_paths(values["--paths"])
    with LedgerLock():
        current = state()
        stale = [name for name in ("base", "ledger")
                 if values["--expected-" + name] != current[name]]
        if stale:
            fail("stale expansion candidate: %s" % ",".join(stale), 3)
        _raw, text, _ids, _numbers = read_ledger()
        row = require_row(text, identity, "open")
        old_paths = declared_paths(row)
        if additions <= old_paths:
            fail("expand-paths must add at least one new path")
        row["paths"] = ",".join(sorted(old_paths | additions))
        new_raw = write_ledger(replace_row(text, identity, row))
        print(json.dumps({"id": identity, "paths": sorted(old_paths | additions),
                          "ledger": digest(new_raw)}, sort_keys=True))


def revalidate(args):
    values = parse_options(args, {"--base", "--ledger", "--id"}, {"--base", "--ledger", "--id"})
    if not ID_RE.fullmatch(values["--id"]):
        fail("--id must be canonical CHG-NNN", 2)
    with LedgerLock():
        current = state()
        _raw, _text, ids, _numbers = read_ledger()
        stale = []
        if values["--base"] != current["base"]:
            stale.append("base")
        if values["--ledger"] != current["ledger"]:
            stale.append("ledger")
        if ids.count(values["--id"]) != 1:
            stale.append("identity")
        if stale:
            sys.stderr.write("change: stale candidate: %s\n" % ",".join(stale))
            raise SystemExit(3)
        print(json.dumps({"id": values["--id"], "valid": True}, sort_keys=True))


def prepare_close(args):
    values = parse_options(args, {"--base", "--ledger", "--id"},
                           {"--base", "--ledger", "--id"})
    identity = values["--id"]
    if not ID_RE.fullmatch(identity):
        fail("--id must be canonical CHG-NNN", 2)
    with LedgerLock():
        current = state()
        _raw, text, _ids, _numbers = read_ledger()
        row = require_row(text, identity, "open")
        stale = [name for name in ("base", "ledger")
                 if values["--" + name] != current[name]]
        if stale:
            fail("stale close candidate: %s" % ",".join(stale), 3)
        print(json.dumps({"id": identity, "task": row["task"],
                          "subject": canonical_subject(row)}, sort_keys=True))


def valid_new_open_row(row):
    return (row["status"] == "open" and row["task"] == row["id"] + ".1"
            and bool(declared_paths(row)) and bool(row["verify"]))


def closing_ledger_transition(before, after, identity):
    before_rows, after_rows = ledger_rows(before), ledger_rows(after)
    new = require_row(after, identity, "done")
    if new["task"] != identity + ".1":
        fail("CHANGES task for %s is not canonical" % identity)
    removed = set(before_rows) - set(after_rows)
    if removed:
        fail("candidate removes a CHANGES entry")
    if any(before_rows[key] != after_rows[key]
           for key in before_rows if key != identity):
        fail("candidate changes another CHANGES entry")
    if identity in before_rows:
        old = require_row(before, identity, "open")
        expected = dict(old)
        expected["status"] = "done"
        if new != expected:
            fail("candidate changes fields other than status for %s" % identity)
    else:
        old = dict(new)
        old["status"] = "open"
    for added in set(after_rows) - set(before_rows) - {identity}:
        if not valid_new_open_row(after_rows[added]):
            fail("candidate adds a non-open peer CHANGES entry")
    return old


def inbox_transition_valid(reference):
    before = git_text("HEAD:.helmit/INBOX.md")
    after = git_text(":.helmit/INBOX.md")
    if not after:
        return False
    for line in before.splitlines():
        if reference in line and line.startswith("- [ ]"):
            return "- [x]" + line[5:] in after.splitlines()
    return False


def candidate(args):
    values = parse_options(args, {"--id", "--subject"}, {"--id", "--subject"})
    identity = values["--id"]
    if not ID_RE.fullmatch(identity):
        fail("--id must be canonical CHG-NNN", 2)
    before = git_text("HEAD:.helmit/CHANGES.md")
    after = git_text(":.helmit/CHANGES.md")
    if not after:
        fail(".helmit/CHANGES.md is missing")
    row = closing_ledger_transition(before, after, identity)
    if values["--subject"] != canonical_subject(row):
        fail("commit subject must be exactly: %s" % canonical_subject(row))
    allowed = declared_paths(row) | {".helmit/CHANGES.md"}
    inbox = row["inbox"]
    if inbox != "-":
        allowed.add(".helmit/INBOX.md")
        if not inbox_transition_valid(inbox):
            fail("candidate does not close exactly its linked INBOX item")
    paths = changed_paths(staged=True)
    undeclared = sorted(paths - allowed)
    if ".helmit/CHANGES.md" not in paths:
        fail("candidate does not close its CHANGES entry")
    if inbox != "-" and ".helmit/INBOX.md" not in paths:
        fail("candidate does not close its linked INBOX item")
    print(json.dumps({"id": identity, "task": row["task"],
                      "subject": canonical_subject(row),
                      "paths": sorted(paths), "undeclared": undeclared},
                     sort_keys=True))


def recover(args):
    values = parse_options(args, {"--id"}, {"--id"})
    identity = values["--id"]
    if not ID_RE.fullmatch(identity):
        fail("--id must be canonical CHG-NNN", 2)
    _raw, text, _ids, _numbers = read_ledger()
    row = require_row(text, identity, "done")
    subject = canonical_subject(row)
    hashes = [line for line in git("log", "--format=%H%x00%s", "HEAD").splitlines()
              if line.endswith("\0" + subject)]
    if len(hashes) != 1:
        fail("expected exactly one commit with canonical subject for %s; found %d"
             % (identity, len(hashes)), 3)
    commit = hashes[0].split("\0", 1)[0]
    events_path = os.path.join(HELMIT_DIR, "run.jsonl")
    try:
        events = [json.loads(line) for line in open(events_path, encoding="utf-8")]
    except (OSError, ValueError):
        events = []
    if any(event.get("event") == "task_committed" and event.get("task") == row["task"]
           and event.get("commit") == commit and event.get("verify_result") == "passed"
           for event in events if isinstance(event, dict)):
        print(json.dumps({"commit": commit, "id": identity, "recovered": False}, sort_keys=True))
        return
    committed_text = git_text(commit + ":.helmit/CHANGES.md")
    committed_row = require_row(committed_text, identity, "done")
    if not committed_row["verify"].strip():
        fail("committed CHG has no verification command", 3)
    if canonical_subject(committed_row) != subject:
        fail("canonical subject does not match the committed CHANGES entry", 3)
    parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
    if len(parents) != 1:
        fail("recovery requires one unambiguous parent", 3)
    closing_ledger_transition(git_text(parents[0] + ":.helmit/CHANGES.md"),
                             committed_text, identity)
    hook_dir = os.path.dirname(os.path.abspath(__file__))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("change_proof_sandbox",
                                                 os.path.join(hook_dir, "proof-sandbox.py"))
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    try:
        with proof.workspace(ROOT, "head") as (path, _head_tree):
            checkout = subprocess.run(["git", "-C", str(path), "checkout", "--detach", "--quiet", commit],
                                      env=proof.proof_environment(ROOT, path, _head_tree, "head"),
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if checkout.returncode:
                fail("could not materialize the recovered commit", 3)
            tree = git("rev-parse", commit + "^{tree}")
            result = subprocess.run(["bash", "-c", committed_row["verify"]], cwd=path,
                                    env=proof.proof_environment(ROOT, path, tree, commit),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                fail("committed CHG verify failed; recovery recorded no completion", 3)
    except proof.ProofSandboxError as error:
        fail("recovery proof failed: %s" % error, 3)
    hook = os.path.join(hook_dir, "run-log.sh")
    result = subprocess.run(["bash", hook, "append", "task_committed",
                             "task=" + row["task"], "commit=" + commit,
                             "verify_result=passed", "verify=" + committed_row["verify"],
                             "tree=" + tree, "proof_source=recovery"], cwd=ROOT,
                            env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT))
    if result.returncode:
        fail("could not record recovered CHG proof")
    print(json.dumps({"commit": commit, "id": identity, "recovered": True}, sort_keys=True))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        stream = sys.stdout if len(sys.argv) >= 2 else sys.stderr
        stream.write(USAGE)
        raise SystemExit(0 if len(sys.argv) >= 2 else 2)
    command = sys.argv[1]
    actions = {
        "snapshot": snapshot,
        "classify": classify,
        "allocate": allocate,
        "open": open_change,
        "expand-paths": expand_paths,
        "revalidate": revalidate,
        "prepare-close": prepare_close,
        "candidate": candidate,
        "recover": recover,
    }
    if command not in actions:
        fail("unknown command %s\n%s" % (command, USAGE), 2)
    actions[command](sys.argv[2:])


main()
