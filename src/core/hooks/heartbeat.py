import json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("HB_ROOT") or os.getcwd()
HOOKS = os.environ.get("HB_HOOKS") or os.path.dirname(os.path.abspath(__file__))
DRY = os.environ.get("HB_DRY") == "1"
SIG = os.environ.get("HB_SIG") or ""
HELMIT = os.path.join(ROOT, ".helmit")
LOG = os.path.join(HELMIT, "run.jsonl")
YOLOSH = os.path.join(HOOKS, "yolo.sh")
RUNLOG = os.path.join(HOOKS, "run-log.sh")
EXECUTOR_LEASE = os.path.join(HOOKS, "executor-lease.sh")
LADDER = (5, 10, 20, 40, 60)
STALE_FLOOR_H = 24
TERMINAL = ("DONE", "DISARM")
COLLAPSED = "burst-collapse"

# TZ from the environment must win before any local-time conversion: the quota
# reset hour is a wall-clock time in the machine timezone.
if hasattr(time, "tzset"):
    time.tzset()


def toint(v, d=0):
    try:
        return int(v)
    except Exception:
        return d


INTERVAL_MIN = max(toint(os.environ.get("HELMIT_BEAT_INTERVAL_MIN"), 15), 1)

# A third of the beat interval: a beat landing inside it cannot be a tick of a
# 15 min cadence, it is a queued one arriving with the rest of the burst.
COLLAPSE_MIN = max(toint(os.environ.get("HELMIT_BEAT_COLLAPSE_MIN"),
                         INTERVAL_MIN // 3), 0)


def now():
    frozen = os.environ.get("HELMIT_BEAT_NOW")
    if frozen:
        d = parse_iso(frozen)
        if d is not None:
            return d
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not isinstance(s, str) or not s.strip():
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(t)
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def sh(argv, env_extra=None):
    """A call to a neighbour. (rc, stdout); nothing here may take the beat down."""
    env = dict(os.environ)
    env.update(env_extra or {})
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=env)
        return p.returncode, p.stdout
    except Exception:
        return 127, ""


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def entries():
    """run.jsonl entries with the run-log.sh tolerance rules: the last line
    with no trailing newline is an interrupted write by construction and is
    dropped; a corrupt line mid-file is skipped."""
    lines = read_text(LOG).split("\n")
    if lines:
        lines.pop()
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("event"), str):
            out.append(obj)
    return out


def git_head():
    """HEAD of the PROJECT repo — only when ROOT is itself the toplevel: from
    a project nested inside a bigger repo, git would answer for the ENCLOSING
    repo and the progress derivation would follow a foreign HEAD."""
    rc, out = sh(["git", "-C", ROOT, "rev-parse", "--show-toplevel"])
    if rc != 0 or os.path.realpath(out.strip()) != os.path.realpath(ROOT):
        return ""
    rc, out = sh(["git", "-C", ROOT, "rev-parse", "HEAD"])
    return out.strip() if rc == 0 else ""


# A recovery beat is not interactive execution and therefore never renews a
# tree lock or executor lease. Liveness belongs to the actual executor.

# --- collapse the burst, then decide ------------------------------------------
all_entries = entries()
beats = [e for e in all_entries if e.get("event") == "beat"]
others = [e for e in all_entries if e.get("event") != "beat"]
head = git_head()


def collapsed(beat):
    return beat.get("reason") == COLLAPSED


def burst_collapse():
    """True when a beat was ALREADY PROCESSED inside the collapse window: this
    one is a queued member of the same burst and must cost nothing."""
    if COLLAPSE_MIN <= 0 or not beats:
        return False
    ts = parse_iso(beats[-1].get("ts"))
    return ts is not None and (now() - ts).total_seconds() < COLLAPSE_MIN * 60


def trailing_beats_on_head():
    """Beats since the last commit: walked backwards while the recorded sha is
    the current HEAD. An empty or unknown sha ends the walk — no derivation
    without evidence. Collapsed beats are walked THROUGH and dropped: they
    decided nothing, so counting them would let a burst hide a RESUME streak
    from the breaker and reset the backoff ladder."""
    out = []
    if not head:
        return out
    for b in reversed(beats):
        if b.get("sha") != head:
            break
        if not collapsed(b):
            out.append(b)
    return out


def open_claims():
    """The claims still in flight, asked of the neighbour that OWNS that
    derivation (REQ-232). Nothing here may take the beat down: a non-zero exit
    means there is none."""
    rc, out = sh(["bash", RUNLOG, "open-entry", "--all"], {"CLAUDE_PROJECT_DIR": ROOT})
    # run-log's documented rc=1 means the derivation succeeded and there are
    # no open claims. Other failures leave activity genuinely unknown.
    if rc == 1:
        return [], True
    if rc != 0:
        return [], False
    claims = []
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            return [], False
        if isinstance(obj, dict):
            claims.append(obj)
        else:
            return [], False
    return claims, True


def executor_activity():
    """active, inactive or unknown from claim + interactive lease evidence."""
    claims, known = open_claims()
    if not known:
        return "unknown"
    uncertain = False
    for claim in claims:
        session = claim.get("session")
        task = claim.get("task")
        if not isinstance(session, str) or not session or not isinstance(task, str) or not task:
            uncertain = True
            continue
        rc, _ = sh(["bash", EXECUTOR_LEASE, "alive", "--task", task,
                    "--session", session], {"CLAUDE_PROJECT_DIR": ROOT})
        if rc == 0:
            return "active"
        if rc != 1:
            uncertain = True
    return "unknown" if uncertain else "inactive"


def decide():
    """(decision, reason, display, extra_kv). The first match wins."""
    # The burst comes FIRST, before the mandate probe (REQ-233): a queued beat
    # must not even spend a subprocess, let alone a turn. It also spares the
    # terminal-repeat guard a false alarm — the beats queued behind a DONE land
    # after the cron is already gone, and they are not evidence of a failed act.
    if burst_collapse():
        return "IDLE", COLLAPSED, "IDLE", {}

    # a. is the mandate still in force? yolo.sh is the single source (REQ-118),
    # and DETECTING is not EXPIRING — the two modes ask it differently:
    # `status` is a pure read that already answers fulfilled-ness, running the
    # same fulfilled() the reap runs and reporting a spent mandate as FULFILLED
    # (REQ-290), so --dry-run gets its verdict without touching .helmit/; the
    # normal mode still runs the reap, because the reap IS what ends the
    # mandate. The FULFILLED prefix is deliberately not `yolo: off` — that one
    # means no mandate at all, and treating a spent one as `off` here would
    # skip the reap and orphan the yolo.json.
    rc, status = sh(["bash", YOLOSH, "status"], {"CLAUDE_PROJECT_DIR": ROOT})
    if rc != 0 or not status.strip() or status.startswith("yolo: off"):
        return "DONE", "no-mandate", "DONE", {}
    if DRY:
        if re.match(r"yolo: \S+ FULFILLED\b", status):
            return "DONE", "scope-fulfilled", "DONE", {}
    else:
        _, reaped = sh(["bash", YOLOSH, "reap"], {"CLAUDE_PROJECT_DIR": ROOT})
        if "REAPED" in reaped:
            return "DONE", "scope-fulfilled", "DONE", {}

    # b/c. what does the log say about the last turn? Only non-beat entries
    # count: the beat records itself, and its own lines must never bury the
    # typed stop (the lesson the tick learned under REQ-090).
    candidate = None
    last = others[-1] if others else None
    if last is not None and last.get("event") == "session_stop":
        reason = last.get("reason")
        if reason in ("clean", "gate", "awaiting_input"):
            return "IDLE", "typed-stop:%s" % reason, "IDLE", {}
        candidate = ("RESUME", "interrupted")
    elif last is not None:
        ts = parse_iso(last.get("ts"))
        if ts is not None and (now() - ts).total_seconds() < INTERVAL_MIN * 60:
            return "IDLE", "in-flight", "IDLE", {}
        # An old log is silence, not death: a task of 20 or 30 minutes writes
        # nothing between its claim and its commit. Ask the executor for a sign
        # of life before calling it interrupted (REQ-234).
        activity = executor_activity()
        if activity == "active":
            candidate = ("IDLE", "in-flight:executor-alive")
        elif activity == "unknown":
            candidate = ("IDLE", "in-flight:activity-unknown")
        else:
            candidate = ("RESUME", "interrupted")
    else:
        # A heartbeat recovers a proven interruption; it never starts a new
        # turn merely because the log is empty. Normal chaining belongs to the
        # route, not the guardian.
        candidate = ("IDLE", "no-interruption")

    # d. quota: only the EXPLICIT signature decides — no fragile detection.
    if SIG:
        m = re.search(r"resets\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
                      SIG, re.IGNORECASE)
        if m:
            hour, minute = toint(m.group(1)), toint(m.group(2))
            ampm = (m.group(3) or "").lower()
            if ampm:
                hour = hour % 12 + (12 if ampm == "pm" else 0)
            if 0 <= hour < 24 and 0 <= minute < 60:
                local_now = now().astimezone()
                target = local_now.replace(hour=hour, minute=minute,
                                           second=0, microsecond=0)
                if target <= local_now:
                    target += timedelta(days=1)
                until = iso(target + timedelta(minutes=7))
                return "WAIT", "quota", "WAIT until %s" % until, {"until": until}
        prior = 0
        for b in trailing_beats_on_head():
            if b.get("decision") == "WAIT" and b.get("reason") == "quota":
                prior += 1
            else:
                break
        backoff = LADDER[min(prior, len(LADDER) - 1)]
        return "WAIT", "quota", "WAIT backoff %d" % backoff, {"backoff_min": str(backoff)}

    # e. breaker (REQ-158): 3 consecutive RESUME beats on the same HEAD — the
    # agent came up three times and committed nothing; a fourth try is a
    # quota-burning machine, not persistence.
    streak = 0
    since_commit = trailing_beats_on_head()
    for b in since_commit:
        if b.get("decision") == "RESUME":
            streak += 1
        else:
            break
    if streak >= 3:
        return "DISARM", "breaker", "DISARM", {}

    # f. floor: a whole day of beats on the same HEAD and not one commit —
    # the mixed patterns the breaker cannot see (RESUME/IDLE alternation).
    if since_commit:
        oldest = parse_iso(since_commit[-1].get("ts"))
        if oldest is not None and (now() - oldest) >= timedelta(hours=STALE_FLOOR_H):
            return "DISARM", "stale-24h", "DISARM", {}

    return candidate[0], candidate[1], candidate[0], {}


decision, reason, display, extra = decide()

# --- step 4: record, then the terminal-repeat guard (REQ-159) -------------------
# The previous DECISION, which a collapsed beat is not: letting one count would
# make a single queued beat forgive a cron removal that never happened.
decided_before = [b for b in beats if not collapsed(b)]
prev_decision = decided_before[-1].get("decision") if decided_before else None

print("heartbeat: %s — %s" % (display, reason))

if not DRY and os.path.isdir(HELMIT):
    kv = ["decision=%s" % decision, "reason=%s" % reason, "sha=%s" % head]
    kv += ["%s=%s" % (k, v) for k, v in extra.items()]
    rc, _ = sh(["bash", RUNLOG, "append", "beat"] + kv,
               {"CLAUDE_PROJECT_DIR": ROOT, "HELMIT_PID": str(os.getppid())})
    if rc != 0:
        sys.stderr.write("WARNING: heartbeat could not record the beat in run.jsonl (run-log.sh exit %d).\n" % rc)

if decision in TERMINAL and prev_decision == decision:
    sys.stderr.write("heartbeat: ERROR — terminal decision repeated (%s); "
                     "the act that should have removed the cron FAILED\n" % decision)
    sys.exit(1)

sys.exit(0)
