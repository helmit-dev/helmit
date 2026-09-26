import datetime
import json
import os
import re
import sys

ROOT = os.environ["RC_ROOT"]
REQS = os.environ["RC_REQS"]
DRY = os.environ.get("RC_DRY") == "1"
PHASE = os.environ.get("RC_PHASE", "")
RECEIPT_MATCH = os.environ.get("RC_MATCH") == "1"
LOG = os.environ.get("RC_LOG", "")

if not re.fullmatch(r"[0-9][0-9A-Za-z_-]*", PHASE):
    print("req-close: --phase requires a valid numbered phase id", file=sys.stderr)
    raise SystemExit(2)

commits = {}
for block in LOG.split("\x1e"):
    if "\x1f" not in block:
        continue
    sha, message = block.split("\x1f", 1)
    commits[sha.strip()] = message

try:
    with open(REQS, encoding="utf-8") as handle:
        lines = handle.readlines()
except OSError as exc:
    print("req-close: could not read %s (%s)" % (REQS, exc), file=sys.stderr)
    raise SystemExit(2)

receipt_path = os.path.join(ROOT, ".helmit", "quality-receipt.json")
try:
    with open(receipt_path, encoding="utf-8") as handle:
        receipt = json.load(handle)
except (OSError, ValueError):
    receipt = {}
scope = receipt.get("scope", "")
valid_scope = (
    scope in ("validate:" + PHASE, "ship:" + PHASE)
    or scope.startswith("implement:" + PHASE + ":integration:")
)
if not RECEIPT_MATCH or receipt.get("result") != "passed" or not valid_scope:
    print("req-close: phase proof requires a matching passed full-suite receipt", file=sys.stderr)
    raise SystemExit(2)

chart_path = os.path.join(ROOT, ".helmit", "phases", PHASE, "CHART.md")
try:
    with open(chart_path, encoding="utf-8") as handle:
        chart_lines = handle.read().splitlines()
except OSError:
    chart_lines = []

tasks = []
covered = set()
for line in chart_lines:
    task = re.match(r"^- \[([ xX>])\] (%s[.][1-9][0-9]*)\b" % re.escape(PHASE), line)
    if not task:
        continue
    tasks.append(task.group(1).lower() == "x")
    # `satisfies:` is the current contract. `covers:` remains readable so an
    # older phase chart can still be closed without rewriting its history.
    claim = re.search(r"\s·\s(?:satisfies|covers):\s*((?:REQ-[0-9]+[ ,]*)+)", line, re.I)
    if claim:
        covered.update(rid.upper() for rid in re.findall(r"REQ-[0-9]+", claim.group(1), re.I))
if not tasks or not all(tasks):
    print("req-close: phase proof requires every planned task complete", file=sys.stderr)
    raise SystemExit(2)

phase_rows = []
for index, line in enumerate(lines):
    if not line.lstrip().startswith("|"):
        continue
    cells = line.rstrip("\n").split("|")
    if len(cells) < 5 or not re.fullmatch(r"REQ-[0-9]+", cells[1].strip()):
        continue
    if cells[-3].strip() == PHASE:
        phase_rows.append((index, cells[1].strip(), cells))

orphans = [rid for _index, rid, _cells in phase_rows if rid not in covered]
if orphans:
    print("req-close: uncovered phase requirements: " + ",".join(orphans), file=sys.stderr)
    raise SystemExit(2)

promoted = []
for index, rid, cells in phase_rows:
    if cells[-2].strip() == "proven":
        continue
    width = len(cells[-2])
    cells[-2] = (" %s " % "proven").ljust(width)[:max(width, 8)]
    lines[index] = "|".join(cells) + "\n"
    promoted.append(rid)

if promoted and not DRY:
    tmp = "%s.tmp.%d" % (REQS, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp, REQS)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        print("req-close: could not write %s (%s)" % (REQS, exc), file=sys.stderr)
        raise SystemExit(2)

for rid in promoted:
    print("req-close: %s -> proven%s (phase %s, matching full-suite receipt)"
          % (rid, " [dry-run]" if DRY else "", PHASE))

# Close only captures explicitly linked to this phase and requirements. The
# receipt retains the commit hashes carrying current `satisfies:` evidence;
# historical `covers:` subjects remain readable for pre-migration phases.
status = {}
phase_of = {}
for line in lines:
    cells = line.rstrip("\n").split("|")
    if len(cells) >= 5 and re.fullmatch(r"REQ-[0-9]+", cells[1].strip()):
        status[cells[1].strip()] = cells[-2].strip()
        phase_of[cells[1].strip()] = cells[-3].strip()

inbox_path = os.path.join(ROOT, ".helmit", "INBOX.md")
try:
    with open(inbox_path, encoding="utf-8", newline="") as handle:
        inbox_lines = handle.readlines()
except OSError:
    inbox_lines = None

if inbox_lines is not None:
    pattern = re.compile(
        r"^(\s*)- \[ \] \[TRIADO -> FASE ([0-9][0-9A-Za-z_-]*) / "
        r"((?:REQ-\d+)(?:,REQ-\d+)*)\] "
    )
    changed = False
    for index, line in enumerate(inbox_lines):
        match = pattern.match(line)
        if not match or match.group(2) != PHASE:
            continue
        rids = match.group(3).split(",")
        if not all(phase_of.get(rid) == PHASE and status.get(rid) == "proven" for rid in rids):
            continue
        covered_by = {rid: set() for rid in rids}
        for sha, message in commits.items():
            claim = re.search(
                r"\[%s[.]([1-9]\d*)\s+(?:satisfies|covers):\s*((?:REQ-\d+[ ,]*)+)\]"
                % re.escape(PHASE), message, re.I
            )
            if not claim:
                continue
            declared = {rid.upper() for rid in re.findall(r"REQ-\d+", claim.group(2), re.I)}
            for rid in rids:
                if rid in declared:
                    covered_by[rid].add(sha)
        if not all(covered_by.values()):
            continue
        hashes = sorted(set().union(*covered_by.values()))
        receipt_text = "FECHADO -> FASE %s / %s / commits %s / closed-at=%s" % (
            PHASE, ",".join(rids), ",".join(hashes), datetime.date.today().isoformat()
        )
        inbox_lines[index] = "%s- [x] [%s] %s" % (
            match.group(1), receipt_text, line[match.end():]
        )
        changed = True
    if changed and not DRY:
        tmp = "%s.tmp.%d" % (inbox_path, os.getpid())
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as handle:
                handle.writelines(inbox_lines)
            os.replace(tmp, inbox_path)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            print("req-close: could not write %s (%s)" % (inbox_path, exc), file=sys.stderr)
            raise SystemExit(2)
