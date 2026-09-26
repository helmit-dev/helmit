"""One atomic, checkout-local activity record per host session.

This is weaker evidence than a task claim: it never changes STATE, lock, lease,
or the WAL. The dashboard uses a hashed identity only for local correlation.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


ROOT = os.path.realpath(os.environ.get("SA_ROOT") or os.getcwd())
HELMIT = os.path.join(ROOT, ".helmit")
HOOKS = os.environ.get("SA_HOOKS") or os.path.dirname(os.path.abspath(__file__))
ENV_SESSION = (os.environ.get("HELMIT_SESSION_ID") or
               os.environ.get("CLAUDE_CODE_SESSION_ID") or
               os.environ.get("CODEX_THREAD_ID") or
               os.environ.get("CODEX_SESSION_ID") or
               os.environ.get("CLAUDE_SESSION_ID") or "")


def payload():
    if sys.stdin.isatty():
        return {}
    try:
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "_payload"],
            stdin=sys.stdin, capture_output=True, text=True, timeout=0.5,
        )
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def read_payload():
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


def valid_session(value):
    return (isinstance(value, str) and 0 < len(value) <= 256 and
            all(32 <= ord(char) < 127 for char in value))


def relevant_command(value):
    if not isinstance(value, str) or not value.strip():
        return False
    # Hooks, dashboard refreshes and recovery probes are not agent activity.
    return not any(token in value for token in (
        "session-activity.sh", "heartbeat.sh", "heartbeat-owner.sh",
        "dashboard.sh", "run-log.sh append awaiting_input",
        "session-close.sh awaiting_input",
    ))


def publish():
    try:
        subprocess.run(["bash", os.path.join(HOOKS, "dashboard.sh"),
                        "publish", "--project", ROOT],
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def record(mode):
    if not os.path.isdir(HELMIT):
        return
    data = payload()
    session = ENV_SESSION or data.get("session_id", "")
    if not valid_session(session):
        return
    if mode == "bash":
        tool = data.get("tool_input")
        command = tool.get("command") if isinstance(tool, dict) else None
        if not relevant_command(command):
            return
    activity_dir = os.path.join(HELMIT, "session-activity")
    if os.path.islink(activity_dir):
        return
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record_data = {"version": 1, "session_hash": digest,
                   "observed_at": now, "source": mode}
    try:
        os.makedirs(activity_dir, exist_ok=True)
        target = os.path.join(activity_dir, digest + ".json")
        tmp = target + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(record_data, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except (OSError, UnboundLocalError):
            pass
        return
    publish()


if __name__ == "__main__":
    if sys.argv[1:] == ["_payload"]:
        sys.stdout.write(json.dumps(read_payload()))
    elif len(sys.argv) == 2 and sys.argv[1] in ("start", "edit", "bash"):
        record(sys.argv[1])
    else:
        raise SystemExit("usage: session-activity.sh {start|edit|bash}")
