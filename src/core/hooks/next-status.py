"""Deterministic, compact routing facts for HelmIt.

`show` is a pure query. It folds the versioned artifacts and the existing
read-only diagnostics once, so skills and presentation surfaces do not each
reimplement phase, CHG, or route selection. `repair-state` is deliberately a
separate, explicit mutation.
"""

import json
import os
import re
import subprocess
import sys
import tempfile


ROOT = os.path.abspath(os.environ.get("NS_ROOT") or os.getcwd())
HOOKS = os.environ.get("NS_HOOKS") or os.path.dirname(__file__)
HELMIT = os.path.join(ROOT, ".helmit")
CLOSED = {"shipped"}
PHASE_ID = re.compile(r"^[0-9][0-9A-Za-z]*$")
WORKFLOW = re.compile(
    r"^(setup-done|spec-app-draft|spec-app-approved|arch-draft|arch-approved|"
    r"env-ready|complete|spec-feature-draft:[0-9][0-9A-Za-z]*|"
    r"spec-feature-approved:[0-9][0-9A-Za-z]*|chart-draft:[0-9][0-9A-Za-z]*|"
    r"chart-approved:[0-9][0-9A-Za-z]*|implementing:[0-9][0-9A-Za-z]*\.[0-9]+|"
    r"implemented:[0-9][0-9A-Za-z]*|validated:[0-9][0-9A-Za-z]*|"
    r"validation-failed:[0-9][0-9A-Za-z]*|shipped:[0-9][0-9A-Za-z]*)$"
)
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
TASK = re.compile(r"^-\s+\[([ xX>])\]\s+([0-9A-Za-z._-]+\.[0-9]+)\b")


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            return stream.read()
    except OSError:
        return ""


def field(text, name):
    match = re.search(r"^\s*-?\s*%s:\s*(.*?)\s*$" % re.escape(name), text, re.M)
    return match.group(1).split("<!--", 1)[0].strip() if match else ""


def table_rows(text, minimum):
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip().replace("\\|", "|").replace("\\\\", "\\")
                 for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]
        if len(cells) < minimum:
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        rows.append(cells)
    return rows


def roadmap():
    phases = []
    for cells in table_rows(read(os.path.join(HELMIT, "ROADMAP.md")), 6):
        pid, name = cells[0], cells[1]
        if pid.lower() == "id" or not PHASE_ID.fullmatch(pid):
            continue
        raw_requires = cells[-3]
        requires = [] if raw_requires.lower() in ("", "none", "-") else [
            item.strip() for item in raw_requires.split(",") if item.strip()
        ]
        phases.append({
            "id": pid,
            "name": name,
            "requires": requires,
            "status": cells[-1].lower(),
        })
    return phases


def eligible_phase(phases):
    statuses = {phase["id"]: phase["status"] for phase in phases}
    open_rows = [phase for phase in phases if phase["status"] not in CLOSED]
    for phase in open_rows:
        if all(statuses.get(required) in CLOSED for required in phase["requires"]):
            return phase, []
    blocked = []
    for phase in open_rows:
        missing = [req for req in phase["requires"] if statuses.get(req) not in CLOSED]
        if missing:
            blocked.append("%s requires %s" % (phase["id"], ",".join(missing)))
    return None, blocked


def phase_artifact_workflow(phase):
    """Best position directly proved by the eligible phase artifacts."""
    if not phase:
        return "complete"
    pid = phase["id"]
    base = os.path.join(HELMIT, "phases", pid)
    spec = read(os.path.join(base, "SPEC.md"))
    chart = HTML_COMMENT.sub("", read(os.path.join(base, "CHART.md")))
    validation = HTML_COMMENT.sub("", read(os.path.join(base, "VALIDATION.md")))
    result = field(validation, "result")
    if result == "failed":
        return "validation-failed:%s" % pid
    if phase["status"] == "validated" or result in ("passed", "passed-with-human-items"):
        return "validated:%s" % pid
    tasks = []
    for line in chart.splitlines():
        match = TASK.match(line.strip())
        if match:
            tasks.append((match.group(1), match.group(2)))
    if tasks:
        open_tasks = [task for mark, task in tasks if mark not in ("x", "X")]
        if not open_tasks:
            return "implemented:%s" % pid
        if any(mark in ("x", "X", ">") for mark, _task in tasks):
            return "implementing:%s" % open_tasks[0]
        return "chart-approved:%s" % pid if field(chart, "status") == "approved" else "chart-draft:%s" % pid
    if chart:
        return "chart-approved:%s" % pid if field(chart, "status") == "approved" else "chart-draft:%s" % pid
    if spec:
        return "spec-feature-approved:%s" % pid if field(spec, "status") == "approved" else "spec-feature-draft:%s" % pid
    return "env-ready"


def state_workflow():
    value = field(read(os.path.join(HELMIT, "STATE.md")), "workflow")
    return value if WORKFLOW.fullmatch(value) else ""


def phase_of(workflow):
    if ":" not in workflow:
        return ""
    value = workflow.split(":", 1)[1]
    return value.split(".", 1)[0]


def effective_workflow(raw, derived, eligible, dependency_blocks=None):
    """Trust a valid intra-phase STATE value only for the eligible phase.

    Artifacts win when STATE is missing, malformed, points at another phase, or
    claims completion while work remains. The query reports the repair but does
    not write it.
    """
    if not raw:
        return derived, "STATE workflow missing or invalid"
    pid = eligible["id"] if eligible else ""
    raw_pid = phase_of(raw)
    if raw == "complete" and eligible:
        return derived, "STATE says complete while ROADMAP has eligible work"
    if raw_pid and pid and raw_pid != pid:
        return derived, "STATE phase %s differs from eligible phase %s" % (raw_pid, pid)
    if eligible and raw == "env-ready" and phase_of(derived):
        return derived, "STATE is at the delivery boundary but phase %s already has progress" % pid
    if raw_pid and pid and raw_pid == pid and phase_of(derived) == pid and raw != derived:
        return derived, "STATE workflow %s differs from artifact position %s" % (raw, derived)
    if not eligible and not dependency_blocks and phase_of(raw):
        return "complete", "STATE has an active position after ROADMAP completion"
    return raw, "none"


ROUTES = {
    "setup-done": ("spec-product", ".helmit/SPEC.md", "product commitment", "approved product spec", "product commitment is approved"),
    "spec-app-draft": ("decide-product", ".helmit/SPEC.md", "material product decision", "explicit authority", "the pending decision is recorded"),
    "spec-app-approved": ("prepare", ".helmit/KEEL.md", "preparation", "architecture and command checks", "the project is ready to execute"),
    "arch-draft": ("decide-architecture", ".helmit/KEEL.md", "material architecture decision", "explicit authority", "the pending decision is recorded"),
    "arch-approved": ("env", ".helmit/KEEL.md", "environment check", "configured command availability", "the environment is ready"),
    "env-ready": ("spec-delivery", ".helmit/phases/<phase>/SPEC.md", "delivery commitment", "approved delivery spec", "the delivery commitment is approved"),
    "spec-feature-draft": ("decide-delivery", ".helmit/phases/<phase>/SPEC.md", "material delivery decision", "explicit authority", "the pending decision is recorded"),
    "spec-feature-approved": ("implement", ".helmit/phases/<phase>/CHART.md", "plan and implement", "focused checks and logical commits", "all promised outcomes are implemented"),
    "chart-draft": ("implement", ".helmit/phases/<phase>/CHART.md", "adapt plan and implement", "focused checks and logical commits", "all promised outcomes are implemented"),
    "chart-approved": ("implement", ".helmit/phases/<phase>/CHART.md", "implement", "focused checks and logical commits", "all promised outcomes are implemented"),
    "implementing": ("implement", ".helmit/phases/<phase>/CHART.md", "resume implementation", "focused checks and logical commits", "all promised outcomes are implemented"),
    "implemented": ("ship", ".helmit/phases/<phase>/VALIDATION.md", "final proof and delivery", "configured full suite and REQ proof", "the delivery milestone closes"),
    "validated": ("ship", ".helmit/phases/<phase>/VALIDATION.md", "delivery closure", "exact reusable quality receipt", "the delivery milestone closes"),
    "validation-failed": ("repair", ".helmit/phases/<phase>/VALIDATION.md", "diagnose and repair", "failed proof rerun", "the named failure is green"),
    "shipped": ("spec-delivery", ".helmit/phases/<next>/SPEC.md", "next delivery commitment", "approved delivery spec", "the next commitment is approved"),
    "complete": ("complete", ".helmit/ROADMAP.md", "none", "all deliveries shipped", "new work is authorized"),
}


def route_for(workflow, phase):
    key = workflow.split(":", 1)[0]
    route, artifact, ceremony, proof, advance = ROUTES.get(
        key, ("diagnose", ".helmit/STATE.md", "state diagnosis", "unambiguous artifact facts", "the position is unambiguous")
    )
    pid = phase["id"] if phase else "<new>"
    artifact = artifact.replace("<phase>", pid).replace("<next>", pid)
    return route, artifact, ceremony, proof, advance


def run_hook(name, *args):
    path = os.path.join(HOOKS, name)
    if not os.path.isfile(path):
        return ""
    try:
        proc = subprocess.run(
            ["bash", path] + list(args), cwd=ROOT,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        return proc.stdout.strip()
    except Exception as exc:
        return "%s unavailable: %s" % (name, exc)


def first_line(text, fallback):
    return text.splitlines()[0].strip() if text.strip() else fallback


def compact_preflight(text):
    line = first_line(text, "READY")
    if not line.startswith("CHANGED"):
        return line
    rest = line[len("CHANGED"):].lstrip()
    decoder = json.JSONDecoder()
    paths = 0
    while rest:
        try:
            _value, end = decoder.raw_decode(rest)
        except ValueError:
            return "CHANGED"
        paths += 1
        rest = rest[end:].lstrip()
    return "CHANGED (%d path%s)" % (paths, "" if paths == 1 else "s")


def changes():
    open_changes = []
    for cells in table_rows(read(os.path.join(HELMIT, "CHANGES.md")), 9):
        if re.fullmatch(r"CHG-[0-9]+", cells[0]) and cells[-1].lower() == "open":
            open_changes.append({"id": cells[0], "task": cells[4], "intent": cells[3]})
    return open_changes


def legacy_corrections():
    routes = {}
    for cells in table_rows(read(os.path.join(HELMIT, "REQUIREMENTS.md")), 4):
        rid, phase, status = cells[0], cells[-2], cells[-1].lower()
        if phase.startswith("corr:") and status == "todo":
            routes.setdefault(phase, []).append(rid)
    return [{"route": route, "requirements": ids} for route, ids in routes.items()]


def inbox_counts():
    text = read(os.path.join(HELMIT, "INBOX.md"))
    section = ""
    counts = {"open": 0, "unrouted": 0, "routed": 0, "backlog": 0}
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if not line.startswith("- [ ] "):
            continue
        if section == "inbox":
            counts["open"] += 1
            if "[TRIADO ->" in line:
                counts["routed"] += 1
            else:
                counts["unrouted"] += 1
        elif section == "backlog":
            counts["backlog"] += 1
    return counts


def pending_decision():
    state = read(os.path.join(HELMIT, "STATE.md"))
    match = re.search(r"^## Decisions still needed\s*$([\s\S]*?)(?=^## |\Z)", state, re.M)
    if match:
        for line in match.group(1).splitlines():
            item = re.match(r"^\s*-\s+(.+)$", line)
            if item and item.group(1).strip().lower() != "none":
                return item.group(1).strip()
    return "none"


def remote_sync_status():
    raw = run_hook("remote-status.sh", "show")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return {
        "available": value.get("available") is True,
        "branch": value.get("branch") if isinstance(value.get("branch"), str) else "",
        "upstream": value.get("upstream") if isinstance(value.get("upstream"), str) else "",
        "head": value.get("head") if isinstance(value.get("head"), str) else "",
        "ahead": value.get("ahead") if isinstance(value.get("ahead"), int) else 0,
        "behind": value.get("behind") if isinstance(value.get("behind"), int) else 0,
        "oldest_local_commit": value.get("oldest_local_commit")
        if isinstance(value.get("oldest_local_commit"), str) else "",
        "tracking": "local-ref",
        "network_refreshed": False,
        "reason": value.get("reason") if isinstance(value.get("reason"), str) else "unavailable",
    }


def snapshot(diagnostics=True):
    phases = roadmap()
    phase, blocked = eligible_phase(phases)
    derived = phase_artifact_workflow(phase)
    raw = state_workflow()
    workflow, repair = effective_workflow(raw, derived, phase, blocked)
    reconciliation = "not checked"
    preflight = "not checked"
    lock = "not checked"
    mandate = "not checked"
    drift_lines = []
    if diagnostics:
        reconciliation = first_line(run_hook("reconcile.sh", "decide"), "FORWARD")
        preflight = compact_preflight(run_hook("preflight.sh", "check"))
        lock = first_line(run_hook("lock.sh", "status"), "lock: unavailable")
        mandate = first_line(run_hook("yolo.sh", "status"), "yolo: off")
        drift_lines = [line for line in run_hook("spec-sync.sh", "check").splitlines() if line.strip()]
    sanity = first_line(run_hook("sanity.sh", "summary"), "clean") if diagnostics else "not checked"
    changes_open = changes()
    inbox = inbox_counts()
    remote_sync = remote_sync_status()
    route, artifact, ceremony, proof, advance = route_for(workflow, phase)
    active_change = changes_open[0] if changes_open else None
    if active_change:
        route = "implement"
        artifact = ".helmit/CHANGES.md"
        ceremony = "resume localized correction"
        proof = "declared focused CHG verify and staged quick floor"
        advance = "the CHG closes in its useful commit"

    verdict = "READY"
    stop_reason = "none"
    if diagnostics and reconciliation.startswith(("UNKNOWN_LOCK", "RECONCILE_DIRTY", "RECONCILE_CLEAN", "HALTED:")):
        verdict, stop_reason = "PAUSE", reconciliation
    elif diagnostics and preflight == "BLOCKED_CONCURRENT":
        verdict, stop_reason = "PAUSE", preflight
    elif route in ("decide-product", "decide-architecture", "decide-delivery"):
        verdict, stop_reason = "DECISION", pending_decision()
    elif blocked and not phase and not active_change:
        verdict, stop_reason = "BLOCKED", "; ".join(blocked)
    elif route == "repair":
        verdict, stop_reason = "PROOF_FAILED", artifact

    position = "complete"
    if active_change:
        position = "%s (%s) — %s" % (
            active_change["id"], active_change["task"], active_change["intent"]
        )
    elif phase:
        position = "phase %s (%s), roadmap=%s" % (phase["id"], phase["name"], phase["status"])
    elif blocked:
        position = "roadmap blocked"

    return {
        "schema": 1,
        "verdict": verdict,
        "position": position,
        "workflow": workflow,
        "workflow_source": "STATE" if workflow == raw and raw else "artifacts",
        "phase": phase["id"] if phase else "",
        "route": route,
        "artifact": artifact,
        "ceremony": ceremony,
        "pending_decision": pending_decision(),
        "proof": proof,
        "advance_when": advance,
        "stop_reason": stop_reason,
        "lock": lock,
        "preflight": preflight,
        "mandate": mandate,
        "drift": drift_lines,
        "reconciliation": reconciliation,
        "repair": repair,
        "sanity": sanity,
        "open_changes": changes_open,
        "legacy_corrections": legacy_corrections(),
        "inbox": inbox,
        "dependency_blocks": blocked,
        "remote_sync": remote_sync,
    }


def show_human(data):
    print("verdict: %s" % data["verdict"])
    print("position: %s" % data["position"])
    print("workflow: %s (%s)" % (data["workflow"], data["workflow_source"]))
    print("route: %s" % data["route"])
    print("artifact: %s" % data["artifact"])
    print("pending decision: %s" % data["pending_decision"])
    print("proof: %s" % data["proof"])
    print("advance when: %s" % data["advance_when"])
    print("safety: %s; %s; %s; %s" % (
        data["reconciliation"], data["preflight"], data["lock"], data["mandate"]
    ))
    if data["sanity"] != "clean":
        print("structure: %s (run sanity.sh check for exact lines)" % data["sanity"])
    if data["repair"] != "none":
        print("repair available: %s (run next-status.sh repair-state explicitly)" % data["repair"])
    if data["open_changes"]:
        print("open CHG: %s" % ", ".join(item["id"] for item in data["open_changes"]))
    if data["drift"]:
        print("advisory drift: %d source(s); inspect only if relevant to this delivery" % len(data["drift"]))
    remote = data["remote_sync"]
    if remote["available"] and (remote["ahead"] or remote["behind"]):
        oldest = ("; oldest local-only=%s" % remote["oldest_local_commit"]
                  if remote["oldest_local_commit"] else "")
        print("remote sync: %s vs %s; ahead=%d behind=%d%s; local tracking ref, not network-refreshed" % (
            remote["branch"], remote["upstream"], remote["ahead"], remote["behind"], oldest
        ))
    elif not remote["available"] and remote["reason"] in ("no-upstream", "unreadable-upstream"):
        print("remote sync: %s; no upstream comparison is available" % remote["reason"])
    counts = data["inbox"]
    if counts["open"] or counts["backlog"]:
        print("inbox: open=%d unrouted=%d routed=%d backlog=%d" % (
            counts["open"], counts["unrouted"], counts["routed"], counts["backlog"]
        ))


def repair_state(data):
    if data["preflight"] == "BLOCKED_CONCURRENT" or data["reconciliation"].startswith("UNKNOWN_LOCK"):
        print("next-status: repair refused — %s" % data["stop_reason"])
        raise SystemExit(1)
    if data["repair"] == "none":
        print("next-status: STATE already agrees with derived artifacts")
        return
    path = os.path.join(HELMIT, "STATE.md")
    text = read(path)
    if not text:
        print("next-status: cannot repair missing STATE.md; run /helmit:env")
        raise SystemExit(1)
    pattern = re.compile(r"^(\s*-?\s*workflow:)\s*.*$", re.M)
    if pattern.search(text):
        updated = pattern.sub(r"\1 %s" % data["workflow"], text, count=1)
    else:
        heading = re.search(r"^## (?:Position|Workflow position)\s*$", text, re.M)
        if not heading:
            print("next-status: STATE has no position section; run /helmit:env")
            raise SystemExit(1)
        end = text.find("\n", heading.end())
        updated = text[: end + 1] + "- workflow: %s\n" % data["workflow"] + text[end + 1 :]
    fd, temp = tempfile.mkstemp(prefix=".STATE.md.", dir=HELMIT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    print("next-status: STATE workflow repaired to %s" % data["workflow"])


def main():
    if not os.path.isdir(HELMIT):
        print("next-status: no .helmit/ — run /helmit:setup")
        return
    args = sys.argv[1:]
    command = args[0] if args and not args[0].startswith("-") else "show"
    data = snapshot(diagnostics=command != "facts")
    if command == "repair-state":
        repair_state(data)
    elif command in ("show", "facts"):
        if "--json" in args:
            print(json.dumps(data, ensure_ascii=False, sort_keys=True))
        else:
            show_human(data)
    else:
        print("usage: next-status.sh [show [--json] | facts [--json] | repair-state]", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
