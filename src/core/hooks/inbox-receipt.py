"""Keep the active Inbox small and expose selective, deterministic reads."""

import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile


ROOT = os.path.abspath(os.environ.get("IR_ROOT") or os.getcwd())
HELMIT = os.path.join(ROOT, ".helmit")
INBOX = os.path.join(HELMIT, "INBOX.md")
HISTORY = os.path.join(HELMIT, "history")
HEADERS = ("## Inbox", "## Backlog", "## Closed")
ITEM = re.compile(r"^- \[([ xX])\] ")
DATE = re.compile(r"\b(20[0-9]{2})-[0-9]{2}-[0-9]{2}\b")


def read_lines(path):
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.readlines()
    except OSError:
        return None


def atomic_write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % os.path.basename(path),
                                              dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sections(lines):
    found = [(index, line.rstrip("\r\n")) for index, line in enumerate(lines)
             if line.rstrip("\r\n") in HEADERS]
    if [name for _index, name in found] != list(HEADERS):
        return None
    result = {}
    for offset, (start, name) in enumerate(found):
        end = found[offset + 1][0] if offset + 1 < len(found) else len(lines)
        result[name] = (start, end)
    return result


def classify(lines):
    parsed = sections(lines)
    counts = {"open": 0, "routed": 0, "unrouted": 0, "backlog": 0, "closed": 0}
    items = {"all": [], "routed": [], "unrouted": [], "backlog": []}
    if parsed is None:
        return counts, items
    for header, (start, end) in parsed.items():
        for line in lines[start + 1:end]:
            match = ITEM.match(line)
            if not match:
                continue
            done = match.group(1).lower() == "x"
            if done:
                counts["closed"] += 1
                continue
            if header == "## Backlog":
                counts["backlog"] += 1
                items["backlog"].append(line.rstrip("\r\n"))
            elif header == "## Inbox":
                counts["open"] += 1
                kind = "routed" if "[TRIADO -> " in line else "unrouted"
                counts[kind] += 1
                items[kind].append(line.rstrip("\r\n"))
                items["all"].append(line.rstrip("\r\n"))
    return counts, items


def history_path(line):
    match = DATE.search(line)
    year = match.group(1) if match else str(datetime.date.today().year)
    return os.path.join(HISTORY, "INBOX-%s.md" % year), year


def archive_closed(lines):
    parsed = sections(lines)
    if parsed is None:
        return lines, 0, "archive skipped: canonical Inbox sections are malformed"
    section_at = {}
    for header, (start, end) in parsed.items():
        for index in range(start + 1, end):
            section_at[index] = header
    selected = []
    for index, line in enumerate(lines):
        match = ITEM.match(line)
        if match and match.group(1).lower() == "x" and section_at.get(index) in HEADERS:
            selected.append((index, line))
    if not selected:
        return lines, 0, ""

    grouped = {}
    for _index, line in selected:
        path, year = history_path(line)
        grouped.setdefault((path, year), []).append(line)

    # History lands first. An interruption can temporarily duplicate an item,
    # but can never lose it; the next idempotent pass removes the active copy.
    for (path, year), additions in sorted(grouped.items()):
        existing = read_lines(path)
        if existing is None:
            existing = ["# Inbox history — %s\n" % year, "parent: inbox\n", "\n"]
        known = {line.rstrip("\r\n") for line in existing if ITEM.match(line)}
        fresh = [line for line in additions if line.rstrip("\r\n") not in known]
        if fresh:
            if existing and existing[-1].strip():
                existing.append("\n")
            existing.extend(fresh)
            atomic_write(path, existing)

    removed = {index for index, _line in selected}
    active = [line for index, line in enumerate(lines) if index not in removed]
    atomic_write(INBOX, active)
    return active, len(selected), ""


def emit_summary(lines, limit, selection, archived=0):
    counts, items = classify(lines)
    print("INBOX summary: open=%d unrouted=%d routed=%d backlog=%d archived=%d" %
          (counts["open"], counts["unrouted"], counts["routed"],
           counts["backlog"], archived))
    chosen = items[selection][:limit]
    for line in chosen:
        print(line)
    remaining = max(0, len(items[selection]) - len(chosen))
    if remaining:
        print("... %d more %s item(s); request the next batch explicitly" %
              (remaining, selection))


def run_sanity():
    sanity = os.environ.get("IR_SANITY")
    if not sanity:
        return
    try:
        result = subprocess.run(["bash", sanity, "check"], text=True,
                                capture_output=True, check=False)
    except OSError:
        return
    if result.stdout:
        sys.stdout.write(result.stdout)
    elif result.returncode == 0:
        print("INBOX receipt: healthy")


def maintain(args):
    lines = read_lines(INBOX)
    if lines is None:
        return
    active, archived, warning = archive_closed(lines)
    if warning:
        print("INBOX receipt: " + warning)
    run_sanity()
    emit_summary(active, args.limit, args.selection, archived)


def archive(args):
    lines = read_lines(INBOX)
    if lines is None:
        return
    _active, archived, warning = archive_closed(lines)
    if warning:
        print("INBOX receipt: " + warning)
    if archived:
        run_sanity()
        print("INBOX archive: %d resolved item(s) moved to versioned history" % archived)


def summary(args):
    lines = read_lines(INBOX)
    if lines is not None:
        emit_summary(lines, args.limit, args.selection)


def find_history(args):
    if not os.path.isdir(HISTORY):
        return
    matches = 0
    for name in sorted(os.listdir(HISTORY)):
        if not re.fullmatch(r"INBOX-20[0-9]{2}\.md", name):
            continue
        path = os.path.join(HISTORY, name)
        for line in read_lines(path) or []:
            if ITEM.match(line) and args.query in line:
                print("%s: %s" % (os.path.relpath(path, ROOT), line.rstrip("\r\n")))
                matches += 1
                if matches >= args.limit:
                    return


def parser():
    root = argparse.ArgumentParser(prog="inbox-receipt.sh")
    commands = root.add_subparsers(dest="action")
    for name in ("maintain", "summary"):
        command = commands.add_parser(name)
        command.add_argument("--limit", type=int, default=5)
        command.add_argument("--selection", choices=("unrouted", "routed", "all", "backlog"),
                             default="unrouted")
        command.set_defaults(handler=maintain if name == "maintain" else summary)
    archive_command = commands.add_parser("archive")
    archive_command.set_defaults(handler=archive)
    history = commands.add_parser("history")
    history.add_argument("--find", dest="query", required=True)
    history.add_argument("--limit", type=int, default=20)
    history.set_defaults(handler=find_history)
    return root


def main():
    args = parser().parse_args()
    if args.action:
        if getattr(args, "limit", 1) < 0:
            raise SystemExit("limit must be non-negative")
        args.handler(args)
        return
    payload = os.environ.get("IR_INPUT", "")
    if ".helmit/INBOX.md" not in payload and ".helmit\\INBOX.md" not in payload:
        return
    maintain(argparse.Namespace(limit=0, selection="unrouted"))


if __name__ == "__main__":
    main()
