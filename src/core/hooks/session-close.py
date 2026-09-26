import os
import re
import subprocess
import sys


root = os.environ.get("SC_ROOT") or os.getcwd()
hooks = os.environ.get("SC_DIR") or os.path.dirname(__file__)

if len(sys.argv) != 2 or sys.argv[1] not in ("clean", "gate", "awaiting_input"):
    print("usage: session-close.sh {clean | gate | awaiting_input}", file=sys.stderr)
    raise SystemExit(2)

reason = sys.argv[1]
run_log = os.path.join(hooks, "run-log.sh")
if os.path.isfile(run_log):
    stopped = subprocess.run(
        ["bash", run_log, "append", "session_stop", "reason=" + reason],
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root),
    )
    if stopped.returncode:
        raise SystemExit(stopped.returncode)

if reason != "clean":
    raise SystemExit(0)

try:
    state = open(
        os.path.join(root, ".helmit", "STATE.md"),
        encoding="utf-8",
        errors="replace",
    ).read()
except OSError:
    state = ""
match = re.search(r"(?m)^\s*-?\s*workflow:\s*(.+?)\s*$", state)
workflow = match.group(1) if match else "unknown"
narrative = "Current STATE workflow: %s\n" % workflow

handoff = os.path.join(hooks, "handoff.sh")
if os.path.isfile(handoff):
    written = subprocess.run(
        ["bash", handoff, "write", "--if-session-end"],
        input=narrative,
        text=True,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root),
    )
    raise SystemExit(written.returncode)
