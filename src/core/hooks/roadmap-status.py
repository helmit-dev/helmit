import os, re, sys

ROOT = os.environ["RS_ROOT"]
ROADMAP = os.environ["RS_ROADMAP"]
DRY = os.environ.get("RS_DRY") == "1"
MODE = os.environ.get("RS_MODE", "derive")
MARK_PHASE = os.environ.get("RS_PHASE", "")
MARK_STATUS = os.environ.get("RS_STATUS", "")

# The enum of the ROADMAP template, in the order of the workflow. Membership is
# also what RECOGNISES a row: the header cell says "status" and the separator
# says "------", so neither is ever mistaken for data. The ORDER is load-bearing
# too: it is the yardstick of the monotonicity, so index() decides every write.
ENUM = ("todo", "spec", "planned", "implementing", "validated", "shipped")

# The three values the VALIDATION template declares, and the reason they are a
# SET instead of a prefix (REQ-287): read by prefix, the template's own line —
# `result: passed | failed | passed-with-human-items` — matched `passed`, so a
# VALIDATION.md nobody had filled in derived `validated`. The value has to be
# one of the three ON ITS OWN.
PASSED = ("passed", "passed-with-human-items")
FAILED = "failed"

# Same regex, same reason as dashboard.sh (REQ-236): the CHART template defines
# the tick format BY EXAMPLE, inside an HTML comment, and that worked example
# parses as a real ticked task. Documentation about the format is not data in
# it. Each comment collapses to the newlines it spanned so the lines around it
# can never be spliced into one that parses as something neither half was.
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
TASK_LINE = re.compile(r"^-\s+\[([ xX>])\]\s+[0-9][0-9A-Za-z]*\.[0-9]+\b")
# A phase id names a DIRECTORY. Anything that could climb out of phases/ is not
# an id, it is a broken row, and a broken row is left alone.
PHASE_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*\Z")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"),
                                    fh.read())
    except OSError:
        return None


def field(text, key):
    m = re.search(r"^%s:[ \t]*(.*)$" % re.escape(key), text, re.M)
    return m.group(1).strip() if m else ""


def derive(phase_dir):
    """The status the artifacts on disk prove, highest level that holds.

    The levels are checked independently instead of as a chain: a phase whose
    SPEC.md was never written but whose VALIDATION.md says `passed` is validated
    — the proof is the artifact that exists, not the set of artifacts that would
    have existed had every step left its trace.
    """
    level = "todo"
    if read(os.path.join(phase_dir, "SPEC.md")) is not None:
        level = "spec"
    chart = read(os.path.join(phase_dir, "CHART.md"))
    if chart is not None:
        if field(chart, "status") == "approved":
            level = "planned"
        for line in chart.splitlines():
            m = TASK_LINE.match(line)
            if m and m.group(1) in ("x", "X", ">"):
                level = "implementing"
                break
    validation = read(os.path.join(phase_dir, "VALIDATION.md"))
    if validation is not None:
        # The tolerance the real case asked for is NOT in the comparison: it is
        # in read(), which drops the inline HTML comment before field() ever
        # sees the value. Measured in this repo, a VALIDATION.md carries
        # `result: passed-with-human-items` followed by a comment on the same
        # line, and it still lands here as the bare value.
        if field(validation, "result") in PASSED:
            level = "validated"
    return level


def failed(phase_dir):
    """The one artifact that may take a level back, read exactly like `passed`."""
    validation = read(os.path.join(phase_dir, "VALIDATION.md"))
    return validation is not None and field(validation, "result") == FAILED


try:
    with open(ROADMAP, encoding="utf-8", newline="") as fh:
        lines = fh.readlines()
except OSError:
    sys.exit(0)


def rows():
    """(index, cells, eol, phase id, current status) of every roadmap row.

    Raw split, no stripping of the outer pipes: the cells are indexed from the
    ENDS of the row, never counted from the start. The anchor cell may hold a
    literal `|` — the phase 28 row of this very repo quotes the status enum and
    so has 13 fields where a naive parser expects 6 — and rebuilding the row
    from the same list is what keeps every other cell byte-identical.
    """
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        body = line.rstrip("\r\n")
        cells = body.split("|")
        if len(cells) < 4:
            continue
        pid = cells[1].strip()
        if not PHASE_ID.match(pid):
            continue
        yield i, cells, line[len(body):], pid, cells[-2].strip().lower()


def apply(edits):
    """Write the edited rows atomically, then say one line per cell changed.

    Exits either way: nothing to change is the silent path (REQ-204), and a
    write that fails says so and still exits 0 — a ledger never breaks the
    command that called it.
    """
    if not edits:
        sys.exit(0)
    for i, row, _ in edits:
        lines[i] = row
    if not DRY:
        tmp = "%s.tmp.%d" % (ROADMAP, os.getpid())
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.writelines(lines)
            os.replace(tmp, ROADMAP)
        except OSError as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            print("roadmap-status: could not write %s (%s) — nothing was changed"
                  % (ROADMAP, e))
            sys.exit(0)
    for _, _, message in edits:
        print("roadmap-status: %s%s"
              % (message, " [dry-run]" if DRY else ""))
    sys.exit(0)


if MODE == "mark":
    if MARK_STATUS not in ENUM:
        print("roadmap-status: %s is not a status — the column holds one of: %s"
              % (MARK_STATUS, ", ".join(ENUM)))
        sys.exit(0)
    for i, cells, eol, pid, current in rows():
        if pid != MARK_PHASE:
            continue
        if current not in ENUM:
            print("roadmap-status: the status cell of phase %s holds %s, which is "
                  "not one of the six statuses — mark does not overwrite a row it "
                  "cannot read" % (pid, cells[-2].strip()))
            sys.exit(0)
        if current == MARK_STATUS:
            sys.exit(0)
        cells[-2] = " %s " % MARK_STATUS
        apply([(i, "|".join(cells) + eol,
                "phase %s marked %s (was %s)" % (pid, MARK_STATUS, current))])
    print("roadmap-status: phase %s has no row in the ROADMAP — mark writes a "
          "cell that exists, it never invents a row" % MARK_PHASE)
    sys.exit(0)

PHASES = os.path.join(ROOT, ".helmit", "phases")
edits = []
for i, cells, eol, pid, current in rows():
    if current not in ENUM or current == "shipped":
        continue
    phase_dir = os.path.join(PHASES, pid)
    reason = ""
    if current == "validated" and failed(phase_dir):
        # Named, not derived: with an unticked chart the derivation would say
        # `planned`, and that is not the regression this requirement allows.
        new = "implementing"
        reason = " — VALIDATION.md says result: failed"
    else:
        new = derive(phase_dir)
        if ENUM.index(new) <= ENUM.index(current):
            continue
    cells[-2] = " %s " % new
    edits.append((i, "|".join(cells) + eol,
                  "phase %s -> %s (was %s)%s" % (pid, new, current, reason)))

apply(edits)
