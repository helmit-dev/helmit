import os
import shutil
import subprocess
import sys


def forward(message):
    print("FORWARD")
    print(message)
    raise SystemExit(0)


def usage():
    print("uso: reconcile.sh decide [--project <path>] [--unattended]", file=sys.stderr)
    raise SystemExit(2)

args = sys.argv[1:]
if not args or args.pop(0) != "decide": usage()
root = os.environ.get("RC_ROOT") or os.getcwd()
unattended = "0"
while args:
    flag = args.pop(0)
    if flag == "--project" and args: root = args.pop(0)
    elif flag == "--unattended": unattended = "1"
    else: usage()
if not shutil.which("git"): forward("git missing — no working tree to inspect (fail-open)")
if not os.path.isfile(os.path.join(root, ".helmit", "run.jsonl")): forward("sem .helmit/run.jsonl em %s — nada em voo registrado (fail-open)" % root)
if subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
    forward("%s is not inside a git repo — no tree to inspect (fail-open)" % root)
runlog = os.path.join(os.environ.get("RC_HOOKS", ""), "run-log.sh")
def read(mode):
    try:
        return subprocess.check_output(["bash", runlog] + mode, env=dict(os.environ, CLAUDE_PROJECT_DIR=root), stderr=subprocess.DEVNULL, text=True)
    except Exception: return ""
os.environ["RC_ROOT"] = root
os.environ["RC_LAST"] = read(["last"])
os.environ["RC_OPEN"] = read(["open-entry", "--all"])
os.environ["RC_UNATTENDED"] = unattended

import json, os, re, subprocess, sys

# REQ-090: HONEST stops. `interrupted` is deliberately absent — it is the
# morte, e morte se reconcilia.
HONEST = ("gate", "awaiting_input", "clean")


def load(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None  # reading never breaks
    return obj if isinstance(obj, dict) else None


def load_all(raw):
    """One JSON object per line (run-log.sh open-entry --all). A line the reader
    cannot parse is dropped, never fatal: reading never breaks."""
    return [c for c in (load(ln) for ln in (raw or "").splitlines()) if c]


def out(verdict, lines):
    print(verdict)
    for line in lines:
        print(line)
    sys.exit(0)


def natural(text):
    """Sort key reading 3b.5 < 3b.6 < 3b.7 < 14.1: digit runs compare as numbers,
    so the printed order follows the task ids and not the order the wave happened
    to write its claims in."""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p)
                 for p in re.findall("[0-9]+|[^0-9]+", text))


root = os.environ["RC_ROOT"]
last = load(os.environ.get("RC_LAST"))
claims = load_all(os.environ.get("RC_OPEN"))

# 1) The typed stop decides BEFORE any look at the tree: a session that stopped
#    at a human gate may well have left the tree dirty on purpose, and
#    reconciling that would be crossing the gate.
#
#    With ONE distinction, and it is the whole of REQ-190: an honest stop with
#    NOTHING IN FLIGHT is not a gate to cross, it is yesterday ending well. The
#    old verdict made a NEW session refuse to route after every clean session
#    end — the most common and most desirable case — which is exactly the
#    scenario ("new session, user lost") /next exists to serve. Measured on two
#    consecutive days: shipped:19 on 04/08, shipped:20 on 05/08, the user paying
#    an extra turn each time to ask for the step by hand.
#
#    UNATTENDED resumption keeps the old, strict answer, always: the target of
#    REQ-090 is the machine that resumes by itself at 3am, never the human who
#    just opened a terminal. A gate is crossed by acting on it, and a person
#    reading a report is not the machine acting.
if last and last.get("event") == "session_stop" and last.get("reason") in HONEST:
    unattended = os.environ.get("RC_UNATTENDED") == "1"
    if unattended or claims:
        why = ("and a task is still OPEN in the log: the stop happened mid-work, "
               "so crossing it would resume work a human parked on purpose."
               if claims else
               "and this is an UNATTENDED resume: a machine may never cross an "
               "honest stop, whatever is or is not in flight (REQ-090).")
        out("HALTED:%s" % last.get("reason"), [
            "stopped at: %s (pid %s)" % (last.get("ts", "?"), last.get("pid", "?")),
            "honest stop, not a crash: REPORT it and stop — do NOT reconcile and do",
            "NOT resume across it. Only a missing session_stop (i.e. `interrupted`)",
            "is auto-resumable.",
            why,
        ])
    out("FORWARD", [
        "the previous session stopped honestly at %s (reason: %s) and left NOTHING"
        % (last.get("ts", "?"), last.get("reason")),
        "in flight — no open task_claimed. Report the stop and route normally",
        "(REQ-190). An unattended resume would still refuse here: it passes",
        "--unattended and gets HALTED.",
    ])

# 2) With no open entry there is nothing in flight — including when the last
#    line is `session_stop{interrupted}` but every task had already been committed.
if not claims:
    out("FORWARD", ["no open task_claimed in the run log — route normally."])

claims.sort(key=lambda c: (natural(str(c.get("task") or "")), str(c.get("ts") or "")))


def files_of(claim):
    return [f.strip() for f in str(claim.get("files") or "").split(",") if f.strip()]


def scope_of(files):
    return ("task files: %s" % ", ".join(files)) if files \
        else "whole tree except .helmit/ (the claim declared no files=)"


def title_of(claim):
    return "task: %s (claimed at %s, pid %s)" % (
        claim.get("task") or "<unnamed>", claim.get("ts") or "?", claim.get("pid", "?"))


# 3) The TREE is what separates "died mid-work" from "died before producing" —
#    and, with more than one claim in flight, WHOSE work each dirty path is. The
#    matching is delegated to git per claim (its own pathspec rules decide what
#    a declared path covers), never re-implemented here.
#    -z because a filename with a space/accent/quote cannot move the verdict.
def dirty_of(files):
    """Dirty paths inside one claim scope, or None when git could not answer."""
    cmd = ["git", "-C", root, "status", "--porcelain", "-z"]
    if files:
        cmd.append("--")
        cmd.extend(files)
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw = proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None
    except Exception:
        raw = None
    if raw is None:
        return None

    found = []
    parts = raw.split("\0")
    i = 0
    while i < len(parts):
        rec = parts[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, path = rec[:2], rec[3:]
        if "R" in xy or "C" in xy:
            i += 1  # rename/copy: the ORIGIN path comes in the next field
        found.append((xy, path))

    if not files:
        # With no declared files=, the whole tree counts — minus the harness's own
        # bookkeeping, which moves by itself and would taint every verdict.
        # (git collapses a whole untracked directory into "?? .helmit/", with or
        #  without the trailing slash depending on the version — both forms match)
        found = [(xy, p) for xy, p in found
                 if not (p.startswith(".helmit/") or p.rstrip("/") == ".helmit")]
    return found


scoped = []
for claim in claims:
    claim_files = files_of(claim)
    claim_dirty = dirty_of(claim_files)
    if claim_dirty is None:
        out("FORWARD", ["git status failed — nothing safe to conclude (fail-open)."])
    scoped.append((claim, claim_files, claim_dirty))

# 4) Keep the verdict and task/scope fields stable for callers.
if len(scoped) == 1:
    claim, files, dirty = scoped[0]
    task = claim.get("task") or "<unnamed>"
    head = [title_of(claim), "scope: %s" % scope_of(files)]
    if dirty:
        out("RECONCILE_DIRTY", head
            + ["dirty (%d):" % len(dirty)]
            + ["  %s %s" % (xy, p) for xy, p in dirty]
            + ["action: inspect and finish or repair the PARTIAL work for task %s." % task,
               "        Preserve staged/unstaged edits and untracked files on failure.",
               "        Verify task completion under the current commit policy;",
               "        a green check alone does not prove the task complete.",
               "do NOT route forward to the next step."])
    out("RECONCILE_CLEAN", head + [
        "dirty (0): nothing partial survived in the task's scope.",
        "action: check for an already-landed commit before re-running missing work",
        "        for task %s; an empty diff alone does not prove nothing was done." % task,
        "do NOT route forward to the next step.",
    ])

# 5) A wave: ONE line per claim, in task-id order, each carrying only the paths
#    ITS OWN files= declared. Naming a single task here would hand one task
#    partial work to another task commit message (REQ-232).
context = ["open claims: %d — each dirty path below belongs to the claim whose "
           "files= DECLARED it" % len(scoped)]
for claim, files, dirty in scoped:
    detail = ", ".join("%s %s" % (xy, p) for xy, p in dirty)
    context.append("%s | scope: %s | dirty (%d)%s" % (
        title_of(claim), scope_of(files), len(dirty), (": " + detail) if dirty else ""))

if any(dirty for _, _, dirty in scoped):
    out("RECONCILE_DIRTY", context + [
        "action: inspect and finish or repair each PARTIAL task independently.",
        "        Preserve staged/unstaged edits and untracked files on failure.",
        "        Verify task completion under the current commit policy, then commit",
        "        each completed claim under its own task identity.",
        "        For dirty (0), check for a landed commit before repeating work.",
        "do NOT route forward to the next step.",
    ])

out("RECONCILE_CLEAN", context + [
    "action: no partial diff remains in any claim scope — check for landed commits",
    "        before re-running missing work for each task above.",
    "do NOT route forward to the next step.",
])
