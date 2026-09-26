import json, os, sys
from datetime import datetime, timezone

ROOT = os.environ.get("HO_ROOT") or os.getcwd()
LOG = os.path.join(ROOT, ".helmit", "run.jsonl")
THREAD = os.environ.get("CODEX_THREAD_ID", "")

def fail(message):
    print("heartbeat-owner: REFUSE — " + message, file=sys.stderr)
    raise SystemExit(2)

def rows():
    try:
        lines = open(LOG, encoding="utf-8").read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict): out.append(row)
    return out

def append(event, automation_id):
    row = {"ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
           "event": event, "automation_id": automation_id, "thread_id": THREAD}
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

def active():
    owners = {}
    for row in rows():
        aid = row.get("automation_id")
        if not isinstance(aid, str) or not aid: continue
        if row.get("event") == "heartbeat_owner_armed": owners[aid] = row
        elif row.get("event") == "heartbeat_owner_cleared": owners.pop(aid, None)
    return owners

def owned(aid):
    if not THREAD: fail("CODEX_THREAD_ID missing; automation has no verifiable task")
    row = active().get(aid)
    if row is None: fail("automation has no verifiable active record")
    if row.get("thread_id") != THREAD: fail("automation belongs to another task")
    return row

def main(args):
    if len(args) != 2 or args[0] not in ("arm", "verify", "clear"):
        fail("uso: heartbeat-owner.sh {arm|verify|clear} <automation-id>")
    action, aid = args
    if not aid: fail("automation-id ausente")
    if action == "arm":
        if not THREAD: fail("CODEX_THREAD_ID missing; no global fallback is created")
        owners = active()
        existing = owners.get(aid)
        if existing and existing.get("thread_id") != THREAD: fail("automation id already belongs to another task")
        if not existing:
            same_thread = sorted(key for key, row in owners.items()
                                 if row.get("thread_id") == THREAD)
            if same_thread:
                fail("task already owns automation %s; clear it before arming another" % same_thread[0])
            append("heartbeat_owner_armed", aid)
    elif action == "verify":
        owned(aid)
    else:
        if not THREAD: fail("CODEX_THREAD_ID missing; automation has no verifiable task")
        existing = active().get(aid)
        if existing and existing.get("thread_id") != THREAD:
            fail("automation belongs to another task")
        if existing:
            append("heartbeat_owner_cleared", aid)
    print("heartbeat-owner: CLEARED" if action == "clear" else "heartbeat-owner: OWNED")

main(sys.argv[1:])
