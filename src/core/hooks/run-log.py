import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

EVENTS = ("task_claimed", "heartbeat", "task_committed", "commit_checkpoint", "commit_started", "commit_landed", "awaiting_input", "session_stop", "autopilot_tick", "beat", "gate_run", "map_shown", "map_refreshed", "remote_sync_deferred")
REASONS = ("gate", "awaiting_input", "clean", "interrupted")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TASK_RE = re.compile(r"^(?:[A-Za-z0-9_-]+\.[0-9]+|CHG-[0-9]{3,}\.1)$")
PRESENCE_EVENTS = ("task_claimed", "task_committed", "awaiting_input",
                   "session_stop")


def fold_claims(rows):
    """The canonical open task claims used by recovery and dashboard presence."""
    claims = {}
    for row in rows:
        event = row.get("event")
        task = row.get("task")
        if event == "task_claimed" and isinstance(task, str) and task:
            claims.pop(task, None)
            claims[task] = row
        elif event == "task_committed" and isinstance(task, str) and task:
            claims.pop(task, None)
        elif event == "session_stop" and row.get("reason") == "clean":
            claims.clear()
    return claims

def fail(message):
    print("error: run-log: " + message, file=sys.stderr)
    raise SystemExit(2)


def publish_dashboard(root):
    """Presence transitions refresh the optional projection, never the WAL."""
    dashboard = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "dashboard.sh")
    try:
        subprocess.run(["bash", dashboard, "publish", "--project", root],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=root), check=False)
    except OSError:
        pass


def mandate_in_progress(root):
    """Ask yolo.sh, which owns fulfilled-ness, instead of duplicating it."""
    yolo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolo.sh")
    try:
        proc = subprocess.run(
            ["bash", yolo, "status"], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=root), check=False,
        )
    except OSError:
        return False
    return (proc.returncode == 0 and
            bool(re.match(r"^yolo: (?:phase|full) in force\b", proc.stdout)))

def entries(path):
    try: data = open(path, encoding="utf-8", errors="replace").read()
    except OSError: data = ""
    lines = data.split("\n")
    if lines: lines.pop()
    result = []
    for line in lines:
        try: value = json.loads(line)
        except Exception: continue
        if isinstance(value, dict) and isinstance(value.get("event"), str): result.append(value)
    return result

def append(event, args):
    if event not in EVENTS: fail("invalid event: %s (valid: %s)" % (event, ", ".join(EVENTS)))
    pid = os.environ.get("RL_PID", "")
    entry = {"ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "event": event, "pid": int(pid) if pid.isdigit() else pid}
    for arg in args:
        if "=" not in arg: fail("argumento extra precisa ser k=v: " + arg)
        key, value = arg.split("=", 1)
        if not KEY_RE.match(key): fail("invalid key: %s (use [A-Za-z_][A-Za-z0-9_]*)" % key)
        if key in ("ts", "event", "pid"): fail("key reserved by the product, cannot be forged: " + key)
        entry[key] = value
    if (event in ("task_claimed", "awaiting_input", "session_stop") and
            not entry.get("session") and os.environ.get("RL_SESSION")):
        entry["session"] = os.environ["RL_SESSION"]
    root = os.environ.get("RL_ROOT") or os.getcwd()
    if event == "session_stop" and entry.get("reason") not in REASONS:
        fail("session_stop exige reason= ∈ %s (recebido: %s)" % ("|".join(REASONS), entry.get("reason", "<ausente>")))
    if "task" in entry and not TASK_RE.fullmatch(entry["task"]):
        fail("task must be a numbered phase task or CHG task")
    if "tasks" in entry:
        task_values = [value for value in entry["tasks"].split(",") if value]
        if not task_values or any(not TASK_RE.fullmatch(value) for value in task_values):
            fail("tasks must contain comma-separated numbered phase or CHG task ids")
    if event == "task_committed" and entry.get("verify_result") not in ("passed", "failed"):
        fail("task_committed requires verify_result=passed|failed")
    if event == "commit_checkpoint":
        tasks = [value for value in entry.get("tasks", "").split(",") if value]
        if not tasks or any(not TASK_RE.fullmatch(value) for value in tasks):
            fail("commit_checkpoint requires tasks=<comma-separated task ids>")
        if not entry.get("commit"):
            fail("commit_checkpoint requires commit=<hash>")
        if entry.get("proof") not in ("quick-floor", "task-verify", "integration"):
            fail("commit_checkpoint requires proof=quick-floor|task-verify|integration")
    if not os.path.isdir(os.path.join(root, ".helmit")): fail(".helmit/ does not exist in %s — no HelmIt project, nothing to record" % root)
    if event == "session_stop" and entry.get("reason") == "clean" and mandate_in_progress(root):
        fail("session_stop reason=clean is forbidden while a yolo mandate is in force; continue the eligible route or record a real stop")
    try:
        with open(os.path.join(root, ".helmit", "run.jsonl"), "a", encoding="utf-8") as out: out.write(json.dumps(entry) + "\n")
    except OSError: fail("could not append to %s" % os.path.join(root, ".helmit", "run.jsonl"))
    if event == "task_claimed" and entry.get("session") and entry.get("task"):
        lease = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "executor-lease.sh")
        try:
            subprocess.run(["bash", lease, "renew", "--task", entry["task"]],
                           cwd=root, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=root,
                                    HELMIT_SESSION_ID=entry["session"]),
                           check=False)
        except OSError:
            pass
    if event in PRESENCE_EVENTS:
        publish_dashboard(root)

def main():
    if len(sys.argv) < 2: fail("usage: run-log.sh {append <evento> [k=v ...] | heartbeat [k=v ...] | last | open-entry [--all]}")
    command, args = sys.argv[1], sys.argv[2:]
    if command == "append":
        if not args: fail("usage: run-log.sh {append <evento> [k=v ...] | heartbeat [k=v ...] | last | open-entry [--all]}")
        append(args[0], args[1:]); return
    if command == "heartbeat": append("heartbeat", args); return
    if command not in ("last", "open-entry") or (args and not (command == "open-entry" and args == ["--all"])):
        fail("%s does not accept %s" % (command, " ".join(args)) if args else "usage: run-log.sh {append <evento> [k=v ...] | heartbeat [k=v ...] | last | open-entry [--all]}")
    got = entries(os.path.join(os.environ.get("RL_ROOT") or os.getcwd(), ".helmit", "run.jsonl"))
    if command == "last":
        if not got: raise SystemExit(1)
        print(json.dumps(got[-1])); return
    open_claims = list(fold_claims(got).values())
    if not open_claims: raise SystemExit(1)
    for claim in open_claims if args else open_claims[-1:]: print(json.dumps(claim))

if __name__ == "__main__": main()
