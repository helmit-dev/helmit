import json, os, re, subprocess, sys
from datetime import datetime, timezone

# This hook is absolutely fail-open. Keep every operational failure below as a
# quiet success: token accounting is an aid, never a gate.
try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
if not isinstance(payload, dict):
    payload = {}

def jget(*keys):
    value = payload
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, str) else ""

event, session, transcript = (jget("hook_event_name"), jget("session_id"),
                              jget("transcript_path"))
if not event or not transcript:
    sys.exit(0)
project = os.environ.get("CLAUDE_PROJECT_DIR") or jget("cwd") or os.getcwd()
if not os.path.isdir(os.path.join(project, ".helmit")):
    sys.exit(0)

msg = ""
if event == "PostToolUse":
    source = "hook"
    command = jget("tool_input", "command")
    commit = (r"(^|[;&|\s(])git(\s+-[^\s]+(\s+[^\s]+)?)*\s+commit(\s|$)")
    if not re.search(commit, command):
        sys.exit(0)
    try:
        msg = subprocess.check_output(["git", "-C", project, "log", "-1", "--format=%s"],
                                      stderr=subprocess.DEVNULL, text=True).rstrip("\n")
    except Exception:
        sys.exit(0)
    if not msg:
        sys.exit(0)
elif event == "Stop":
    source = "stop"
else:
    sys.exit(0)

body_dir = os.environ.get("METRICS_COLLECT_DIR", os.path.dirname(__file__))
metrics_sh = os.path.join(body_dir, "metrics.sh")
if not os.path.isfile(metrics_sh):
    sys.exit(0)
mfile = os.path.join(project, ".helmit", "metrics.jsonl")
cursor = ""
try:
    with open(mfile, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("session") == session and row.get("cursor"):
                cursor = row["cursor"]
except OSError:
    pass

cmd = ["bash", metrics_sh, "scan", transcript]
if cursor:
    cmd.extend(["--since-cursor", cursor])
try:
    scan = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
except Exception:
    sys.exit(0)
if not scan:
    sys.exit(0)
try:
    res = json.loads(scan)
    assert isinstance(res, dict)
except Exception:
    sys.exit(0)

def toint(v):
    try:
        return int(v)
    except Exception:
        return 0


def phase_id(raw):
    """Numeric phase ids keep their int type, alphanumeric ones stay strings
    (REQ-151) — the same typing the aggregate filters by."""
    return int(raw) if raw.isdigit() else raw


def open_session_task(path, wanted_session):
    """Return the sole open task claim owned by this exact session."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    claims = {}
    for raw in lines:
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        task_id = row.get("task")
        if row.get("event") == "task_claimed" and isinstance(task_id, str):
            claims[task_id] = row
        elif row.get("event") == "task_committed" and isinstance(task_id, str):
            claims.pop(task_id, None)
        elif row.get("event") == "session_stop" and row.get("reason") == "clean":
            stopped = row.get("session")
            if isinstance(stopped, str) and stopped:
                claims = {key: value for key, value in claims.items()
                          if value.get("session") != stopped}
    matches = [task_id for task_id, claim in claims.items()
               if claim.get("session") == wanted_session]
    return matches[0] if len(matches) == 1 else None


def attribution(task_id):
    if not task_id:
        return None, None, None
    chg = re.fullmatch(r"(CHG-[0-9]{3,})\.[0-9]+", task_id)
    if chg:
        return "change", chg.group(1), None
    delivery = re.fullmatch(r"([0-9][0-9A-Za-z]*)\.([0-9]+)", task_id)
    if delivery:
        pid = phase_id(delivery.group(1))
        return "delivery", "phase:%s" % delivery.group(1), pid
    return None, None, None


fields = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
totals = {k: toint(res.get(k)) for k in fields}
if not any(totals.values()):
    sys.exit(0)  # nothing new since the last cursor: no line

# Per-model breakdown (REQ-167), normalized here so a malformed scan can never
# put anything but {model id: {4 int fields}} on the durable line.
models = {}
raw_models = res.get("models")
if isinstance(raw_models, dict):
    for name, bucket in raw_models.items():
        if isinstance(name, str) and name and isinstance(bucket, dict):
            models[name] = {k: toint(bucket.get(k)) for k in fields}

# Window-variant dimension (REQ-228), normalized like `models` so a malformed
# scan can never put anything but {base id: [variant, ...]} on the line.
variants = {}
raw_variants = res.get("model_variants")
if isinstance(raw_variants, dict):
    for base, seen in raw_variants.items():
        if isinstance(base, str) and base and isinstance(seen, list):
            found = sorted({v for v in seen if isinstance(v, str) and v})
            if found:
                variants[base] = found

# Per-subagent facts and the cross-check of the second source (REQ-227),
# normalized like the two above so a malformed scan can never put anything but
# the declared shape on the durable line. `tolerance` is the only float in the
# schema: it is the floor the divergence was judged against, stored WITH the
# verdict so a line read later is not judged by a constant that changed since.
subagents = {}
raw_subagents = res.get("subagents")
if isinstance(raw_subagents, dict):
    for aid, fact in raw_subagents.items():
        if not (isinstance(aid, str) and aid and isinstance(fact, dict)):
            continue
        one = {}
        model = fact.get("model")
        if isinstance(model, str) and model:
            one["model"] = model
        for key in ("duration_ms", "final_context_tokens"):
            if fact.get(key) is not None:
                one[key] = max(toint(fact.get(key)), 0)
        if one:
            subagents[aid] = one

cross = {}
raw_cross = res.get("cross_check")
if isinstance(raw_cross, dict) and raw_cross:
    tolerance = raw_cross.get("tolerance")
    cross = {"tolerance": float(tolerance) if isinstance(tolerance, float) else 0.0,
             "confronted": toint(raw_cross.get("confronted")),
             "reported_final_context": toint(raw_cross.get("reported_final_context")),
             "collected": toint(raw_cross.get("collected")),
             "divergent": [a for a in (raw_cross.get("divergent") or [])
                           if isinstance(a, str) and a]}

# Commit messages provide exact task identity; direct commits stay unassigned.
# Session residue uses the sole
# open claim from this same session; ambiguity stays unassigned rather than
# leaking maintenance into the phase preserved by STATE.md.
task, phase_source = None, None
match = re.search(r"\[(CHG-[0-9]{3,}\.[0-9]+|[0-9][0-9A-Za-z]*\.[0-9]+)\b", msg)
if match:
    task, phase_source = match.group(1), "commit"
elif not msg and source in ("hook", "stop"):
    task = open_session_task(os.path.join(project, ".helmit", "run.jsonl"), session)
    phase_source = "session-claim" if task else None
scope, workstream, phase = attribution(task)

row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
       "platform": res.get("platform") or "unknown",
       "token_schema": res.get("token_schema") or "legacy",
       "model_calls": max(toint(res.get("model_calls")), 0),
       "model": res.get("model") or "",
       "models": models,
       "model_variants": variants,
       "subagents": subagents,
       "cross_check": cross,
       "task": task, "scope": scope, "workstream": workstream,
       "phase": phase, "phase_source": phase_source,
       "session": session,
       "input_tokens": totals["input_tokens"],
       "output_tokens": totals["output_tokens"],
       "cache_read_tokens": totals["cache_read_tokens"],
       "cache_creation_tokens": totals["cache_creation_tokens"],
       "source": source, "cursor": res.get("cursor")}
try:
    with open(mfile, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
except OSError:
    sys.exit(0)

# metrics.jsonl is a canonical dashboard input. Keep the projection current in
# the same fail-open operation that changed the source, just like the other
# transition writers do. The dashboard remains optional: an absent script or a
# render failure cannot affect the successful metrics capture.
dashboard = os.path.join(body_dir, "dashboard.sh")
if os.path.isfile(dashboard):
    try:
        subprocess.run(["bash", dashboard, "publish", "--project", project],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=project),
                       check=False)
    except OSError:
        pass
sys.exit(0)
