import json, os, socket, subprocess, sys, time
from datetime import datetime, timezone

USAGE = (
    "usage:\n"
    "  lock.sh acquire   [--session <id>] [--force]\n"
    "  lock.sh release   [--session <id>] [--force]\n"
    "  lock.sh status    [--session <id>]\n"
    "  lock.sh heartbeat [--session <id>] [--force]\n"
)

ROOT = os.environ.get("LK_ROOT") or os.getcwd()
SELF = os.environ.get("LK_SELF") or "lock.sh"
HELMIT_DIR = os.path.join(ROOT, ".helmit")
LOCK = os.path.join(HELMIT_DIR, "lock.json")
MUTEX = os.path.join(HELMIT_DIR, ".lock.takeover.d")
HOST = socket.gethostname()
MUTEX_STALE = 60  # seconds: a takeover mutex older than this is debris


def toint(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


OUR_PID = toint(os.environ.get("LK_PID"), os.getppid())
STALE = max(toint(os.environ.get("LK_STALE"), 900), 0)
DEFAULT_SESSION = os.environ.get("LK_SESSION") or ("pid-%d" % OUR_PID)


def fail(msg, code=1):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def publish_dashboard():
    """Presence transitions refresh the optional projection, never the gate."""
    dashboard = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "dashboard.sh")
    try:
        subprocess.run(["bash", dashboard, "publish", "--project", ROOT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT), check=False)
    except OSError:
        pass


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def age(s):
    """Seconds since the stamp; None = unreadable (treated as infinitely old)."""
    d = parse_iso(s)
    return None if d is None else max((now() - d).total_seconds(), 0.0)


def pid_alive(pid):
    """True/False, or None when it cannot be known (missing/invalid pid)."""
    p = toint(pid, 0)
    if p <= 0:
        return None
    try:
        os.kill(p, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, it is just not ours
    except OSError:
        return None
    return True


# --- lock read/write -----------------------------------------------------------

def read_lock():
    """('free'|'corrupt'|'held', data)."""
    try:
        with open(LOCK, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return "free", None
    except Exception:
        return "corrupt", None
    return ("held", d) if isinstance(d, dict) else ("corrupt", None)


def mkpayload(session, acquired=None):
    t = iso(now())
    return {"pid": OUR_PID, "host": HOST, "session": session,
            "acquired_at": acquired or t, "heartbeat_at": t, "version": 1}


def dump(payload, fh):
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.write("\n")


def create_exclusive(payload):
    """Genuinely atomic acquisition: O_CREAT|O_EXCL has no window between
    check and write — either the kernel creates it for us, or someone had it."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    except OSError as e:
        fail("could not create %s (%s)" % (LOCK, e))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        dump(payload, fh)
    return True


def write_atomic(payload):
    """Replaces the lock via rename: if anything fails midway, the OLD lock
    stays intact — we never leave a half-written lock behind."""
    tmp = "%s.tmp.%d" % (LOCK, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            dump(payload, fh)
        os.replace(tmp, LOCK)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        fail("could not write %s (%s)" % (LOCK, e))


def mutex_enter():
    """Critical section of the takeover. mkdir is atomic on POSIX: two processes
    recovering the same orphan lock do not overwrite each other."""
    for attempt in (1, 2):
        try:
            os.mkdir(MUTEX)
            return True
        except FileExistsError:
            try:
                stale = (time.time() - os.stat(MUTEX).st_mtime) > MUTEX_STALE
            except OSError:
                stale = False
            if attempt == 1 and stale:  # debris of a dead takeover
                try:
                    os.rmdir(MUTEX)
                except OSError:
                    pass
                continue
            return False
        except OSError:
            return False
    return False


def mutex_exit():
    try:
        os.rmdir(MUTEX)
    except OSError:
        pass


# --- classification ------------------------------------------------------------

def classify(d, session):
    """'reentrant' | 'orphan' | 'stale' | 'live'.

    Proof of life = HEARTBEAT, and a dead pid never outvotes a fresh one. Under
    Claude Code every Bash call gets its OWN shell that exits when the call ends
    (measured 03/08: pid 77552 on one call, 29380 on the next), so the pid stored
    a minute ago is already dead while the session is still typing. Treating that
    as death recovered the lock on EVERY acquisition, which is the same as having
    no lock (REQ-231). The pid is only asked once the heartbeat has ALREADY
    expired, and then it separates the two expired cases: a provably dead owner is
    the ORPHAN, worth recovering unasked; an owner still around, or one we cannot
    inspect, is the zombie REPL of a quota stall, which only a human resolves."""
    same_host = (d.get("host") or "") == HOST
    if session and d.get("session") == session:
        return "reentrant"
    if same_host and toint(d.get("pid"), -1) == OUR_PID:
        return "reentrant"
    a = age(d.get("heartbeat_at"))
    if a is not None and a < STALE:
        return "live"
    return "orphan" if owner_gone(d) else "stale"


def owner_gone(d):
    """The recorded owner is a process of THIS host that no longer exists."""
    return (d.get("host") or "") == HOST and pid_alive(d.get("pid")) is False


def describe(d):
    a = age(d.get("heartbeat_at"))
    when = ("%ds ago" % int(a)) if a is not None else "unreadable stamp"
    if (d.get("host") or "") == HOST:
        proc = {True: "ALIVE on this host", False: "DEAD"}[bool(pid_alive(d.get("pid")))]
    else:
        proc = "UNKNOWN (another host — only the heartbeat decides)"
    return [
        "  who:              pid=%s host=%s session=%s" % (
            d.get("pid"), d.get("host"), d.get("session")),
        "  since:            %s  (acquired_at)" % d.get("acquired_at"),
        "  last heartbeat:   %s  (%s; threshold %ds)" % (
            d.get("heartbeat_at"), when, STALE),
        "  owner process:    %s" % proc,
    ]


def explain(d, kind, cmd):
    """Readable block: who, since when, last heartbeat — and the OFFER to
    unlock. No state ever asks for a hand-edited file."""
    head = ("LOCK HELD, but the heartbeat EXPIRED — I will not take it on my own."
            if kind == "stale" else
            "LOCK BUSY — live session working (fresh heartbeat).")
    # Without this note the block reads as a contradiction: "live session" over
    # an owner process the same block reports as DEAD.
    note = [] if kind == "stale" or not owner_gone(d) else [
        "  note:             the recorded process is gone, and that settles nothing —",
        "                    each call runs in its own short-lived shell, so the pid",
        "                    dies while the session keeps working. The FRESH heartbeat",
        "                    is what says somebody is there.",
    ]
    tail = ("If that session died for good (on a quota stall the REPL stays alive and idle),"
            if kind == "stale" else
            "Wait for it to finish; if you know it is stuck,")
    return "\n".join([head] + describe(d) + note + [
        tail, "unlock with:", "  %s %s --force" % (SELF, cmd)])


def blocked(d, kind, cmd):
    print(explain(d, kind, cmd))
    return 2 if kind == "stale" else 3


# --- subcommands ---------------------------------------------------------------

def parse_common(argv):
    session, force = "", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--session":
            i += 1
            if i >= len(argv):
                fail("--session requires a value\n" + USAGE)
            session = argv[i]
        elif a == "--force":
            force = True
        elif a in ("-h", "--help"):
            sys.stdout.write(USAGE)
            sys.exit(0)
        else:
            fail("unknown argument: %s\n%s" % (a, USAGE))
        i += 1
    return (session or DEFAULT_SESSION), force


def need_helmit():
    if not os.path.isdir(HELMIT_DIR):
        fail(".helmit/ does not exist in %s — nothing to lock" % ROOT)


def takeover(session, why, allowed, keep_acquired=False):
    """Takes the lock under the mutex, re-checking the state inside (allowed=None
    skips the re-check: that is --force, which takes it in any state)."""
    if not mutex_enter():
        print("LOCK BUSY — another session is taking over the lock RIGHT NOW (%s). Try again." % MUTEX)
        return 3
    try:
        state, d = read_lock()
        acquired = None
        if state == "held" and d is not None:
            kind = classify(d, session)
            if allowed is not None and kind not in allowed:
                return blocked(d, kind, "acquire")  # the state changed between the read and the mutex
            if keep_acquired:
                acquired = d.get("acquired_at")
        write_atomic(mkpayload(session, acquired))
    finally:
        mutex_exit()
    print(why)
    return 0


def cmd_acquire(argv):
    session, force = parse_common(argv)
    need_helmit()
    if create_exclusive(mkpayload(session)):
        print("lock: acquired — pid=%d host=%s session=%s (%s)" % (
            OUR_PID, HOST, session, LOCK))
        return 0

    state, d = read_lock()
    if state == "free":  # the owner released between the O_EXCL and the read: one retry
        if create_exclusive(mkpayload(session)):
            print("lock: acquired — pid=%d host=%s session=%s (%s)" % (
                OUR_PID, HOST, session, LOCK))
            return 0
        state, d = read_lock()

    if state != "held" or d is None:
        if force:
            return takeover(session, "lock: FORCED takeover over an unreadable lock — pid=%d session=%s" % (
                OUR_PID, session), allowed=None)
        print("\n".join([
            "UNREADABLE LOCK — %s exists but is not a valid lock." % LOCK,
            "I will not touch it on my own, to avoid destroying somebody else state.",
            "unlock with:", "  %s acquire --force" % SELF]))
        return 2

    kind = classify(d, session)
    if force:
        return takeover(session, "lock: FORCED takeover (was pid=%s session=%s, state=%s) — now yours (session=%s)" % (
            d.get("pid"), d.get("session"), kind, session), allowed=None)
    if kind == "reentrant":
        return takeover(session, "lock: re-entrant — it was already yours (session=%s); heartbeat refreshed" % session,
                        allowed=("reentrant",), keep_acquired=True)
    if kind == "orphan":
        return takeover(session, "lock: ORPHAN recovered without asking (owner pid=%s DEAD, session=%s) — now yours (session=%s)" % (
            d.get("pid"), d.get("session"), session), allowed=("orphan", "reentrant"))
    return blocked(d, kind, "acquire")


def cmd_release(argv):
    session, force = parse_common(argv)
    state, d = read_lock()
    if state == "free":
        return 0  # idempotent and silent: releasing what does not exist is success
    if state != "held" or d is None:
        if not force:
            print("UNREADABLE LOCK — %s is not a valid lock; release with: %s release --force" % (LOCK, SELF))
            return 2
        d, kind = {}, "corrupt"
    else:
        kind = classify(d, session)
        # A foreign lock only yields to --force. Releasing is where the tolerance
        # `acquire` gave up in REQ-231 has to stay: the holder comes back to
        # release from a NEW shell with a NEW pid and, unless it names its
        # --session, nothing links it to the record it wrote itself. Refusing
        # here would strand every lock under its own owner until the heartbeat
        # expired. Taking somebody else lock still needs --force, which is the
        # asymmetry: `acquire` may not ASSUME death, `release` may not INVENT a
        # live owner out of a pid the harness itself made ephemeral.
        if not force and kind != "reentrant" and not owner_gone(d):
            return blocked(d, kind, "release")
    try:
        os.unlink(LOCK)
    except FileNotFoundError:
        pass
    except OSError as e:
        fail("could not remove %s (%s)" % (LOCK, e))
    print("lock: released (was pid=%s session=%s, state=%s)" % (
        d.get("pid"), d.get("session"), kind))
    return 0


def cmd_status(argv):
    session, _ = parse_common(argv)
    state, d = read_lock()
    if state == "free":
        print("lock: FREE (%s)" % LOCK)
        return 0
    if state != "held" or d is None:
        print("lock: UNREADABLE (%s) — resolve with: %s acquire --force" % (LOCK, SELF))
        return 0
    label = {"reentrant": "YOURS (re-entrant)",
             "orphan": "ORPHAN (heartbeat expired AND owner dead — the next acquire recovers on its own)",
             "stale": "STALE (heartbeat expired — acquire explains and offers --force)",
             "live": "LIVE (session working)"}[classify(d, session)]
    print("lock: %s" % label)
    for line in describe(d):
        print(line)
    return 0


def cmd_heartbeat(argv):
    session, force = parse_common(argv)
    state, d = read_lock()
    if state == "free":
        sys.stderr.write("error: no active lock at %s — nothing to beat\n" % LOCK)
        return 1
    if state != "held" or d is None:
        sys.stderr.write("error: unreadable lock at %s — resolve with: %s acquire --force\n" % (LOCK, SELF))
        return 1
    kind = classify(d, session)
    if kind != "reentrant" and not force:
        return blocked(d, kind, "heartbeat")  # a heartbeat NEVER steals somebody else lock
    d["pid"], d["host"] = OUR_PID, HOST
    d["heartbeat_at"] = iso(now())
    write_atomic(d)
    print("lock: heartbeat %s (session=%s pid=%d)" % (d["heartbeat_at"], d.get("session"), OUR_PID))
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write(USAGE)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "acquire":
        return cmd_acquire(rest)
    if cmd == "release":
        return cmd_release(rest)
    if cmd == "status":
        return cmd_status(rest)
    if cmd == "heartbeat":
        return cmd_heartbeat(rest)
    sys.stderr.write(USAGE)
    return 1


command = sys.argv[1] if len(sys.argv) > 1 else ""
result = main()
if result == 0 and command in ("acquire", "release", "heartbeat"):
    publish_dashboard()
sys.exit(result)
