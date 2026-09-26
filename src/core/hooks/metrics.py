import json, os, re, sys, tempfile
from datetime import datetime, timezone

USAGE = (
    "usage:\n"
    "  metrics.sh scan <transcript.jsonl> [--since-cursor <cursor>]\n"
    "  metrics.sh agg [--file <metrics.jsonl>] [--phase <id>] [--task <id>.N] [--project]\n"
    "  metrics.sh reconcile [--claude-dir <dir>] [--codex-dir <dir>] [--file <metrics.jsonl>]\n"
)

FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
# Bucket for usage whose message carries no model id (never seen on real data;
# keeps sum(buckets) == totals no matter what the transcript holds).
UNKNOWN_MODEL = "unknown"
UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jsonl$")
# Window variant of a model id: the bracketed suffix of "claude-opus-5[1m]".
VARIANT_RE = re.compile(r"^(.+?)\[([^\[\]]+)\]$")
# How far the collector's own sum may fall under the final context the platform
# reports for the same subagent before it is a finding (REQ-227). The margin
# measured on real transcripts is 7.8x, so the constant is slack for a snapshot
# taken while the last chunk was still being flushed, never a tuning knob: what
# carries the check is the DIRECTION (a floor), not the number.
CROSS_CHECK_TOLERANCE = 0.01
# Overrides the derived <tmp>/claude-<uid> background root (tests, odd setups).
TASKS_ENV = "HELMIT_CLAUDE_TASKS_DIR"
# The stop record of an ASYNCHRONOUS subagent (REQ-239): the parent transcript
# gets a `<task-notification>` naming it, and the notification of an agent
# carries a `<status>` — a status-less one is a Monitor event about something
# else and names no agent of this fleet.
NOTIFY_MARK = "<task-notification>"
NOTIFY_ID_RE = re.compile(r"<task-id>([^<>]+)</task-id>")
NOTIFY_STATUS_RE = re.compile(r"<status>[^<>]*</status>")
# Cursor namespaces for subagent ids, stripped to compare across roots.
AGENT_PREFIXES = ("tasks/", "agent-")
# A cursor entry of an agent already counted: id, the stop generation it was
# counted at and how many lines of its file that count covered (REQ-240). An
# entry that does not match is a bare id from an older cursor — sealed.
AGENT_ENTRY_RE = re.compile(r"^(.+)#([0-9]+)@([0-9]+)$")
# Where the shell wrapper leaves the OPEN claims of the write-ahead log, one
# JSON per line, for the cold path to ask what is still alive (REQ-241).
OPEN_CLAIMS_ENV = "HELMIT_OPEN_CLAIMS"


def jload(line):
    """Parse one JSONL line; anything malformed is silently ignored."""
    try:
        v = json.loads(line)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def read_lines(path):
    """File lines, or None when missing/unreadable (metrics never break)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return None


def toint(v):
    try:
        return int(v)
    except Exception:
        return 0


def san(s):
    """Cursor-safe token: our cursor separators are ':' and ','."""
    return re.sub(r"[:,]", "_", s or "")


def zeros():
    return dict.fromkeys(FIELDS, 0)


def add_tokens(dst, src):
    """Accumulate one token bucket into another (both keyed by FIELDS)."""
    for k in FIELDS:
        dst[k] += toint(src.get(k))


def normalized_tokens(row, bucket=None):
    """Disjoint fields for new rows and historical Codex v1 captures."""
    source = bucket if isinstance(bucket, dict) else row
    values = {key: max(toint(source.get(key)), 0) for key in FIELDS}
    cursor = row.get("cursor") if isinstance(row.get("cursor"), str) else ""
    if (row.get("platform") == "codex"
            and row.get("token_schema") != "disjoint-v1"
            and cursor.startswith("codex:v1:")):
        values["input_tokens"] = max(
            values["input_tokens"] - values["cache_read_tokens"]
            - values["cache_creation_tokens"], 0)
    return values


def merge_models(dst, src):
    """Accumulate a per-model breakdown into another one."""
    for name, bucket in (src or {}).items():
        add_tokens(dst.setdefault(name, zeros()), bucket)


def split_variant(model_id):
    """Model id as (base, window variant): "claude-opus-5[1m]" gives
    ("claude-opus-5", "1m"), anything without the bracketed suffix gives
    (id, "")."""
    m = VARIANT_RE.match(model_id or "")
    return (m.group(1), m.group(2)) if m else (model_id or "", "")


def note_variant(dst, base, variant):
    """Record one window variant of a base model id. The list behaves as a
    SET, kept sorted: the same id repeats all over a transcript, and an
    observation cannot be double-counted the way a token can."""
    if not base or not variant:
        return
    seen = dst.setdefault(base, [])
    if variant not in seen:
        seen.append(variant)
        seen.sort()


def note_model(dst, model_id):
    """Record the window variant a model id carries, if it carries one."""
    note_variant(dst, *split_variant(model_id))


def merge_variants(dst, src):
    """Accumulate a window-variant dimension into another one."""
    for base, seen in (src or {}).items():
        if isinstance(base, str) and isinstance(seen, list):
            for v in seen:
                if isinstance(v, str):
                    note_variant(dst, base, v)


def tool_results(lines):
    """Every `toolUseResult` of a transcript — what the orchestrator records
    about each subagent it launched, and a second source of truth about the
    fleet next to the transcripts the collector sums itself. The field rides the
    tool-result line, which is of type "user", so nothing here filters by
    type."""
    for d in (jload(l) for l in lines):
        if not d:
            continue
        result = d.get("toolUseResult")
        if isinstance(result, dict):
            yield result


def resolved_models(lines):
    """Every `toolUseResult.resolvedModel` — the only place the window variant
    survives, since `message.model` carries the bare id."""
    for result in tool_results(lines):
        if isinstance(result.get("resolvedModel"), str):
            yield result["resolvedModel"]


def tonum(v):
    """A JSON number as a non-negative int, or None when the field is absent or
    is not one. `True` is an int in python and is not a number here."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v) if v >= 0 else None


def subagent_facts(lines):
    """What the parent transcript knows about each subagent (REQ-227), keyed by
    the same normalized agent id the fleet files are keyed by: the RESOLVED
    model (per subagent, where `message.model` only ever gives the bare id of
    each message), the real duration, which exists nowhere else in this data,
    and the token figure the platform reports for it.

    A launched-but-unfinished subagent records its id and model and no numbers;
    the record of the same agent completing merges over it, so an interrupted
    fleet still carries its models. Read over the WHOLE transcript, never the
    cursor slice, for the reason model_variants is: a fact about an agent cannot
    be double-counted the way a token can, and slicing would drop the agents of
    a window that spent nothing new."""
    facts = {}
    for result in tool_results(lines):
        aid = result.get("agentId")
        if not isinstance(aid, str) or not aid:
            continue
        fact = facts.setdefault(norm_agent(san(aid)), {})
        model = result.get("resolvedModel")
        if isinstance(model, str) and model:
            fact["model"] = model
        for key, field in (("duration_ms", "totalDurationMs"),
                           ("final_context_tokens", "totalTokens")):
            value = tonum(result.get(field))
            if value is not None:
                fact[key] = value
    return {aid: fact for aid, fact in facts.items() if fact}


def message_texts(d):
    """The plain text one transcript line carries: the `content` of a
    queue-operation and the content of a user message, which is a string or a
    list of blocks (both shapes seen on real notifications)."""
    msg = d.get("message")
    for value in (d.get("content"), msg.get("content") if isinstance(msg, dict) else None):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for block in value:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    yield block["text"]


def notified_stops(lines):
    """One entry per stop a `<task-notification>` reports — the only stop record
    a BACKGROUND subagent leaves on the parent transcript. The `<status>` is
    what makes the notification an agent one (completed, failed, killed and
    stopped were all observed, and all of them mean the agent stopped writing);
    a notification without it is a Monitor event, whose id belongs to no fleet
    file and would change nothing even if it were read.

    Stops, not agents: the notification lands once PER STOP, which is what tells
    an agent that stopped once from one that was RESUMED and stopped again
    (REQ-240). One LINE is one stop even when its text repeats across the fields
    message_texts reads, because that repetition is a shape of the record, never
    a second event."""
    stops = []
    for d in (jload(l) for l in lines):
        if not d:
            continue
        here = set()
        for text in message_texts(d):
            if NOTIFY_MARK not in text or not NOTIFY_STATUS_RE.search(text):
                continue
            m = NOTIFY_ID_RE.search(text)
            if m:
                here.add(norm_agent(san(m.group(1))))
        stops.extend(here)
    return stops


def stop_counts(lines):
    """HOW MANY TIMES this transcript says each subagent STOPPED writing, keyed
    like the fleet files (REQ-239/240). Two record shapes, because the platform
    writes two: the completion figures of a synchronous Task (which is exactly
    what the launch record of an async agent lacks) and the notification of an
    asynchronous one. An agent absent from here has no stop record at all: it is
    not summed and not written to the cursor, so a later sweep reads it whole.

    The COUNT is what makes a RESUMED agent visible. Its file was already
    counted and its id is already in the cursor, so the only thing that can
    reopen it is the record of a SECOND stop. The two shapes are added up rather
    than reconciled: no agent was ever seen carrying both (115 of them,
    18/08/2026), and an inflated generation would at worst reopen a finished
    file for a delta of zero, where a missed one loses the spend."""
    counts = {}
    for result in tool_results(lines):
        aid = result.get("agentId")
        if not isinstance(aid, str) or not aid:
            continue
        if all(tonum(result.get(f)) is None
               for f in ("totalTokens", "totalDurationMs")):
            continue
        key = norm_agent(san(aid))
        counts[key] = counts.get(key, 0) + 1
    for key in notified_stops(lines):
        counts[key] = counts.get(key, 0) + 1
    return counts


def cross_check(facts, collected, carried):
    """Confront the platform's own figure for each subagent against what this
    collector summed for the very same agent.

    A FLOOR, not a proximity test, and the distinction is the whole point:
    `totalTokens` is the FINAL CONTEXT of the subagent and the collector's sum
    is the sum of its session — different quantities that CONFER each other and
    never substitute one another. The final context is one of the terms being
    summed, so `collected >= reported` is structural; a sum that lands BELOW it
    means a class of line stopped being counted (or the fleet transcript is
    gone), which is exactly what a second source exists to catch. A number
    ABOVE it is the normal state and says nothing.

    Only agents summed in THIS window are confronted: one the cursor already
    counted was counted right, and comparing it here would report the guard
    against double counting as a defect. That scoping used to leave a blind
    spot, and the stop rule (REQ-239) closed it without a line of change here:
    an agent read in flight was summed in a window where its completion record
    did not exist yet — nothing to confront — and skipped as `carried` in every
    window after. A synchronous agent is now summed in the very window that
    carries its record, so it is always confronted. An asynchronous one reports
    no figure at all (its stop record is a notification), so it stays outside
    the confrontation: no second source there, and no false finding either. An
    agent RESUMED after being counted (REQ-240) is carried by the same rule, and
    for the same reason: what this window sums for it is the GROWTH of its file,
    a quantity the reported final context is no floor for."""
    confronted, reported_sum, collected_sum, divergent = 0, 0, 0, []
    for aid in sorted(facts):
        reported = facts[aid].get("final_context_tokens")
        if reported is None or aid in carried:
            continue
        got = toint(collected.get(aid))
        confronted += 1
        reported_sum += reported
        collected_sum += got
        if got < reported * (1.0 - CROSS_CHECK_TOLERANCE):
            divergent.append(aid)
    if not confronted:
        return {}
    return {"tolerance": CROSS_CHECK_TOLERANCE, "confronted": confronted,
            "reported_final_context": reported_sum, "collected": collected_sum,
            "divergent": divergent}


def is_codex(lines):
    for d in (jload(l) for l in lines):
        if d and d.get("type") == "event_msg":
            p = d.get("payload")
            if isinstance(p, dict) and p.get("type") == "token_count":
                return True
    return False


# --- claude-code parser (REQ-036) -------------------------------------------

def claude_entries(lines):
    for d in (jload(l) for l in lines):
        if not d or d.get("type") != "assistant":
            continue
        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        yield d.get("requestId") or d.get("uuid") or "", usage, msg.get("model") or ""


def pack_counted(usage):
    """Cursor field holding the usage already counted for a request id."""
    return ",".join(str(toint((usage or {}).get(k))) for k in FIELDS)


def unpack_counted(field):
    """The packed field back as a bucket, or None when it is not one."""
    parts = field.split(",")
    if len(parts) != len(FIELDS):
        return None
    return dict(zip(FIELDS, (toint(p) for p in parts)))


def parse_claude_cursor(cursor):
    """(lines already scanned, last request id, usage counted for it, agent
    ids). A v1 cursor carries no usage and yields None there, which is the
    caller's signal to skip that request id whole — what v1 meant."""
    parts = (cursor or "").split(":", 5)
    if len(parts) < 5 or parts[0] != "claude" or parts[1] not in ("v1", "v2"):
        return 0, "", None, []
    counted, agents = None, parts[4]
    if parts[1] == "v2" and len(parts) == 6:
        counted, agents = unpack_counted(parts[4]), parts[5]
    return toint(parts[2]), parts[3], counted, [a for a in agents.split(",") if a]


def sum_claude(lines, carry_rid="", carry_usage=None):
    """Dedup by requestId and sum. The LAST occurrence wins: streamed chunks
    repeat the id with a cumulative usage snapshot (REQ-166). Returns
    (totals, models, model, sanitized-last-request-id, usage counted for it),
    where models is the per-model-id breakdown of the very same requests
    (REQ-167) — the winning chunk carries the model, so buckets and totals can
    never disagree.

    Straddle guard (REQ-229): a cursor written BETWEEN the chunks of a message
    still being streamed reopens its request id in the next window, with a
    larger cumulative snapshot. `carry_usage` is what the previous scan already
    counted for that id, so only the difference is added and the final chunk —
    the one carrying the whole output of the message — is never lost. The
    returned usage is the full snapshot, not the difference: it is what the next
    window must subtract, however many windows the message straddles."""
    seen, order, model, anon = {}, [], "", 0
    for rid, usage, m in claude_entries(lines):
        if not rid:
            anon += 1
            rid = "_anon_%d" % anon
        if carry_usage is None and carry_rid and san(rid) == carry_rid:
            continue  # v1 cursor: no usage to subtract, drop the id as it did
        if rid not in seen:
            order.append(rid)
        seen[rid] = (usage, m)
        if m and not m.startswith("<"):  # e.g. "<synthetic>"
            model = m
    totals, models, cumulative, calls = zeros(), {}, {}, 0
    for rid in order:
        u, m = seen[rid]
        one = {"input_tokens": toint(u.get("input_tokens")),
               "output_tokens": toint(u.get("output_tokens")),
               "cache_read_tokens": toint(u.get("cache_read_input_tokens")),
               "cache_creation_tokens": toint(u.get("cache_creation_input_tokens"))}
        cumulative[rid] = dict(one)
        carried_request = carry_usage is not None and san(rid) == carry_rid
        if carried_request:
            one = {k: max(one[k] - toint(carry_usage.get(k)), 0) for k in FIELDS}
        if any(one.values()) and not carried_request:
            calls += 1
        add_tokens(totals, one)
        add_tokens(models.setdefault(m or UNKNOWN_MODEL, zeros()), one)
    # All-zero buckets are dropped: "<synthetic>" messages (API placeholders)
    # always report zero usage and would otherwise show up as a phantom model
    # on every single line. Dropping them cannot break sum(buckets) == totals.
    models = {k: v for k, v in models.items() if any(v.values())}
    if not order:  # empty window: the cursor keeps pointing where it pointed
        return totals, models, model, carry_rid, carry_usage, calls
    return totals, models, model, san(order[-1]), cumulative[order[-1]], calls


def norm_agent(aid):
    """Root-independent agent key. Verified on real data: when a session has
    both roots, tasks/<id>.output and subagents/agent-<id>.jsonl are the SAME
    agent (byte-identical files), so the dedup key must ignore the namespace —
    otherwise every mirrored agent would be counted twice. Stripping also lets
    cursors written before the tasks/ root existed keep matching."""
    for prefix in AGENT_PREFIXES:
        if aid.startswith(prefix):
            aid = aid[len(prefix):]
    return aid


def bg_roots():
    """Roots where a background session keeps its subagent fleet, derived from
    the platform tmp dir and the uid and never hardcoded; TASKS_ENV replaces
    them. Any failure yields no root (fail-open)."""
    override = os.environ.get(TASKS_ENV) or ""
    if override:
        return [override]
    roots = []
    try:
        for tmp in (tempfile.gettempdir(), "/tmp"):
            root = os.path.join(tmp, "claude-%d" % os.getuid())
            if root not in roots:
                roots.append(root)
    except Exception:
        return []
    return roots


def bg_tasks_dirs(path):
    """Background-session subagent dirs for this transcript:
    <root>/<project-slug>/<session-id>/tasks. The slug and session id come from
    the transcript path itself (same slug convention as ~/.claude/projects).
    Any failure yields no dir (fail-open)."""
    try:
        sid = os.path.basename(path)
        if sid.endswith(".jsonl"):
            sid = sid[:-6]
        slug = os.path.basename(os.path.dirname(path))
        if not sid or not slug:
            return []
        found = []
        for root in bg_roots():
            d = os.path.join(root, slug, sid, "tasks")
            if os.path.isdir(d) and d not in found:
                found.append(d)
        return found
    except Exception:
        return []


def bg_session_ids(slug):
    """Session ids that left a subagent fleet under <root>/<slug>/<id>/tasks.
    A background session writes its fleet there and often nothing at all to the
    interactive dir, so whoever only LISTS that dir never learns those sessions
    exist (REQ-226)."""
    found = []
    for root in bg_roots():
        base = os.path.join(root, slug)
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for sid in names:
            if sid not in found and os.path.isdir(os.path.join(base, sid, "tasks")):
                found.append(sid)
    return found


def parse_agent_entry(entry):
    """One agent token of a cursor as (key, stop generation counted, lines
    already summed). A BARE id — every cursor written before REQ-240 — carries
    neither and reads as (key, None, None): SEALED, which is the behaviour it had
    when it was written. There is no way to tell how much of that file it
    counted, and guessing a boundary is how a recount starts."""
    m = AGENT_ENTRY_RE.match(entry)
    if not m:
        return norm_agent(entry), None, None
    return norm_agent(m.group(1)), toint(m.group(2)), toint(m.group(3))


def agent_entry(aid, generation, counted_lines):
    """The cursor token of an agent counted at `generation` up to
    `counted_lines`. The id keeps the namespace it was read under; only the
    comparison strips it (norm_agent)."""
    return "%s#%d@%d" % (aid, generation, counted_lines)


def agent_states(entries):
    """Cursor agent tokens as {key: (token, generation, lines summed)}, the token
    kept as written so its namespace survives a rewrite. The same agent can
    appear more than once when a cold complement merges the cursors of several
    lines: the read that went FURTHEST wins, and a SEALED entry beats any of
    them — it cannot say what it counted, so reading past a boundary nobody knows
    would count part of that file twice."""
    states = {}
    for entry in entries:
        key, generation, counted = parse_agent_entry(entry)
        prev = states.get(key)
        if prev is None:
            states[key] = (entry, generation, counted)
            continue
        if prev[2] is None:
            continue
        if counted is None or (counted, generation) > (prev[2], prev[1]):
            states[key] = (entry, generation, counted)
    return states


def merge_agents(carried, summed):
    """The agent list a cursor carries after a sweep: what came in keeps its
    place, the entry of an agent this sweep read AGAIN is substituted there, and
    a genuinely new agent goes to the end. One token per agent, always — a second
    one would let the older, shorter read seal the newer."""
    states = agent_states(carried)
    fresh = {parse_agent_entry(e)[0]: e for e in summed}
    merged = [fresh.get(key, state[0]) for key, state in states.items()]
    return merged + [e for e in summed if parse_agent_entry(e)[0] not in states]


def fleet_delta(lines, already):
    """What a subagent transcript holds BEYOND its first `already` lines: the
    whole file summed, minus the very same read over the prefix a cursor says was
    already counted (REQ-240).

    A subtraction and not a scan of the tail, because usage is CUMULATIVE per
    request id and the dedup keeps the last chunk: the difference between the two
    reads is exactly the growth — per model bucket too, which is why the counted
    amount cannot be a stored total — whether the boundary fell between two
    messages or inside one. An `already` past the end of the file (a transcript
    that shrank, which append-only data does not do) yields no delta rather than
    a second count of everything."""
    totals, models, model, _rid, _counted, calls = sum_claude(lines)
    if not already:
        return totals, models, model, calls
    old_totals, old_models, _m, _r, _c, old_calls = sum_claude(lines[:already])
    totals = {k: max(totals[k] - old_totals[k], 0) for k in FIELDS}
    for name, old in old_models.items():
        bucket = models.get(name)
        if bucket:
            for k in FIELDS:
                bucket[k] = max(bucket[k] - toint(old.get(k)), 0)
    return (totals, {k: v for k, v in models.items() if any(v.values())},
            model, max(calls - old_calls, 0))


def sum_fleet(path, seen_agents, stops):
    """Sum the subagent transcripts of one session, skipping what the cursor
    already counted. Subagents live in two roots (interactive and background)
    that MIRROR each other, so the dedup key ignores the namespace (norm_agent)
    and an agent is counted once across both.

    `stops` is how many stop records the parent transcript holds for each agent,
    or None for the COLD path, where nothing is running any more, a stop record
    may never have been written and what is on disk is spend. Two rules ride on
    it:
      REQ-239 — an agent with NO stop record is left for a later sweep and is not
        returned in `agents`, so it never enters the cursor. That absence is what
        kills the freeze: the next sweep reads the finished file whole.
      REQ-240 — an agent whose cursor entry names an OLDER generation was resumed
        and stopped again; its file is read once more, and only what grew past
        the line the entry names is summed.

    Returns (totals, models, model, collected, agents), where `agents` are the
    cursor entries of what THIS sweep summed — new agents and re-read ones, which
    the caller substitutes into the list it carried."""
    totals, models, model, collected, agents, calls = zeros(), {}, "", {}, [], 0
    base = path[:-6] if path.endswith(".jsonl") else path
    states = agent_states(seen_agents)
    done = set()
    sources = [(os.path.join(base, "subagents"), ".jsonl", "")]
    sources += [(d, ".output", "tasks/") for d in bg_tasks_dirs(path)]
    for subdir, suffix, prefix in sources:
        if not os.path.isdir(subdir):
            continue
        try:
            names = sorted(os.listdir(subdir))
        except OSError:
            names = []
        for name in names:
            if not name.endswith(suffix):
                continue
            aid = prefix + san(name[:-len(suffix)])
            key = norm_agent(aid)
            if key in done:
                continue
            _token, counted_at, already = states.get(key, (None, None, 0))
            if already is None:
                continue  # sealed entry of an older cursor: never read again
            generation = counted_at or 0
            if stops is not None:
                generation = stops.get(key, 0)
                if generation < 1 or generation <= (counted_at or 0):
                    continue
            sub_lines = read_lines(os.path.join(subdir, name)) or []
            sub_totals, sub_models, sub_model, sub_calls = fleet_delta(sub_lines, already)
            add_tokens(totals, sub_totals)
            calls += sub_calls
            merge_models(models, sub_models)  # a subagent on another model
            if not model and sub_model:       # keeps its own bucket (REQ-167)
                model = sub_model
            collected[key] = sum(sub_totals.values())
            agents.append(agent_entry(aid, generation, len(sub_lines)))
            done.add(key)
    return totals, models, model, collected, agents, calls


def scan_claude(path, lines, cursor, cold=False):
    skip_lines, carry_rid, carry_usage, seen_agents = parse_claude_cursor(cursor)
    if skip_lines > len(lines):  # rotated/truncated file => full rescan
        skip_lines, carry_rid, carry_usage = 0, "", None
    totals, models, model, last, counted, calls = sum_claude(
        lines[skip_lines:], carry_rid, carry_usage)

    # The second source of truth about the fleet (REQ-227): the model and the
    # duration of each subagent as the parent transcript recorded them. Read
    # BEFORE the sweep because it is also where the stop records are (REQ-239).
    facts = subagent_facts(lines)
    fleet, fleet_models, fleet_model, collected, summed_agents, fleet_calls = sum_fleet(
        path, seen_agents, None if cold else stop_counts(lines))
    add_tokens(totals, fleet)
    calls += fleet_calls
    merge_models(models, fleet_models)
    if not model and fleet_model:
        model = fleet_model
    agents = merge_agents(seen_agents, summed_agents)
    carried = {parse_agent_entry(a)[0] for a in seen_agents}

    # Window variants (REQ-228), read from the WHOLE transcript and not from
    # the delta slice: a bucket id that already carries the suffix keeps it,
    # and the resolved ids of the tool results supply the variant the bare
    # `message.model` dropped.
    variants = {}
    for name in models:
        note_model(variants, name)
    for resolved in resolved_models(lines):
        note_model(variants, resolved)

    # ...and the confrontation of the figure the second source reports for each
    # subagent against what was summed for it above.
    cur = "claude:v2:%d:%s:%s:%s" % (len(lines), last, pack_counted(counted),
                                     ",".join(agents))
    return dict(platform="claude-code", model=model, models=models,
                model_variants=variants, subagents=facts,
                cross_check=cross_check(facts, collected, carried),
                token_schema="disjoint-v1", model_calls=calls,
                cursor=cur, **totals)


# --- codex parser (REQ-036) --------------------------------------------------

def scan_codex(lines, cursor):
    base_idx, b_in, b_cached, b_write, b_out = -1, 0, 0, 0, 0
    if cursor:
        parts = cursor.split(":")
        if len(parts) == 6 and parts[0] == "codex" and parts[1] == "v1":
            base_idx, b_in, b_cached, b_out = (toint(x) for x in parts[2:6])
        elif len(parts) == 7 and parts[0] == "codex" and parts[1] == "v2":
            base_idx, b_in, b_cached, b_write, b_out = (toint(x) for x in parts[2:7])
    last_idx, total, model, declared = -1, None, "", []
    calls = 0
    previous = (b_in, b_cached, b_write, b_out)
    for i, d in enumerate(jload(l) for l in lines):
        if not d:
            continue
        p = d.get("payload")
        if not isinstance(p, dict):
            continue
        if d.get("type") == "event_msg" and p.get("type") == "token_count":
            info = p.get("info")
            if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                last_idx, total = i, info["total_token_usage"]
                current = (toint(total.get("input_tokens")),
                           toint(total.get("cached_input_tokens")),
                           toint(total.get("cache_write_input_tokens")),
                           toint(total.get("output_tokens")))
                if i > base_idx and current != previous:
                    calls += 1
                if i > base_idx:
                    previous = current
        elif d.get("type") in ("turn_context", "session_meta"):
            m = p.get("model")  # best-effort model field
            if isinstance(m, str) and m:
                model = m
                if m not in declared:
                    declared.append(m)
    variants = {}
    for m in declared:
        note_model(variants, m)
    # Codex writes no per-subagent record, so the second-source dimensions stay
    # empty here instead of absent: the schema is the same on both platforms.
    if total is None:
        return dict(platform="codex", model=model, models={},
                    model_variants=variants, subagents={}, cross_check={},
                    token_schema="disjoint-v1", model_calls=0,
                    cursor=cursor or "codex:v2:-1:0:0:0:0", **zeros())
    c_in = toint(total.get("input_tokens"))
    c_cached = toint(total.get("cached_input_tokens"))
    c_write = toint(total.get("cache_write_input_tokens"))
    c_out = toint(total.get("output_tokens"))
    if base_idx > last_idx:  # rotated/truncated file => full rescan
        b_in = b_cached = b_write = b_out = 0
    delta_in = max(c_in - b_in, 0)
    delta_cached = max(c_cached - b_cached, 0)
    delta_write = max(c_write - b_write, 0)
    totals = {"input_tokens": max(delta_in - delta_cached - delta_write, 0),
              "output_tokens": max(c_out - b_out, 0),
              "cache_read_tokens": delta_cached,
              "cache_creation_tokens": delta_write}
    # The codex counter has no model tag: attribute it only when the session
    # declared exactly ONE model — otherwise leave the breakdown empty (a split
    # would be invention, and consumers already handle the field's absence).
    models = {declared[0]: dict(totals)} if len(declared) == 1 and any(totals.values()) else {}
    cur = "codex:v2:%d:%d:%d:%d:%d" % (last_idx, c_in, c_cached, c_write, c_out)
    return dict(platform="codex", model=model, models=models,
                model_variants=variants, subagents={}, cross_check={},
                token_schema="disjoint-v1", model_calls=calls,
                cursor=cur, **totals)


# --- scan ---------------------------------------------------------------------

def cmd_scan(argv):
    path, cursor = "", ""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--since-cursor":
            i += 1
            cursor = argv[i] if i < len(argv) else ""
        elif not path:
            path = a
        i += 1
    if not path:
        sys.stderr.write(USAGE)
        return 1
    lines = read_lines(path)
    if lines is None:  # missing transcript: empty result, never an error
        print(json.dumps(dict(platform="unknown", model="", models={},
                              model_variants={}, subagents={}, cross_check={},
                              cursor=None, **zeros())))
        return 0
    res = scan_codex(lines, cursor) if is_codex(lines) else scan_claude(path, lines, cursor)
    print(json.dumps(res))
    return 0


# --- agg (REQ-038) --------------------------------------------------------------

def load_metrics(path):
    return [d for d in (jload(l) for l in (read_lines(path) or [])) if d]


def cmd_agg(argv):
    path = os.path.join(os.getcwd(), ".helmit", "metrics.jsonl")
    phase, task, scope = None, None, "project"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--file":
            i += 1
            path = argv[i] if i < len(argv) else path
        elif a == "--phase":
            i += 1
            raw = argv[i] if i < len(argv) else ""
            # Numeric ids are stored as ints, alphanumeric ones (e.g. 3c)
            # as strings — match the stored type (REQ-151).
            phase = toint(raw) if raw.isdigit() else (raw or None)
            scope = "phase %s" % phase
        elif a == "--task":
            i += 1
            task = argv[i] if i < len(argv) else None
            scope = "task %s" % task
        elif a == "--project":
            scope = "project"
        i += 1
    rows = load_metrics(path)
    if phase is not None:
        rows = [r for r in rows if r.get("phase") == phase]
    if task is not None:
        rows = [r for r in rows if r.get("task") == task]
    totals = {k: sum(normalized_tokens(r)[k] for r in rows) for k in FIELDS}
    print("metrics agg — scope: %s — file: %s" % (scope, path))
    print("  lines:                  %d" % len(rows))
    print("  input_tokens:           %d" % totals["input_tokens"])
    print("  output_tokens:          %d" % totals["output_tokens"])
    print("  cache_read_tokens:      %d" % totals["cache_read_tokens"])
    print("  cache_creation_tokens:  %d" % totals["cache_creation_tokens"])
    for plat in sorted({r.get("platform") or "?" for r in rows}):
        sub = [r for r in rows if (r.get("platform") or "?") == plat]
        print("  by platform %-12s lines=%d in=%d out=%d" % (
            plat + ":", len(sub),
            sum(normalized_tokens(r)["input_tokens"] for r in sub),
            sum(normalized_tokens(r)["output_tokens"] for r in sub)))
    # Per-model breakdown (REQ-167). Lines written before the field existed are
    # counted apart instead of being attributed to their (session-wide) "model":
    # no silent misattribution, and the JSON tail line keeps its old shape.
    by_model, no_breakdown = {}, 0
    for r in rows:
        mm = r.get("models")
        if isinstance(mm, dict) and mm:
            for name, bucket in mm.items():
                if isinstance(bucket, dict):
                    add_tokens(by_model.setdefault(name, zeros()),
                               normalized_tokens(r, bucket))
        elif any(normalized_tokens(r).values()):
            no_breakdown += 1
    for name in sorted(by_model):
        b = by_model[name]
        print("  by model %-15s in=%d out=%d cache_read=%d cache_creation=%d" % (
            name + ":", b["input_tokens"], b["output_tokens"],
            b["cache_read_tokens"], b["cache_creation_tokens"]))
    if no_breakdown:
        print("  by model: %d line(s) with no per-model breakdown (written before REQ-167)"
              % no_breakdown)
    # Window variants (REQ-228). Printed on their own line, never appended to a
    # "by model" one, whose shape is a parsed contract.
    variants = {}
    for r in rows:
        merge_variants(variants, r.get("model_variants")
                       if isinstance(r.get("model_variants"), dict) else {})
    if variants:
        print("  window variants: %s (priced apart from the bare id; an observed"
              " dimension, never a per-token split)"
              % ", ".join("%s -> %s" % (b, "/".join(variants[b]))
                          for b in sorted(variants)))
    # The cross-check of the second source (REQ-227), reported where the data is
    # read. Only the confrontations are aggregated, never the per-subagent facts:
    # those are observed over the whole transcript and repeat on every line of a
    # session, so summing durations across lines would multiply them. The
    # confrontations do not repeat — each agent is confronted in the one window
    # that summed it.
    confronted, reported_ctx, collected_sum, divergent = 0, 0, 0, []
    for r in rows:
        c = r.get("cross_check")
        if not isinstance(c, dict) or not c:
            continue
        confronted += toint(c.get("confronted"))
        reported_ctx += toint(c.get("reported_final_context"))
        collected_sum += toint(c.get("collected"))
        for aid in c.get("divergent") or []:
            if isinstance(aid, str) and aid not in divergent:
                divergent.append(aid)
    if confronted:
        print("  cross-check: %d subagent(s) confronted against the platform's own"
              " record — collected %d against %d of final context reported. These"
              " are DIFFERENT quantities: the reported figure is the FINAL CONTEXT"
              " of the subagent, not the sum of its session, so they confer each"
              " other and never substitute one another. Only a collected sum BELOW"
              " the reported context is a finding, because that context is one of"
              " the terms summed." % (confronted, collected_sum, reported_ctx))
    if divergent:
        print("  cross-check DIVERGENCE: %d subagent(s) summed less than their own"
              " final context (floor: %g%% of it) — a class of line stopped being"
              " counted, or the fleet transcript is gone: %s"
              % (len(divergent), (1.0 - CROSS_CHECK_TOLERANCE) * 100,
                 ", ".join(divergent)))
    # The caveat that rides with an inherited phase, declared where it is read
    # (REQ-225). The count is over the FILTERED rows: it describes this scope.
    inherited = sum(1 for r in rows if r.get("phase_source") == "state")
    if inherited:
        print("  phase: %d line(s) inherited the phase from STATE.md instead of"
              " a commit message (session residue, no task). A residue can"
              " straddle a phase boundary, so an inherited phase is an"
              " approximate attribution, not a measurement." % inherited)
    print(json.dumps(dict(totals, lines=len(rows))))
    return 0


# --- reconcile (REQ-038) --------------------------------------------------------

def mkline(res, session, attribution=None, diagnostic=None):
    # `phase` stays null here on purpose: unlike the hot capture, a cold
    # reconciliation runs long after the session it is recovering, so the
    # phase STATE.md holds today says nothing about the work in that
    # transcript. Inheriting it would be inventing an attribution.
    attribution = attribution or {}
    row = {"ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "platform": res["platform"], "model": res["model"],
            "models": res.get("models") or {},
            "model_variants": res.get("model_variants") or {},
            "subagents": res.get("subagents") or {},
            "cross_check": res.get("cross_check") or {},
            "task": attribution.get("task"), "phase": attribution.get("phase"),
            "phase_source": attribution.get("phase_source"), "session": session,
            "input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
            "cache_read_tokens": res["cache_read_tokens"],
            "cache_creation_tokens": res["cache_creation_tokens"],
            "token_schema": res.get("token_schema") or "legacy",
            "model_calls": max(toint(res.get("model_calls")), 0),
            "source": "reconcile", "cursor": res.get("cursor")}
    if diagnostic:
        row["diagnostic"] = diagnostic
    return row


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def codex_rollout_context(lines):
    """The project and time interval a Codex rollout itself can prove."""
    roots, times = set(), []
    for item in (jload(line) for line in lines):
        if not item:
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
            roots.add(os.path.realpath(payload["cwd"]))
        stamp = parse_timestamp(item.get("timestamp"))
        if stamp:
            times.append(stamp)
    return roots, (min(times), max(times)) if times else (None, None)


def closed_task_windows(root):
    """Closed WAL intervals, keyed by task, without guessing from STATE."""
    path = os.path.join(root, ".helmit", "run.jsonl")
    claims, windows = {}, []
    for event in (jload(line) for line in (read_lines(path) or [])):
        if not event:
            continue
        task, stamp = event.get("task"), parse_timestamp(event.get("ts"))
        if not isinstance(task, str) or not stamp:
            continue
        if event.get("event") == "task_claimed":
            claims[task] = stamp
        elif event.get("event") == "task_committed":
            claimed = claims.pop(task, None)
            if claimed and claimed <= stamp:
                windows.append((task, claimed, stamp))
    return windows


def codex_wal_attribution(lines, root):
    """A recovered Codex rollout is attributable only inside one closed task window."""
    roots, interval = codex_rollout_context(lines)
    project = os.path.realpath(root)
    if project not in roots:
        return None, "foreign project rollout"
    start, end = interval
    if not start or not end:
        return None, "rollout has no complete timestamp interval"
    matches = [task for task, opened, closed in closed_task_windows(root)
               if opened <= start and end <= closed]
    if len(matches) != 1:
        reason = "no closed WAL window" if not matches else "ambiguous WAL windows"
        return None, reason
    task = matches[0]
    phase = task.split(".", 1)[0] if "." in task else None
    if not phase:
        return None, "WAL task has no phase id"
    phase = int(phase) if phase.isdigit() else phase
    return {"task": task, "phase": phase, "phase_source": "reconcile-wal"}, None


def live_sessions():
    """The sessions with work IN FLIGHT right now (REQ-241), read off the OPEN
    claims of the write-ahead log the shell wrapper handed over.

    The cold sweep sums whatever is on disk, so a session that is still writing
    would be counted PARTIALLY and frozen at that partial — the defect the stop
    rule closed on the hot side, walking back in through the door reconcile
    leaves open. The signal is the `session=` of the claim (REQ-234) and nothing
    else: it is per session, so one live wave never stops the sweep from
    recovering the dead sessions around it, and a claim that cannot name its
    session makes no session live — refusing over a record that names nobody
    would be guessing. No log, no claim, no run-log.sh: no live session."""
    live = set()
    for claim in (jload(l) for l in (os.environ.get(OPEN_CLAIMS_ENV) or "").splitlines()):
        sid = (claim or {}).get("session")
        if isinstance(sid, str) and sid:
            live.add(sid)
    return live


def counted_agents(rows):
    """The agent ids a session's metrics lines PROVE were already counted, read
    off their own cursors, or None when a line cannot say — no cursor at all, or
    one this parser does not own. Proof is the condition for completing a
    session (REQ-239): with a line that cannot say what it counted, the only
    append-only answer is to leave the session alone. The same agent may show up
    in two lines at two generations (it was resumed): the tokens are handed over
    as they were written and agent_states keeps the read that went furthest."""
    agents = []
    for r in rows:
        cur = r.get("cursor")
        if not isinstance(cur, str) or not cur.startswith(("claude:v1:", "claude:v2:")):
            return None
        for aid in parse_claude_cursor(cur)[3]:
            if aid not in agents:
                agents.append(aid)
    return agents


def complete_fleet(path, lines, rows):
    """The cold net for a session that already has lines but whose fleet is only
    PARTLY in them (REQ-239): sum the agents missing from the record and nothing
    else. Returns a scan result, or None when the record cannot prove what it
    counted.

    The parent transcript is frozen by a cursor that points past its last line:
    what the hot capture already counted there is not counted again, and a
    session abandoned mid-wave still gets the agents it was waiting on. The
    resulting cursor keeps the POSITION the session's last line recorded and
    only takes the new agent list from this sweep — a session that is somehow
    still alive would otherwise resume past lines nobody ever counted."""
    counted = counted_agents(rows)
    if counted is None:
        return None
    frozen = "claude:v2:%d::%s:%s" % (len(lines), pack_counted(None), ",".join(counted))
    res = scan_claude(path, lines, frozen, cold=True)
    base = rows[-1]["cursor"]
    res["cursor"] = base.rsplit(":", 1)[0] + ":" + res["cursor"].rsplit(":", 1)[1]
    return res


def cmd_reconcile(argv):
    home = os.path.expanduser("~")
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
    claude_dir = os.path.join(home, ".claude", "projects", slug)
    codex_dir = os.path.join(home, ".codex", "sessions")
    mfile = os.path.join(os.getcwd(), ".helmit", "metrics.jsonl")
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--claude-dir":
            i += 1
            claude_dir = argv[i] if i < len(argv) else claude_dir
        elif a == "--codex-dir":
            i += 1
            codex_dir = argv[i] if i < len(argv) else codex_dir
        elif a == "--file":
            i += 1
            mfile = argv[i] if i < len(argv) else mfile
        i += 1

    # The lines a session already has (source hook|stop|reconcile). Their
    # PARENT transcript is never read again — v1 simplification, never
    # double-count — but their fleet can still be completed (REQ-239).
    recorded = {}
    for r in load_metrics(mfile):
        sid = r.get("session")
        if sid:
            recorded.setdefault(sid, []).append(r)
    existing = set(recorded)
    new_rows = []

    # The sessions to sweep are the UNION of the transcripts in claude_dir and
    # the background sessions that only left a fleet in tasks/ (REQ-226): the
    # parent transcript of a background session may never land here, and listing
    # this dir alone would then hide the whole fleet. So a missing claude_dir is
    # not the end of the sweep either — the fleet of an absent parent is spend
    # all the same.
    names = []
    if os.path.isdir(claude_dir):
        try:
            names = sorted(os.listdir(claude_dir))
        except OSError:
            names = []
    sids = [n[:-6] for n in names if n.endswith(".jsonl")]
    for sid in bg_session_ids(os.path.basename(os.path.normpath(claude_dir))):
        if sid not in sids:
            sids.append(sid)
    # ...minus the ones still WORKING (REQ-241). The rule the hot sweep obeys —
    # do not read what still changes — cannot be obeyed here, since the cold path
    # has to sum a fleet that will never get a stop record; so the session that
    # is still writing is not read at all, and stays whole for a later sweep.
    # Platform boundary (ADR-010): the claude sweep only. Codex takes the session
    # total as a delta of its own cumulative counter and never freezes a partial.
    live = live_sessions()
    skipped_live = [sid for sid in sids if sid in live]
    for sid in sids:
        if sid in live:
            continue
        # The path need not exist: scan_claude locates the fleet FROM it and
        # reads an absent parent as an empty transcript.
        fpath = os.path.join(claude_dir, sid + ".jsonl")
        lines = read_lines(fpath) or []
        # A cold sweep sums whatever is on disk (cold=True): the sessions here
        # are dead, so a fleet with no stop record is spend, not work in flight.
        if sid in recorded:
            res = complete_fleet(fpath, lines, recorded[sid])
        else:
            res = scan_claude(fpath, lines, "", cold=True)
        if res is None or not any(res[k] for k in FIELDS):
            continue  # nothing missing, or zero-usage session: no noise line
        new_rows.append(mkline(res, sid))
        existing.add(sid)

    skipped_foreign = []
    project_root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if os.path.isdir(codex_dir):
        for dirpath, _dirs, files in os.walk(codex_dir):
            for name in sorted(files):
                if not (name.startswith("rollout-") and name.endswith(".jsonl")):
                    continue
                m = UUID_RE.search(name)
                sid = m.group(1) if m else name[:-6]
                if sid in existing:
                    continue
                lines = read_lines(os.path.join(dirpath, name)) or []
                res = scan_codex(lines, "")
                if not any(res[k] for k in FIELDS):
                    continue
                attribution, diagnostic = codex_wal_attribution(lines, project_root)
                if diagnostic == "foreign project rollout":
                    skipped_foreign.append(sid)
                    continue
                new_rows.append(mkline(res, sid, attribution, diagnostic))
                existing.add(sid)

    if new_rows:
        try:
            with open(mfile, "a", encoding="utf-8") as fh:
                for row in new_rows:
                    fh.write(json.dumps(row) + "\n")
        except OSError as e:
            sys.stderr.write("metrics reconcile: cannot write %s (%s)\n" % (mfile, e))
            return 0
    print("reconcile: %d session(s) appended to %s" % (len(new_rows), mfile))
    for row in new_rows:
        print("  + %s %s (in=%d out=%d)" % (
            row["platform"], row["session"], row["input_tokens"], row["output_tokens"]))
    # Said out loud, and per session: a skip nobody hears is a session silently
    # missing from the totals, which is the same hole read from the other side.
    for sid in skipped_live:
        print("  - claude-code %s SKIPPED: live session (the run log still has an"
              " open claim for it). A session that is still writing would be"
              " summed in flight; run reconcile again when the work is done."
              % sid)
    for sid in skipped_foreign:
        print("  - codex %s SKIPPED: foreign project rollout (not imported into this"
              " project's telemetry)." % sid)
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write(USAGE)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "scan":
        return cmd_scan(rest)
    if cmd == "agg":
        return cmd_agg(rest)
    if cmd == "reconcile":
        return cmd_reconcile(rest)
    sys.stderr.write(USAGE)
    return 1


sys.exit(main())
