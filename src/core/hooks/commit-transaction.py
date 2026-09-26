import hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone

ROOT = os.environ.get("CT_ROOT") or os.getcwd()
LOG = os.path.join(ROOT, ".helmit", "run.jsonl")
TASK_RE = re.compile(r"^(?:[A-Za-z0-9_-]+\.[0-9]+|CHG-[0-9]{3,}\.1)$")

def fail(message):
    print("error: commit-transaction: " + message, file=sys.stderr)
    raise SystemExit(2)

def git(*args):
    p = subprocess.run(["git", "-C", ROOT] + list(args), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout.strip() if p.returncode == 0 else ""

def index_path():
    path = git("rev-parse", "--path-format=absolute", "--git-path", "index")
    if not path or not os.path.isabs(path):
        fail("cannot resolve the effective Git index path")
    return path

def fingerprint():
    path = index_path()
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return "missing"

def entries():
    try: lines = open(LOG, encoding="utf-8").read().splitlines()
    except OSError: return []
    out = []
    for line in lines:
        try: row = json.loads(line)
        except ValueError: continue
        if isinstance(row, dict): out.append(row)
    return out

def append(event, **fields):
    row = {"ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
           "event": event, "pid": os.getpid()}
    row.update(fields)
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(row) + "\n")

def task_set(value):
    tasks = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not tasks or any(not TASK_RE.fullmatch(task) for task in tasks):
        fail("task-set must contain comma-separated task ids")
    return ",".join(tasks)

def start(args):
    if len(args) != 1: fail("usage: start <task-set>")
    tasks = task_set(args[0])
    fields = {"tasks": tasks}
    if "," not in tasks: fields["task"] = tasks
    append("commit_started", **fields, session=os.environ.get("CT_SESSION", ""),
           recorder_pid=str(os.getpid()), base_head=git("rev-parse", "HEAD"), index=fingerprint())

def landed(args):
    if len(args) != 2: fail("usage: landed <task-set> <commit>")
    tasks = task_set(args[0])
    fields = {"tasks": tasks}
    if "," not in tasks: fields["task"] = tasks
    append("commit_landed", **fields, commit=args[1], base_head=git("rev-parse", "HEAD"), index=fingerprint())

def recover(args):
    if args: fail("usage: recover")
    lock = index_path() + ".lock"
    if os.path.lexists(lock):
        print("UNKNOWN_LOCK: preserve index.lock (commit records do not prove Git lock ownership)")
        return
    open_attempts = {}
    for row in entries():
        identity = row.get("tasks") or row.get("task")
        if row.get("event") == "commit_started": open_attempts[identity] = row
        elif row.get("event") == "commit_landed": open_attempts.pop(identity, None)
    if not open_attempts:
        print("SAFE_RETRY: no open HelmIt commit attempt")
        return
    attempt = list(open_attempts.values())[-1]
    base, current = attempt.get("base_head", ""), git("rev-parse", "HEAD")
    if current and current != base:
        print("LANDED: HEAD advanced after commit_started; append commit_landed after identifying the landed commit")
        return
    print("SAFE_RETRY: open attempt has no index.lock")

def main():
    if not os.path.isdir(os.path.join(ROOT, ".helmit")): fail(".helmit missing")
    if len(sys.argv) < 2: fail("usage: {start|landed|recover}")
    {"start": start, "landed": landed, "recover": recover}.get(sys.argv[1], lambda _: fail("unknown command"))(sys.argv[2:])

if __name__ == "__main__": main()
