import json, os, re, sys
from datetime import datetime, timezone

USAGE = (
    "usage:\n"
    "  yolo.sh arm <off|phase|full> [--unattended] [--until <iso>]\n"
    "                               [--budget <n>] [--stop-at <point>]\n"
    "  yolo.sh status\n"
    "  yolo.sh expire [--reason <r>]\n"
    "  yolo.sh reap\n"
)

ROOT = os.environ.get("YL_ROOT") or os.getcwd()
SELF = os.environ.get("YL_SELF") or "yolo.sh"
HELMIT_DIR = os.path.join(ROOT, ".helmit")
MANDATE = os.path.join(HELMIT_DIR, "yolo.json")
STATE = os.path.join(HELMIT_DIR, "STATE.md")
ROADMAP = os.path.join(HELMIT_DIR, "ROADMAP.md")
SCOPES = ("off", "phase", "full")


def now():
    frozen = os.environ.get("HELMIT_YOLO_NOW")
    if frozen:
        d = parse_iso(frozen)
        if d is not None:
            return d
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def fail(msg, code=1):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


# --- the mandate file ----------------------------------------------------------

def read_mandate():
    """The armed mandate, or None. An unreadable file is treated as NO mandate:
    failing open here means falling back to supervision, which is the safe side."""
    try:
        with open(MANDATE, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if d.get("scope") not in SCOPES or d.get("scope") == "off":
        return None
    return d


def write_mandate(payload):
    tmp = "%s.tmp.%d" % (MANDATE, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, MANDATE)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        fail("could not write %s (%s)" % (MANDATE, e))


def remove_mandate():
    try:
        os.unlink(MANDATE)
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        fail("could not remove %s (%s)" % (MANDATE, e))


# --- position, read from the artifacts the workflow already keeps ---------------

def workflow_position():
    """The `workflow:` field of STATE.md, or '' when it cannot be read."""
    try:
        with open(STATE, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.search(r"^-\s*workflow:\s*([^\s<]+)", text, re.M)
    return m.group(1).strip() if m else ""


def phase_of(position):
    """The phase id inside a position (`implementing:14.3` -> `14`), or ''."""
    if ":" not in position:
        return ""
    tail = position.split(":", 1)[1].strip()
    return tail.split(".", 1)[0] if tail else ""


def roadmap_order():
    """Phase ids in ROADMAP order. Empty when there is no readable roadmap —
    and an empty order simply means `reap` never claims 'moved past', which is
    the conservative direction."""
    try:
        with open(ROADMAP, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    ids = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        pid = cells[0].strip("`")
        if not pid or set(pid) <= set("-: ") or pid.lower() in ("phase", "id", "fase"):
            continue
        if pid not in ids:
            ids.append(pid)
    return ids


def next_open_phase():
    """(phase_id, err) — the phase a `phase` mandate means: the first ROADMAP
    row, top-down, whose own status is still open and whose `requires:` are all
    satisfied (only shipped counts as satisfied; `none` always is). Same
    queue logic the /next router derives (REQ-139) — deriving from the POSITION
    number instead is the bug that armed a mandate born fulfilled (REQ-156).
    err is non-empty when the roadmap is missing or has no parseable phase
    table; ("", "") means every phase is already closed."""
    closed = {"shipped"}
    known = {"todo", "spec", "planned", "implementing", "validated"} | closed
    try:
        with open(ROADMAP, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return "", "ROADMAP.md is missing or unreadable"
    rows = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0].strip("`") and cells[-1] in known:
            rows.append((cells[0].strip("`"), cells[-3], cells[-1]))
    if not rows:
        return "", "ROADMAP.md has no parseable phase table"
    done = {pid for pid, _, st in rows if st in closed}
    for pid, req, st in rows:
        if st in closed:
            continue
        needs = [x.strip().strip("`") for x in req.split(",")
                 if x.strip() and x.strip().strip("`") != "none"]
        if all(x in done for x in needs):
            return pid, ""
    return "", ""


# --- rendering -----------------------------------------------------------------

def describe(d):
    until = d.get("until") or "none"
    budget = d.get("budget_out")
    budget = "none" if budget in (None, "") else str(budget)
    return ("yolo: %s in force — stops at %s · unattended=%s · until=%s · "
            "budget_out=%s (armed %s)" % (
                d.get("scope"), d.get("stop_at") or "none",
                "yes" if d.get("unattended") else "no",
                until, budget, d.get("armed_at")))


def mandate_progress():
    """Return the mandate and whether it still owns the workflow.

    This pure-read fact is shared by status and reap so all consumers see the
    same boundary between a live mandate and a spent mandate file.
    """
    d = read_mandate()
    if d is None:
        return None, False, ""
    done, why = fulfilled(d, workflow_position())
    return d, not done, why


# --- subcommands ---------------------------------------------------------------

def cmd_arm(argv):
    if not argv or argv[0].startswith("-"):
        fail("arm requires a scope: off | phase | full\n" + USAGE)
    scope, rest = argv[0], argv[1:]
    if scope not in SCOPES:
        fail("unknown scope %r — use off | phase | full\n%s" % (scope, USAGE))

    unattended, until, budget, stop_at = False, None, None, ""
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--unattended":
            unattended = True
        elif a in ("--until", "--budget", "--stop-at"):
            i += 1
            if i >= len(rest):
                fail("%s requires a value\n%s" % (a, USAGE))
            if a == "--until":
                if parse_iso(rest[i]) is None:
                    fail("--until is not an ISO-8601 timestamp: %r" % rest[i])
                until = iso(parse_iso(rest[i]))
            elif a == "--budget":
                try:
                    budget = int(rest[i])
                except ValueError:
                    fail("--budget takes a number of OUTPUT tokens (or omit it for no ceiling)")
            else:
                stop_at = rest[i]
        else:
            fail("unknown argument: %s\n%s" % (a, USAGE))
        i += 1

    if not os.path.isdir(HELMIT_DIR):
        fail(".helmit/ does not exist in %s — nothing to arm" % ROOT)

    if scope == "off":
        return cmd_expire(["--reason", "disarmed"])

    if not stop_at:
        if scope == "full":
            stop_at = "ship:final"
        else:
            phase, err = next_open_phase()
            if err:
                fail("cannot derive the phase for a `phase` mandate — %s. Pass "
                     "--stop-at ship:<phase> to be explicit (never guess: a wrong "
                     "derivation arms a mandate for the wrong phase)." % err)
            if not phase:
                fail("cannot derive the phase for a `phase` mandate — every phase "
                     "in the roadmap is already shipped. Pass "
                     "--stop-at ship:<phase> to be explicit.")
            stop_at = "ship:%s" % phase

    # Born-fulfilled guard (REQ-156): the exact comparison `reap` will run.
    # A mandate whose stopping point is already behind the position would be
    # reaped by the FIRST reap, silently — armed at 04/08, bitten twice.
    # `until` is excluded on purpose: it is an agenda ceiling, not the target.
    done, why = fulfilled({"stop_at": stop_at, "until": None},
                          workflow_position())
    if done:
        fail("mandate would be born fulfilled — stop_at %s is already behind "
             "the current position (%s). Nothing to arm; pass --stop-at with a "
             "point still ahead if you really mean it." % (stop_at, why))

    write_mandate({"version": 1, "scope": scope, "stop_at": stop_at,
                   "unattended": bool(unattended), "until": until,
                   "armed_at": iso(now()), "budget_out": budget})
    print(describe(read_mandate() or {}))
    return 0


def cmd_status(argv):
    """The pure-read verdict on the mandate — the verb every other consumer
    asks when it may not write (REQ-290). It answers the SAME question `reap`
    answers, minus the harvest: a mandate whose stopping point is already
    behind us is reported SPENT, not `in force`, so nobody has to re-implement
    fulfilled() to find that out. The prefix is deliberately not `yolo: off`:
    the file is still on disk and the next reap is what collects it."""
    if argv:
        fail("status takes no arguments\n" + USAGE)
    d, active, why = mandate_progress()
    if d is None:
        print("yolo: off — no mandate in force; every gate is a conversation")
        return 0
    if not active:
        print("yolo: %s FULFILLED — %s; not in force, the next reap collects it"
              % (d.get("scope"), why))
        return 0
    print(describe(d))
    return 0


def cmd_expire(argv):
    reason = ""
    i = 0
    while i < len(argv):
        if argv[i] == "--reason":
            i += 1
            if i >= len(argv):
                fail("--reason requires a value\n" + USAGE)
            reason = argv[i]
        else:
            fail("unknown argument: %s\n%s" % (argv[i], USAGE))
        i += 1
    d = read_mandate()
    existed = remove_mandate()
    if d is None:
        print("yolo: off — no mandate to expire" if not existed
              else "yolo: off — unreadable mandate file removed")
        return 0
    print("yolo: EXPIRED — the %s mandate (%s) is over%s; approvals are "
          "conversations again" % (d.get("scope"), d.get("stop_at"),
                                   ", reason: %s" % reason if reason else ""))
    return 0


def fulfilled(d, position):
    """(bool, reason) — is this mandate's own stopping point behind us?"""
    until = d.get("until")
    if until:
        dt = parse_iso(until)
        if dt is not None and dt <= now():
            return True, "until %s has passed" % until
    stop_at = d.get("stop_at") or ""
    if not position:
        return False, ""
    if stop_at == "ship:final":
        if position == "complete":
            return True, "the project reached `complete`"
        return False, ""
    if stop_at.startswith("ship:"):
        target = stop_at.split(":", 1)[1]
        if position == "complete":
            return True, "the project reached `complete`"
        # The VERB of the stopping point decides, and `ship:` means shipped
        # (REQ-284). Accepting `validated:<target>` too made the mandate die in
        # the window between the commit of /validate and the commit of /ship —
        # a `reap` landing there expired the mandate BEFORE the ship it names,
        # and the /ship gate then read `off` with nobody awake to approve.
        if position == "shipped:%s" % target:
            return True, "phase %s reached `%s`" % (target, position)
        order = roadmap_order()
        here = phase_of(position)
        # A target that is no longer IN the roadmap is a mandate with no scope
        # left, and a mandate with no scope cannot go on holding. Without this
        # the `moved past` clause below is simply dead — measured on 19/08, a
        # mandate aimed at `ship:27` survived shipped:26, shipped:16 AND
        # shipped:6, dying only at `complete`: the most RESTRICTED mandate
        # turned into the widest one because somebody edited ANOTHER artifact.
        # The last phase of a queue is typically the public release, so the
        # blast radius of that silence is the whole point.
        if order and target not in order:
            return True, ("phase %s is no longer in the ROADMAP — a mandate "
                          "whose stopping point vanished has no scope left" % target)
        if here and target in order and here in order:
            if order.index(here) > order.index(target):
                return True, "the project moved past phase %s (now at %s)" % (target, here)
    return False, ""


def cmd_reap(argv):
    """Silent when there is nothing to say: a hook that speaks on every call in
    a project that never armed anything is noise, and noise gets ignored."""
    if argv:
        fail("reap takes no arguments\n" + USAGE)
    d, active, why = mandate_progress()
    if d is None:
        return 0
    if active:
        print(describe(d))
        return 0
    remove_mandate()
    print("yolo: REAPED — the %s mandate ended on its own (%s); approvals are "
          "conversations again" % (d.get("scope"), why))
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write(USAGE)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "arm":
        return cmd_arm(rest)
    if cmd == "status":
        return cmd_status(rest)
    if cmd == "expire":
        return cmd_expire(rest)
    if cmd == "reap":
        return cmd_reap(rest)
    if cmd in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    sys.stderr.write(USAGE)
    return 1


sys.exit(main())
