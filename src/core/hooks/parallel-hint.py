import re, sys

USAGE = (
    "usage:\n"
    "  parallel-hint.sh suggest --command \"<test command>\"\n"
)

# One row per runner. `detect` finds the runner in the command line, `parallel`
# finds a parallel form ALREADY there, `flag` is what would be appended, and
# `note` is the one-breath explanation of what changes. Boundaries are written
# by hand because a test command is a shell line, not a token list: `npx jest`,
# `poetry run pytest`, `./node_modules/.bin/vitest` all have to land.
LEAD = r"(?<![A-Za-z0-9_.-])"
TAIL = r"(?![A-Za-z0-9_-])"

TABLE = [
    {
        "name": "pytest",
        "detect": LEAD + r"(?:pytest|py\.test)" + TAIL,
        "parallel": r"(?<![A-Za-z0-9_-])(?:-n(?=[ =]|$)|--numprocesses|--dist)" + TAIL,
        "flag": "-n auto",
        "note": "one worker per core instead of one process, via pytest-xdist",
    },
    {
        "name": "jest",
        "detect": LEAD + r"jest" + TAIL,
        "parallel": r"(?<![A-Za-z0-9_-])(?:--maxWorkers|-w(?=[ =]|$))" + TAIL,
        "flag": "--maxWorkers=50%",
        "note": "pins the worker pool to half the cores, leaving headroom",
    },
    {
        "name": "vitest",
        "detect": LEAD + r"vitest" + TAIL,
        "parallel": r"(?<![A-Za-z0-9_-])(?:--pool(?=[ =]|$)|--poolOptions|--threads)" + TAIL,
        "flag": "--pool=threads",
        "note": "test files run on worker threads instead of child processes",
    },
    {
        "name": "cargo",
        "detect": LEAD + r"cargo" + TAIL,
        "parallel": LEAD + r"nextest" + TAIL,
        "flag": "",   # cargo is a REPLACEMENT, not an appended flag
        "note": "nextest runs each test in its own process, in parallel",
    },
    {
        "name": "go test",
        "detect": LEAD + r"go\s+test" + TAIL,
        "parallel": r"(?<![A-Za-z0-9_-])(?:-p(?=[ =]|$)|-parallel|--parallel)" + TAIL,
        "flag": "-p 4",
        "note": "builds and tests up to four packages at the same time",
    },
]


def pick(command):
    """The runner this command is running, or None. When more than one row
    matches (a chained command), the LEFTMOST match wins: that is the runner the
    line is about, and picking by table order instead would depend on the order
    somebody happened to type the rows in."""
    best = None
    for row in TABLE:
        m = re.search(row["detect"], command)
        if m is None:
            continue
        if best is None or m.start() < best[0]:
            best = (m.start(), row)
    return None if best is None else best[1]


def suggested(row, command):
    """The command as it would look with the parallel form. Appending is safe
    for every runner in the table (all of them accept flags after positional
    arguments); cargo is the exception, because nextest is a different
    subcommand and not a flag at all."""
    if row["name"] != "cargo":
        return "%s %s" % (command, row["flag"])
    swapped, n = re.subn(LEAD + r"cargo\s+test" + TAIL, "cargo nextest run",
                         command, count=1)
    return swapped if n else "cargo nextest run"


def cmd_suggest(argv):
    command = None
    i = 0
    while i < len(argv):
        if argv[i] == "--command":
            i += 1
            if i >= len(argv):
                sys.stderr.write("--command requires a value\n" + USAGE)
                return 2
            command = argv[i]
        else:
            sys.stderr.write("unknown argument: %s\n%s" % (argv[i], USAGE))
            return 2
        i += 1
    if command is None:
        sys.stderr.write("suggest requires --command\n" + USAGE)
        return 2

    command = command.strip()
    if not command:
        return 0
    row = pick(command)
    if row is None:
        return 0

    already = re.search(row["parallel"], command)
    if already:
        print("parallel-hint: %s — already parallel (%s); nothing to propose"
              % (row["name"], already.group(0)))
        return 0
    print("parallel-hint: %s — %s (%s)"
          % (row["name"], suggested(row, command), row["note"]))
    return 0


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write(USAGE)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if cmd != "suggest":
        sys.stderr.write("unknown subcommand: %s\n%s" % (cmd, USAGE))
        return 2
    return cmd_suggest(rest)


sys.exit(main())
