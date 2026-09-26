import codecs
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


ROOT = os.environ.get("LEASE_ROOT") or os.getcwd()
HOOKS = os.environ.get("LEASE_HOOKS") or os.path.dirname(os.path.abspath(__file__))
LEASE = os.path.join(ROOT, ".helmit", "executor-lease.json")
RUNLOG = os.path.join(HOOKS, "run-log.sh")
LOCK = os.path.join(ROOT, ".helmit", "lock.json")
LOCK_HOOK = os.path.join(HOOKS, "lock.sh")
ENVIRONMENT_SESSION = (os.environ.get("HELMIT_SESSION_ID")
                       or os.environ.get("CLAUDE_CODE_SESSION_ID")
                       or os.environ.get("CODEX_THREAD_ID")
                       or os.environ.get("CODEX_SESSION_ID")
                       or os.environ.get("CLAUDE_SESSION_ID") or "")
PAYLOAD_READ_TIMEOUT = 0.5
PAYLOAD_READ_LIMIT = 1024 * 1024


def usage():
    sys.stderr.write("usage: executor-lease.sh renew [--task <id>] | alive --task <id> --session <id>\n")
    return 2


def parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def current_time():
    frozen = os.environ.get("HELMIT_EXECUTOR_LEASE_NOW")
    return parse_iso(frozen) if frozen and parse_iso(frozen) else datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ttl_seconds():
    try:
        return max(int(os.environ.get("HELMIT_EXECUTOR_LEASE_SECS", "900")), 0)
    except ValueError:
        return 900


def publish_dashboard():
    """Lease renewal refreshes the optional projection, never the hook."""
    dashboard = os.path.join(HOOKS, "dashboard.sh")
    try:
        subprocess.run(["bash", dashboard, "publish", "--project", ROOT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT), check=False)
    except OSError:
        pass


def open_claims():
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = ROOT
    try:
        result = subprocess.run(["bash", RUNLOG, "open-entry", "--all"],
                                capture_output=True, text=True, env=env)
    except OSError:
        return []
    if result.returncode != 0:
        return []
    claims = []
    for line in result.stdout.splitlines():
        try:
            claim = json.loads(line)
        except ValueError:
            continue
        if isinstance(claim, dict):
            claims.append(claim)
    return claims


def read_payload_data():
    decoder = codecs.getincrementaldecoder("utf-8")()
    parser = json.JSONDecoder()
    text = ""
    size = 0
    while size < PAYLOAD_READ_LIMIT:
        try:
            chunk = os.read(sys.stdin.fileno(), min(4096, PAYLOAD_READ_LIMIT - size))
            text += decoder.decode(chunk, final=not chunk)
        except (OSError, UnicodeDecodeError, ValueError):
            return {}
        if not chunk:
            return {}
        size += len(chunk)
        stripped = text.lstrip()
        try:
            payload, end = parser.raw_decode(stripped)
        except json.JSONDecodeError:
            continue
        if stripped[end:].strip():
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def payload_data():
    if sys.stdin.isatty():
        return {}
    try:
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "_payload-data"],
            stdin=sys.stdin, capture_output=True, text=True,
            timeout=PAYLOAD_READ_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    try:
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except ValueError:
        return {}


def resolve_task(requested, session):
    matches = []
    for claim in open_claims():
        if claim.get("session") != session:
            continue
        task = claim.get("task")
        if isinstance(task, str) and task and (not requested or task == requested):
            matches.append(task)
    return matches[0] if len(set(matches)) == 1 else ""


def renew(task, session):
    if not session or not os.path.isdir(os.path.join(ROOT, ".helmit")):
        return 0
    task = resolve_task(task, session)
    if not task:
        return 0
    try:
        with open(LOCK, encoding="utf-8") as handle:
            lock = json.load(handle)
    except (OSError, ValueError):
        return 0
    if not isinstance(lock, dict) or lock.get("session") != session:
        return 0
    try:
        beat = subprocess.run(["bash", LOCK_HOOK, "heartbeat", "--session", session],
                              cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
                              check=False)
    except OSError:
        return 0
    if beat.returncode != 0:
        return 0
    data = {"version": 1, "task": task, "session": session,
            "renewed_at": iso(current_time())}
    tmp = "%s.tmp.%d" % (LEASE, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, LEASE)
        publish_dashboard()
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return 0


def alive(task, session):
    try:
        with open(LEASE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return 1
    renewed = parse_iso(data.get("renewed_at")) if isinstance(data, dict) else None
    fresh = renewed is not None and 0 <= (current_time() - renewed).total_seconds() < ttl_seconds()
    return 0 if (fresh and data.get("task") == task and data.get("session") == session) else 1


def main(argv):
    if argv == ["_payload-data"]:
        sys.stdout.write(json.dumps(read_payload_data()))
        return 0
    if not argv or argv[0] not in ("renew", "alive"):
        return usage()
    command = argv[0]
    task = ""
    session = ""
    activity = False
    index = 1
    while index < len(argv):
        if command == "renew" and argv[index] == "--activity":
            activity = True
            index += 1
            continue
        if argv[index] not in ("--task", "--session") or index + 1 >= len(argv):
            return usage()
        if argv[index] == "--task":
            task = argv[index + 1]
        else:
            session = argv[index + 1]
        index += 2
    if command == "renew":
        if not ENVIRONMENT_SESSION and not os.path.isdir(os.path.join(ROOT, ".helmit")):
            return 0
        payload = payload_data() if activity or not ENVIRONMENT_SESSION else {}
        if activity:
            tool_input = payload.get("tool_input")
            command_text = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
            if not isinstance(command_text, str) or not command_text:
                return 0
            if "heartbeat.sh" in command_text or "heartbeat-owner.sh" in command_text:
                return 0
        payload_session = payload.get("session_id")
        session = ENVIRONMENT_SESSION or (payload_session if isinstance(payload_session, str) else "")
        return renew(task, session)
    if not task or not session:
        return usage()
    return alive(task, session)


sys.exit(main(sys.argv[1:]))
