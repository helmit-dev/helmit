import os, re, sys

ROOT = os.environ.get("SN_ROOT") or os.getcwd()
HELMIT = os.path.join(ROOT, ".helmit")
MODE = os.environ.get("SN_MODE", "check")

CANONICAL = ["## Inbox", "## Backlog", "## Closed"]
FIELD_COMMENT_MAX = 10  # lines, field line through the closing --> inclusive
STATE_DECISIONS_MAX = 12
INBOX_ITEM = re.compile(r"^- \[ \] (?:\[TRIADO -> FASE [0-9][0-9A-Za-z]*(?: / REQ-\d+(?:,REQ-\d+)*)?\] )?\d{4}-\d{2}-\d{2} · [^·\n]+ · .+$")
CHANGE_CLOSED_ITEM = re.compile(r"^- \[x\] \d{4}-\d{2}-\d{2} · [^·\n]+ · .+$")
BACKLOG_ITEM = re.compile(r"^- \[ \] \[BACKLOG -> [^\]\n]+\] \d{4}-\d{2}-\d{2} · [^·\n]+ · .+$")
CLOSED_ITEM = re.compile(r"^- \[x\] \[FECHADO -> [^\]\n]+\] \d{4}-\d{2}-\d{2} · [^·\n]+ · .+$")

# Detection e (REQ-201): the two ledgers, their row selector, the name of the
# penultimate anchor and the enum the last cell must belong to.
REQ_ROW_ID = re.compile(r"^REQ-[0-9]+$")
PHASE_ROW_ID = re.compile(r"^[0-9][0-9A-Za-z]*$")
REQ_STATUS = ("todo", "covered", "proven", "retired")
PHASE_STATUS = ("todo", "spec", "planned", "implementing", "validated", "shipped")


def read_lines(path):
    """File lines, or None when missing/unreadable (fail-open: silence)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().split("\n")
    except OSError:
        return None


def closed_change_inbox_references():
    lines = read_lines(os.path.join(HELMIT, "CHANGES.md")) or []
    references = set()
    for line in lines:
        if not re.match(r"^\| CHG-[0-9]{3,} \|", line):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
        if len(cells) == 9 and cells[8] == "done" and cells[7] != "-":
            references.add(cells[7].replace("\\|", "|").replace("\\\\", "\\"))
    return references


findings = []  # (file, line, description) in detection order — deterministic


def check_inbox():
    rel = os.path.join(".helmit", "INBOX.md")
    lines = read_lines(os.path.join(HELMIT, "INBOX.md"))
    if lines is None:
        return

    # a. duplicated canonical header (whole-line match, first occurrence kept)
    seen_header = {}
    for n, line in enumerate(lines, 1):
        if line in CANONICAL:
            if line in seen_header:
                findings.append((rel, n, "duplicated canonical header '%s' (first at line %d)"
                                 % (line, seen_header[line])))
            else:
                seen_header[line] = n

    # b. exact duplicated item — byte-identical checkbox lines, 2+ occurrences
    seen_item = {}
    for n, line in enumerate(lines, 1):
        if re.match(r"^- \[[ x]\] ", line):
            if line in seen_item:
                findings.append((rel, n, "duplicated item, byte-identical to line %d: %s"
                                 % (seen_item[line], line)))
            else:
                seen_item[line] = n

    # c. canonical order over FIRST occurrences (duplicates are finding a).
    rank = {h: i for i, h in enumerate(CANONICAL)}
    max_rank = -1
    for header, n in sorted(seen_header.items(), key=lambda kv: kv[1]):
        if rank[header] < max_rank:
            findings.append((rel, n, "section '%s' out of canonical order (expected %s)"
                             % (header, " -> ".join(CANONICAL))))
        else:
            max_rank = rank[header]

    # REQ-322: the template is an operational input, rather than informal
    # prose. A complete canonical section set and per-section grammar make a
    # destination/count receipt deterministic; fail open only when INBOX.md
    # itself is absent (handled above), never by guessing a malformed write.
    for header in CANONICAL:
        if header not in seen_header:
            findings.append((rel, 1, "missing canonical section '%s'" % header))

    section = None
    closed_change_references = closed_change_inbox_references()
    item_patterns = {
        "## Inbox": INBOX_ITEM,
        "## Backlog": BACKLOG_ITEM,
        "## Closed": CLOSED_ITEM,
    }
    for n, line in enumerate(lines, 1):
        if line in CANONICAL:
            section = line
            continue
        if re.match(r"^- \[[^\]]*\]", line):
            if section is None:
                findings.append((rel, n, "checkbox item is outside a canonical section"))
            elif (not item_patterns[section].match(line)
                  and not (section == "## Inbox" and CHANGE_CLOSED_ITEM.match(line)
                           and any(reference in line for reference in closed_change_references))):
                findings.append((rel, n, "item violates %s canonical format/destination contract" % section))


def check_inbox_history():
    directory = os.path.join(HELMIT, "history")
    if not os.path.isdir(directory):
        return
    seen = {}
    for name in sorted(os.listdir(directory)):
        if not name.startswith("INBOX-"):
            continue
        rel = os.path.join(".helmit", "history", name)
        if not re.fullmatch(r"INBOX-20[0-9]{2}\.md", name):
            findings.append((rel, 1, "history filename must be INBOX-<year>.md"))
            continue
        lines = read_lines(os.path.join(directory, name))
        if lines is None:
            continue
        for n, line in enumerate(lines, 1):
            if not re.match(r"^- \[[ xX]\] ", line):
                continue
            if not re.match(r"^- \[[xX]\] ", line):
                findings.append((rel, n, "active item found in resolved Inbox history"))
            if line in seen:
                findings.append((rel, n, "duplicated archived item, first at %s:%d" % seen[line]))
            else:
                seen[line] = (rel, n)


def check_state():
    rel = os.path.join(".helmit", "STATE.md")
    lines = read_lines(os.path.join(HELMIT, "STATE.md"))
    if lines is None:
        return

    # d. HTML comment opened on a field line and spanning over the budget.
    #    An unterminated comment counts to EOF — worse than a long one.
    field_re = re.compile(r"^\s*-\s*([A-Za-z][A-Za-z0-9 _-]*):")
    for i, line in enumerate(lines):
        m = field_re.match(line)
        if not m:
            continue
        tail = line[line.rfind("<!--"):] if "<!--" in line else ""
        if not tail or "-->" in tail:
            continue  # no comment opened, or opened and closed on the field line
        end = i
        for j in range(i + 1, len(lines)):
            if "-->" in lines[j]:
                end = j
                break
        else:
            end = len(lines) - 1  # never closed: span to EOF
        span = end - i + 1
        if span > FIELD_COMMENT_MAX:
            findings.append((rel, i + 1,
                             "field '%s' carries an HTML comment spanning %d lines (over %d)"
                             % (m.group(1).strip(), span, FIELD_COMMENT_MAX)))

    start = next((i for i, line in enumerate(lines)
                  if line in ("## Decisions made this session", "## Decisions still needed")), None)
    end = next((i for i, line in enumerate(lines[start + 1:], start + 1)
                if line.startswith("## ")), None) if start is not None else None
    if start is not None and end is not None:
        decisions = [i for i in range(start + 1, end) if lines[i].startswith("- ")]
        if len(decisions) > STATE_DECISIONS_MAX:
            findings.append((rel, decisions[STATE_DECISIONS_MAX] + 1,
                             "operational decisions has %d entries (over %d); preserve durable decisions in their owner, then remove them from STATE"
                             % (len(decisions), STATE_DECISIONS_MAX)))


CHART_HEADER = ("status", "parent", "anchor", "requires")


def check_charts():
    phases = os.path.join(HELMIT, "phases")
    if not os.path.isdir(phases):
        return
    for phase in sorted(os.listdir(phases)):
        rel = os.path.join(".helmit", "phases", phase, "CHART.md")
        lines = read_lines(os.path.join(phases, phase, "CHART.md"))
        if lines is None:
            continue
        task_at = next((i for i, line in enumerate(lines) if line == "## Tasks"), len(lines))
        header = {line.split(":", 1)[0] for line in lines[:task_at]
                  if re.match(r"^[a-z-]+:", line)}
        # Historical charts may predate both markers. A newly prepared chart
        # carries prepared-by; approved-by remains readable compatibility.
        modern = "prepared-by" in header or "approved-by" in header
        if modern:
            for name in CHART_HEADER:
                if name not in header:
                    findings.append((rel, 1, "chart header missing '%s:'" % name))
            if not {"satisfies", "covers"}.intersection(header):
                findings.append((rel, 1, "chart header missing relation: expected "
                                 "'satisfies:' or historical 'covers:'"))
        for n, line in enumerate(lines, 1):
            if not re.match(r"^- \[[ x>]\] \S+\s+", line):
                continue
            if not modern:
                continue
            if " · anchor:" not in line:
                findings.append((rel, n, "task missing anchor:"))
            if not any(marker in line for marker in (" · satisfies:", " · supports:", " · covers:")):
                findings.append((rel, n, "task missing requirement relation"))
            if " · verify:" not in line:
                findings.append((rel, n, "task missing focused verify:"))


def table_rows(lines):
    """(line number, cells) for every markdown table row.

    A cell may LEGALLY carry a pipe — `off | phase | full` appears inside the
    prose of 7 rows of this repo's own REQUIREMENTS.md — so the caller indexes
    from BOTH ENDS and never from a cell count. Same reading as the board's
    `table_rows` in dashboard.sh, deliberately: one shape, one interpretation."""
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if len(s) > 1 and s.startswith("|") and s.endswith("|"):
            yield n, [c.strip() for c in s[1:-1].split("|")]


def check_table(rel, path, row_id, mid_name, statuses):
    """e. anchor cells of a ledger row: first (id), penultimate, last (status).

    Header and separator rows are skipped by the SELECTOR (their first cell is
    not an id), never by position — an artifact edited by hand moves lines."""
    lines = read_lines(path)
    if lines is None:
        return
    enum = " | ".join(statuses)
    for n, cells in table_rows(lines):
        if not row_id.match(cells[0]):
            continue
        rid = cells[0]
        if len(cells) < 3:
            # The three anchors would land on the same cells: the row lost a
            # whole column, so there is nothing left to read from the ends.
            # Not a cell count posing as a criterion — a pipe in the prose only
            # ever grows the MIDDLE, so no legitimate row can fall under this.
            findings.append((rel, n, "row '%s': id, '%s' and status collapse onto the "
                             "same cells — the row lost a whole column" % (rid, mid_name)))
            continue
        if not cells[-2]:
            findings.append((rel, n, "row '%s': empty '%s' cell — an anchor column "
                             "(a doubled pipe empties one silently)" % (rid, mid_name)))
        if cells[-1].lower() not in statuses:
            findings.append((rel, n, "row '%s': status '%s' outside the enum (%s)"
                             % (rid, cells[-1], enum)))


check_inbox()
check_inbox_history()
check_state()
check_charts()
check_table(os.path.join(".helmit", "REQUIREMENTS.md"),
            os.path.join(HELMIT, "REQUIREMENTS.md"),
            REQ_ROW_ID, "phase", REQ_STATUS)
check_table(os.path.join(".helmit", "ROADMAP.md"),
            os.path.join(HELMIT, "ROADMAP.md"),
            PHASE_ROW_ID, "covers", PHASE_STATUS)

# REQ-108: the content decides IF we speak — zero findings means zero output.
ordered = sorted(findings, key=lambda x: (x[0], x[1]))
if MODE == "summary":
    grouped = {}
    for artifact, _line, _description in ordered:
        grouped[artifact] = grouped.get(artifact, 0) + 1
    if grouped:
        print("sanity: %d finding(s) in %d artifact(s): %s" % (
            len(ordered), len(grouped),
            ", ".join("%s=%d" % item for item in sorted(grouped.items())),
        ))
else:
    for f, n, desc in ordered:
        print("%s:%d: %s" % (f, n, desc))
sys.exit(0)
