import calendar, hashlib, html, json, os, pathlib, re, runpy, subprocess, sys, tempfile, textwrap
from datetime import date, datetime, timedelta, timezone

ROOT = os.environ["DASH_ROOT"]
SELF_DIR = os.environ["DASH_DIR"]
CMD = os.environ.get("DASH_CMD", "render")
WANT_PHASE = os.environ.get("DASH_PHASE", "").strip()
HELMIT = os.path.join(ROOT, ".helmit")
fold_claims = runpy.run_path(os.path.join(SELF_DIR, "run-log.py"))["fold_claims"]
OUT = os.path.join(HELMIT, "dashboard.html")
FINGERPRINT_META = 'name="helmit-source-fingerprint" content="([0-9a-f]{64})"'
STATUS_START = "<!-- helmit-dashboard-status:start -->"
STATUS_END = "<!-- helmit-dashboard-status:end -->"

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens",
                "cache_creation_tokens")
# The phase ladder, in order: the board colors it as an ORDINAL ramp, so the
# order here IS the visual order. `implementing` is pulled out of the ramp and
# painted with the accent instead: it is the one state a reader looks for.
PHASE_LADDER = ("todo", "spec", "planned", "implementing", "shipped", "validated")
REQ_LADDER = ("todo", "covered", "proven")
# A phase id is digit-led alphanumeric (REQ-151: `3c` is legal).
PHASE_ID = re.compile(r"^[0-9][0-9A-Za-z]*$")
REQ_ID = re.compile(r"^REQ-[0-9]+$")
TASK_LINE = re.compile(r"^-\s+\[([ xX>])\]\s+([0-9][0-9A-Za-z]*\.[0-9]+)\b(.*)$")
# An HTML comment, closed or running to the end of the file. What lives inside
# one is prose ABOUT the chart, and the template puts a worked task line there
# to define the tick format — read as data, that example becomes a task nobody
# ever wrote (REQ-236).
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
# The whole `(done, commit <hash> ...)` parenthetical, cut out of the title:
# charts do append prose inside it ("(done, commit d93f02b - no fix, ...)"), so
# stopping at the hash would leave that prose sitting in the title.
TASK_COMMIT = re.compile(r"\(done,\s*commit\s+[0-9a-fA-F]{6,40}[^)]*\)")
# The same parenthetical, read for its HASH: the phase report answers "which
# commit closed this task", and the chart is where that answer is recorded.
TASK_HASH = re.compile(r"\(done,\s*commit\s+([0-9a-fA-F]{6,40})")
TASK_DONE = re.compile(r"\(done\)")
# A tick CLOSED WITHOUT a commit: the `[human]` gate, whose closing act is an
# approval and not code. Before REQ-188 the report printed "open" next to a task
# marked [x], because it only knew how to read a hash. The mark is what says the
# task is closed; this reads WHY, so the report can say it instead of lying.
TASK_CLOSE = re.compile(r"\(done[,)]?\s*(.*?)\)\s*$")
# ISO-8601 as the two logs write it: metrics.jsonl ends in `+00:00`, run.jsonl
# in `Z`. Both are parsed by hand — `datetime.fromisoformat` only learned to
# read the `Z` suffix in 3.11, and the floor here is whatever python3 the
# machine has (ADR-001).
TS = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
                r"(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
# How much of a phase anchor reaches the tooltip. The anchors are full
# paragraphs by design; dumping them on the board would bury it.
ANCHOR_CAP = 240
TIMELINE_DAYS = 60
RECENT_EVENTS = 12
# How many `gate_run` records the TESTS block plots. Same reasoning as the
# timeline's day window: a project with a thousand commits would otherwise draw
# a thousand columns four pixels apart, and the recent ones are the readable
# ones. The slice that is shown is DECLARED on the axis caption.
TEST_RUNS = 40
# How many map records the health block lists. Same reasoning as the two
# windows above: the recent ones are the readable ones, and the cap is
# declared on the panel the moment it actually cuts something off.
MAP_EVENTS = 12
# The three words `repo-map.sh check` can answer, and the ONLY strings
# this board will transcribe as a verdict. Enum values, English wherever
# they appear, like every other one here. Anything else on a record is a
# verdict this board cannot read, and an unreadable verdict is reported as
# unrecorded rather than passed through to a reader who would trust it.
MAP_VERDICTS = ("fresh", "stale", "absent")
# The fields the two map records carry, in the order the table prints
# them. Field NAMES are the log's own, never translated: a table that
# renamed the keys would stop agreeing with the file it transcribes.
MAP_FIELDS = ("freshness", "parsed", "reused", "chars", "scope")
# How many rows each of the two map charts draws. Same reasoning as MAP_EVENTS
# and the two windows above: a repo with two hundred directories would draw two
# hundred rows nobody reads, and the cap is DECLARED on the panel the moment it
# actually cuts something off.
MAP_DIRS = 10
MAP_TOP = 10
# How much of a path reaches the label column of those charts. The names are
# repository-relative paths and some of them are long, and SVG text does not
# ELLIPSIS on its own the way a CSS box does — this cap IS the mechanism, so it
# has to hold in the worst case rather than the usual one. The label column is
# 340 user units; a rank prefix adds up to 3 characters; lowercase path text
# runs about 0.62em, so 38 + 3 characters at 13px come to ~330 units and stop
# short of the plot. The whole path is in the table twin under every chart.
MAP_PATH_CAP = 38
# The line repo-map writes between the two layers of `map.txt`: above it, files
# with their symbols, ranked; below it, files it read no symbols from, listed by
# name alone. The string is repo-map's own and is MATCHED, never printed — the
# symbol reader stops there, because a bare path under that line is a file and
# not a symbol. It is absent whenever that second layer is empty, so its absence
# says nothing at all about whether the budget truncated the first one.
MAP_PLAIN_MARK = "(no symbols / unmapped language:)"
# One symbol row of `map.txt`, exactly as repo-map writes it: two spaces, the
# capture kind, the identifier, and `:<line>`. Anything that does not match is
# skipped in silence — this reader parses an artifact another tool renders under
# a character budget, so a half-written last line is expected, never an error.
MAP_SYMBOL = re.compile(r"^ {2}(\S+) (\S+) :(\d+)$")
DAY = 86400
# Last day of the period the token record is known to UNDERCOUNT (REQ-242). Up
# to and including it, the fleet scan summed subagents that were still running:
# the id went into the cursor at that reading and the file was never reopened,
# so the sum froze. REQ-239 stopped the scan from reading live agents, which
# repairs every capture from the next day on and NOTHING before it — the past
# cursors still hold frozen ids, and recovering them would need a cursor purge
# plus a rescan, which collides with the append-only contract of `reconcile`.
# So the figure stands as recorded and the board declares what it is missing.
UNDERCOUNT_THROUGH = "2026-08-18"


# --- reading (every reader is fail-open) --------------------------------------

def read_text(path):
    """File contents, or None when missing/unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def read_json(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


_NEXT_FACTS = None


def next_facts():
    """Shared phase/route derivation. The board remains fail-open."""
    global _NEXT_FACTS
    if _NEXT_FACTS is not None:
        return _NEXT_FACTS
    try:
        proc = subprocess.run(
            ["bash", os.path.join(SELF_DIR, "next-status.sh"), "facts", "--json"],
            cwd=ROOT, env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
            capture_output=True, text=True, timeout=30,
        )
        value = json.loads(proc.stdout)
        _NEXT_FACTS = value if isinstance(value, dict) else {}
    except Exception:
        _NEXT_FACTS = {}
    return _NEXT_FACTS


def table_rows(text):
    """Cell lists of every markdown table row. A cell may legally contain a
    pipe (the config enums do: `off | phase | full`), so callers index from
    BOTH ends and join the middle instead of trusting the column count."""
    for line in text.splitlines():
        s = line.strip()
        if len(s) > 1 and s.startswith("|") and s.endswith("|"):
            yield [c.strip() for c in s[1:-1].split("|")]


def toint(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def epoch(ts):
    """Seconds since the epoch for an ISO-8601 stamp, or None when unreadable.
    Comparing the raw strings would be wrong across the two logs: `...53Z` and
    `...53+00:00` are the same instant and sort apart."""
    m = TS.match((ts or "").strip()) if isinstance(ts, str) else None
    if not m:
        return None
    parts = [int(x) for x in m.groups()[:6]]
    try:
        seconds = calendar.timegm(tuple(parts) + (0, 0, 0))
    except (OverflowError, ValueError):
        return None
    offset = m.group(7)
    if offset and offset != "Z":
        digits = offset[1:].replace(":", "")
        shift = toint(digits[:2]) * 3600 + toint(digits[2:4]) * 60
        seconds -= shift if offset[0] == "+" else -shift
    return seconds


# --- the five sources ---------------------------------------------------------

def parse_roadmap():
    """Phases in ROADMAP order: id, name, anchor, requires, covers, status."""
    text = read_text(os.path.join(HELMIT, "ROADMAP.md"))
    out = []
    if not text:
        return out
    for cells in table_rows(text):
        if len(cells) < 4 or not PHASE_ID.match(cells[0]):
            continue
        out.append({
            "id": cells[0],
            "name": cells[1],
            "anchor": " | ".join(cells[2:-3]) if len(cells) > 5 else "",
            "requires": cells[-3] if len(cells) > 4 else "",
            "covers": cells[-2],
            "status": cells[-1].lower(),
        })
    return out


def strip_html_comments(text):
    """A chart with its HTML comments blanked out, line structure intact.

    The CHART template DEFINES the tick format inside a comment, and it defines
    it by example — a worked task line the parser was happy to read as a real
    task (REQ-236: a phase of 4 tasks reported 5 of 5 and the report listed the
    example among them). Documentation about the format is not data in it.

    Each comment collapses to the newlines it spanned instead of vanishing, so
    the text around a comment can never be spliced into one line that parses as
    something neither half was. An unterminated comment runs to the end: a
    chart that opens one and never closes it is commented out from there on,
    which is what a reader of the markdown sees too.
    """
    return HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def parse_charts():
    """Tasks per phase from phases/<id>/CHART.md. Not every phase has one."""
    out = {}
    base = os.path.join(HELMIT, "phases")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for name in names:
        text = read_text(os.path.join(base, name, "CHART.md"))
        if not text:
            continue
        tasks = []
        for line in strip_html_comments(text).splitlines():
            m = TASK_LINE.match(line.strip())
            if not m:
                continue
            mark, tid, rest = m.group(1), m.group(2), m.group(3)
            sha = TASK_HASH.search(rest)
            closed = TASK_CLOSE.search(rest)
            note = ""
            if not sha and closed:
                note = closed.group(1).strip()
            tasks.append({
                "id": tid,
                "state": "done" if mark in "xX" else ("doing" if mark == ">" else "todo"),
                "title": TASK_DONE.sub("", TASK_COMMIT.sub("", rest)).split("·")[0].strip(),
                "commit": sha.group(1) if sha else "",
                "closed_note": note,
            })
        if tasks:
            out[name] = tasks
    return out


def parse_requirements():
    """REQ rows as id, phase and status.

    The requirement PROSE is read past on purpose: 172 rows of it would more
    than double the page for text nobody reads at a glance, and the registry
    itself is one file away. The board answers how many and where, not what."""
    text = read_text(os.path.join(HELMIT, "REQUIREMENTS.md"))
    out = []
    if not text:
        return out
    for cells in table_rows(text):
        if len(cells) < 4 or not REQ_ID.match(cells[0]):
            continue
        out.append({"id": cells[0], "phase": cells[-2],
                    "status": cells[-1].lower()})
    return out


def metrics_rows():
    """Every readable line of metrics.jsonl, in file order. Split out of the
    fold below so the board and the phase report share ONE reader: the report
    needs the rows themselves (to scope them to a phase) and then folds the
    survivors with exactly the same rules."""
    lines = read_text(os.path.join(HELMIT, "metrics.jsonl"))
    out = []
    if not lines:
        return out
    for raw in lines.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def normalized_token_bucket(row, bucket=None):
    """Return disjoint token fields for current and historical metric rows.

    Claude reports ordinary input, cache reads and cache writes as separate
    fields. Codex v1 rows copied cached input both inside `input_tokens` and
    into `cache_read_tokens`; their cursor identifies that historical shape.
    New adapters stamp `disjoint-v1`, so every consumer can sum the fields.
    """
    source = bucket if isinstance(bucket, dict) else row
    values = {key: max(toint(source.get(key)), 0) for key in TOKEN_FIELDS}
    cursor = row.get("cursor") if isinstance(row.get("cursor"), str) else ""
    legacy_codex = (row.get("platform") == "codex"
                    and row.get("token_schema") != "disjoint-v1"
                    and cursor.startswith("codex:v1:"))
    if legacy_codex:
        values["input_tokens"] = max(
            values["input_tokens"] - values["cache_read_tokens"]
            - values["cache_creation_tokens"], 0)
    return values


def usage_profile(row):
    values = normalized_token_bucket(row)
    total = sum(values.values())
    fresh = values["input_tokens"] + values["cache_creation_tokens"]
    input_total = (values["input_tokens"] + values["cache_read_tokens"]
                   + values["cache_creation_tokens"])
    raw_calls = row.get("model_calls")
    calls_known = (isinstance(raw_calls, int) and not isinstance(raw_calls, bool)
                   and raw_calls >= 0)
    return {"tokens": total, "fresh": fresh, "input_total": input_total,
            "cache": values["cache_read_tokens"],
            "output": values["output_tokens"],
            "cache_share": share(values["cache_read_tokens"], input_total),
            "calls": raw_calls if calls_known else 0,
            "calls_known": 1 if calls_known else 0}


def add_usage(slot, row):
    usage = usage_profile(row)
    for key in ("tokens", "fresh", "input_total", "cache", "output", "calls",
                "calls_known"):
        slot[key] += usage[key]
    slot["captures"] += 1
    source = row.get("phase_source")
    if isinstance(source, str) and source:
        slot["attribution_sources"].add(source)


def fold_metrics(rows):
    """Totals, per-model buckets and the count of lines with NO breakdown.

    Mirrors `metrics.sh agg` on the one judgement call that matters: a line
    written before REQ-167 carries no `models` key, and guessing which model
    spent those tokens would be inventing data. Such lines feed the totals and
    are DECLARED as unbroken-down, never folded into a bucket."""
    st = {"totals": dict.fromkeys(TOKEN_FIELDS, 0), "models": {}, "no_breakdown": 0,
          "captures": 0, "model_calls": 0, "model_calls_known": 0,
          "sessions": set(), "last_ts": ""}
    for row in rows:
        st["captures"] += 1
        values = normalized_token_bucket(row)
        for k in TOKEN_FIELDS:
            st["totals"][k] += values[k]
        usage = usage_profile(row)
        st["model_calls"] += usage["calls"]
        st["model_calls_known"] += usage["calls_known"]
        sess = row.get("session")
        if isinstance(sess, str) and sess:
            st["sessions"].add(sess)
        ts = row.get("ts")
        if isinstance(ts, str) and ts > st["last_ts"]:
            st["last_ts"] = ts
        models = row.get("models")
        if isinstance(models, dict) and models:
            for name, bucket in models.items():
                if not isinstance(bucket, dict):
                    continue
                slot = st["models"].setdefault(name, dict.fromkeys(TOKEN_FIELDS, 0))
                values = normalized_token_bucket(row, bucket)
                for k in TOKEN_FIELDS:
                    slot[k] += values[k]
        elif any(values.values()):
            st["no_breakdown"] += 1
    return st


def token_attribution(row):
    """Normalize current and historical token attribution without guessing."""
    task = row.get("task") if isinstance(row.get("task"), str) else ""
    scope = row.get("scope") if isinstance(row.get("scope"), str) else ""
    workstream = row.get("workstream") if isinstance(row.get("workstream"), str) else ""
    if scope == "change" or re.fullmatch(r"CHG-[0-9]{3,}\.[0-9]+", task):
        change = workstream if workstream.startswith("CHG-") else task.split(".", 1)[0]
        return "change", change, ""
    pid = row.get("phase")
    pid = str(pid).strip() if pid is not None else ""
    if not pid and re.fullmatch(r"[0-9][0-9A-Za-z]*\.[0-9]+", task):
        pid = phase_of(task)
    if scope == "delivery" or pid:
        return "delivery", workstream or ("phase:%s" % pid), pid
    return "", "", ""


def fold_phase_tokens(rows, roadmap=None):
    """What each phase cost, how much of the record that even covers, and how
    much of the attribution is APPROXIMATE rather than measured.

    A capture carries a `phase` in one of two ways, and the `phase_source`
    field says which: `commit`, read by the commit hook off the commit message
    — exact; or `state`, inherited from STATE.md by a session residue that
    named no task (REQ-225) — approximate, because a residue can straddle a
    phase boundary. Older lines carry neither. Three rules keep the answer
    honest:

    * The phase is read from the `phase` field and, failing that, from the
      prefix of the `task` id (`20.3` -> `20`) — the same reading `phase_of`
      does everywhere else. Nothing else is consulted: charging a line to the
      phase of the line above it, because it happens to sit next to it, is
      inventing an attribution the record does not carry.
    * A line with NEITHER is never charged to a phase. It is counted apart,
      with its tokens, and the caller declares it — exactly the rule the
      per-model breakdown already follows for the lines written before
      REQ-167.
    * The INHERITED ones ARE charged, and counted apart as well, so the caller
      can declare them too: a bar that mixes measured and inherited
      attribution without saying so reads as if all of it had been measured.
    """
    names = {p["id"]: p["name"] for p in (roadmap or [])}
    st = {"phases": {}, "attributed": 0, "total": 0, "loose": 0,
          "loose_tokens": 0, "inherited": 0, "recovered_unassigned": 0,
          "recovered_unassigned_tokens": 0,
          "unassigned": {"tokens": 0, "fresh": 0, "input_total": 0,
                         "cache": 0, "output": 0, "calls": 0,
                         "calls_known": 0, "captures": 0,
                         "attribution_sources": set()}}
    for row in rows:
        spent = usage_profile(row)["tokens"]
        st["total"] += spent
        kind, _workstream, pid = token_attribution(row)
        if kind == "change":
            continue
        if kind != "delivery" or not pid:
            st["loose"] += 1
            st["loose_tokens"] += spent
            add_usage(st["unassigned"], row)
            if row.get("source") == "reconcile":
                st["recovered_unassigned"] += 1
                st["recovered_unassigned_tokens"] += spent
            continue
        slot = st["phases"].setdefault(
            pid, {"name": names.get(pid, ""), "tokens": 0, "fresh": 0,
                  "input_total": 0, "cache": 0, "output": 0, "calls": 0,
                  "calls_known": 0, "captures": 0, "inherited": 0,
                  "attribution_sources": set()})
        add_usage(slot, row)
        st["attributed"] += spent
        if row.get("phase_source") == "state":
            st["inherited"] += 1
            slot["inherited"] += 1
    return st


def fold_change_tokens(rows):
    result = {"changes": {}, "attributed": 0, "captures": 0}
    for row in rows:
        kind, workstream, _pid = token_attribution(row)
        if kind != "change" or not workstream:
            continue
        spent = usage_profile(row)["tokens"]
        slot = result["changes"].setdefault(workstream,
                                             {"tokens": 0, "fresh": 0,
                                              "input_total": 0, "cache": 0,
                                              "output": 0, "calls": 0,
                                              "calls_known": 0, "captures": 0,
                                              "attribution_sources": set(),
                                              "claim": 0})
        add_usage(slot, row)
        if row.get("phase_source") == "session-claim":
            slot["claim"] += 1
        result["attributed"] += spent
        result["captures"] += 1
    return result


def parse_runlog():
    """Typed events, read as tolerantly as run-log.sh reads them."""
    lines = read_text(os.path.join(HELMIT, "run.jsonl"))
    events = []
    if not lines:
        return events
    for raw in lines.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        ts, event = row.get("ts"), row.get("event")
        if not isinstance(ts, str) or not isinstance(event, str) or len(ts) < 10:
            continue
        detail = ""
        # `verdict` is last: it is the only detail a `gate_run` carries, and no
        # other event has one, so reading it changes nothing for the others.
        for key in ("task", "reason", "note", "verdict"):
            v = row.get(key)
            if isinstance(v, str) and v:
                detail = v
                break
        task = row.get("task")
        # The whole row rides along: the typed fields above are what every
        # reader shared before `gate_run` arrived with a dozen of its own, and
        # widening the common shape for one event's fields would make every
        # other reader carry them. Readers that want more parse `row`.
        events.append({"ts": ts, "day": ts[:10], "event": event, "detail": detail,
                       "task": task if isinstance(task, str) else "", "row": row})
    events.sort(key=lambda e: e["ts"])
    return events


def parse_state():
    """The `workflow:` field of STATE.md as (state, phase id) — either may be
    empty. `implementing:20.6` is a position INSIDE phase 20, so the task
    suffix is dropped: the report is about the phase."""
    shared = next_facts()
    workflow = shared.get("workflow", "")
    phase = shared.get("phase", "")
    if workflow:
        return workflow.split(":", 1)[0], phase
    text = read_text(os.path.join(HELMIT, "STATE.md")) or ""
    m = re.search(r"^[ \t]*[-*]?[ \t]*workflow:[ \t]*([A-Za-z][A-Za-z_-]*)"
                  r"(?:[ \t]*:[ \t]*([0-9][0-9A-Za-z]*)(?:\.[0-9]+)?)?", text, re.M)
    if not m:
        return "", ""
    return m.group(1), (m.group(2) or "")


def ttl(name):
    try:
        return max(int(os.environ.get(name, "900")), 0)
    except ValueError:
        return 900


def session_activities():
    """Read only atomic per-session records from this project's local cache."""
    folder = os.path.join(HELMIT, "session-activity")
    if os.path.islink(folder) or not os.path.isdir(folder):
        return []
    result = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in names:
        if not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            continue
        path = os.path.join(folder, name)
        if os.path.islink(path):
            continue
        row = read_json(path)
        if not row or row.get("version") != 1 or row.get("session_hash") != name[:-5] \
                or row.get("source") not in ("start", "edit", "bash"):
            continue
        at = epoch(row.get("observed_at"))
        if at is not None:
            result.append((at, row["observed_at"], row["session_hash"]))
    return result


def presence_task(task, phases, charts):
    operation = task.startswith("ship.")
    phase_id = task.split(".", 1)[1] if operation else phase_of(task)
    phase = next((item for item in phases if item["id"] == phase_id), None)
    task_row = next((item for item in charts.get(phase_id, [])
                     if item["id"] == task), None)
    title = t("p_ship_title") if operation else (task_row["title"] if task_row else "")
    return {"task": task, "phase": phase_id,
            "phase_name": phase["name"] if phase else "", "title": title}


def fold_presence(events, phases, charts):
    """Evidence for the browser to classify against its own current clock."""
    lock_path = os.path.join(HELMIT, "lock.json")
    lease_path = os.path.join(HELMIT, "executor-lease.json")
    lock, lease = read_json(lock_path), read_json(lease_path)
    malformed = ((os.path.exists(lock_path) and lock is None) or
                 (os.path.exists(lease_path) and lease is None))
    open_claims = fold_claims(event["row"] for event in events)
    pauses = {}
    legacy_wait = None
    stopped = {}
    global_stop = None
    for event in events:
        row = event["row"]
        session = row.get("session")
        named = isinstance(session, str) and bool(session)
        waiting = (event["event"] == "awaiting_input" or
                   (event["event"] == "session_stop" and
                    row.get("reason") == "awaiting_input"))
        if waiting:
            if named:
                pauses[session] = event
                legacy_wait = None
            else:
                legacy_wait = event
        elif event["event"] in ("task_claimed", "task_committed", "heartbeat",
                                 "commit_started", "commit_landed"):
            if named:
                pauses.pop(session, None)
            legacy_wait = None
        elif event["event"] == "session_stop":
            if named:
                pauses.pop(session, None)
                stopped[session] = epoch(event["ts"])
            else:
                pauses.clear()
                global_stop = epoch(event["ts"])
            legacy_wait = None

    facts = {"state": "unknown" if malformed else "idle", "matched": False,
             "task": "", "title": "", "phase": "", "phase_name": "",
             "last_at": "", "expires_at": "", "base_state": "idle",
             "base_last_at": "", "base_task": "", "base_phase": "", "base_title": "",
             "strong_last_at": "", "strong_task": "", "strong_phase": "", "strong_title": "",
             "session_last_at": "", "session_expires_at": ""}
    if malformed:
        facts["base_state"] = "unknown"
        return facts
    activity = session_activities()
    by_hash = {digest: at for at, _, digest in activity}
    effective_pauses = {}
    for session, pause in pauses.items():
        digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
        if by_hash.get(digest, -1) > (epoch(pause["ts"]) or -1):
            continue
        effective_pauses[session] = pause
    activity = [(at, stamp, digest) for at, stamp, digest in activity
                if (global_stop is None or at > global_stop) and
                all(at > stop for session, stop in stopped.items()
                    if stop is not None and
                    hashlib.sha256(session.encode("utf-8")).hexdigest() == digest)]
    if activity:
        at, stamp, _ = max(activity)
        facts["session_last_at"] = stamp
        facts["session_expires_at"] = str(at + ttl("HELMIT_SESSION_ACTIVITY_SECS"))
    matches = []
    for task, claim in open_claims.items():
        session = claim.get("session")
        if not isinstance(session, str) or not session:
            continue
        if not (isinstance(lock, dict) and isinstance(lease, dict)):
            continue
        if lock.get("session") == session and lease.get("session") == session \
                and lease.get("task") == task:
            matches.append((task, session))
    waiting_claims = []
    for task, claim in open_claims.items():
        session = claim.get("session")
        pause = effective_pauses.get(session) if isinstance(session, str) else None
        if pause and (not pause["task"] or pause["task"] == task):
            waiting_claims.append((epoch(pause["ts"]) or 0, task, pause))
    if waiting_claims:
        _, task, pause = max(waiting_claims)
        facts["base_state"] = "awaiting"
        facts["base_last_at"] = pause["ts"]
        facts["base_task"] = task
        info = presence_task(task, phases, charts)
        facts["base_phase"] = info["phase"]
        facts["base_title"] = info["title"]
    elif legacy_wait or effective_pauses:
        pause = legacy_wait or max(effective_pauses.values(), key=lambda e: epoch(e["ts"]) or 0)
        facts["base_state"] = "awaiting"
        facts["base_last_at"] = pause["ts"]
    elif open_claims:
        facts["base_state"] = "interrupted"

    if (facts["base_state"] == "awaiting" and facts["session_last_at"] and
            (epoch(facts["session_last_at"]) or 0) <=
            (epoch(facts["base_last_at"]) or 0)):
        facts["session_last_at"] = ""
        facts["session_expires_at"] = ""

    if len(matches) == 1:
        task, session = matches[0]
        lock_at, lease_at = lock.get("heartbeat_at"), lease.get("renewed_at")
        lock_epoch, lease_epoch = epoch(lock_at), epoch(lease_at)
        if session not in effective_pauses and lock_epoch is not None and lease_epoch is not None:
            facts["matched"] = True
            facts["strong_last_at"] = lease_at
            facts["strong_task"] = task
            info = presence_task(task, phases, charts)
            facts["strong_phase"] = info["phase"]
            facts["strong_title"] = info["title"]
            facts["expires_at"] = str(min(lock_epoch + ttl("HELMIT_LOCK_STALE_SECS"),
                                          lease_epoch + ttl("HELMIT_EXECUTOR_LEASE_SECS")))

    if facts["matched"]:
        facts["state"] = "recent"
        facts["last_at"] = facts["strong_last_at"]
        facts.update(presence_task(facts["strong_task"], phases, charts))
    elif facts["session_last_at"] and (facts["base_state"] != "awaiting" or
          (epoch(facts["session_last_at"]) or 0) >
          (epoch(facts["base_last_at"]) or 0)):
        facts["state"] = "recent"
        facts["last_at"] = facts["session_last_at"]
    else:
        facts["state"] = facts["base_state"]
        facts["last_at"] = facts["base_last_at"]
        if facts["base_task"]:
            facts.update(presence_task(facts["base_task"], phases, charts))
    return facts


# --- labels: English in the code, translations in the sibling data file -------

LABELS = {
    "lang": "en",
    "num_group": ",", "num_decimal": ".", "c_k": "K", "c_m": "M", "c_b": "B",
    "page_title": "HelmIt board",
    "header_sub": "Derived from the artifacts in .helmit/ — counted facts, never scores",
    "data_through": "data through",
    "source_updated": "source updated",
    "inbox_open": "Inbox open",
    "projection_ok": "Live local view · checks for updates every 3 seconds",
    "theme": "Switch theme",
    "table": "Table view",
    "empty": "No data yet",
    "hero_label": "Phases shipped",
    "kpi_tasks": "Tasks done",
    "kpi_reqs": "Requirements proven",
    "kpi_tokens": "Tokens recorded",
    "kpi_tokens_sub": "%s capture(s) · %s session(s)",
    "p_eyebrow": "Project status",
    "p_working": "Work in progress",
    "p_recent": "Recent activity recorded",
    "p_awaiting": "Waiting for your decision",
    "p_interrupted": "Work may have been interrupted",
    "p_idle": "No work in progress",
    "p_ship_title": "Final proof and delivery closure",
    "p_unknown": "Project status unavailable",
    "p_last": "Last activity recorded %s",
    "p_no_activity": "No current activity was recorded",
    "p_phase": "Phase %s",
    "p_seconds": "%s seconds ago",
    "p_minute": "1 minute ago",
    "p_minutes": "%s minutes ago",
    "p_hour": "1 hour ago",
    "p_hours": "%s hours ago",
    "b_phases": "Phases",
    "b_phases_sub": "ROADMAP.md — one tile per phase, in roadmap order",
    "b_tasks": "Task progress",
    "b_tasks_sub": "phases/<id>/CHART.md — tasks done per phase",
    "b_reqs": "Requirements by status",
    "b_reqs_sub": "REQUIREMENTS.md — the whole registry",
    # --- the TOKENS block (REQ-177) -------------------------------------------
    "b_tokens": "Tokens",
    "b_tokens_sub": "metrics.jsonl — recorded calls, new input, cache, output "
                    "and attribution across phases, changes and unassigned work",
    "tk_undercount": "%s capture(s) recorded through %s come from an "
                     "UNDERCOUNTED period: a subagent read while it was still "
                     "running had its sum frozen at that reading and was never "
                     "reopened, so part of what it spent never reached this "
                     "record. REQ-239 stopped the scan from reading a live "
                     "agent and holds from the next day on, never backwards — "
                     "the cursors of the past keep their frozen ids. The gap "
                     "is not recoverable from the record and is NEVER "
                     "estimated, so everything below is a FLOOR for that "
                     "period and never a total. Audited on that last day: 9 of "
                     "the 12 subagent tasks of the session were read in flight "
                     "and 20.7M of the 37.7M tokens the fleet really spent "
                     "went uncounted, 54.7 percent of the day and 87.4 percent "
                     "in the worst single agent.",
    "tk_composition": "Composition by model and token type",
    "tk_by_phase": "Consumption by phase",
    "tk_by_change": "Consumption by change",
    "tk_unassigned_work": "Unassigned work",
    "tk_unassigned_note": "Conversations and other captured work with no phase or change assignment",
    "tk_capture_explainer": "Capture = one token delta persisted in metrics.jsonl by a commit, session stop or reconciliation.",
    "tk_calls_explainer": "Calls = model requests observed by the adapter. A dash means that historical capture predates this field; an asterisk means the total also contains captures with no call count.",
    "tk_attribution_explainer": "Attribution identifies how the workstream was determined: commit from the commit message; session claim from the sole open task owned by the session; reconciliation from a closed WAL window; inherited from STATE.md; mixed when more than one method contributed; missing when none was safe.",
    "tk_cover_change": "%s token(s) across %s capture(s) are assigned to changes",
    "tk_change_tip": "%s capture(s) · %s of the recorded total",
    "tk_cover_model": "%s of the %s token(s) recorded (%s) carry a per-model "
                      "breakdown — the rest is counted and NEVER attributed to "
                      "a model",
    "tk_cover_phase": "%s of the %s token(s) recorded (%s) carry a phase — the "
                      "rest is counted and NEVER attributed to a phase",
    "tk_nophase": "%s line(s) with no phase: a capture carries one only when "
                  "the commit hook read it off the commit message or a session "
                  "residue inherited it from STATE.md, so this chart describes "
                  "a PART of the record and never all of it",
    "tk_recovered_unassigned": "%s recovered reconciliation capture(s), %s token(s), "
                               "could not be assigned safely and are excluded from phase totals",
    "tk_phase_inherited": "%s of the attributed capture(s) INHERITED the phase "
                          "from STATE.md instead of a commit message — the "
                          "phase_source field tells them apart: commit is "
                          "exact, state is inherited. A session residue can "
                          "straddle a phase boundary, so an inherited phase is "
                          "an approximate attribution and never a measurement",
    "tk_unattr": "not attributed",
    "tk_phase_tip": "%s capture(s) · %s of the recorded total",
    # --- the TESTS block (REQ-176) --------------------------------------------
    "b_tests": "Tests",
    "b_tests_sub": "run.jsonl — the commit gate's own record of the suite, %s "
                   "→ %s. Only the runs it recorded: nothing before them is "
                   "reconstructed",
    "b_tests_sub_none": "run.jsonl — the commit gate has not recorded a suite "
                        "run yet",
    "tst_none": "No test history yet — the gate only began recording "
                "task verify and the quick floor in this version, so every commit made before it "
                "left no record. This is the absence of a record, not the "
                "absence of tests: the next agent commit starts "
                "the history.",
    "tst_bias": "Recorded on AGENT commits only: a commit typed by hand in the "
                "terminal runs the git floor, which does not reach the writer "
                "of this log — so what follows is a subset of the project's "
                "commits, never all of them.",
    "tst_double": "The task verify runs once in the harness layer. Both layers "
                  "apply the bounded staged quick floor independently; the git "
                  "floor never duplicates the product suite. Full-suite cost "
                  "belongs to wave, validation and ship receipts.",
    "tst_nocount": "%s run(s) with no case count: the test command printed no "
                   "summary to read it from, and a count is never invented — "
                   "those runs keep their verdict and their duration, and "
                   "their column is a gap instead of a zero",
    "tst_no_value": "not recorded",
    "f_last": "Last result",
    "f_last_sub": "%s failed · %s",
    "f_last_none": "no case count on this record · %s",
    "f_last_tip": "the last gate_run of run.jsonl\ncases = cases_passed + "
                  "cases_failed, exactly as the test command reported them",
    "f_runs": "Gate runs recorded",
    "f_runs_sub": "%s passed · %s blocked · %s of gate time",
    "f_runs_tip": "one record per agent commit the gate checked, green or "
                  "blocked\ngate time summed over the %s run(s) that recorded "
                  "a duration",
    "tst_suite": "Suite size per gate run",
    "tst_cost": "What the gate cost per run",
    "tst_axis_cases": "test cases in the suite",
    "tst_axis_ms": "duration of the gate",
    "tst_axis_x": "commit gate run, oldest → newest",
    "tst_first": "first recorded",
    "tst_ref_avg": "average over the %s run(s) shown",
    "lg_pass": "gate that passed",
    "lg_block": "gate that blocked",
    "lg_nub": "not recorded on that run",
    "last_runs": "last %s run(s)",
    # --- the TIME block (REQ-174) ---------------------------------------------
    "b_time": "Time recorded",
    "b_time_sub": "run.jsonl — instrumented window %s → %s. Only what the run "
                  "log recorded: nothing before it is estimated",
    "b_time_sub_none": "run.jsonl — no instrumented window yet",
    "f_tasks": "Time on tasks",
    "f_tasks_sub": "%s task(s) closed · average %s · longest %s",
    "f_tasks_tip": "task_claimed → task_committed of the same task\n"
                   "longest: %s (%s)",
    "f_sessions": "Time in sessions",
    "f_sessions_sub": "%s session(s) closed · longest %s",
    "f_sessions_tip": "first event of the session → its session_stop",
    # The DIFFERENCE between the two measures, and the caveat that makes the
    # first one readable. Both live in the BODY of the panel and not in a
    # tooltip (REQ-178): a value nobody can reach without a pointer is a value
    # the board did not publish.
    "t_explained": "Time on tasks sums the task_claimed → task_committed "
                   "windows; time in sessions runs from a session's first "
                   "event to its session_stop, so it also covers conversation, "
                   "planning, gates waiting on a human and the gap between "
                   "tasks. Tasks in a parallel wave OVERLAP (%s overlapping "
                   "pair(s) recorded), so their sum can exceed the wall clock "
                   "— and with it the time in sessions.",
    "tl_overlap": "A day can add up past 24h: tasks in a parallel wave overlap "
                  "and each window is counted whole (%s overlapping pair(s) "
                  "recorded).",
    "t_open": "Not counted: %s claim(s) with no commit · %s commit(s) with no "
              "claim · %s session(s) with no stop — an open record has no "
              "recorded end and is never closed against the current time",
    "t_by_phase": "Time by phase",
    "t_phase_tip": "%s task(s) closed · longest %s · %s claim(s) still open",
    # --- the daily timeline (REQ-173) -----------------------------------------
    "b_timeline": "Timeline — hours per day",
    "b_timeline_sub": "run.jsonl — time on tasks per day, task_claimed → "
                      "task_committed, split at UTC midnight (%s)",
    "axis_y": "time on tasks per day",
    "axis_x": "day (UTC)",
    "lg_bar": "time on tasks that day",
    "lg_ref": "average over the %s days shown",
    "lg_avg": "average",
    "last_days": "last %s days",
    # --- the MAP health panel (REQ-252) ---------------------------------------
    "b_map": "Repo map — health",
    "b_map_sub": "run.jsonl + .helmit/map/ — the optional layer's own account, "
                 "%s → %s. What it was RECORDED to be, never what this render "
                 "recomputed",
    "b_map_sub_none": "run.jsonl + .helmit/map/ — a map on disk that the run "
                      "log has never mentioned",
    "f_map_verdict": "Freshness",
    "f_map_verdict_sub": "as recorded %s",
    "f_map_verdict_disk": "no fingerprints under .helmit/map/",
    "f_map_verdict_none": "on disk, and no verdict was ever recorded for it",
    "f_map_verdict_tip": "the freshness repo-map itself wrote on its record\n"
                         "absent is the one read off the disk: no fingerprints "
                         "file, no map to be fresh about",
    "f_map_age": "Age of the map",
    "f_map_age_sub": "generated %s",
    "f_map_age_none": "no map_refreshed on record — when it was generated was "
                      "never written down",
    "f_map_age_tip": "last recorded map_refreshed → the newest fact on this "
                     "board, the same data through the header prints\nnever "
                     "measured against the current time",
    "f_map_pair": "Generated × consumed",
    "f_map_pair_sub": "%s refresh(es) · %s handover(s)",
    "f_map_pair_tip": "map_refreshed × map_shown in run.jsonl\ngenerating is "
                      "not consuming: while only one of the two was recorded, "
                      "a map rebuilt on every wave and a map nobody had opened "
                      "read exactly alike",
    "mp_unrecorded": "not recorded",
    "mp_explained": "The verdict is TRANSCRIBED from the record repo-map "
                    "wrote, never recomputed here: `check` hashes the working "
                    "tree file by file, so re-running it on every render would "
                    "be a second source for a truth that already has one — and "
                    "one that answers differently on a machine without the "
                    "optional library. Read it together with the age beside "
                    "it: fresh means fresh AT the moment printed under it, and "
                    "this map has been seven hours old with nobody told.",
    "mp_floor": "%s consumption record(s) predate the first recorded "
                "generation: the log learned to record map_shown before it "
                "learned to record map_refreshed, so over that stretch the "
                "generated side is a FLOOR and never a count.",
    "mp_last": "The table below lists the last %s record(s); the counts above "
               "are over the whole log.",
    # --- the MAP drawing (REQ-253) --------------------------------------------
    # Every one of these says WHAT IS BEING COUNTED, and the answer is never
    # "the repository": map.txt is a budget-capped excerpt, and a chart drawn
    # from it that let itself be read as the whole tree would be off by two
    # orders of magnitude while looking perfectly fine.
    "mp_excerpt": "Both charts below describe the EXCERPT, never the "
                  "repository. `map.txt` is what repo-map renders under a "
                  "character budget and what a subagent is actually handed: it "
                  "keeps the top of the ranking and stops where the budget "
                  "runs out. In it: %s file(s), %s symbol(s), %s character(s).",
    "mp_tracked": "`fingerprints.json` records %s tracked file(s) in all; the "
                  "excerpt names %s of them. The difference is not missing "
                  "work — it is the budget.",
    "mp_plain": "%s file(s) of the excerpt are listed by name only — repo-map "
                "read no symbols from them, or their language has no query "
                "pack — and they are counted in neither chart.",
    "mp_dirs_cap": "The chart draws the %s largest of the %s directories the "
                   "excerpt covers.",
    "mp_top_cap": "The ladder lists the first %s of the %s ranked file(s) in "
                  "the excerpt.",
    "mp_table_dirs": "Table view — density by directory",
    "mp_table_rank": "Table view — the ranking, with whole paths",
    "mp_density": "Symbol density by directory",
    "mp_density_alt": "Bar chart: symbols the map excerpt keeps, per directory",
    "mp_density_axis": "symbols the excerpt keeps, per directory · largest "
                       "first, ties by directory name",
    "mp_rank": "Top of the ranking",
    "mp_rank_alt": "Bar chart: the first files of repo-map's ranking, with the "
                   "symbols the excerpt keeps for each",
    "mp_rank_axis": "in repo-map's OWN order, transcribed and never recomputed "
                    "here: its score is a file's definitions plus the "
                    "references other files make to them. The bar is something "
                    "else — the number of symbols the excerpt kept for that "
                    "file — so the bars are not meant to descend with the rank",
    "th_phase": "Phase", "th_change": "Change", "th_name": "Name", "th_status": "Status",
    "th_requires": "Requires", "th_covers": "Covers", "th_anchor": "Anchor",
    "th_done": "Done", "th_total": "Total", "th_open": "Open",
    "th_model": "Model", "th_input": "New input", "th_output": "Output",
    "th_cache_read": "Cache read", "th_cache_creation": "Cache creation",
    "th_day": "Day", "th_events": "Events", "th_event": "Event",
    "th_tasks": "Tasks", "th_avg": "Average", "th_longest": "Longest",
    "th_task_time": "Time on tasks", "th_when": "When", "th_verdict": "Verdict",
    "th_cases": "Cases", "th_failed": "Failed", "th_duration": "Duration",
    "th_steps": "Steps", "th_captures": "Captures", "th_calls": "Calls",
    "th_fresh": "New input", "th_cache_share": "Cache share",
    "th_attribution": "Attribution", "th_tokens": "Tokens",
    "th_share": "Share", "th_detail": "Detail", "th_dir": "Directory",
    "th_files": "Files", "th_symbols": "Symbols", "th_rank": "Rank",
    "th_file": "File",
    "attr_commit": "commit", "attr_claim": "session claim",
    "attr_mixed": "mixed", "attr_inherited": "inherited",
    "attr_reconcile": "reconciliation", "attr_direct": "direct",
    "attr_missing": "missing",
    "no_breakdown": "%s line(s) with no per-model breakdown",
    "recent": "Latest events",
    # --- the phase report (`summary`) -----------------------------------------
    "s_phase": "phase",
    "s_project": "project",
    "s_no_phase": "no phase to report on — no `workflow:` in STATE.md, no phase "
                  "in the ROADMAP and no CHART under phases/",
    "s_none": "no data",
    "s_tasks": "TASKS",
    "s_done_of": "%s of %s done",
    "s_open": "open",
    "s_no_commit": "closed without a commit",
    "s_closed_no_commit": "(%s closed by approval, no commit by design)",
    "s_commits": "commits: %s recorded in the CHART · %s task_committed event(s) "
                 "in the run log",
    "s_chart_wal_gap": "CHART × WAL discrepancy: %s closed task(s) have no matching claim/commit pair: %s",
    "s_reqs": "REQUIREMENTS",
    "s_proven_of": "%s of %s proven",
    "s_to_prove": "still to prove: %s",
    "s_all_proven": "every requirement of this phase is proven",
    "s_tokens": "TOKENS BY MODEL",
    "s_window": "window %s → %s",
    "s_tagged": "%s capture(s) tagged to this phase",
    "s_total": "total",
    "s_sessions": "SESSIONS",
    "s_sessions_sub": "%s session(s) · %s recorded",
    "s_captures": "%s capture(s)",
    "s_more": "+%s more",
    "s_board": "board: %s",
    "s_board_missing": "board: not generated yet — session start will repair it",
    "u_d": "d", "u_h": "h", "u_m": "m", "u_s": "s", "u_ms": "ms",
}


def load_labels():
    """English defaults, overlaid with the artifact language when we ship one."""
    labels = dict(LABELS)
    cfg = read_json(os.path.join(HELMIT, "config.json")) or {}
    want = cfg.get("artifact_language") or cfg.get("language") or "en"
    if not isinstance(want, str) or not want:
        want = "en"
    labels["lang"] = want
    packs = read_json(os.path.join(SELF_DIR, "dashboard-i18n.json")) or {}
    pack = packs.get(want)
    if not isinstance(pack, dict):
        # `pt` matches a `pt-BR` pack: the base subtag is the useful fallback.
        base = want.split("-")[0].lower()
        for key, value in packs.items():
            if isinstance(key, str) and key.split("-")[0].lower() == base \
                    and isinstance(value, dict):
                pack = value
                break
    if isinstance(pack, dict):
        for k, v in pack.items():
            if k in labels and isinstance(v, str):
                labels[k] = v
    return labels


L = load_labels()


UNFORMATTABLE = set()


def t(key, *args):
    """A label, formatted. The overlay is DATA (ADR-013), and data written by a
    translator can carry one placeholder too many, or a percent sign it forgot
    to double — which used to raise and take the whole render down with a
    traceback. Bad data degrades to the built-in English label instead: the
    board is an aid, never a gate.

    EVERY label goes through the formatting, with arguments or without, because
    that is what gives the overlay ONE rule a translator can actually apply: a
    literal percent is written `%%`, in every label. Short-circuiting the
    argument-less ones would render `%%` as `%%` in the ~115 labels that take no
    arguments, so the rule would hold for some keys and not others — and which
    keys is something the translator cannot see from the file being edited.

    The keys that failed are remembered, not swallowed: degrading is correct,
    doing it in silence is what left a half-translated board with nobody told."""
    s = L.get(key, LABELS.get(key, key))
    try:
        return s % args
    except (TypeError, ValueError):
        UNFORMATTABLE.add(key)
        fallback = LABELS.get(key, key)
        try:
            return fallback % args
        except (TypeError, ValueError):
            return fallback


# --- numbers ------------------------------------------------------------------

def num(n):
    """Grouped integer, in the artifact language's grouping character."""
    return "{:,}".format(int(n)).replace(",", L["num_group"])


def compact(n):
    """Short form for large dashboard magnitudes."""
    n = int(n)
    for limit, suffix in ((1000000000, "c_b"), (1000000, "c_m"), (1000, "c_k")):
        if abs(n) >= limit:
            value = "%.1f" % (n / float(limit))
            return value.replace(".", L["num_decimal"]) + " " + t(suffix)
    return num(n)


def pct(part, whole):
    return 0.0 if not whole else (100.0 * part / float(whole))


def share(part, whole):
    """A ratio as PROSE, in the artifact language's decimal mark. A chart that
    covers a fraction of the record has to print the fraction in words: the
    geometry says "some of it" and only the number says how much."""
    return ("%.1f" % pct(part, whole)).replace(".", L["num_decimal"]) + "%"


def msec(ms):
    """A gate duration, in the unit a person would have used for it. The gate
    records milliseconds and its runs span three orders of magnitude — a suite
    that answers in 380ms and one that takes two minutes are both normal — so
    the unit follows the value. A whole second keeps no decimal, which is what
    makes the axis ticks read as the round numbers they are."""
    ms = max(0, int(ms))
    if ms < 1000:
        return "%s%s" % (num(ms), t("u_ms"))
    if ms < 60000:
        if ms % 1000 == 0:
            return "%s%s" % (num(ms // 1000), t("u_s"))
        return ("%.1f" % (ms / 1000.0)).replace(".", L["num_decimal"]) + t("u_s")
    seconds = ms // 1000
    return "%s%s %02d%s" % (num(seconds // 60), t("u_m"), seconds % 60, t("u_s"))


def nice_scale(top):
    """A round ceiling whose HALF is round too: the axis prints the ceiling and
    its midpoint, so both have to be values a person would have chosen. The
    ladder is 1/2/5 x 10^k, doubled — the same rule for a count of test cases
    and for a duration in milliseconds, because one scale rule per board is one
    thing for the reader to learn."""
    top = max(0, int(top))
    if top <= 0:
        return 2
    unit = 1
    while True:  # 10x per turn: any finite ceiling is reached in a few turns
        for k in (1, 2, 5):
            if 2 * k * unit >= top:
                return 2 * k * unit
        unit *= 10


# --- spans --------------------------------------------------------------------
# Shared by BOTH surfaces (the board's TIME block and the phase report): a span
# printed two ways would be two answers to the same question. Every span here is
# the distance between two RECORDED moments — the wall clock is never one of the
# two ends, which is what keeps an unfinished record from growing a duration.

def dur(seconds):
    """A span in the two coarsest units that still say something."""
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, DAY)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return "%s%s %s%s" % (num(days), t("u_d"), hours, t("u_h"))
    if hours:
        return "%s%s %s%s" % (hours, t("u_h"), minutes, t("u_m"))
    return "%s%s" % (minutes, t("u_m"))


def hours(seconds):
    """A span that never rolls up into days. The question the TIME block
    answers is "how many hours did this cost", and `1d 2h` answers a different
    one — it reads as elapsed calendar time and hides the hours it took. The
    phase report keeps `dur` (a session that ran three days IS three days)."""
    seconds = max(0, int(seconds))
    whole, rest = divmod(seconds, 3600)
    if not whole:
        return "%s%s" % (rest // 60, t("u_m"))
    return "%s%s %s%s" % (num(whole), t("u_h"), rest // 60, t("u_m"))


def span(seconds):
    """A span as an AXIS TICK: whole hours stay whole (`2h`, not `2h 0m`), so
    the scale reads as the round numbers a tick is supposed to carry."""
    seconds = max(0, int(seconds))
    if seconds and seconds % 3600 == 0:
        return "%s%s" % (num(seconds // 3600), t("u_h"))
    return hours(seconds)


def nice_top(seconds):
    """A round ceiling for a time scale. The step coarsens with the magnitude
    (quarter hour, hour, two hours), so the two ticks the axis prints are
    always values a person would have chosen."""
    seconds = max(0, int(seconds))
    if seconds <= 0:
        return 3600
    for limit, step in ((3600, 900), (21600, 3600), (DAY, 7200)):
        if seconds <= limit:
            return ((seconds + step - 1) // step) * step
    # Parallel tasks can make one UTC day exceed 24 hours. Keep the ceiling in
    # twelve-hour steps so both the top and midpoint ticks remain whole hours,
    # while every bar and its direct label stay inside the plot.
    step = 12 * 3600
    return ((seconds + step - 1) // step) * step


def stamp(ts):
    """A timestamp as a person reads it (both logs write UTC)."""
    return (ts or "").replace("T", " ")[:19]


def stamp_epoch(seconds):
    """An epoch second as a person reads it, in UTC — the same shape `stamp`
    prints, so the two never disagree on the board."""
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(seconds)))


def iso_day(seconds):
    """The UTC day a moment falls on. `date.fromtimestamp` would answer in
    LOCAL time, and a board whose days shift when the reader travels is not
    the deterministic artifact the rest of this file is."""
    return (date(1970, 1, 1) + timedelta(days=int(seconds) // DAY)).isoformat()


def day_slices(start, end):
    """Seconds of the window [start, end] falling on each UTC day. A window
    that runs past midnight is SPLIT, never charged whole to the day it
    started on: a daily bar has to add up to the day it names."""
    out = {}
    if end <= start:
        return out
    edge = start - (start % DAY)
    while edge < end:
        nxt = edge + DAY
        piece = min(end, nxt) - max(start, edge)
        if piece > 0:
            out[iso_day(edge)] = piece
        edge = nxt
    return out


def phase_of(task):
    """The phase a task id belongs to: everything before the first dot. The
    correction routes (`corr.REQ-118`) are not roadmap phases and are NOT
    folded into one: they are real recorded work and say so under their own
    name."""
    return (task or "").split(".")[0]


def fold_time(events, roadmap=None):
    """Every duration the board shows, derived from run.jsonl and NOTHING else.

    Three rules decide every number here, and each exists because the
    alternative would invent data:

    * A TASK is the window of one `task_claimed` and the `task_committed` that
      closes it. A commit is paired with the LATEST unmatched claim of the same
      task: a second claim is a RESUMPTION, so the window that produced the
      commit is the one that started after the interruption. Summing both
      windows would charge the task for the dead time between them, and taking
      the first would charge it for an interruption of unknown length.
    * A record with no pair is NEVER closed with the current time. An open
      claim (the task died, or is in flight right now), a commit with no claim
      and a session with no stop are counted APART and declared on the panel.
      Closing them against the clock would turn "still running" into "took this
      long" — a number that grows every time the board is rendered.
    * A SESSION runs from the first event after one `session_stop` to the next
      `session_stop`. The tail after the last stop has no recorded end, so it
      is open by exactly the same rule.
    * MAP events are not session activity and neither open nor extend a
      window. `map_shown` and `map_refreshed` are fired by a COMMAND (`/chart`
      refreshes unconditionally, `/implement` before a wave), not by somebody
      working: a lone refresh anchoring a window would report a session that
      never happened. A stop CLOSES a window and never opens one, which is the
      other half of the same rule — without it the stretch the map events used
      to hold comes back as a session of zero seconds, counted in the tally
      and reported as one more session than there were.

    `roadmap` is optional and only supplies phase NAMES; no figure depends on
    it, so a project with no ROADMAP still gets its time.
    """
    st = {"window": None, "tasks": [], "task_seconds": 0, "open_claims": [],
          "loose_commits": [], "sessions": [], "session_seconds": 0,
          "open_sessions": 0, "by_phase": {}, "per_day": {}, "overlaps": 0}
    dated = [(e, epoch(e["ts"])) for e in events]
    dated = [(e, w) for e, w in dated if w is not None]
    if not dated:
        return st
    st["window"] = (dated[0][0]["ts"], dated[-1][0]["ts"])
    names = {p["id"]: p["name"] for p in (roadmap or [])}

    def slot(pid):
        return st["by_phase"].setdefault(pid, {"name": names.get(pid, ""),
                                               "seconds": 0, "tasks": 0,
                                               "longest": 0, "open": 0})

    pending, segment = {}, None
    for e, when in dated:
        if str(e.get("event") or "").startswith("map_"):
            continue
        if e["event"] == "session_stop":
            if segment is not None:
                st["sessions"].append({"from": segment["from"], "to": e["ts"],
                                       "seconds": max(0, when - segment["at"])})
            segment = None
            continue
        if segment is None:
            segment = {"at": when, "from": e["ts"]}
        if e["event"] == "task_claimed" and e["task"] and not e["task"].startswith("ship."):
            pending.setdefault(e["task"], []).append((e["ts"], when))
        elif e["event"] == "task_committed" and e["task"] and not e["task"].startswith("ship."):
            stack = pending.get(e["task"])
            if stack:
                from_ts, from_at = stack.pop()
                if not stack:
                    del pending[e["task"]]
                st["tasks"].append({"task": e["task"], "from": from_ts,
                                    "to": e["ts"], "at": from_at,
                                    "seconds": max(0, when - from_at)})
            else:
                st["loose_commits"].append({"task": e["task"], "ts": e["ts"]})
    if segment is not None:
        st["open_sessions"] = 1
    for task in sorted(pending):
        for ts, _ in pending[task]:
            st["open_claims"].append({"task": task, "ts": ts})
    st["open_claims"].sort(key=lambda x: (x["ts"], x["task"]))

    st["task_seconds"] = sum(x["seconds"] for x in st["tasks"])
    st["session_seconds"] = sum(x["seconds"] for x in st["sessions"])
    # How many task windows RAN AT THE SAME TIME as another, counted in pairs.
    # `/implement` runs a wave of tasks in parallel, so the sum of the windows
    # is not elapsed time and can exceed the wall clock — the one caveat that
    # makes "time on tasks" readable. It is COUNTED here instead of asserted in
    # prose: a caveat with a measured number beside it is a fact, and one
    # without is a disclaimer the reader has no way to weigh.
    windows = sorted((x["at"], x["at"] + x["seconds"]) for x in st["tasks"])
    for i, (start, end) in enumerate(windows):
        for other_start, _ in windows[i + 1:]:
            if other_start >= end:
                break
            st["overlaps"] += 1
    for x in st["tasks"]:
        bucket = slot(phase_of(x["task"]))
        bucket["seconds"] += x["seconds"]
        bucket["tasks"] += 1
        bucket["longest"] = max(bucket["longest"], x["seconds"])
        for day, piece in day_slices(x["at"], x["at"] + x["seconds"]).items():
            st["per_day"][day] = st["per_day"].get(day, 0) + piece
    for x in st["open_claims"]:
        slot(phase_of(x["task"]))["open"] += 1
    return st


def maybe_count(value):
    """A non-negative whole number from a log field, or None when the field is
    absent or unreadable. `run-log.sh` stores every k=v as a STRING (numeric
    coercion would turn task=14.1 into a float), so the digits arrive quoted;
    an int is accepted too, for a record written by any other hand. MISSING is
    never zero here: a suite whose size was not recorded must not be drawn as a
    suite of no tests."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def fold_tests(events):
    """The commit gate's own record of the suite, oldest first (REQ-176).

    Every figure comes from a `gate_run` line and from nothing else. Three
    rules decide what is shown, and each exists because the alternative would
    invent data:

    * `cases_passed`/`cases_failed` are OPTIONAL by contract. The gate reads
      them from the output of the test command, and every project declares its
      own command, so a suite that summarizes nothing leaves a record with a
      verdict and a duration and NO count. Such a run is counted apart and its
      column is drawn as a GAP — never as zero cases, which would read as a
      suite that ran nothing.
    * A `blocked` verdict is kept and shown. A history that hid the red commits
      would describe a project that never fails, and the blocked runs are the
      most informative half of the record.
    * Nothing is reconstructed for the commits made before the gate started
      recording. The window is printed with the figures, and when there is no
      record at all the block says so instead of rendering an empty plot.
    """
    st = {"runs": [], "passed": 0, "blocked": 0, "uncounted": 0,
          "gate_ms": 0, "timed": 0, "window": None}
    for e in events:
        if e["event"] != "gate_run":
            continue
        row = e["row"]
        verdict = row.get("verdict")
        verdict = verdict if isinstance(verdict, str) else ""
        good = maybe_count(row.get("cases_passed"))
        bad = maybe_count(row.get("cases_failed"))
        # Both halves or neither: half a count is not a count.
        cases = good + bad if good is not None and bad is not None else None
        steps = row.get("steps")
        steps = steps if isinstance(steps, str) else ""
        # Per-step durations, for the tooltip. `steps` lists only what actually
        # ran — a suite that fails never reaches build or lint.
        marks = []
        for name in [s for s in steps.split(",") if s]:
            each = maybe_count(row.get("%s_ms" % name))
            marks.append((name, msec(each) if each is not None else "—"))
        failed_step = row.get("failed_step")
        total = maybe_count(row.get("duration_ms"))
        st["runs"].append({"ts": e["ts"], "verdict": verdict, "cases": cases,
                           "passed": good, "failed": bad, "ms": total,
                           "steps": steps, "marks": marks,
                           "failed_step": failed_step
                           if isinstance(failed_step, str) else ""})
        if verdict == "blocked":
            st["blocked"] += 1
        elif verdict == "passed":
            st["passed"] += 1
        if cases is None:
            st["uncounted"] += 1
        if total is not None:
            st["gate_ms"] += total
            st["timed"] += 1
    if st["runs"]:
        st["window"] = (st["runs"][0]["ts"], st["runs"][-1]["ts"])
    return st


def fold_map(events):
    """The health of the repo map, from the two sources this board already
    reads: the run log, and whether `.helmit/map/` is there at all (REQ-252).

    What this does NOT do is run `repo-map.sh check`. That command is the
    authority on freshness — one sha1 pass over the tracked tree against
    `map/fingerprints.json` — and calling it from here would be a second source
    for a truth that already has one, on four counts: it needs the OPTIONAL
    tree-sitter library, so a machine without it would report `absent` over a
    map sitting on disk; it reads the WORKING TREE, so this render would stop
    being byte-identical over unchanged sources; it costs a full repo hash per
    board; and a renderer that re-derives another hook's verdict will
    eventually disagree with it about the same map. So the verdict is
    TRANSCRIBED: repo-map stamps its own on every `map_shown`, and what is read
    here is the last one it stamped, together with WHEN it stamped it.

    Two derivations, and each is the source's own rule rather than a new one.
    `absent` is read off the disk because repo-map itself calls the map absent
    when there are no fingerprints — a file question, not a hash question. And
    a `map_refreshed` newer than the last stamped verdict is read as `fresh`,
    because refreshing is the act that MAKES it fresh, which is repo-map's own
    documented reason for writing no freshness field on that record.

    A map on disk the log never mentioned has NO recorded verdict, and none is
    invented — the block says so, the way the TESTS block says a run recorded
    no case count."""
    st = {"present": os.path.isdir(os.path.join(HELMIT, "map")),
          "fingerprints": os.path.isfile(os.path.join(HELMIT, "map",
                                                      "fingerprints.json")),
          "refreshed": 0, "shown": 0, "last_refresh": "", "verdict": "",
          "verdict_at": "", "floor": 0, "window": None, "records": []}
    for e in events:
        if e["event"] == "map_refreshed":
            st["refreshed"] += 1
            st["last_refresh"] = e["ts"]
        elif e["event"] == "map_shown":
            st["shown"] += 1
            got = e["row"].get("freshness")
            if isinstance(got, str) and got in MAP_VERDICTS:
                st["verdict"], st["verdict_at"] = got, e["ts"]
        else:
            continue
        st["records"].append(e)
    # Consumption recorded BEFORE any generation ever was. The pair is a FLOOR
    # over that stretch, and this count is what lets the panel say so with a
    # number instead of a disclaimer nobody can weigh.
    first = next((i for i, e in enumerate(st["records"])
                  if e["event"] == "map_refreshed"), len(st["records"]))
    st["floor"] = sum(1 for e in st["records"][:first]
                      if e["event"] == "map_shown")
    if not st["fingerprints"]:
        st["verdict"], st["verdict_at"] = "absent", ""
    elif st["last_refresh"] > st["verdict_at"]:
        st["verdict"], st["verdict_at"] = "fresh", st["last_refresh"]
    if st["records"]:
        st["window"] = (st["records"][0]["ts"], st["records"][-1]["ts"])
    return st


def fold_map_shape():
    """What the map EXCERPT holds, read off the two files repo-map writes.

    Not what the repository holds, and the difference is the whole reason this
    function returns `tracked` alongside the rest. `map.txt` is a render under a
    CHARACTER BUDGET (4000 by default): it carries the top of repo-map's ranking
    and stops mid-list the moment the budget runs out, so every count here
    describes that excerpt. Measured on this repo the day it was written: 5648
    files fingerprinted, a few dozen in the excerpt. A density chart drawn from
    it and captioned as the repository would be off by two orders of magnitude
    while reading perfectly, which is worse than drawing nothing.

    The ranking is TRANSCRIBED, never recomputed. The order the files appear in
    IS repo-map's ranking — own definitions plus the references its identifiers
    receive from other files — and re-deriving that formula here would be a
    second implementation of it, free to drift from the one that wrote the file,
    exactly as a re-run `check` would drift from the recorded verdict. The
    fingerprints hold every `defs` list and the score could be rebuilt from
    them; it deliberately is not.

    `fingerprints.json` answers the one question `map.txt` cannot: how many
    files repo-map tracked at all. That is the number the excerpt is a slice of.

    Fail-open like every reader here: no file, no section. The parser cannot
    raise on a malformed line either — it skips what it does not recognise."""
    st = {"files": [], "dirs": [], "symbols": 0, "plain": 0, "tracked": 0,
          "chars": 0}
    text = read_text(os.path.join(HELMIT, "map", "map.txt"))
    fp = read_json(os.path.join(HELMIT, "map", "fingerprints.json"))
    tracked = fp.get("files") if isinstance(fp, dict) else None
    if isinstance(tracked, dict):
        st["tracked"] = len(tracked)
    if not text:
        return st
    st["chars"] = len(text)
    lines = text.split("\n")
    cut = lines.index(MAP_PLAIN_MARK) if MAP_PLAIN_MARK in lines else len(lines)
    st["plain"] = sum(1 for line in lines[cut + 1:] if line.startswith("  ")
                      and line.strip())
    for line in lines[:cut]:
        if MAP_SYMBOL.match(line):
            if st["files"]:
                st["files"][-1][1] += 1
                st["symbols"] += 1
        elif line and not line.startswith(" ") and line.endswith(":"):
            st["files"].append([line[:-1], 0])
    per_dir = {}
    for rel, count in st["files"]:
        # A file at the top level has no dirname; `.` is the directory it is in,
        # in the same relative-path convention every other name here uses.
        slot = per_dir.setdefault(os.path.dirname(rel) or ".", [0, 0])
        slot[0] += 1
        slot[1] += count
    # Magnitude order, and the tie broken by NAME: two directories with the same
    # symbol count must land in the same places on every render, and dict order
    # is the order the excerpt happened to be written in, not a rule.
    st["dirs"] = sorted(((name, per_dir[name][0], per_dir[name][1])
                         for name in per_dir), key=lambda r: (-r[2], r[0]))
    st["files"] = [(rel, count) for rel, count in st["files"]]
    return st


# --- palette ------------------------------------------------------------------
# Every value below comes from the validated reference palette of the `dataviz`
# skill (blue ramp + orange accent), and every ramp used here was checked with
# that skill's validator: the 5-step phase ramp and the 3-step REQ ramp both
# pass the ordinal gate (monotone lightness, adjacent dL >= 0.06, the step
# nearest the surface clearing 2:1) in light AND dark, and the blue/orange pair
# passes the categorical gate in both. The skill guided the EXECUTION; nothing
# of it is embedded in the plugin beyond these hex values.

INK_LIGHT, INK_DARK = "#0b0b0b", "#ffffff"
# Ordinal blue steps, light surface: light -> dark as the phase matures.
PHASE_LIGHT = {"todo": "#86b6ef", "spec": "#5598e7", "planned": "#2a78d6",
               "shipped": "#1c5cab", "validated": "#104281",
               "implementing": "#eb6834"}
# The same ladder re-stepped for the dark surface (dark -> light), not flipped.
PHASE_DARK = {"todo": "#184f95", "spec": "#256abf", "planned": "#3987e5",
              "shipped": "#6da7ec", "validated": "#9ec5f4",
              "implementing": "#d95926"}
REQ_LIGHT = {"todo": "#86b6ef", "covered": "#2a78d6", "proven": "#104281"}
REQ_DARK = {"todo": "#184f95", "covered": "#3987e5", "proven": "#9ec5f4"}
# The four token types are an IDENTITY set (input, output, cache read, cache
# creation), not a magnitude, so they take the skill's categorical theme in its
# FIXED slot order — blue, orange, aqua, yellow — never cycled and never
# re-ordered per chart. Validated as a 4-slot set against THIS board's own
# surfaces: adjacent CVD dE 9.1 light / 8.4 dark (target >= 8) and adjacent
# normal-vision dE 22.9 / 19.8 (floor >= 15), all four inside the lightness band
# and above the chroma floor. Light mode WARNS on contrast for aqua and yellow,
# which is not dismissable: it obliges the relief rule, and this block ships
# BOTH reliefs — a legend carrying every value and a table twin — so no segment
# ever depends on its color alone.
TOKEN_LIGHT = {"input_tokens": "#2a78d6", "output_tokens": "#eb6834",
               "cache_read_tokens": "#1baf7a", "cache_creation_tokens": "#eda100"}
TOKEN_DARK = {"input_tokens": "#3987e5", "output_tokens": "#d95926",
              "cache_read_tokens": "#199e70", "cache_creation_tokens": "#c98500"}
# Which label names each token type. The header labels are reused on purpose:
# the legend and the table twin must say the SAME word for the same thing.
FIELD_LABEL = {"input_tokens": "th_input", "output_tokens": "th_output",
               "cache_read_tokens": "th_cache_read",
               "cache_creation_tokens": "th_cache_creation"}

# `bad` is the RESERVED status step (critical), never themed and never used for
# anything but a losing verdict — a status hue that doubles as a series stops
# meaning anything. It is the only status step on the board: the `passed` side
# deliberately wears the board's own data hue instead of the green of the status
# scale, because green-vs-red collapses under deuteranopia (the skill's
# validator measures that pair at dE 4.1 in BOTH modes, a hard fail) while
# blue-vs-red clears every gate (23.8 light / 25.7 dark, contrast >= 3:1 on both
# surfaces). The word `passed` or `blocked` is printed beside every mark anyway
# — a status color never carries the meaning alone.
CHROME_LIGHT = {
    "page": "#f9f9f7", "surface": "#fcfcfb", "ink": INK_LIGHT, "ink2": "#52514e",
    "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
    "border": "rgba(11,11,11,0.10)", "fill": "#2a78d6", "track": "#cde2fb",
    "accent": "#eb6834", "neutral": "#c3c2b7", "bad": "#d03b3b",
    "tip-bg": "#0b0b0b", "tip-ink": "#fcfcfb", "scheme": "light",
}
CHROME_DARK = {
    "page": "#0d0d0d", "surface": "#1a1a19", "ink": INK_DARK, "ink2": "#c3c2b7",
    "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
    "border": "rgba(255,255,255,0.10)", "fill": "#3987e5", "track": "#0d366b",
    "accent": "#d95926", "neutral": "#383835", "bad": "#d03b3b",
    "tip-bg": "#fcfcfb", "tip-ink": "#0b0b0b", "scheme": "dark",
}


def _channel(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ink_on(fill):
    """Whichever of ink/paper contrasts more on `fill` — a label set inside a
    colored mark is the one place text may leave the text tokens, and it must
    always clear contrast."""
    lf = _luminance(fill)

    def ratio(other):
        lo, hi = sorted((lf, _luminance(other)))
        return (hi + 0.05) / (lo + 0.05)

    return INK_LIGHT if ratio(INK_LIGHT) >= ratio(INK_DARK) else INK_DARK


def short_field(field):
    """`input_tokens` -> `input`: the CSS custom property and the class both
    wear the type's own name, so the markup says which slot a segment is."""
    return field[:-len("_tokens")] if field.endswith("_tokens") else field


def theme_vars(chrome, phase_map, req_map, token_map):
    out = ["color-scheme: %s;" % chrome["scheme"]]
    for key, value in chrome.items():
        if key != "scheme":
            out.append("--%s: %s;" % (key, value))
    for status in PHASE_LADDER:
        fill = phase_map[status]
        out.append("--ph-%s: %s;" % (status, fill))
        out.append("--ph-%s-ink: %s;" % (status, ink_on(fill)))
    out.append("--ph-other: %s;" % chrome["neutral"])
    out.append("--ph-other-ink: %s;" % ink_on(chrome["neutral"]))
    for status in REQ_LADDER:
        fill = req_map[status]
        out.append("--rq-%s: %s;" % (status, fill))
        out.append("--rq-%s-ink: %s;" % (status, ink_on(fill)))
    for field in TOKEN_FIELDS:
        out.append("--tk-%s: %s;" % (short_field(field), token_map[field]))
    return "\n    ".join(out)


# --- html helpers -------------------------------------------------------------

def h(value):
    return html.escape("" if value is None else str(value), quote=True)


def tip(value):
    """Attribute-safe multi-line tooltip text."""
    return h(value).replace("\n", "&#10;")


def shorten(text, cap):
    text = " ".join((text or "").split())
    return text if len(text) <= cap else text[:cap].rstrip() + "…"


def card(block, title, subtitle, body):
    return ("<section class=\"card\" data-block=\"%s\">\n"
            "<h2>%s</h2>\n<p class=\"sub\">%s</p>\n%s</section>\n"
            % (h(block), h(title), h(subtitle), body))


def empty():
    return "<p class=\"empty\">%s</p>\n" % h(t("empty"))


def plot_frame(y_title, ticks, rule, columns):
    """The plot every time series on this board is drawn in: a TITLED vertical
    axis, a stepped scale carrying VALUES, two hairline gridlines to read them
    against, an optional annotation rule and the columns themselves.

    One anatomy, shared: the reader learns to read the plot once and every
    series answers the same questions in the same places. It is a 3-column grid
    (axis title, tick values, plot area) so the ticks stay glued to the
    gridlines they name at any width."""
    return ("<div class=\"plot\"><span class=\"ylab\">%s</span>"
            "<div class=\"yaxis\">%s</div>"
            "<div class=\"area\">%s%s<div class=\"cols\">%s</div></div></div>\n"
            % (h(y_title),
               "".join("<span>%s</span>" % h(v) for v in ticks),
               "<span class=\"gl\" style=\"bottom:100%\"></span>"
               "<span class=\"gl\" style=\"bottom:50%\"></span>",
               rule, "".join(columns)))


def ref_rule(share, label):
    """A reference value as an ANNOTATION, not a series: it wears a text token,
    never a data hue, and carries its own label so it never depends on the
    legend alone."""
    return ("<span class=\"ref\" style=\"bottom:%.1f%%\"><b>%s</b></span>"
            % (share, h(label)))


def col_label(text, height, side):
    """ONE direct label, on the extreme — a value over every column is chaos
    and goes unread. It is anchored to the side of its own column that keeps it
    inside the card instead of centred and clipped."""
    return ("<span class=\"cval %s\" style=\"bottom:%.1f%%\">%s</span>"
            % (side, height, h(text)))


def label_side(index, total):
    """Which edge of its column a direct label hangs from."""
    if index * 3 < total:
        return "start"
    return "end" if index * 3 >= total * 2 else "mid"


def column(detail, mark, label=""):
    return ("<span class=\"col\" tabindex=\"0\" data-tip=\"%s\">%s%s</span>"
            % (tip(detail), label, mark))


def bar(height, extra=""):
    return ("<span class=\"cbar%s\" style=\"height:%.1f%%\"></span>"
            % (extra, height))


def details_table(head, rows, extra_class="", label=""):
    """The table twin every block carries: the values a tooltip shows are
    always reachable without hovering.

    `label` names the twin when a block carries more than one of them — three
    collapsed summaries all reading "Table view" tell a reader nothing about
    which table is under which."""
    out = ["<details class=\"tv\"><summary>%s</summary><div class=\"tw\">"
           % h(label or t("table")), "<table class=\"%s\"><thead><tr>"
           % h(extra_class)]
    for col in head:
        out.append("<th>%s</th>" % h(col))
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % c for c in row) + "</tr>")
    out.append("</tbody></table></div></details>\n")
    return "".join(out)


# The geometry of the inline SVG charts, in user units of their own viewBox: a
# name column, a plot column, a value column, over a 1000-unit canvas that is
# about the inner width of a card, so the chart is roughly 1:1 on a wide screen
# and scales down whole on a narrow one.
SVG_W, SVG_NAME, SVG_BAR, SVG_GAP = 1000, 340, 560, 12
SVG_ROW, SVG_BARH = 26, 12


def svg_bars(caption, rows):
    """A ranked horizontal bar chart, INLINE, in the page's own colors.

    SVG and not the div plot the other charts here use, because these rows are
    labelled on BOTH sides — a repository path on the left, its count on the
    right — which is a shape the column plot was never built for.

    Self-contained by decision (REQ-253): no `<image>`, no `xlink:href`, no
    stylesheet and no font from anywhere else. The board is one file a person
    opens over `file://`, frequently with no network at all, and a chart that
    fetched anything would be a blank rectangle everywhere but the machine that
    drew it. The colors come from the page's own CSS custom properties, so both
    themes are the validated ones the rest of the board already wears.

    Every value is DRAWN, beside its bar, rather than hidden in a tooltip. Not a
    style choice: this board's tooltip is a CSS `::after` on a data attribute,
    and generated content does not render inside SVG — so a value put there
    would be reachable by nobody. Which is the rule anyway (REQ-178): a value
    nobody can reach without a pointer is a value the board did not publish.

    `rows` are (label, value text, magnitude), already in the order they are to
    be drawn. This function never re-sorts them: one of the two charts is drawn
    in an order that is NOT its magnitude, and a helper that quietly sorted
    would silently turn that chart into a lie."""
    height = SVG_ROW * len(rows) + 6
    peak = max([n for _, _, n in rows] + [0]) or 1
    out = ["<svg class=\"mapsvg\" role=\"img\" viewBox=\"0 0 %d %d\">"
           "<title>%s</title>" % (SVG_W, height, h(caption))]
    for i, (label, value, count) in enumerate(rows):
        top = SVG_ROW * i
        base, bar = top + 20, top + (SVG_ROW - SVG_BARH) // 2
        out.append("<text class=\"sname\" x=\"0\" y=\"%d\">%s</text>"
                   "<rect class=\"strack\" x=\"%d\" y=\"%d\" width=\"%d\""
                   " height=\"%d\" rx=\"4\"/>"
                   % (base, h(label), SVG_NAME + SVG_GAP, bar, SVG_BAR,
                      SVG_BARH))
        if count > 0:
            # A floor of 3 units under a rounded end: a directory with one
            # symbol beside one with two hundred must still be VISIBLE as a
            # mark, or the chart drops the row it just claimed to draw.
            out.append("<rect class=\"sbar\" x=\"%d\" y=\"%d\" width=\"%.1f\""
                       " height=\"%d\" rx=\"4\"/>"
                       % (SVG_NAME + SVG_GAP, bar,
                          max(3.0, SVG_BAR * count / float(peak)), SVG_BARH))
        out.append("<text class=\"sval\" x=\"%d\" y=\"%d\""
                   " text-anchor=\"end\">%s</text>" % (SVG_W, base, h(value)))
    out.append("</svg>\n")
    return "".join(out)


# --- blocks -------------------------------------------------------------------

def block_phases(phases):
    if not phases:
        return card("phases", t("b_phases"), t("b_phases_sub"), empty())
    counts = {}
    for p in phases:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    tiles = []
    for p in phases:
        known = p["status"] in PHASE_LADDER
        klass = "ph ph-%s" % (p["status"] if known else "other")
        detail = "%s %s · %s\n%s: %s\n%s: %s\n%s: %s" % (
            t("th_phase"), p["id"], p["name"],
            t("th_status"), p["status"],
            t("th_requires"), p["requires"] or "—",
            t("th_covers"), p["covers"] or "—")
        if p["anchor"]:
            detail += "\n\n" + shorten(p["anchor"], ANCHOR_CAP)
        tiles.append("<div class=\"%s\" tabindex=\"0\" data-tip=\"%s\">%s</div>"
                     % (klass, tip(detail), h(p["id"])))
    legend = []
    for status in PHASE_LADDER:
        if counts.get(status):
            legend.append("<li><span class=\"key ph-%s\"></span>%s<b>%s</b></li>"
                          % (h(status), h(status), num(counts[status])))
    for status in sorted(s for s in counts if s not in PHASE_LADDER):
        legend.append("<li><span class=\"key ph-other\"></span>%s<b>%s</b></li>"
                      % (h(status), num(counts[status])))
    rows = [(h(p["id"]), h(p["name"]), h(p["status"]), h(p["requires"]),
             h(p["covers"]), h(shorten(p["anchor"], 400))) for p in phases]
    body = ("<div class=\"strip\">%s</div>\n<ul class=\"legend\">%s</ul>\n%s"
            % ("".join(tiles), "".join(legend),
               details_table([t("th_phase"), t("th_name"), t("th_status"),
                              t("th_requires"), t("th_covers"), t("th_anchor")],
                             rows)))
    return card("phases", t("b_phases"), t("b_phases_sub"), body)


def block_tasks(phases, charts):
    if not charts:
        return card("tasks", t("b_tasks"), t("b_tasks_sub"), empty())
    order = [p["id"] for p in phases if p["id"] in charts]
    order += [pid for pid in sorted(charts) if pid not in order]
    meters, rows = [], []
    for pid in order:
        tasks = charts[pid]
        done = sum(1 for x in tasks if x["state"] == "done")
        total = len(tasks)
        name = next((p["name"] for p in phases if p["id"] == pid), "")
        open_titles = [x["id"] + " " + x["title"] for x in tasks if x["state"] != "done"]
        detail = "%s %s · %s\n%s: %s/%s" % (t("th_phase"), pid, name,
                                            t("th_done"), num(done), num(total))
        if open_titles:
            detail += "\n" + t("th_open") + ":\n" + "\n".join(
                shorten(x, 70) for x in open_titles[:6])
        meters.append(
            "<div class=\"mrow\" tabindex=\"0\" data-tip=\"%s\">"
            "<span class=\"mid\">%s</span>"
            "<span class=\"mname\">%s</span>"
            "<span class=\"meter\"><span class=\"mfill\" style=\"width:%.1f%%\"></span></span>"
            "<span class=\"mval\">%s/%s</span></div>"
            % (tip(detail), h(pid), h(shorten(name, 42)), pct(done, total),
               num(done), num(total)))
        rows.append((h(pid), h(name), h(num(done)), h(num(total)),
                     h(num(total - done))))
    body = ("<div class=\"meters\">%s</div>\n%s"
            % ("".join(meters),
               details_table([t("th_phase"), t("th_name"), t("th_done"),
                              t("th_total"), t("th_open")], rows, "numeric")))
    return card("tasks", t("b_tasks"), t("b_tasks_sub"), body)


def block_reqs(reqs):
    if not reqs:
        return card("reqs", t("b_reqs"), t("b_reqs_sub"), empty())
    counts = {}
    for r in reqs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    total = len(reqs)
    segments, legend = [], []
    ordered = [s for s in REQ_LADDER if counts.get(s)]
    ordered += sorted(s for s in counts if s not in REQ_LADDER)
    for status in ordered:
        n = counts[status]
        share = pct(n, total)
        known = status in REQ_LADDER
        # A label only goes INSIDE the segment when it plainly fits; below that
        # the segment stays clean and the value is read from the legend/table.
        inner = ("<span class=\"segl\">%s</span>" % h(num(n))) if share >= 12 else ""
        segments.append(
            "<span class=\"seg %s\" style=\"width:%.2f%%\" tabindex=\"0\" "
            "data-tip=\"%s: %s (%.1f%%)\">%s</span>"
            % ("rq-%s" % status if known else "rq-other", share,
               h(status), num(n), share, inner))
        legend.append("<li><span class=\"key %s\"></span>%s<b>%s</b></li>"
                      % ("rq-%s" % h(status) if known else "rq-other",
                         h(status), num(n)))
    by_phase = {}
    for r in reqs:
        slot = by_phase.setdefault(r["phase"] or "—", {})
        slot[r["status"]] = slot.get(r["status"], 0) + 1
    rows = []
    for phase in sorted(by_phase, key=lambda s: (len(s), s)):
        slot = by_phase[phase]
        rows.append((h(phase), h(num(sum(slot.values()))),
                     h(num(slot.get("todo", 0))), h(num(slot.get("covered", 0))),
                     h(num(slot.get("proven", 0)))))
    body = ("<div class=\"stack\">%s</div>\n<ul class=\"legend\">%s</ul>\n%s"
            % ("".join(segments), "".join(legend),
               details_table([t("th_phase"), t("th_total"), "todo", "covered",
                              "proven"], rows, "numeric")))
    return card("reqs", t("b_reqs"), t("b_reqs_sub"), body)


def block_tests(tests):
    """What task verification did, from the gate's own record (REQ-176).

    The gate writes one `gate_run` per agent commit it checks. A task verify may
    report case counts; the quick floor does not invent them. Full-suite proof
    now lives in quality receipts at wave, validation, and ship boundaries.

    TWO MEASURES, TWO PLOTS. Cases and milliseconds share no scale, and putting
    them on one plot with two axes would invent a correlation the data does not
    contain (the single worst thing a chart can do). They are drawn instead as
    small multiples over the SAME x — one slot per recorded run, same order,
    same width — so "the gate costs more as the suite grows" is read by
    comparing two shapes that line up, which is a claim the reader makes and
    not one the chart forges.

    The source bias is printed on the panel: only agent commits pass through
    the writer. The second, git-native layer is intentionally invisible here;
    it repeats only quick staged guards and never the product suite.
    """
    runs = tests["runs"]
    if not runs:
        # Not `empty()`: a bare "no data yet" under a TESTS heading reads as a
        # project with no tests, which is a different and much worse claim.
        # The absence is stated WITH its reason and carries no number at all.
        return card("tests", t("b_tests"), t("b_tests_sub_none"),
                    "<p class=\"empty\">%s</p>\n" % h(t("tst_none")))
    shown = runs[-TEST_RUNS:]
    last = runs[-1]
    kind = last["verdict"] if last["verdict"] in ("passed", "blocked") else "other"
    badge = ("<span class=\"key vd-%s\"></span>%s"
             % (h(kind), h(last["verdict"] or "—")))
    if last["cases"] is None:
        head, tail = "—", t("f_last_none", stamp(last["ts"]))
    else:
        head = num(last["cases"])
        tail = t("f_last_sub", num(last["failed"]), stamp(last["ts"]))
    figs = ("<div class=\"fig\" tabindex=\"0\" data-tip=\"%s\">"
            "<p class=\"lbl\">%s</p><p class=\"big\">%s</p>"
            "<p class=\"lbl\">%s · %s</p></div>"
            "<div class=\"fig\" tabindex=\"0\" data-tip=\"%s\">"
            "<p class=\"lbl\">%s</p><p class=\"big\">%s</p>"
            "<p class=\"lbl\">%s</p></div>"
            % (tip(t("f_last_tip")), h(t("f_last")), h(head), badge, h(tail),
               tip(t("f_runs_tip", num(tests["timed"]))), h(t("f_runs")),
               h(num(len(runs))),
               h(t("f_runs_sub", num(tests["passed"]), num(tests["blocked"]),
                   msec(tests["gate_ms"])))))
    notes = ["<p class=\"note\">%s</p>" % h(t("tst_bias")),
             "<p class=\"note\">%s</p>" % h(t("tst_double"))]
    if tests["uncounted"]:
        notes.append("<p class=\"note\">%s</p>"
                     % h(t("tst_nocount", num(tests["uncounted"]))))

    def caption():
        text = "%s — %s · %s" % (stamp(shown[0]["ts"]), stamp(shown[-1]["ts"]),
                                 t("tst_axis_x"))
        if len(runs) > len(shown):
            text += " · " + t("last_runs", num(len(shown)))
        return "<p class=\"axis\">%s</p>\n" % h(text)

    def key(name, label, value):
        return ("<li><span class=\"key %s\"></span>%s<b>%s</b></li>"
                % (h(name), h(label), h(value)))

    def series(pick, unit, y_title, direct, rule_of, first_key):
        """One plot: the value `pick` reads off each run, on its own scale.

        Every recorded run keeps its slot even when it has no value — the two
        plots only line up if they have the same x — and a slot with nothing to
        show gets a MUTED STUB at the baseline, which reads as "not recorded"
        instead of as a value of zero."""
        values = [pick(r) for r in shown]
        have = [v for v in values if v is not None]
        if not have:
            return ""
        top = nice_scale(max(have))
        marked = direct(values)
        columns = []
        for i, r in enumerate(shown):
            value, extra = values[i], ""
            detail = "%s: %s\n%s: %s" % (t("th_when"), stamp(r["ts"]),
                                         t("th_verdict"), r["verdict"] or "—")
            if r["failed_step"]:
                detail += " (%s)" % r["failed_step"]
            if r["cases"] is None:
                detail += "\n%s: %s" % (t("th_cases"), t("tst_no_value"))
            else:
                detail += "\n%s: %s\n%s: %s" % (t("th_cases"), num(r["cases"]),
                                                t("th_failed"), num(r["failed"]))
            detail += "\n%s: %s" % (t("th_duration"),
                                    msec(r["ms"]) if r["ms"] is not None
                                    else t("tst_no_value"))
            for name, each in r["marks"]:
                detail += "\n%s: %s" % (name, each)
            if value is None:
                mark = "<span class=\"nub\"></span>"
                height = 0.0
            else:
                height = max(pct(value, top), 1.5)
                if r["verdict"] == "blocked":
                    extra = " bad"
                mark = bar(height, extra)
            label = ""
            if i == marked and value is not None:
                label = col_label(unit(value), height, label_side(i, len(shown)))
            columns.append(column(detail, mark, label))
        rule, legend_ref = rule_of(have, top)
        # The legend counts the MARKS that are on this plot, not the runs by
        # verdict: a run whose value was not recorded is drawn as a stub, and
        # counting it under its verdict too would make the keys add up to more
        # slots than the plot has.
        drawn = [(values[i], shown[i]["verdict"]) for i in range(len(shown))]
        missing = sum(1 for v, _ in drawn if v is None)
        legend = [key("kbar", t("lg_pass"),
                      num(sum(1 for v, vd in drawn
                              if v is not None and vd != "blocked"))),
                  key("kbad", t("lg_block"),
                      num(sum(1 for v, vd in drawn
                              if v is not None and vd == "blocked")))]
        if missing:
            legend.append(key("knub", t("lg_nub"), num(missing)))
        if legend_ref:
            legend.append(key("kref", legend_ref[0], legend_ref[1]))
        return ("<h3>%s</h3>\n%s%s<ul class=\"legend\">%s</ul>\n"
                % (h(first_key), plot_frame(y_title, (unit(top), unit(top // 2), "0"),
                                            rule, columns),
                   caption(), "".join(legend)))

    def last_marked(values):
        """The direct label of the suite plot rides the LAST recorded value:
        the question the reader arrives with is how big the suite is NOW."""
        for i in range(len(values) - 1, -1, -1):
            if values[i] is not None:
                return i
        return -1

    def peak_marked(values):
        """The duration plot labels its PEAK: the slowest gate is the one that
        costs a person their patience, and the one that eventually times out."""
        best, at = None, -1
        for i, v in enumerate(values):
            if v is not None and (best is None or v > best):
                best, at = v, i
        return at

    def first_rule(have, top):
        """The suite plot's annotation is the FIRST recorded size, not an
        average: the question is whether the suite is growing, and a baseline
        answers it where a mean of the two ends does not."""
        if len(have) < 2:
            return "", None
        return (ref_rule(pct(have[0], top), "%s %s" % (t("tst_first"), num(have[0]))),
                (t("tst_first"), num(have[0])))

    def mean_rule(have, top):
        if len(have) < 2:
            return "", None
        mean = sum(have) // len(have)
        return (ref_rule(pct(mean, top), "%s %s" % (t("lg_avg"), msec(mean))),
                (t("tst_ref_avg", num(len(shown))), msec(mean)))

    rows = []
    for r in shown:
        rows.append((h(stamp(r["ts"])),
                     h((r["verdict"] or "—")
                       + (" (%s)" % r["failed_step"] if r["failed_step"] else "")),
                     h(num(r["cases"]) if r["cases"] is not None else "—"),
                     h(num(r["failed"]) if r["failed"] is not None else "—"),
                     h(msec(r["ms"]) if r["ms"] is not None else "—"),
                     h(r["steps"] or "—")))
    body = ("<div class=\"figs\">%s</div>\n%s%s%s%s"
            % (figs, "".join(notes),
               series(lambda r: r["cases"], num, t("tst_axis_cases"),
                      last_marked, first_rule, t("tst_suite")),
               series(lambda r: r["ms"], msec, t("tst_axis_ms"),
                      peak_marked, mean_rule, t("tst_cost")),
               details_table([t("th_when"), t("th_verdict"), t("th_cases"),
                              t("th_failed"), t("th_duration"), t("th_steps")],
                             rows)))
    return card("tests", t("b_tests"),
                t("b_tests_sub", stamp(tests["window"][0]),
                  stamp(tests["window"][1])), body)


def coverage(part, whole, text):
    """How much of the record the chart below actually covers — a single ratio
    against its limit, so it is drawn as a METER and never as a series.

    A chart that plots a fraction of the data and does not say so lets that
    fraction read as the whole, which is the one failure worse than having no
    chart. The unattributed remainder is deliberately NOT a bar of its own
    here: on the real record it runs an order of magnitude past the largest
    phase, and a bar that size flattens every other bar into a sliver and
    destroys the comparison the chart exists for. It is a ratio, so it is
    drawn as a ratio — and printed in words beside it, because the geometry
    says "some of it" and only the number says how much."""
    return ("<div class=\"cov\">"
            "<span class=\"meter\"><span class=\"mfill\" style=\"width:%.1f%%\">"
            "</span></span><p class=\"note\">%s</p></div>\n"
            % (pct(part, whole), h(text)))


def block_tokens(metrics, rows, phases):
    """One block with composition, phase, change, and unassigned views (REQ-177).

    The block used to be a lone figure. With a single model in the record a
    bar chart of one bar encodes nothing the number does not already say, so
    the bar was dropped — and the block went blind. Plotting a bar per model
    is not the fix either; the fix is that the record has FOUR categories the
    reader can actually see a composition in (input, output, cache read, cache
    creation). One stacked bar per model reads as a composition when there is
    one model and as a comparison when there are several, so a single form
    answers both cases and neither of them is a lone bar.

    The phase chart answers what each PHASE cost. Composition, phase, and
    change views each describe a part of the record, so their coverage is
    drawn and written. Unassigned work has its own table.

    The REQ-167 rule stands untouched: a line with no `models` key feeds the
    totals, is counted and declared, and is NEVER attributed to a model. The
    same rule now governs the phase: a line with no `phase` and no `task` is
    counted apart, never charged to a neighbour's phase.
    """
    grand = sum(metrics["totals"][k] for k in TOKEN_FIELDS)
    if not metrics["captures"] and not grand:
        return card("tokens", t("b_tokens"), t("b_tokens_sub"), empty())

    # What this record is known to UNDERCOUNT (REQ-242) opens the block, above
    # both charts: the frozen sums are missing from the GRAND TOTAL, so they
    # qualify every figure here and not the attribution of one chart — the same
    # block-wide role `tst_bias` and `tst_double` play in the TESTS block.
    #
    # The note can AGE OUT because it names a closed period and this block
    # windows nothing: its slice is the whole of metrics.jsonl, so it speaks
    # exactly while a capture from that period is still in the file and goes
    # silent when none is left — the conditional speech `tk_phase_inherited`
    # already follows. A capture with no readable date is NOT claimed for the
    # period: attributing what the record does not carry is the one thing this
    # board never does, even to widen a confession.
    stale = sum(1 for row in rows
                if isinstance(row.get("ts"), str) and len(row["ts"]) >= 10
                and row["ts"][:10] <= UNDERCOUNT_THROUGH)
    undercount = ""
    if stale:
        undercount = ("<p class=\"note\">%s</p>"
                      % h(t("tk_undercount", num(stale), UNDERCOUNT_THROUGH)))

    models = metrics["models"]
    totals = {name: sum(b[k] for k in TOKEN_FIELDS) for name, b in models.items()}
    order = sorted(totals, key=lambda n: (-totals[n], n))
    attributed = sum(totals.values())
    top = max(totals.values()) if totals else 0

    marks, trows = [], []
    for name in order:
        b = models[name]
        detail = "%s: %s\n%s: %s\n%s: %s\n%s: %s\n%s: %s\n%s: %s" % (
            t("th_model"), name,
            t("th_input"), compact(b["input_tokens"]),
            t("th_output"), compact(b["output_tokens"]),
            t("th_cache_read"), compact(b["cache_read_tokens"]),
            t("th_cache_creation"), compact(b["cache_creation_tokens"]),
            t("th_total"), compact(totals[name]))
        # No inline label on a segment: an INTERIOR stack segment has no free
        # end to hang one from, and a clipped label is worse than none. The
        # legend, the tooltip and the table twin carry every value.
        segments = "".join(
            "<span class=\"sseg tk-%s\" style=\"width:%.2f%%\"></span>"
            % (h(short_field(field)), pct(b[field], top or 1))
            for field in TOKEN_FIELDS if b[field] > 0)
        marks.append("<div class=\"srow\" tabindex=\"0\" data-tip=\"%s\">"
                     "<span class=\"bname\">%s</span>"
                     "<span class=\"sbar\">%s</span>"
                     "<span class=\"bval\">%s</span></div>"
                     % (tip(detail), h(name), segments,
                        h(compact(totals[name]))))
        trows.append((h(name), h(compact(b["input_tokens"])),
                      h(compact(b["output_tokens"])), h(compact(b["cache_read_tokens"])),
                      h(compact(b["cache_creation_tokens"])), h(compact(totals[name]))))
    # What the models do NOT account for, per type: the totals minus what the
    # buckets carry. Derived, never guessed — and it is a ROW of the table, so
    # the columns add up to the grand total instead of quietly falling short.
    rest = {k: metrics["totals"][k] - sum(models[n][k] for n in order)
            for k in TOKEN_FIELDS}
    trows.append((h(t("tk_unattr")),)
                 + tuple(h(compact(rest[k])) for k in TOKEN_FIELDS)
                 + (h(compact(sum(rest.values()))),))
    trows.append((h(t("s_total")),)
                 + tuple(h(compact(metrics["totals"][k])) for k in TOKEN_FIELDS)
                 + (h(compact(grand)),))
    legend = "".join(
        "<li><span class=\"key tk-%s\"></span>%s<b>%s</b></li>"
        % (h(short_field(field)), h(t(FIELD_LABEL[field])),
           compact(sum(models[n][field] for n in order)))
        for field in TOKEN_FIELDS if sum(models[n][field] for n in order) > 0)
    notes = ""
    if metrics["no_breakdown"]:
        notes = ("<p class=\"note\">%s</p>"
                 % h(t("no_breakdown", num(metrics["no_breakdown"]))))
    composition = (
        "<h3>%s</h3>\n%s<div class=\"bars\">%s</div>\n"
        "<ul class=\"legend\">%s</ul>\n%s%s"
        % (h(t("tk_composition")),
           coverage(attributed, grand,
                    t("tk_cover_model", compact(attributed), compact(grand),
                      share(attributed, grand))),
           "".join(marks), legend, notes,
           details_table([t("th_model"), t("th_input"), t("th_output"),
                          t("th_cache_read"), t("th_cache_creation"),
                          t("th_total")], trows, "numeric")))

    # Magnitude, one hue, ordered by weight — the same mark the TIME block uses
    # for its own per-phase answer, because it is the same question asked of a
    # different unit, and one anatomy per board is one thing to learn.
    clock = fold_phase_tokens(rows, phases)
    total_usage = {
        "tokens": grand,
        "fresh": metrics["totals"]["input_tokens"]
                 + metrics["totals"]["cache_creation_tokens"],
        "input_total": metrics["totals"]["input_tokens"]
                       + metrics["totals"]["cache_read_tokens"]
                       + metrics["totals"]["cache_creation_tokens"],
        "cache": metrics["totals"]["cache_read_tokens"],
        "output": metrics["totals"]["output_tokens"],
        "calls": metrics["model_calls"],
        "calls_known": metrics["model_calls_known"],
        "captures": metrics["captures"]}

    def calls_cell(slot):
        known = slot["calls_known"]
        if not known:
            return "—"
        suffix = "*" if known < slot["captures"] else ""
        return h(num(slot["calls"]) + suffix)

    def usage_cells(slot):
        return (h(num(slot["captures"])), calls_cell(slot),
                h(compact(slot["fresh"])), h(compact(slot["cache"])),
                h(share(slot["cache"], slot["input_total"])),
                h(compact(slot["output"])), h(compact(slot["tokens"])),
                h(share(slot["tokens"], grand)))

    def attribution_label(slot):
        mapping = {"commit": "attr_commit", "session-claim": "attr_claim",
                   "reconcile-wal": "attr_reconcile", "state": "attr_inherited"}
        labels = {mapping.get(source, "attr_missing")
                  for source in slot["attribution_sources"]}
        if not labels:
            return t("attr_missing")
        return t(next(iter(labels))) if len(labels) == 1 else t("attr_mixed")

    def usage_bar(slot, widest):
        total = slot["tokens"]
        segments = "".join(
            "<span class=\"sseg tk-%s\" style=\"width:%.2f%%\"></span>"
            % (kind, pct(value, total or 1))
            for kind, value in (("input", slot["fresh"]),
                                ("cache_read", slot["cache"]),
                                ("output", slot["output"])) if value > 0)
        return ("<span class=\"btrack\"><span class=\"sbar usage-bar\" "
                "style=\"width:%.1f%%\">%s</span></span>"
                % (pct(total, widest or 1), segments))

    usage_legend = "<ul class=\"legend\">%s</ul>" % "".join(
        "<li><span class=\"key tk-%s\"></span>%s<b>%s</b></li>"
        % (kind, h(label), compact(value))
        for kind, label, value in (
            ("input", t("th_fresh"), total_usage["fresh"]),
            ("cache_read", t("th_cache_read"), total_usage["cache"]),
            ("output", t("th_output"), total_usage["output"])))

    usage_headers = [t("th_captures"), t("th_calls"), t("th_fresh"),
                     t("th_cache_read"), t("th_cache_share"), t("th_output"),
                     t("th_tokens"), t("th_share")]
    porder = sorted(clock["phases"],
                    key=lambda p: (-clock["phases"][p]["tokens"], p))
    widest = clock["phases"][porder[0]]["tokens"] if porder else 0
    pmarks, prows = [], []
    for pid in porder:
        slot = clock["phases"][pid]
        detail = "%s %s\n%s: %s\n%s" % (
            t("th_phase"), pid, t("th_tokens"), compact(slot["tokens"]),
            t("tk_phase_tip", num(slot["captures"]),
              share(slot["tokens"], grand)))
        pmarks.append(
            "<div class=\"brow\" tabindex=\"0\" data-tip=\"%s\">"
            "<span class=\"bname\">%s</span>"
            "%s"
            "<span class=\"bval\">%s</span></div>"
            % (tip(detail),
               h(("%s %s" % (pid, shorten(slot["name"], 34))).strip()),
               usage_bar(slot, widest), h(compact(slot["tokens"]))))
        attribution = attribution_label(slot)
        prows.append((h(pid), h(slot["name"]) or "—") + usage_cells(slot)
                     + (h(attribution),))
    prows.append((h(t("s_total")), "—") + usage_cells(total_usage) + ("—",))
    # Two notes, two different confessions: what this chart does NOT cover, and
    # how much of what it DOES cover is inherited instead of measured (REQ-225).
    # Each is spoken only when it has something to describe, the same rule
    # `metrics.sh agg` follows for its own inherited count.
    phase_notes = ""
    if clock["loose"]:
        phase_notes = ("<p class=\"note\">%s</p>"
                       % h(t("tk_nophase", num(clock["loose"]))))
    if clock["recovered_unassigned"]:
        phase_notes += ("<p class=\"note\">%s</p>"
                        % h(t("tk_recovered_unassigned",
                              num(clock["recovered_unassigned"]),
                              compact(clock["recovered_unassigned_tokens"]))))
    if clock["inherited"]:
        phase_notes += ("<p class=\"note\">%s</p>"
                        % h(t("tk_phase_inherited", num(clock["inherited"]))))
    explainers = ("<p class=\"note\">%s</p><p class=\"note\">%s</p>"
                  "<p class=\"note\">%s</p>"
                  % (h(t("tk_capture_explainer")), h(t("tk_calls_explainer")),
                     h(t("tk_attribution_explainer"))))
    by_phase = ("<h3>%s</h3>\n%s%s<div class=\"bars\">%s</div>\n%s%s%s"
                % (h(t("tk_by_phase")),
                   coverage(clock["attributed"], grand,
                            t("tk_cover_phase", compact(clock["attributed"]),
                              compact(grand), share(clock["attributed"], grand))),
                   usage_legend, "".join(pmarks), explainers, phase_notes,
                   details_table([t("th_phase"), t("th_name")] + usage_headers
                                 + [t("th_attribution")], prows, "numeric")))

    changes = fold_change_tokens(rows)
    corder = sorted(changes["changes"],
                    key=lambda key: (-changes["changes"][key]["tokens"], key))
    cwide = changes["changes"][corder[0]]["tokens"] if corder else 0
    cmarks, crows = [], []
    for change in corder:
        slot = changes["changes"][change]
        detail = "%s %s\n%s: %s\n%s" % (
            t("th_change"), change, t("th_tokens"), compact(slot["tokens"]),
            t("tk_change_tip", num(slot["captures"]),
              share(slot["tokens"], grand)))
        cmarks.append(
            "<div class=\"brow\" tabindex=\"0\" data-tip=\"%s\">"
            "<span class=\"bname\">%s</span>"
            "%s"
            "<span class=\"bval\">%s</span></div>"
            % (tip(detail), h(change), usage_bar(slot, cwide),
               h(compact(slot["tokens"]))))
        attribution = attribution_label(slot)
        crows.append((h(change),) + usage_cells(slot) + (h(attribution),))
    by_change = ""
    if corder:
        by_change = ("<h3>%s</h3>\n%s%s<div class=\"bars\">%s</div>\n%s"
                     % (h(t("tk_by_change")),
                        coverage(changes["attributed"], grand,
                                 t("tk_cover_change", compact(changes["attributed"]),
                                   num(changes["captures"]))),
                        usage_legend, "".join(cmarks),
                        details_table([t("th_change")] + usage_headers
                                      + [t("th_attribution")], crows, "numeric")))
    unassigned = clock["unassigned"]
    by_unassigned = ""
    if unassigned["captures"]:
        urow = ((h(t("tk_unassigned_work")),) + usage_cells(unassigned)
                + (h(t("attr_missing")),))
        urows = [urow]
        by_unassigned = ("<h3>%s</h3>\n<p class=\"note\">%s</p>\n%s"
                         % (h(t("tk_unassigned_work")),
                            h(t("tk_unassigned_note")),
                            details_table([t("th_name")] + usage_headers
                                          + [t("th_attribution")], urows,
                                          "numeric")))
    return card("tokens", t("b_tokens"), t("b_tokens_sub"),
                undercount + composition + by_phase + by_change + by_unassigned)


def block_timeline(events, clock):
    """The daily mark measures TIME ON TASKS, not the volume of events.

    It used to plot events per day and said so nowhere, so a reader had to
    guess the unit — and the guess a reader actually makes is "hours", which is
    the one thing the bar did not mean. Two changes fix that at the root: the
    mark now carries the measure the reader wants (seconds between a claim and
    its commit, split at UTC midnight), and the block DECLARES it — the title
    names the unit, the axis is labelled and stepped, the legend names both
    marks and the period average is drawn as a reference rule.

    ONE measure per mark. The event count did not move onto a second bar (two
    scales on one plot is a chart that invents a correlation): it stayed as a
    number, in the tooltip and in the table twin, where a count belongs.
    """
    subtitle = t("b_timeline_sub", t("last_days", num(TIMELINE_DAYS)))
    if not events:
        return card("timeline", t("b_timeline"), subtitle, empty())
    per_day = {}
    for e in events:
        slot = per_day.setdefault(e["day"], {})
        slot[e["event"]] = slot.get(e["event"], 0) + 1
    # A continuous daily axis, zero-filled: only rendering the days that HAVE
    # events would squeeze a quiet week into the same space as a busy one.
    try:
        last = date(*(int(x) for x in events[-1]["day"].split("-")))
        first = date(*(int(x) for x in events[0]["day"].split("-")))
    except (TypeError, ValueError):
        return card("timeline", t("b_timeline"), subtitle, empty())
    if (last - first).days > TIMELINE_DAYS - 1:
        first = last - timedelta(days=TIMELINE_DAYS - 1)
    axis = []
    day = first
    while day <= last:
        axis.append(day.isoformat())
        day += timedelta(days=1)
    worked = [clock["per_day"].get(d, 0) for d in axis]
    peak = max(worked)
    top = nice_top(peak)
    # Integer mean, over the days SHOWN (the quiet ones included — an average
    # that skipped them would describe a period that is not the one on screen).
    mean = sum(worked) // len(axis)
    rule = ref_rule(pct(mean, top), "%s %s" % (t("lg_avg"), hours(mean)))
    columns = []
    for i, d in enumerate(axis):
        seconds = worked[i]
        slot = per_day.get(d, {})
        total = sum(slot.values())
        detail = "%s: %s\n%s: %s\n%s: %s" % (
            t("th_day"), d, t("th_task_time"), hours(seconds),
            t("th_events"), num(total))
        for kind in sorted(slot):
            detail += "\n%s: %s" % (kind, num(slot[kind]))
        height = max(pct(seconds, top), 1.5) if seconds else 0.0
        label = ""
        if peak and seconds == peak and not any(
                worked[j] == peak for j in range(i)):
            label = col_label(hours(seconds), height, label_side(i, len(axis)))
        columns.append(column(detail, bar(height), label))
    legend = ("<li><span class=\"key kbar\"></span>%s<b>%s</b></li>"
              "<li><span class=\"key kref\"></span>%s<b>%s</b></li>"
              % (h(t("lg_bar")), h(hours(sum(worked))),
                 h(t("lg_ref", num(len(axis)))), h(hours(mean))))
    recent = []
    for e in reversed(events[-RECENT_EVENTS:]):
        recent.append("<li><span class=\"when\">%s</span>"
                      "<span class=\"kind\">%s</span>"
                      "<span class=\"what\">%s</span></li>"
                      % (h(stamp(e["ts"])), h(e["event"]),
                         h(shorten(e["detail"], 60))))
    rows = [(h(d), h(num(sum(per_day.get(d, {}).values()))),
             h(", ".join("%s %s" % (k, num(v))
                         for k, v in sorted(per_day.get(d, {}).items()))) or "—",
             h(hours(clock["per_day"].get(d, 0))))
            for d in axis]
    # A range caption, not a pair of edge labels: the columns are capped at
    # 24px and left-aligned, so a "last" label pinned to the card's right edge
    # would sit nowhere near the last column on a short history.
    body = ("%s<p class=\"axis\">%s — %s · %s</p>\n"
            "<ul class=\"legend\">%s</ul>\n<p class=\"note\">%s</p>\n"
            "<h3>%s</h3><ol class=\"events\">%s</ol>\n%s"
            % (plot_frame(t("axis_y"), (span(top), span(top // 2), "0"),
                          rule, columns),
               h(axis[0]), h(axis[-1]), h(t("axis_x")), legend,
               h(t("tl_overlap", num(clock["overlaps"]))),
               h(t("recent")), "".join(recent),
               details_table([t("th_day"), t("th_events"), t("th_event"),
                              t("th_task_time")], rows)))
    return card("timeline", t("b_timeline"), subtitle, body)


def block_time(clock):
    """How many hours the project cost, and over WHICH window.

    The window is printed with the figures and is not decoration: run.jsonl was
    born in phase 14, the project started before it, and an hour count without
    its window is a claim about the whole project that the log cannot support.
    Nothing here is estimated from git history or from anything else — what was
    not recorded is simply not counted, and the records that have no duration
    are declared instead of being closed against the clock.
    """
    if not clock["window"]:
        return card("time", t("b_time"), t("b_time_sub_none"), empty())
    subtitle = t("b_time_sub", stamp(clock["window"][0]),
                 stamp(clock["window"][1]))
    tasks, sessions = clock["tasks"], clock["sessions"]
    longest = max(tasks, key=lambda x: (x["seconds"], x["task"]), default=None)
    average = (clock["task_seconds"] // len(tasks)) if tasks else 0
    longest_session = max((x["seconds"] for x in sessions), default=0)
    figures = [
        (t("f_tasks"), hours(clock["task_seconds"]),
         t("f_tasks_sub", num(len(tasks)), hours(average),
           hours(longest["seconds"] if longest else 0)),
         t("f_tasks_tip", longest["task"] if longest else "—",
           hours(longest["seconds"] if longest else 0))),
        (t("f_sessions"), hours(clock["session_seconds"]),
         t("f_sessions_sub", num(len(sessions)), hours(longest_session)),
         t("f_sessions_tip")),
    ]
    figs = "".join(
        "<div class=\"fig\" tabindex=\"0\" data-tip=\"%s\">"
        "<p class=\"lbl\">%s</p><p class=\"big\">%s</p>"
        "<p class=\"lbl\">%s</p></div>" % (tip(hint), h(label), h(value), h(sub))
        for label, value, sub, hint in figures)
    # What the two figures MEAN, in the body of the panel (REQ-178). The user
    # asked the difference between them at the visual gate, and the answer
    # already existed — inside a tooltip attribute, where it obeyed nothing but
    # a pointer. The board's own rule is that no value depends on hover, so the
    # explanation reads as text, and the overlap caveat comes with its
    # MEASURED count instead of as a disclaimer nobody can weigh.
    explained = ("<p class=\"note\">%s</p>"
                 % h(t("t_explained", num(clock["overlaps"]))))
    note = ("<p class=\"note\">%s</p>"
            % h(t("t_open", num(len(clock["open_claims"])),
                  num(len(clock["loose_commits"])),
                  num(clock["open_sessions"]))))
    bars, rows = "", []
    if clock["by_phase"]:
        # Magnitude, one hue, ordered by weight: the question this answers is
        # "where did the time go", and the answer is the order of the bars.
        order = sorted(clock["by_phase"],
                       key=lambda p: (-clock["by_phase"][p]["seconds"], p))
        widest = clock["by_phase"][order[0]]["seconds"] or 1
        marks = []
        for pid in order:
            slot = clock["by_phase"][pid]
            name = ("%s %s" % (pid, shorten(slot["name"], 34))).strip()
            detail = "%s %s\n%s: %s\n%s" % (
                t("th_phase"), pid, t("th_total"), hours(slot["seconds"]),
                t("t_phase_tip", num(slot["tasks"]), hours(slot["longest"]),
                  num(slot["open"])))
            marks.append(
                "<div class=\"brow\" tabindex=\"0\" data-tip=\"%s\">"
                "<span class=\"bname\">%s</span>"
                "<span class=\"btrack\"><span class=\"bfill\" style=\"width:%.1f%%\"></span></span>"
                "<span class=\"bval\">%s</span></div>"
                % (tip(detail), h(name), pct(slot["seconds"], widest),
                   h(hours(slot["seconds"]))))
            mean = slot["seconds"] // slot["tasks"] if slot["tasks"] else 0
            rows.append((h(pid), h(num(slot["tasks"])), h(hours(slot["seconds"])),
                         h(hours(mean)), h(hours(slot["longest"])),
                         h(num(slot["open"]))))
        bars = ("<h3>%s</h3>\n<div class=\"bars\">%s</div>\n"
                % (h(t("t_by_phase")), "".join(marks)))
    body = ("<div class=\"figs\">%s</div>\n%s%s%s%s"
            % (figs, explained, note, bars,
               details_table([t("th_phase"), t("th_tasks"), t("th_total"),
                              t("th_avg"), t("th_longest"), t("th_open")],
                             rows, "numeric")))
    return card("time", t("b_time"), subtitle, body)


def map_visual(shape):
    """The map's PRODUCT, drawn: what the excerpt keeps, and in which order.

    Two charts, and neither one is a picture of the repository. `map.txt` is
    what a subagent is actually handed, so what it keeps is the only thing worth
    drawing — and the panel spends its first paragraph saying exactly that,
    with both counts in it, because a visualization that overstates its own
    coverage is worse than no visualization at all.

    DENSITY is a magnitude, so it is ordered by magnitude, ties by name.
    THE RANKING is not: it is drawn in repo-map's OWN order, never re-sorted by
    the bar beside it, because the bar is the number of symbols the excerpt kept
    and the order is a score built from definitions plus incoming references —
    two different measures, and the caption says so. Re-sorting would have
    produced a chart that looks tidier and claims something nobody computed.
    That the bars come out non-monotone is the honest shape of it: it is what a
    reader needs in order to stop reading rank as size.

    NO dependency graph. The v1 map stores DEFINITIONS, not edges — the spec
    decided that — so there is nothing here to draw arrows from, and inventing
    them from name collisions would be a diagram of a guess.

    Empty in, empty out: no `map.txt` means no section, and the health panel
    above it renders exactly as it did before (REQ-252)."""
    if not shape["files"]:
        return ""
    notes = [t("mp_excerpt", num(len(shape["files"])), num(shape["symbols"]),
               num(shape["chars"]))]
    if shape["tracked"]:
        notes.append(t("mp_tracked", num(shape["tracked"]),
                       num(len(shape["files"]))))
    if shape["plain"]:
        notes.append(t("mp_plain", num(shape["plain"])))
    dirs = shape["dirs"][:MAP_DIRS]
    if len(shape["dirs"]) > len(dirs):
        notes.append(t("mp_dirs_cap", num(len(dirs)), num(len(shape["dirs"]))))
    top = shape["files"][:MAP_TOP]
    if len(shape["files"]) > len(top):
        notes.append(t("mp_top_cap", num(len(top)), num(len(shape["files"]))))
    density = svg_bars(t("mp_density_alt"),
                       [(shorten(name, MAP_PATH_CAP), num(count), count)
                        for name, _, count in dirs])
    ladder = svg_bars(t("mp_rank_alt"),
                      [("%s %s" % (num(i + 1), shorten(rel, MAP_PATH_CAP)),
                        num(count), count)
                       for i, (rel, count) in enumerate(top)])
    return ("%s<h3>%s</h3>\n%s<p class=\"axis\">%s</p>\n%s"
            "<h3>%s</h3>\n%s<p class=\"axis\">%s</p>\n%s"
            % ("".join("<p class=\"note\">%s</p>" % h(n) for n in notes),
               h(t("mp_density")), density, h(t("mp_density_axis")),
               details_table([t("th_dir"), t("th_files"), t("th_symbols")],
                             [(h(name), h(num(files)), h(num(count)))
                              for name, files, count in dirs], "numeric",
                             t("mp_table_dirs")),
               h(t("mp_rank")), ladder, h(t("mp_rank_axis")),
               # The table twin carries the path WHOLE: the chart's label
               # column is finite and the names it draws are truncated.
               details_table([t("th_rank"), t("th_file"), t("th_symbols")],
                             [(h(num(i + 1)), h(rel), h(num(count)))
                              for i, (rel, count) in enumerate(top)], "",
                             t("mp_table_rank"))))


def block_map(mp, newest, shape):
    """The health of the project's one OPTIONAL layer, and then its product.

    Three facts, each answering a question the map could not answer before: the
    verdict repo-map last RECORDED, how old the map on disk is, and how often it
    was generated against how often anybody read it. The pair is the point — for
    a whole phase the map could prove it had been generated and never that it
    had been used (REQ-243) — and the age is why health came before the pretty
    block: the map went seven hours stale with nobody told, because staleness is
    invisible until something prints it.

    The age is the distance from the last recorded generation to the newest fact
    on this board, the same `data through` the header prints. NEVER the wall
    clock: this render is byte-identical over unchanged sources, and an age
    measured against the current time would change on every call."""
    subtitle = (t("b_map_sub", stamp(mp["window"][0]), stamp(mp["window"][1]))
                if mp["window"] else t("b_map_sub_none"))
    if mp["verdict_at"]:
        verdict_sub = t("f_map_verdict_sub", stamp(mp["verdict_at"]))
    elif mp["fingerprints"]:
        verdict_sub = t("f_map_verdict_none")
    else:
        verdict_sub = t("f_map_verdict_disk")
    age, age_sub = t("mp_unrecorded"), t("f_map_age_none")
    if mp["last_refresh"]:
        age_sub = t("f_map_age_sub", stamp(mp["last_refresh"]))
        made, last = epoch(mp["last_refresh"]), epoch(newest)
        if made is not None and last is not None:
            age = dur(max(0, last - made))
    figures = [
        (t("f_map_verdict"), mp["verdict"] or t("mp_unrecorded"), verdict_sub,
         t("f_map_verdict_tip")),
        (t("f_map_age"), age, age_sub, t("f_map_age_tip")),
        (t("f_map_pair"), "%s × %s" % (num(mp["refreshed"]), num(mp["shown"])),
         t("f_map_pair_sub", num(mp["refreshed"]), num(mp["shown"])),
         t("f_map_pair_tip")),
    ]
    figs = "".join(
        "<div class=\"fig\" tabindex=\"0\" data-tip=\"%s\">"
        "<p class=\"lbl\">%s</p><p class=\"big\">%s</p>"
        "<p class=\"lbl\">%s</p></div>" % (tip(hint), h(label), h(value), h(sub))
        for label, value, sub, hint in figures)
    notes = "<p class=\"note\">%s</p>" % h(t("mp_explained"))
    if mp["floor"]:
        notes += "<p class=\"note\">%s</p>" % h(t("mp_floor", num(mp["floor"])))
    listed = list(reversed(mp["records"][-MAP_EVENTS:]))
    if len(mp["records"]) > len(listed):
        notes += ("<p class=\"note\">%s</p>"
                  % h(t("mp_last", num(len(listed)))))
    rows = []
    for e in listed:
        parts = []
        for key in MAP_FIELDS:
            value = e["row"].get(key)
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                continue
            if not str(value):
                continue
            parts.append("%s %s" % (key, value))
        rows.append((h(stamp(e["ts"])), h(e["event"]),
                     h(" · ".join(parts)) or "—"))
    # The drawing goes BETWEEN the health figures and the record they came from:
    # a ranking is read against the verdict that qualifies it, and a `stale` two
    # screens above a picture of the map is a `stale` nobody applies to it.
    body = ("<div class=\"figs\">%s</div>\n%s%s%s"
            % (figs, notes, map_visual(shape),
               details_table([t("th_when"), t("th_event"), t("th_detail")],
                             rows)))
    return card("map", t("b_map"), subtitle, body)


def block_summary(phases, charts, reqs, metrics):
    closed = sum(1 for p in phases if p["status"] == "shipped")
    tasks = [x for group in charts.values() for x in group]
    done = sum(1 for x in tasks if x["state"] == "done")
    proven = sum(1 for r in reqs if r["status"] == "proven")
    grand = sum(metrics["totals"][k] for k in TOKEN_FIELDS)
    tiles = [
        ("hero", t("hero_label"), closed, len(phases)),
        ("tile", t("kpi_tasks"), done, len(tasks)),
        ("tile", t("kpi_reqs"), proven, len(reqs)),
    ]
    out = []
    for klass, label, part, whole in tiles:
        out.append(
            "<div class=\"%s\"><p class=\"lbl\">%s</p>"
            "<p class=\"big\">%s<span class=\"of\">/%s</span></p>"
            "<span class=\"meter\"><span class=\"mfill\" style=\"width:%.1f%%\"></span></span>"
            "</div>" % (klass, h(label), h(num(part)), h(num(whole)),
                        pct(part, whole)))
    out.append("<div class=\"tile\"><p class=\"lbl\">%s</p>"
               "<p class=\"big\">%s</p><p class=\"lbl\">%s</p></div>"
               % (h(t("kpi_tokens")), h(compact(grand)),
                  h(t("kpi_tokens_sub", num(metrics["captures"]),
                      num(len(metrics["sessions"]))))))
    return ("<section class=\"kpis\" data-block=\"summary\">%s</section>\n"
            % "".join(out))


def block_presence(presence):
    state = presence["state"]
    labels = {"recent": "p_recent", "awaiting": "p_awaiting",
              "interrupted": "p_interrupted", "idle": "p_idle",
              "unknown": "p_unknown"}
    status = t(labels.get(state, "p_unknown"))
    task = presence["task"]
    title = presence["title"]
    task_line = "%s%s" % (task, (" · " + title) if title else "") if task else ""
    phase_badge = ("<span class=\"presence-phase\" id=\"presence-phase\"%s>%s</span>" %
                   ("" if presence["phase"] else " hidden",
                    h(t("p_phase", presence["phase"])) if presence["phase"] else ""))
    def task_text(task_id, title):
        if not task_id:
            return ""
        return task_id + ((" · " + title) if title else "")
    last = (t("p_last", stamp(presence["last_at"])) if presence["last_at"]
            else t("p_no_activity"))
    orbit = ("<svg class=\"presence-orbit\" aria-hidden=\"true\" viewBox=\"0 0 48 48\">"
             "<circle class=\"orbit-track\" cx=\"24\" cy=\"24\" r=\"18\"/>"
             "<circle class=\"orbit-arc\" cx=\"24\" cy=\"24\" r=\"18\"/>"
             "<circle class=\"orbit-core\" cx=\"24\" cy=\"24\" r=\"4\"/>"
             "</svg>")
    attrs = {
        "data-state": state,
        "data-matched": "true" if presence["matched"] else "false",
        "data-last-at": str(epoch(presence["last_at"]) or ""),
        "data-expires-at": presence["expires_at"],
        "data-base-state": presence["base_state"],
        "data-base-last-at": str(epoch(presence["base_last_at"]) or ""),
        "data-base-task": presence["base_task"],
        "data-base-phase": presence["base_phase"],
        "data-strong-last-at": str(epoch(presence["strong_last_at"]) or ""),
        "data-strong-task": presence["strong_task"],
        "data-strong-phase": presence["strong_phase"],
        "data-session-last-at": str(epoch(presence["session_last_at"]) or ""),
        "data-session-expires-at": presence["session_expires_at"],
        "data-label-working": t("p_working"),
        "data-label-recent": t("p_recent"),
        "data-label-awaiting": t("p_awaiting"),
        "data-label-interrupted": t("p_interrupted"),
        "data-label-idle": t("p_idle"),
        "data-label-unknown": t("p_unknown"),
        "data-phase-template": t("p_phase", "{n}"),
        "data-no-activity": t("p_no_activity"),
        "data-base-task-line": task_text(presence["base_task"], presence["base_title"]),
        "data-strong-task-line": task_text(presence["strong_task"], presence["strong_title"]),
        "data-seconds": t("p_seconds", "{n}"),
        "data-minute": t("p_minute"),
        "data-minutes": t("p_minutes", "{n}"),
        "data-hour": t("p_hour"),
        "data-hours": t("p_hours", "{n}"),
    }
    packed = " ".join('%s=\"%s\"' % (key, h(value))
                      for key, value in attrs.items())
    return ("<section class=\"presence presence-%s\" data-block=\"presence\" "
            "id=\"project-presence\" %s><div class=\"presence-mark\">%s</div>"
            "<div class=\"presence-copy\"><p class=\"presence-eyebrow\">%s</p>"
            "<div class=\"presence-heading\"><h2 id=\"presence-state\">%s</h2>%s</div>"
            "<p class=\"presence-task\" id=\"presence-task\"%s>%s</p>"
            "<p class=\"presence-age\" id=\"presence-age\">%s</p></div></section>\n"
            % (h(state), packed, orbit, h(t("p_eyebrow")), h(status), phase_badge,
               "" if task_line else " hidden", h(task_line),
               h(last)))


# --- the phase report: the same sources, on the screen (REQ-171) --------------
# An artifact generated in silence does not exist for the user, and a milestone
# read once deserves better than a path nobody prints. `summary` is the TEXT
# twin of the board: the same parsers, the same fail-open posture, no writes.
# Every figure is counted from `.helmit/` — never the wall clock, never judged
# (KEEL: no AI scores, ever).
#
# Tokens and sessions are scoped by the phase's WINDOW, not by the `phase` tag
# alone: the commit hook can only tag the captures it happens to see, so a tag
# scope reports a fraction of what a phase cost. The window is derived from the
# artifacts (run log events of the phase's tasks + metrics lines tagged to it)
# and is PRINTED with the numbers, so the reader knows exactly what was summed.

TITLE_CAP = 52
SESSION_ROWS = 8
WRAP = 76


def table(rows, head=None, right=()):
    """Aligned plain-text columns — the report is read in a terminal."""
    grid = ([list(head)] if head else []) + [[str(c) for c in r] for r in rows]
    if not grid:
        return []
    width = [max(len(row[i]) for row in grid) for i in range(len(grid[0]))]
    out = []
    for row in grid:
        cells = [(c.rjust(width[i]) if i in right else c.ljust(width[i]))
                 for i, c in enumerate(row)]
        out.append(("  " + "  ".join(cells)).rstrip())
    return out


def listing(label, ids):
    """`label  REQ-001, REQ-002, ...`, wrapped so no line runs off the screen."""
    body = ", ".join(ids)
    pad = " " * (len(label) + 4)
    return textwrap.wrap("  %s  %s" % (label, body), width=WRAP,
                         subsequent_indent=pad) or ["  %s" % label]


def pick_phase(phases, charts):
    """Which phase the report is about. `--phase` wins; then STATE.md, which is
    the project's declared position; then the ROADMAP's live row; then the last
    phase that has a chart. Every step is a fact from an artifact."""
    if WANT_PHASE:
        return WANT_PHASE
    shared = next_facts().get("phase", "")
    if shared:
        return shared
    declared = parse_state()[1]
    if declared:
        return declared
    live = [p["id"] for p in phases if p["status"] == "implementing"]
    if live:
        return live[0]
    charted = [p["id"] for p in phases if p["id"] in charts]
    if charted:
        return charted[-1]
    return sorted(charts)[-1] if charts else ""


def phase_window(pid, events, rows):
    """(first, last) stamps of everything that proves this phase happened."""
    prefix = pid + "."
    seen = []
    for e in events:
        if e["task"].startswith(prefix):
            seen.append((epoch(e["ts"]), e["ts"]))
    for r in rows:
        if str(r.get("phase")) == pid or str(r.get("task") or "").startswith(prefix):
            seen.append((epoch(r.get("ts")), r.get("ts")))
    seen = [s for s in seen if s[0] is not None]
    if not seen:
        return None
    return min(seen), max(seen)


def report_tasks(pid, charts, events):
    tasks = charts.get(pid, [])
    done = sum(1 for x in tasks if x["state"] == "done")
    out = ["%s  %s" % (t("s_tasks"), t("s_done_of", num(done), num(len(tasks))))]
    if not tasks:
        return out + ["  " + t("s_none")]
    marks = {"done": "[x]", "doing": "[>]", "todo": "[ ]"}

    landed = {e["task"]: e["row"].get("commit", "") for e in events
              if e["event"] == "task_committed" and e["task"]}
    effective = {x["id"]: x["commit"] or landed.get(x["id"], "") for x in tasks}
    def closing(x):
        """What closed the task: the hash, or — for a `[human]` gate — the
        reason written in the tick. Only a task that is NOT done is open."""
        if effective[x["id"]]:
            return effective[x["id"]]
        if x["state"] == "done":
            return shorten(x["closed_note"], TITLE_CAP) if x["closed_note"] \
                else t("s_no_commit")
        return t("s_open")

    out += table([(marks.get(x["state"], "[ ]"), x["id"],
                   shorten(x["title"], TITLE_CAP), closing(x))
                  for x in tasks])
    logged = sum(1 for e in events
                 if e["event"] == "task_committed" and e["task"].startswith(pid + "."))
    recorded = len({effective[x["id"]] for x in tasks if effective[x["id"]]})
    # A task closed by approval has no hash and never will, so counting it as a
    # missing commit reads as a bookkeeping error when it is the normal shape of
    # a `[human]` gate. Say how many there are instead of hiding the difference.
    no_commit = sum(1 for x in tasks
                    if x["state"] == "done" and not effective[x["id"]])
    caption = t("s_commits", num(recorded), num(logged))
    if no_commit:
        caption += " " + t("s_closed_no_commit", num(no_commit))
    claimed = {e["task"] for e in events if e["event"] == "task_claimed"}
    committed = {e["task"] for e in events if e["event"] == "task_committed"}
    gaps = [x["id"] for x in tasks if x["state"] == "done"
            and not (x["id"] in claimed and x["id"] in committed)]
    out.append("  " + caption)
    if gaps:
        out += textwrap.wrap("  " + t("s_chart_wal_gap", num(len(gaps)), ", ".join(gaps)),
                             width=WRAP, subsequent_indent="  ")
    return out


def report_reqs(pid, reqs):
    mine = [r for r in reqs if r["phase"] == pid]
    proven = [r["id"] for r in mine if r["status"] == "proven"]
    out = ["%s  %s" % (t("s_reqs"),
                       t("s_proven_of", num(len(proven)), num(len(mine))))]
    if not mine:
        return out + ["  " + t("s_none")]
    buckets = {}
    for r in mine:
        buckets.setdefault(r["status"], []).append(r["id"])
    order = [s for s in REQ_LADDER if s in buckets]
    order += sorted(s for s in buckets if s not in REQ_LADDER)
    width = max(len(s) for s in order)
    for status in order:
        out += listing(status.ljust(width), sorted(buckets[status]))
    missing = sorted(r["id"] for r in mine if r["status"] != "proven")
    if missing:
        out += textwrap.wrap("  " + t("s_to_prove", ", ".join(missing)),
                             width=WRAP, subsequent_indent="  ")
    else:
        out.append("  " + t("s_all_proven"))
    return out


def report_tokens(pid, scoped, tagged, window, unassigned):
    st = fold_metrics(scoped)
    head = t("s_tokens")
    if window:
        head += "  " + t("s_window", stamp(window[0][1]), stamp(window[1][1]))
    out = [head]
    if not st["captures"]:
        out.append("  " + t("s_none"))
    else:
        # The TOTAL row is printed even when no line carries a breakdown: a
        # phase whose captures predate REQ-167 still cost what it cost, and
        # showing nothing would read as "no tokens" instead of "no breakdown".
        totals = {name: sum(b[k] for k in TOKEN_FIELDS)
                  for name, b in st["models"].items()}
        rows = []
        for name in sorted(totals, key=lambda n: (-totals[n], n)):
            b = st["models"][name]
            rows.append((name, compact(b["input_tokens"]), compact(b["output_tokens"]),
                         compact(b["cache_read_tokens"]),
                         compact(b["cache_creation_tokens"]), compact(totals[name])))
        rows.append((t("s_total"),
                     compact(st["totals"]["input_tokens"]),
                     compact(st["totals"]["output_tokens"]),
                     compact(st["totals"]["cache_read_tokens"]),
                     compact(st["totals"]["cache_creation_tokens"]),
                     compact(sum(st["totals"][k] for k in TOKEN_FIELDS))))
        out += table(rows, head=(t("th_model"), t("th_input"), t("th_output"),
                                 t("th_cache_read"), t("th_cache_creation"),
                                 t("th_total")), right=(1, 2, 3, 4, 5))
    note = [t("s_tagged", num(tagged))]
    if st["no_breakdown"]:
        note.append(t("no_breakdown", num(st["no_breakdown"])))
    if unassigned:
        tokens = sum(sum(toint(row.get(k)) for k in TOKEN_FIELDS) for row in unassigned)
        note.append(t("tk_recovered_unassigned", num(len(unassigned)), compact(tokens)))
    return out + ["  " + " · ".join(note)]


def report_sessions(scoped):
    spans = {}
    for r in scoped:
        name = r.get("session")
        when = epoch(r.get("ts"))
        if not isinstance(name, str) or not name or when is None:
            continue
        slot = spans.setdefault(name, {"first": when, "last": when,
                                       "from": r.get("ts"), "to": r.get("ts"),
                                       "captures": 0})
        if when <= slot["first"]:
            slot["first"], slot["from"] = when, r.get("ts")
        if when >= slot["last"]:
            slot["last"], slot["to"] = when, r.get("ts")
        slot["captures"] += 1
    if not spans:
        return [t("s_sessions"), "  " + t("s_none")]
    order = sorted(spans, key=lambda n: (spans[n]["first"], n))
    total = sum(spans[n]["last"] - spans[n]["first"] for n in order)
    out = ["%s  %s" % (t("s_sessions"),
                       t("s_sessions_sub", num(len(order)), dur(total)))]
    rows = []
    for name in order[:SESSION_ROWS]:
        slot = spans[name]
        rows.append((name[:8], stamp(slot["from"]), "→", stamp(slot["to"]),
                     dur(slot["last"] - slot["first"]),
                     t("s_captures", num(slot["captures"]))))
    out += table(rows, right=(4, 5))
    if len(order) > SESSION_ROWS:
        out.append("  " + t("s_more", num(len(order) - SESSION_ROWS)))
    return out


def board_uri():
    """The board as a clickable location. A path nobody can click is a path
    nobody opens — and the core stays platform-free: it PRINTS the URL, the
    adapter decides whether it can also hand the file over."""
    path = os.path.abspath(OUT)
    try:
        return pathlib.Path(path).as_uri()
    except ValueError:
        return path


def summary():
    phases = parse_roadmap()
    charts = parse_charts()
    reqs = parse_requirements()
    rows = metrics_rows()
    events = parse_runlog()

    pid = pick_phase(phases, charts)
    if not pid:
        return t("s_no_phase")
    row = next((p for p in phases if p["id"] == pid), None)

    stamps = [s for s in (fold_metrics(rows)["last_ts"],
                          events[-1]["ts"] if events else "") if s]
    through = stamp(max(stamps)) if stamps else ""

    head = "%s %s" % (t("s_phase"), pid)
    if row:
        head += " · %s" % row["name"]
        if row["status"]:
            head += " — %s" % row["status"]
    sub = "%s %s" % (t("s_project"), os.path.basename(os.path.abspath(ROOT)))
    if through:
        sub += " · %s %s" % (t("data_through"), through)
    open_changes = next_facts().get("open_changes", [])
    if open_changes:
        sub += " · open CHG %s" % ", ".join(
            change.get("id", "?") for change in open_changes
        )

    window = phase_window(pid, events, rows)
    scoped = []
    if window:
        low, high = window[0][0], window[1][0]
        scoped = [r for r in rows
                  if low <= (epoch(r.get("ts")) if epoch(r.get("ts")) is not None
                             else low - 1) <= high]
    tagged_rows = [r for r in rows if str(r.get("phase")) == pid]
    tagged = len(tagged_rows)

    out = [head, sub, ""]
    for section in (report_tasks(pid, charts, events),
                    report_reqs(pid, reqs),
                    report_tokens(pid, tagged_rows, tagged, window,
                                  [r for r in rows if r.get("source") == "reconcile"
                                   and r.get("phase") is None]),
                    report_sessions(scoped)):
        out += section + [""]
    out.append(t("s_board", board_uri()) if os.path.isfile(OUT)
               else t("s_board_missing"))
    return "\n".join(out)


# --- page ---------------------------------------------------------------------

CSS = """
:root { /*LIGHT*/ }
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) { /*DARK*/ }
}
:root[data-theme="dark"] { /*DARK*/ }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 28px 20px 64px;
  background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
.dash-status { max-width: 1080px; margin: 0 auto 12px; padding: 7px 10px;
               border: 1px solid var(--border); border-radius: 8px;
               color: var(--ink2); background: var(--surface); font-size: 12px; }
.dash-status.failed { color: #7a271a; border-color: #f0a08f; background: #fff3f0; }
:root[data-theme="dark"] .dash-status.failed { color: #ffc6ba; border-color: #8d3e31;
                                                background: #321d1a; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0; letter-spacing: -0.01em; }
h2 { font-size: 15px; margin: 0; letter-spacing: -0.01em; }
h3 { font-size: 12px; margin: 22px 0 8px; color: var(--ink2);
     text-transform: uppercase; letter-spacing: 0.06em; }
p { margin: 0; }
.sub { color: var(--ink2); font-size: 12.5px; margin-top: 2px; }
.top { display: flex; align-items: flex-start; justify-content: space-between;
       gap: 16px; margin-bottom: 20px; }
.tgl { border: 1px solid var(--border); background: var(--surface);
       color: var(--ink2); border-radius: 8px; padding: 7px 12px;
       font: inherit; font-size: 12.5px; cursor: pointer; }
.tgl:hover { color: var(--ink); }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 12px; padding: 18px 20px; margin-bottom: 14px; }
.kpis { display: grid; gap: 14px; margin-bottom: 14px;
        grid-template-columns: 1.4fr 1fr 1fr 1fr; }
.hero, .tile { background: var(--surface); border: 1px solid var(--border);
               border-radius: 12px; padding: 16px 18px; }
.lbl { color: var(--ink2); font-size: 12.5px; }
.big { font-size: 30px; font-weight: 600; margin: 6px 0 10px;
       letter-spacing: -0.02em; }
.hero .big { font-size: 52px; line-height: 1; margin: 10px 0 14px; }
.of { color: var(--muted); font-size: 0.5em; font-weight: 500; }
.hero .of { font-size: 0.36em; }
.empty { color: var(--muted); font-size: 13px; padding: 18px 0 4px; }
.note { color: var(--ink2); font-size: 12.5px; margin-top: 10px; }

.presence { position: relative; display: grid; grid-template-columns: 58px 1fr;
            gap: 16px; align-items: center; overflow: hidden;
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px; padding: 17px 20px; margin-bottom: 14px; }
.presence-working { border-color: var(--accent); }
.presence-mark { width: 48px; height: 48px; display: grid; place-items: center; }
.presence-orbit { width: 48px; height: 48px; overflow: visible; }
.orbit-track, .orbit-arc { fill: none; stroke-width: 2.5; }
.orbit-track { stroke: var(--grid); }
.orbit-arc { opacity: 0; stroke: var(--muted); stroke-linecap: round;
             transform-origin: 24px 24px; }
.orbit-core { fill: var(--muted); transform-origin: 24px 24px; }
.presence-working .orbit-arc { opacity: 1; stroke: var(--accent);
                              stroke-dasharray: 35 79;
                              animation: presence-spin 2.1s linear infinite; }
.presence-working .orbit-core { fill: var(--accent);
                               animation: presence-pulse 1.8s ease-in-out infinite; }
.presence-awaiting .orbit-track { stroke: var(--accent); opacity: .55; }
.presence-awaiting .orbit-core { fill: var(--accent); opacity: .75; }
.presence-eyebrow { color: var(--muted); font-size: 11px; font-weight: 650;
                    letter-spacing: .08em; text-transform: uppercase; }
.presence-heading { display: flex; flex-wrap: wrap; align-items: center;
                    gap: 8px 12px; margin-top: 2px; }
.presence-heading h2 { font-size: 18px; letter-spacing: -.015em; }
.presence-phase { border: 1px solid var(--border); border-radius: 999px;
                  color: var(--ink2); padding: 2px 8px; font-size: 11.5px; }
.presence-task { color: var(--ink2); font-size: 13px; margin-top: 3px; }
.presence [hidden] { display: none !important; }
.presence-age { color: var(--muted); font-size: 11.5px; margin-top: 2px; }
@keyframes presence-spin { to { transform: rotate(360deg); } }
@keyframes presence-pulse { 50% { transform: scale(1.65); opacity: .55; } }

/* phase strip: one tile per phase, filled by the ordinal status ramp */
.strip { display: grid; gap: 2px; margin: 16px 0 4px;
         grid-template-columns: repeat(auto-fill, minmax(46px, 1fr)); }
.ph { min-height: 46px; display: flex; align-items: center;
      justify-content: center; border-radius: 4px; font-size: 13px;
      font-weight: 600; cursor: default; }
.ph:focus-visible, .mrow:focus-visible, .brow:focus-visible,
.seg:focus-visible, .col:focus-visible { outline: 2px solid var(--accent);
      outline-offset: 2px; }
.ph-todo { background: var(--ph-todo); color: var(--ph-todo-ink); }
.ph-spec { background: var(--ph-spec); color: var(--ph-spec-ink); }
.ph-planned { background: var(--ph-planned); color: var(--ph-planned-ink); }
.ph-implementing { background: var(--ph-implementing);
                   color: var(--ph-implementing-ink); }
.ph-shipped { background: var(--ph-shipped); color: var(--ph-shipped-ink); }
.ph-validated { background: var(--ph-validated); color: var(--ph-validated-ink); }
.ph-other { background: var(--ph-other); color: var(--ph-other-ink); }
.rq-todo { background: var(--rq-todo); color: var(--rq-todo-ink); }
.rq-covered { background: var(--rq-covered); color: var(--rq-covered-ink); }
.rq-proven { background: var(--rq-proven); color: var(--rq-proven-ink); }
.rq-other { background: var(--ph-other); color: var(--ph-other-ink); }

.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 18px;
          padding: 0; margin: 14px 0 0; font-size: 12.5px; color: var(--ink2); }
.legend li { display: flex; align-items: center; gap: 6px; }
.legend b { color: var(--ink); font-variant-numeric: tabular-nums; }
.key { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

/* task meters: one ratio per phase, against its own total */
.meters { margin: 16px 0 4px; }
.mrow { display: grid; grid-template-columns: 34px minmax(0, 200px) 1fr 64px;
        align-items: center; gap: 12px; padding: 3px 0; }
.mid { font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
.mname { color: var(--ink2); font-size: 12.5px; overflow: hidden;
         text-overflow: ellipsis; white-space: nowrap; }
.meter { display: block; height: 8px; border-radius: 4px;
         background: var(--track); overflow: hidden; }
.mfill { display: block; height: 100%; background: var(--fill);
         border-radius: 0 4px 4px 0; }
.mval { font-size: 12.5px; color: var(--ink2); text-align: right;
        font-variant-numeric: tabular-nums; }

/* requirements: a single part-to-whole bar, 2px of surface between segments */
.stack { display: flex; gap: 2px; height: 30px; margin: 18px 0 0;
         border-radius: 4px; overflow: hidden; }
.seg { display: flex; align-items: center; justify-content: center;
       min-width: 3px; }
.segl { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }

/* tokens: magnitude per model, one hue */
.bars { margin: 16px 0 4px; }
.brow { display: grid; grid-template-columns: minmax(0, 190px) 1fr 84px;
        align-items: center; gap: 12px; padding: 4px 0; }
.bname { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.btrack { display: block; height: 14px; background: var(--track);
          border-radius: 4px; overflow: hidden; }
.bfill { display: block; height: 100%; background: var(--fill);
         border-radius: 0 4px 4px 0; min-width: 2px; }
.bval { font-size: 12.5px; color: var(--ink2); text-align: right;
        font-variant-numeric: tabular-nums; }

/* tokens, composition: one part-to-whole bar per model, segments = token type.
   Thin marks, a 2px gap of SURFACE doing the separating (never a stroke drawn
   around a segment), and no inline label on an interior segment — the legend,
   the tooltip and the table twin carry the values. */
.srow { display: grid; grid-template-columns: minmax(0, 190px) 1fr 84px;
        align-items: center; gap: 12px; padding: 4px 0; }
.sbar { display: flex; gap: 2px; height: 14px; }
.usage-bar { height: 100%; }
.sseg { display: block; min-width: 2px; border-radius: 2px; }
.tk-input { background: var(--tk-input); }
.tk-output { background: var(--tk-output); }
.tk-cache_read { background: var(--tk-cache_read); }
.tk-cache_creation { background: var(--tk-cache_creation); }
/* how much of the record the chart below covers: a ratio against its limit,
   on the same ramp as its track, with the number printed beside it */
.cov { margin: 14px 0 2px; }
.cov .note { margin-top: 6px; }

/* time: two figures, then magnitude per phase on the token block's own marks */
.figs { display: grid; gap: 14px; margin: 16px 0 4px;
        grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
.fig .big { margin: 4px 0 4px; }

/* timeline: one column per day, zero-filled, on a LABELLED and STEPPED scale.
   The plot is a 3-column grid — axis title, tick values, plot area — so the
   ticks stay glued to the gridlines they name at any width. */
.plot { display: grid; grid-template-columns: auto auto 1fr; gap: 0 8px;
        margin: 18px 0 0; padding-top: 18px; }
.ylab { writing-mode: vertical-rl; transform: rotate(180deg);
        align-self: center; color: var(--muted); font-size: 11.5px;
        white-space: nowrap; }
.yaxis { display: flex; flex-direction: column; justify-content: space-between;
         align-items: flex-end; height: 110px; color: var(--muted);
         font-size: 11.5px; font-variant-numeric: tabular-nums; }
.yaxis span { line-height: 1; }
.yaxis span:first-child { margin-top: -0.5em; }
.yaxis span:last-child { margin-bottom: -0.5em; }
.area { position: relative; height: 110px;
        border-bottom: 1px solid var(--axis); }
/* gridlines and the axis rule are solid hairlines, one step off the surface */
.gl { position: absolute; left: 0; right: 0; height: 1px;
      background: var(--grid); }
/* the period average: an ANNOTATION, so it wears a text token and never a
   data hue — it must not be mistaken for a series */
.ref { position: absolute; left: 0; right: 0; height: 2px;
       background: var(--ink2); }
.ref b { position: absolute; right: 0; bottom: 4px; white-space: nowrap;
         font-size: 11.5px; font-weight: 500; color: var(--ink2); }
.cols { display: flex; align-items: flex-end; justify-content: flex-start;
        gap: 2px; height: 100%; }
.col { flex: 1 1 0; min-width: 4px; max-width: 24px; height: 100%;
       display: flex; align-items: flex-end; position: relative; }
.cbar { display: block; width: 100%; background: var(--fill);
        border-radius: 4px 4px 0 0; }
.cval { position: absolute; margin-bottom: 4px; white-space: nowrap;
        font-size: 11.5px; color: var(--ink2);
        font-variant-numeric: tabular-nums; }
.cval.mid { left: 50%; transform: translateX(-50%); }
.cval.start { left: 0; }
.cval.end { right: 0; }
.key.kbar { background: var(--fill); }
.key.kref { width: 14px; height: 2px; border-radius: 0; background: var(--ink2); }

/* tests: the losing verdict wears the reserved status step, and it is the only
   place on the board that leaves the single data hue. A run that recorded no
   value keeps its slot with a muted stub at the baseline — "not recorded",
   which a column of height zero would have read as "zero". */
.cbar.bad { background: var(--bad); }
.key.kbad { background: var(--bad); }
.nub { display: block; width: 100%; height: 3px; border-radius: 2px;
       background: var(--muted); }
.key.knub { height: 3px; border-radius: 2px; background: var(--muted); }
.vd-passed { background: var(--fill); }
.vd-blocked { background: var(--bad); }
.vd-other { background: var(--neutral); }
.lbl .key { vertical-align: -1px; margin-right: 6px; }
.axis { color: var(--muted); font-size: 11.5px; margin-top: 6px;
        font-variant-numeric: tabular-nums; }

/* the repo map drawn: inline SVG, wearing the page's own tokens. Nothing here
   points outside this file — no image, no sheet, no font (REQ-253) — and the
   text wears an INK token, never the series color. */
.mapsvg { display: block; width: 100%; height: auto; margin: 12px 0 2px; }
.mapsvg .sname { fill: var(--ink2); font-size: 13px; }
.mapsvg .sval { fill: var(--ink); font-size: 13px; font-weight: 600;
                font-variant-numeric: tabular-nums; }
.mapsvg .strack { fill: var(--track); }
.mapsvg .sbar { fill: var(--fill); }
.events { list-style: none; padding: 0; margin: 0; font-size: 12.5px; }
.events li { display: grid; grid-template-columns: 150px 130px 1fr; gap: 10px;
             padding: 3px 0; border-top: 1px solid var(--grid); }
.when { color: var(--muted); font-variant-numeric: tabular-nums; }
.kind { color: var(--ink2); }
.what { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* the table twin — every value stays reachable without hovering */
.tv { margin-top: 16px; border-top: 1px solid var(--grid); padding-top: 10px; }
.tv summary { cursor: pointer; color: var(--ink2); font-size: 12.5px; }
.tw { overflow-x: auto; margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th, td { text-align: left; padding: 5px 10px 5px 0; vertical-align: top;
         border-bottom: 1px solid var(--grid); }
th { color: var(--muted); font-weight: 500; white-space: nowrap; }
.numeric td + td, .numeric th + th { text-align: right;
         font-variant-numeric: tabular-nums; }

#tip { position: fixed; z-index: 9; max-width: 340px; padding: 8px 10px;
       border-radius: 8px; background: var(--tip-bg); color: var(--tip-ink);
       font-size: 12px; line-height: 1.45; white-space: pre-line;
       pointer-events: none; opacity: 0; transition: opacity .08s; }
#tip.on { opacity: 1; }
@media (max-width: 860px) {
  .kpis { grid-template-columns: 1fr 1fr; }
  .mrow { grid-template-columns: 30px 1fr 58px; }
  .mname { display: none; }
  .events li { grid-template-columns: 1fr; gap: 0; }
}
@media (max-width: 520px) {
  .presence { grid-template-columns: 42px 1fr; padding: 15px 16px; gap: 12px; }
  .presence-mark, .presence-orbit { width: 38px; height: 38px; }
}
@media (prefers-reduced-motion: reduce) {
  #tip { transition: none; }
  .presence-working .orbit-arc, .presence-working .orbit-core { animation: none; }
}
"""

# The whole script: a tooltip layer and a theme toggle. Both are ENHANCEMENTS —
# every value they reveal is also printed in the block's table twin, so the page
# is complete with scripting disabled.
JS = """
(function () {
  var tip = document.createElement("div");
  tip.id = "tip";
  document.body.appendChild(tip);
  var shown = null;
  function place(x, y) {
    var r = tip.getBoundingClientRect();
    var left = Math.min(Math.max(8, x + 14), window.innerWidth - r.width - 8);
    var top = y + 18 + r.height > window.innerHeight ? y - r.height - 12 : y + 18;
    tip.style.left = left + "px";
    tip.style.top = Math.max(8, top) + "px";
  }
  function show(el, x, y) {
    if (shown !== el) {
      shown = el;
      tip.textContent = el.getAttribute("data-tip");
      tip.classList.add("on");
    }
    place(x, y);
  }
  function hide() { shown = null; tip.classList.remove("on"); }
  document.addEventListener("pointermove", function (e) {
    var el = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (el) { show(el, e.clientX, e.clientY); } else { hide(); }
  });
  document.addEventListener("pointerleave", hide);
  document.addEventListener("focusin", function (e) {
    var el = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!el) { return hide(); }
    var r = el.getBoundingClientRect();
    show(el, r.left + r.width / 2, r.bottom - 12);
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { hide(); }
  });

  var root = document.documentElement;
  var btn = document.getElementById("theme");
  var KEY = "helmit-dashboard-theme";
  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") { root.setAttribute("data-theme", saved); }
  } catch (err) { /* private mode: the OS preference still rules */ }
  btn.addEventListener("click", function () {
    var dark = root.getAttribute("data-theme") === "dark" ||
      (!root.hasAttribute("data-theme") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    var next = dark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { window.localStorage.setItem(KEY, next); } catch (err) { /* ignore */ }
  });

  var presence = document.getElementById("project-presence");
  function relativeAge(seconds) {
    if (seconds < 60) { return presence.dataset.seconds.replace("{n}", seconds); }
    var minutes = Math.floor(seconds / 60);
    if (minutes === 1) { return presence.dataset.minute; }
    if (minutes < 60) { return presence.dataset.minutes.replace("{n}", minutes); }
    var hours = Math.floor(minutes / 60);
    return hours === 1 ? presence.dataset.hour :
      presence.dataset.hours.replace("{n}", hours);
  }
  function updatePresence() {
    if (!presence) { return; }
    var now = Math.floor(Date.now() / 1000);
    var strong = presence.dataset.matched === "true" &&
      now < Number(presence.dataset.expiresAt || 0);
    var session = now < Number(presence.dataset.sessionExpiresAt || 0);
    var state = strong ? "working" : session ? "recent" : presence.dataset.baseState;
    var last = Number(strong ? presence.dataset.strongLastAt :
      session ? presence.dataset.sessionLastAt : presence.dataset.baseLastAt) || 0;
    var task = strong ? presence.dataset.strongTaskLine :
      session ? "" : presence.dataset.baseTaskLine;
    var phase = strong ? presence.dataset.strongPhase :
      session ? "" : presence.dataset.basePhase;
    for (var i of ["working", "recent", "awaiting", "interrupted", "idle", "unknown"]) {
      presence.classList.toggle("presence-" + i, state === i);
    }
    presence.dataset.state = state;
    document.getElementById("presence-state").textContent =
      presence.dataset["label" + state.charAt(0).toUpperCase() + state.slice(1)];
    var taskEl = document.getElementById("presence-task");
    taskEl.textContent = task;
    taskEl.hidden = !task;
    var phaseEl = document.getElementById("presence-phase");
    phaseEl.textContent = phase ? presence.dataset.phaseTemplate.replace("{n}", phase) : "";
    phaseEl.hidden = !phase;
    document.getElementById("presence-age").textContent = last > 0 ?
      relativeAge(Math.max(0, now - last)) : presence.dataset.noActivity;
  }
  updatePresence();
  window.setInterval(updatePresence, 1000);

  // A file:// page cannot rely on a server, filesystem watcher or model call.
  // Preserve the reading state and reload the single local file lightly while
  // the tab is visible; canonical writers replace it only when sources change.
  var VIEW_KEY = "helmit-dashboard-view:" + window.location.pathname;
  function saveView() {
    var open = [];
    document.querySelectorAll("details").forEach(function (el, index) {
      if (el.open) { open.push(index); }
    });
    try {
      window.sessionStorage.setItem(VIEW_KEY, JSON.stringify({
        x: window.scrollX, y: window.scrollY, open: open
      }));
    } catch (err) { /* private mode: reload still works */ }
  }
  try {
    var view = JSON.parse(window.sessionStorage.getItem(VIEW_KEY) || "null");
    if (view) {
      document.querySelectorAll("details").forEach(function (el, index) {
        el.open = view.open.indexOf(index) !== -1;
      });
      window.requestAnimationFrame(function () { window.scrollTo(view.x, view.y); });
    }
  } catch (err) { /* malformed browser state is disposable */ }
  window.addEventListener("beforeunload", saveView);
  window.setInterval(function () {
    if (!document.hidden) { saveView(); window.location.reload(); }
  }, 3000);
})();
"""


def source_paths():
    """Canonical inputs actually projected by the board, in stable order."""
    paths = []
    for name in ("config.json", "ROADMAP.md", "REQUIREMENTS.md", "STATE.md", "CHANGES.md",
                 "INBOX.md", "metrics.jsonl", "run.jsonl", "quality-receipt.json",
                 "lock.json", "executor-lease.json"):
        paths.append(os.path.join(HELMIT, name))
    phases = os.path.join(HELMIT, "phases")
    if os.path.isdir(phases):
        for base, dirs, files in os.walk(phases):
            dirs.sort()
            for name in sorted(files):
                if name.endswith(".md"):
                    paths.append(os.path.join(base, name))
    map_dir = os.path.join(HELMIT, "map")
    if os.path.isdir(map_dir):
        for base, dirs, files in os.walk(map_dir):
            dirs.sort()
            for name in sorted(files):
                paths.append(os.path.join(base, name))
    activity_dir = os.path.join(HELMIT, "session-activity")
    if os.path.isdir(activity_dir) and not os.path.islink(activity_dir):
        try:
            names = sorted(os.listdir(activity_dir))
        except OSError:
            names = []
        for name in names:
            path = os.path.join(activity_dir, name)
            if re.fullmatch(r"[0-9a-f]{64}\.json", name) and not os.path.islink(path):
                paths.append(path)
    return sorted(set(paths))


def source_fingerprint():
    digest = hashlib.sha256(b"helmit-dashboard-v1\0")
    for path in source_paths():
        rel = os.path.relpath(path, ROOT).encode("utf-8", "surrogateescape")
        digest.update(len(rel).to_bytes(4, "big")); digest.update(rel)
        try:
            data = open(path, "rb").read()
        except OSError:
            data = b"<missing>"
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def source_updated_at():
    stamps = []
    for path in source_paths():
        try:
            stamps.append(os.path.getmtime(path))
        except OSError:
            pass
    if not stamps:
        return ""
    return datetime.fromtimestamp(max(stamps), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def board_fingerprint():
    text = read_text(OUT) or ""
    match = re.search(FINGERPRINT_META, text)
    return match.group(1) if match else ""


def render():
    if os.environ.get("HELMIT_TEST_DASHBOARD_FAILURE") == "1":
        raise RuntimeError("injected dashboard render failure")
    phases = parse_roadmap()
    charts = parse_charts()
    reqs = parse_requirements()
    # ONE read of metrics.jsonl feeds both token charts: the composition folds
    # it per model, the second chart folds the same rows per phase.
    rows = metrics_rows()
    metrics = fold_metrics(rows)
    events = parse_runlog()
    presence = fold_presence(events, phases, charts)
    # ONE fold of the run log feeds both time surfaces: the TIME block reads it
    # per task/session/phase, the timeline reads the same spans per day.
    clock = fold_time(events, phases)
    tests = fold_tests(events)
    mapinfo = fold_map(events)

    # "Data through" is DERIVED from the sources, never the wall clock: the
    # render is then byte-identical over unchanged inputs, and the date shown
    # is the one that matters (how fresh the data is, not when it was drawn).
    # The RAW stamp is kept and not only the pretty one: the map block measures
    # the age of the map against it, so that age hangs off the same anchor the
    # header prints instead of a second, quieter one.
    stamps = [s for s in (metrics["last_ts"], events[-1]["ts"] if events else "") if s]
    newest = max(stamps) if stamps else ""
    through = newest.replace("T", " ")[:19] if newest else ""

    project = os.path.basename(os.path.abspath(ROOT)) or "project"
    title = "%s · %s" % (project, t("page_title"))
    sub = t("header_sub")
    if through:
        sub += " · %s %s" % (t("data_through"), through)
    facts = next_facts()
    open_changes = facts.get("open_changes", [])
    if open_changes:
        sub += " · open CHG %s" % ", ".join(
            change.get("id", "?") for change in open_changes
        )
    inbox = facts.get("inbox", {})
    if inbox.get("open"):
        sub += " · %s %s" % (t("inbox_open"), inbox["open"])
    updated = source_updated_at()
    if updated:
        sub += " · %s %s" % (t("source_updated"), updated)
    fingerprint = source_fingerprint()

    css = (CSS
           .replace("/*LIGHT*/", theme_vars(CHROME_LIGHT, PHASE_LIGHT, REQ_LIGHT,
                                            TOKEN_LIGHT))
           .replace("/*DARK*/", theme_vars(CHROME_DARK, PHASE_DARK, REQ_DARK,
                                           TOKEN_DARK)))

    page = [
        "<!doctype html>",
        "<html lang=\"%s\">" % h(L["lang"]),
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<meta name=\"helmit-source-fingerprint\" content=\"%s\">" % fingerprint,
        "<title>%s</title>" % h(title),
        "<style>%s</style>" % css,
        "</head>",
        "<body>",
        STATUS_START,
        "<div class=\"dash-status\">%s</div>" % h(t("projection_ok")),
        STATUS_END,
        "<main class=\"wrap\">",
        "<header class=\"top\"><div><h1>%s</h1><p class=\"sub\">%s</p></div>"
        "<button type=\"button\" class=\"tgl\" id=\"theme\">%s</button></header>"
        % (h(title), h(sub), h(t("theme"))),
        block_summary(phases, charts, reqs, metrics),
        block_presence(presence),
        block_phases(phases),
        block_tasks(phases, charts),
        block_reqs(reqs),
        # TESTS sits right after the requirements: a requirement is proven by a
        # test, so the block that says what the suite did belongs beside the
        # block that says what is proven — and before the two cost blocks.
        block_tests(tests),
        block_tokens(metrics, rows, phases),
        block_time(clock),
        block_timeline(events, clock),
    ]
    # MAP HEALTH goes LAST, and it is the only block that can be absent — the
    # two facts are one argument. Every block above describes the PROJECT: its
    # phases, its requirements, its suite, its cost, its clock. This one
    # describes a TOOL the project may or may not use, the single optional
    # layer (ADR-009) accounting for whether it pays for itself, so it reads as
    # an appendix to the record and not as a step inside it. Placed higher it
    # would also reshuffle that argued sequence for every project with no map;
    # at the end it ADDS a section instead of displacing one.
    # The map's drawing (REQ-253) is a SECTION of that same block and never a
    # ninth one: the argument above is what makes the block optional, and a
    # second optional block would put the page's shape at the mercy of two
    # conditions instead of one — present with a map dir, present with a
    # `map.txt`, present with neither but a record in the log. One block, one
    # absence. With no excerpt on disk the drawing is simply not in it.
    if mapinfo["present"] or mapinfo["records"]:
        page.append(block_map(mapinfo, newest, fold_map_shape()))
    page += [
        "</main>",
        "<script>%s</script>" % JS,
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(page)


def write_atomically(text):
    current = read_text(OUT)
    if current == text:
        return False
    fd, tmp = tempfile.mkstemp(dir=HELMIT, prefix=".dashboard-", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, OUT)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def failure_view(error):
    """Keep the last valid snapshot and make projection failure visible."""
    current = read_text(OUT)
    if not current:
        return
    message = ("Dashboard update failed; showing the last valid snapshot — %s: %s"
               % (type(error).__name__, error))
    replacement = "%s\n<div class=\"dash-status failed\">%s</div>\n%s" % (
        STATUS_START, h(message), STATUS_END)
    pattern = re.compile(re.escape(STATUS_START) + ".*?" + re.escape(STATUS_END), re.S)
    marked = pattern.sub(replacement, current, count=1)
    if marked == current:
        marked = current.replace("<body>", "<body>\n" + replacement, 1)
    marked = re.sub(FINGERPRINT_META,
                    'name="helmit-source-fingerprint" content="%s"' % ("0" * 64),
                    marked, count=1)
    write_atomically(marked)


def freshness():
    if not os.path.isfile(OUT):
        return "board: ABSENT (%s)" % OUT
    actual = board_fingerprint()
    expected = source_fingerprint()
    if actual and actual == expected:
        return "board: FRESH (source fingerprint %s)" % actual[:12]
    return "board: STALE (board %s, source %s)" % (
        actual[:12] if actual else "unversioned", expected[:12])


try:
    if CMD in ("stale", "freshness"):
        print(freshness())
    elif CMD == "summary":
        print(summary())
    elif CMD == "ensure":
        verdict = freshness()
        if "FRESH" in verdict:
            print(verdict)
        else:
            changed = write_atomically(render())
            print("board: REPAIRED %s" % OUT if changed else "board: FRESH %s" % OUT)
    elif CMD == "publish":
        changed = write_atomically(render())
        print("board: PUBLISHED %s" % OUT if changed else "board: UNCHANGED %s" % OUT)
    else:
        write_atomically(render())
        print(OUT)
except Exception as err:
    # A board is never a gate: say what went wrong and let the caller continue.
    # EVERY exception, not a chosen few — the header promises exit 0 on every
    # data path, and a promise narrower than its code is the most dangerous
    # defect this repo can hold (a TypeError from a malformed i18n overlay used
    # to escape and print a traceback). Usage errors are refused before this,
    # in the shell, and still exit 2. The class name goes in the message so
    # degrading never costs the diagnosis.
    if CMD in ("render", "publish", "ensure"):
        try:
            failure_view(err)
        except Exception:
            pass
    print("dashboard: could not render (%s: %s)" % (type(err).__name__, err))

if UNFORMATTABLE:
    # Fail-open is not the same thing as quiet. A label the overlay cannot
    # format falls back to the built-in English one and the board still renders
    # — that part is by design. What was never by design is the SILENCE: the
    # page comes out half translated and nothing anywhere says why, which is how
    # a lone `%` in a translation survives review.
    #
    # It goes to stderr and never to the page (a board is an aid, never noise),
    # it is built from the English constants and NEVER through t() — a message
    # about a broken overlay must not be read out of that overlay — and it
    # changes no exit code. Sorted, so the same broken pack says the same thing
    # every run.
    sys.stderr.write(
        "WARNING: HelmIt dashboard — %d label(s) of the '%s' overlay could not "
        "be formatted and fell back to English: %s. In dashboard-i18n.json a "
        "literal percent sign must be written %%%% (see its $note).\n"
        % (len(UNFORMATTABLE), L.get("lang", "en"),
           ", ".join(sorted(UNFORMATTABLE))))
