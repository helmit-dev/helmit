import argparse
import json
import os
import pathlib
import re
import subprocess


TASK_RE = re.compile(r"^- \[[ xX>]\] (\S+)\s+(.+)$")


def task_metadata(root):
    paths = sorted((root / ".helmit" / "phases").glob("*/CHART.md"))
    paths += sorted((root / ".helmit" / "corrections").glob("*.md"))
    tasks = {}
    order = []
    ledger = root / ".helmit" / "CHANGES.md"
    try:
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            if not re.match(r"^\| CHG-[0-9]{3,} \|", line):
                continue
            cells = [value.strip() for value in re.split(r"(?<!\\)\|", line.strip("|"))]
            if len(cells) == 9:
                task = cells[4]
                tasks[task] = {"title": cells[3], "relation": "Supports", "requirements": "not applicable (CHG)",
                               "verify": cells[6]}
                order.append(task)
    except OSError:
        pass
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            match = TASK_RE.match(line)
            if not match:
                continue
            task, rest = match.groups()
            parts = [part.strip() for part in rest.split(" · ")]
            title = re.sub(r"\s+\(done(?:, commit [^)]+)?\)$", "", parts[0]).strip()
            fields = {}
            for part in parts[1:]:
                key, separator, value = part.partition(":")
                if separator:
                    fields[key.strip()] = value.strip()
            if task not in tasks:
                order.append(task)
            tasks[task] = {
                "title": title,
                "relation": "Satisfies" if "satisfies" in fields else "Supports" if "supports" in fields else "Covers" if "covers" in fields else "Relation",
                "requirements": fields.get("satisfies", fields.get("supports", fields.get("covers", "not declared"))),
                "verify": fields.get("verify", "not declared"),
            }
    return tasks, order


def run_events(root):
    path = root / ".helmit" / "run.jsonl"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def committed_tasks(events, phase, session):
    claims = {}
    committed = {}
    for event in events:
        task = event.get("task")
        if event.get("event") == "task_claimed" and isinstance(task, str):
            claims[task] = event.get("session", "")
            continue
        if event.get("event") != "task_committed" or not isinstance(task, str):
            continue
        if phase is not None and not task.startswith(phase + "."):
            continue
        if session is not None and claims.get(task) != session:
            continue
        commit = event.get("commit")
        if isinstance(commit, str) and commit:
            committed[task] = event
    return committed


def git(root, *args, binary=False):
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def real_commit(root, value):
    full = git(root, "rev-parse", "--verify", value + "^{commit}")
    if full is None:
        return None
    full = full.strip()
    if subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", full, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        return None
    short = git(root, "show", "-s", "--format=%h", full)
    subject = git(root, "show", "-s", "--format=%s", full)
    if short is None or subject is None:
        return None
    return short.strip(), subject.strip()


def event_tasks(event):
    values = event.get("tasks") or event.get("task") or ""
    return [value for value in values.split(",") if value]


def task_commits(root, events, task, closing_event):
    values = []
    for event in events:
        if event.get("event") != "commit_checkpoint" or task not in event_tasks(event):
            continue
        commit = event.get("commit")
        if isinstance(commit, str) and commit and commit not in values:
            values.append(commit)
    closing = closing_event.get("commit")
    if isinstance(closing, str) and closing and closing not in values:
        values.append(closing)
    return [resolved for value in values if (resolved := real_commit(root, value))]


def verify_result(events, event):
    recorded = event.get("verify_result") or event.get("verify")
    if recorded:
        return recorded
    task = event.get("task")
    commit = event.get("commit")
    end = events.index(event)
    starts = [i for i, item in enumerate(events[:end])
              if item.get("event") == "commit_started" and task in event_tasks(item)]
    if not starts:
        return "not recorded"
    start = starts[-1]
    landed = [i for i, item in enumerate(events[start + 1:end], start + 1)
              if item.get("event") == "commit_landed"
              and task in event_tasks(item)
              and str(commit).startswith(str(item.get("commit", "")))]
    if len(landed) != 1:
        return "not recorded"
    gates = [item for item in events[start + 1:landed[0]]
             if item.get("event") == "gate_run"
             and item.get("verdict") == "passed"
             and item.get("steps") == "test,build,lint"]
    return "passed — global gate" if len(gates) == 1 else "not recorded"


def report(root, phase, session):
    metadata, order = task_metadata(root)
    events = run_events(root)
    committed = committed_tasks(events, phase, session)
    rows = []
    for task in order:
        event = committed.get(task)
        if event is None:
            continue
        commit = real_commit(root, event["commit"])
        if commit is None:
            continue
        rows.append((task, metadata[task], event, task_commits(root, events, task, event)))

    print("Delivery report")
    if not rows:
        print("No tasks were delivered.")
        return
    for task, meta, event, commits in rows:
        result = verify_result(events, event)
        print("- %s — %s" % (task, meta["title"]))
        print("  Commits:")
        for short, subject in commits:
            print("    - %s %s" % (short, subject))
        print("  %s: %s" % (meta["relation"], meta["requirements"]))
        print("  Verify: %s — %s" % (meta["verify"], result))


def main():
    parser = argparse.ArgumentParser(
        prog="delivery-report.sh",
        description="derive an on-screen delivery report from HelmIt artifacts and Git",
    )
    parser.add_argument("--phase", help="include committed tasks from this phase")
    parser.add_argument("--session", help="include tasks claimed by this session")
    args = parser.parse_args()
    if args.phase is None and args.session is None:
        parser.error("one of --phase or --session is required")
    root = pathlib.Path(os.environ.get("DR_ROOT", os.getcwd())).resolve()
    report(root, args.phase, args.session)


if __name__ == "__main__":
    main()
