import json
import os
import subprocess
import sys
from datetime import datetime, timezone


ROOT = os.path.abspath(os.environ.get("PREFLIGHT_ROOT") or os.getcwd())
HELMIT = os.path.join(ROOT, ".helmit")
SESSION = (os.environ.get("HELMIT_SESSION_ID")
           or os.environ.get("CLAUDE_CODE_SESSION_ID")
           or os.environ.get("CODEX_THREAD_ID")
           or os.environ.get("CODEX_SESSION_ID")
           or os.environ.get("CLAUDE_SESSION_ID") or "")


def fail(message):
    print("error: preflight: " + message, file=sys.stderr)
    raise SystemExit(2)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def now():
    frozen = os.environ.get("HELMIT_PREFLIGHT_NOW")
    return parse_time(frozen) or datetime.now(timezone.utc)


def fresh(stamp, variable, default):
    parsed = parse_time(stamp)
    try:
        ttl = max(int(os.environ.get(variable, default)), 0)
    except ValueError:
        ttl = int(default)
    return parsed is not None and 0 <= (now() - parsed).total_seconds() < ttl


def concurrent():
    lock = read_json(os.path.join(HELMIT, "lock.json"))
    if (not lock or not lock.get("session") or lock.get("session") == SESSION
            or not fresh(lock.get("heartbeat_at"), "HELMIT_LOCK_STALE_SECS", "900")):
        return False
    lease = read_json(os.path.join(HELMIT, "executor-lease.json"))
    return bool(lease and lease.get("session") == lock.get("session")
                and fresh(lease.get("renewed_at"),
                          "HELMIT_EXECUTOR_LEASE_SECS", "900"))


def git_paths():
    process = subprocess.run(
        ["git", "-C", ROOT, "status", "--porcelain=v1", "-z",
         "--untracked-files=all"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if process.returncode != 0:
        fail("could not inspect the Git worktree")
    fields = process.stdout.split(b"\0")
    paths = []
    index = 0
    while index < len(fields) and fields[index]:
        record = fields[index]
        if len(record) < 4:
            fail("Git returned a malformed status record")
        status = record[:2]
        paths.append(os.fsdecode(record[3:]))
        index += 1
        if b"R" in status or b"C" in status:
            if index >= len(fields) or not fields[index]:
                fail("Git returned an incomplete rename record")
            paths.append(os.fsdecode(fields[index]))
            index += 1
    return sorted(set(paths))


def emit(verdict, paths=None):
    if paths:
        encoded = " ".join(json.dumps(path, ensure_ascii=False) for path in paths)
        print(verdict + " " + encoded)
    else:
        print(verdict)


def main(argv):
    if argv not in ([], ["check"]):
        fail("usage: preflight.sh [check]")
    if not os.path.isdir(HELMIT):
        fail(".helmit/ is missing; run /helmit:setup first")
    if concurrent():
        emit("BLOCKED_CONCURRENT")
        return 1
    paths = git_paths()
    emit("CHANGED" if paths else "READY", paths)
    return 0


sys.exit(main(sys.argv[1:]))
