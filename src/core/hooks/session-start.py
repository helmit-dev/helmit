import os
import subprocess

root = os.environ.get("HS_ROOT") or os.getcwd()
hooks = os.environ.get("HS_DIR") or os.path.dirname(__file__)
def read_hook(name, args):
    try:
        return subprocess.check_output(["bash", os.path.join(hooks, name)] + args, env=dict(os.environ, CLAUDE_PROJECT_DIR=root), stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return ""
os.environ["HS_RENDER"] = read_hook("handoff.sh", ["render"])
os.environ["HS_ENV"] = read_hook("env-check.sh", ["check"]) if os.path.isfile(os.path.join(hooks, "env-check.sh")) else ""
os.environ["HS_YOLO"] = read_hook("yolo.sh", ["status"]) if os.path.isfile(os.path.join(root, ".helmit", "yolo.json")) else ""
os.environ["HS_DASH"] = read_hook("dashboard.sh", ["ensure", "--project", root])

import json, os, re, sys

render = os.environ.get("HS_RENDER", "")


def mandate_notice():
    """The REQ-160 re-arm instruction, or the empty string, derived from the
    ONE line `yolo.sh status` answered (REQ-290). Everything this hook needs is
    in it: whether the mandate is in force — status runs fulfilled() itself and
    reports a spent one as FULFILLED — plus the scope, the stopping point and
    the unattended flag. A fulfilled or expired mandate gets NO instruction:
    the next reap collects it, and instructing a re-arm for a dead mandate
    would be the born-fulfilled defect (REQ-156) back through the window.
    Anything unreadable means no instruction: fail open, fall back to
    silence."""
    line = os.environ.get("HS_YOLO", "").strip()
    m = re.match(r"^yolo: (phase|full) in force\b", line)
    if not m:
        return ""
    if "unattended=yes" not in line:
        return ""
    stop = re.search(r"stops at (\S+)", line)
    return ("HelmIt mandate in force (scope %s, stops at %s, unattended): "
            "the session guardian died with the previous session — re-arm "
            "it now with /helmit:heartbeat on and declare it (REQ-160)."
            % (m.group(1), stop.group(1) if stop else "none"))


notice = mandate_notice()
env_lines = os.environ.get("HS_ENV", "").strip()
dashboard_line = os.environ.get("HS_DASH", "").strip()
dashboard_problem = dashboard_line if "could not render" in dashboard_line else ""

# The fixed core render ALWAYS prints; anything beyond it is real pendency.
# An unattended mandate in force is real pendency too (REQ-160): the session
# has no guardian, and that must be heard even over an otherwise clean tree.
# So is env-check staleness (REQ-207): artifacts the plugin update never
# touches aged, and only this trigger can say so without a human remembering.
CORE = re.compile(r"^(position|workflow|last stop):")
if not notice and not env_lines and not dashboard_problem \
        and not any(l.strip() and not CORE.match(l)
                    for l in render.split("\n")):
    sys.exit(0)  # only the fixed core: silence is the contract (REQ-108)

context = "HelmIt handoff (previous session):\n" + render
if env_lines:
    context += ("\n\nHelmIt environment pendencies (env-check):\n"
                + env_lines)
if notice:
    context += "\n\n" + notice
if dashboard_problem:
    context += "\n\nHelmIt dashboard projection: " + dashboard_problem

print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": context,
}}))
