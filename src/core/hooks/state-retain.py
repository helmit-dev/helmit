"""Compact STATE to current operational facts and expose a bounded summary."""

import argparse
import os
import re
import tempfile


ROOT = os.path.abspath(os.environ.get("SR_ROOT") or os.getcwd())
PATH = os.path.join(ROOT, ".helmit", "STATE.md")


def read_lines():
    try:
        with open(PATH, encoding="utf-8") as handle:
            return handle.readlines()
    except OSError:
        return None


def section_map(lines):
    headings = [(index, line.strip()) for index, line in enumerate(lines)
                if line.startswith("## ")]
    result = {}
    for offset, (start, name) in enumerate(headings):
        end = headings[offset + 1][0] if offset + 1 < len(headings) else len(lines)
        result[name] = lines[start + 1:end]
    return result


def bullets(lines):
    return [line.rstrip("\n")[2:].strip() for line in lines
            if line.startswith("- ") and line[2:].strip() not in ("", "none")]


def field(lines, names, default="none"):
    for line in lines:
        match = re.match(r"^- ([^:]+):\s*(.*?)\s*(?:<!--.*)?$", line.rstrip("\n"))
        if match and match.group(1).strip().lower() in names:
            return match.group(2).strip() or default
    return default


def facts(lines):
    sections = section_map(lines)
    position = sections.get("## Workflow position", []) + sections.get("## Position", [])
    focus = sections.get("## Current focus", []) + sections.get("## Current work", [])
    blockers = bullets(sections.get("## Blockers", []))
    decisions = (bullets(sections.get("## Decisions made this session", [])) +
                 bullets(sections.get("## Decisions still needed", [])) +
                 bullets(sections.get("## Notes for next session", [])))
    decisions = [item for item in decisions if not item.startswith("[expired] ")]
    decisions = list(dict.fromkeys(decisions))
    current = field(focus, {"current", "current task", "current phase", "last completed task"})
    next_step = field(focus, {"next", "next task", "next step"})
    return {
        "workflow": field(position, {"workflow"}),
        "active": field(position, {"active", "active phase"}),
        "current": current,
        "next": next_step,
        "blockers": blockers,
        "decisions": decisions,
    }


def rendered(data):
    lines = [
        "# Project State\n", "\n",
        "> Current operational resume context only. Durable product, architecture,\n",
        "> requirement, plan, proof, and history facts live in their owning artifacts.\n",
        "\n", "## Position\n",
        "- workflow: %s\n" % data["workflow"],
        "- Active: %s\n" % data["active"],
        "\n", "## Current work\n",
        "- Current: %s\n" % data["current"],
        "- Next: %s\n" % data["next"],
        "\n", "## Blockers\n",
    ]
    lines.extend(["- %s\n" % item for item in data["blockers"]] or ["- none\n"])
    lines.extend(["\n", "## Decisions still needed\n"])
    lines.extend(["- %s\n" % item for item in data["decisions"]] or ["- none\n"])
    return lines


def atomic_write(lines):
    directory = os.path.dirname(PATH)
    descriptor, temporary = tempfile.mkstemp(prefix=".STATE.", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(temporary, PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def compact(_args):
    lines = read_lines()
    if lines is None:
        return
    before = "".join(lines)
    data = facts(lines)
    after_lines = rendered(data)
    after = "".join(after_lines)
    if after == before:
        return
    atomic_write(after_lines)
    removed = sum(1 for line in lines if line.startswith("- [expired] "))
    print("STATE compacted: workflow=%s blockers=%d decisions=%d expired_removed=%d" %
          (data["workflow"], len(data["blockers"]), len(data["decisions"]), removed))
    if len(data["decisions"]) > 8:
        print("STATE attention: %d unresolved legacy decisions remain; classify them without blocking independent work" %
              len(data["decisions"]))


def summary(args):
    lines = read_lines()
    if lines is None:
        return
    data = facts(lines)
    print("STATE summary: workflow=%s active=%s current=%s next=%s blockers=%d decisions=%d" %
          (data["workflow"], data["active"], data["current"], data["next"],
           len(data["blockers"]), len(data["decisions"])))
    for item in data["blockers"]:
        print("BLOCKER: " + item)
    for item in data["decisions"][:args.limit]:
        print("DECISION: " + item)
    remaining = max(0, len(data["decisions"]) - args.limit)
    if remaining:
        print("... %d more decision(s); inspect only if relevant to the next action" % remaining)


def main():
    parser = argparse.ArgumentParser(prog="state-retain.sh")
    commands = parser.add_subparsers(dest="action")
    commands.add_parser("compact").set_defaults(handler=compact)
    summary_parser = commands.add_parser("summary")
    summary_parser.add_argument("--limit", type=int, default=5)
    summary_parser.set_defaults(handler=summary)
    args = parser.parse_args()
    if args.action is None:
        args.handler = compact
    if getattr(args, "limit", 0) < 0:
        raise SystemExit("limit must be non-negative")
    args.handler(args)


if __name__ == "__main__":
    main()
