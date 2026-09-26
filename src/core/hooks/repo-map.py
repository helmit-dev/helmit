import hashlib, json, os, subprocess, sys
from collections import defaultdict

try:
    from tree_sitter import Query, QueryCursor
    from tree_sitter_language_pack import get_language, get_parser
except ImportError:
    # The directed query answers from the stored base alone, so it must survive
    # the absent optional layer (REQ-271). Every mode that parses was already
    # turned away by the guard in the bash half above.
    Query = QueryCursor = get_language = get_parser = None

MODE = sys.argv[1]
ROOT = os.path.realpath(sys.argv[2])
QDIR = sys.argv[3]
BUDGET = int(sys.argv[4])
FILES_ARG = sys.argv[5] if len(sys.argv) > 5 else ""
SYMBOL_ARG = sys.argv[6] if len(sys.argv) > 6 else ""
CAP = 200 * 1024  # per-file read cap
MAP_DIR = os.path.join(ROOT, ".helmit", "map")
FP_PATH = os.path.join(MAP_DIR, "fingerprints.json")
MAP_PATH = os.path.join(MAP_DIR, "map.txt")

# extension -> language-pack key (must have a matching <lang>-tags.scm)
EXT_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".cs": "csharp",
    ".go": "go", ".rb": "ruby", ".java": "java", ".rs": "rust",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".php": "php", ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
    ".ex": "elixir", ".exs": "elixir", ".el": "elisp", ".ml": "ocaml",
    ".lua": "lua", ".r": "r", ".jl": "julia", ".zig": "zig",
    ".sh": "bash", ".bash": "bash",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build",
             "bin", "obj", "__pycache__", ".helmit",
             "vendor", "third_party", "bower_components"}
VENDOR_SEGMENTS = ("/wwwroot/lib/",)  # ASP.NET static-libs convention

def is_noise(rel):
    """Vendored/minified assets drown the signal (learned on a real repo:
    jquery.min.js outranked every Controller). Skipped entirely."""
    base = os.path.basename(rel)
    if ".min." in base:
        return True
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return True
    return any(seg in f"/{rel}" for seg in VENDOR_SEGMENTS)

def repo_files():
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()
    except Exception:
        pass
    acc = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            acc.append(os.path.relpath(os.path.join(base, f), ROOT))
        if len(acc) > 5000:
            break
    return acc

_lang_cache = {}
def lang_tools(lang):
    """(parser, query) for a language, or None — silent per-file fallback."""
    if lang in _lang_cache:
        return _lang_cache[lang]
    tools = None
    try:
        scm = os.path.join(QDIR, f"{lang}-tags.scm")
        if os.path.isfile(scm):
            language = get_language(lang)
            with open(scm, encoding="utf-8") as f:
                query = Query(language, f.read())
            tools = (get_parser(lang), query)
    except Exception:
        tools = None  # never let one language break the map
    _lang_cache[lang] = tools
    return tools

def extract(rel):
    """-> (defs [(name, kind, line)], refs [name]) or None (fallback)."""
    ext = os.path.splitext(rel)[1].lower()
    lang = EXT_LANG.get(ext)
    if not lang:
        return None
    tools = lang_tools(lang)
    if not tools:
        return None
    parser, query = tools
    full = os.path.join(ROOT, rel)
    try:
        if os.path.getsize(full) > CAP:
            return None
        with open(full, "rb") as f:
            code = f.read(CAP)
        tree = parser.parse(code)
        captures = QueryCursor(query).captures(tree.root_node)
    except Exception:
        return None
    defs, refs = [], []
    for cap_name, nodes in captures.items():
        for node in nodes:
            name = node.text.decode("utf-8", errors="replace")
            if cap_name.startswith("name.definition."):
                kind = cap_name.rsplit(".", 1)[-1]
                defs.append((name, kind, node.start_point[0] + 1))
            elif cap_name.startswith("name.reference."):
                refs.append(name)
    return defs, refs

def extract_entry(rel):
    got = extract(rel)
    if got is None:
        return {"defs": [], "refs": {}}
    defs, refs = got
    rc = defaultdict(int)
    for n in refs:
        rc[n] += 1
    return {"defs": [[n, k, l] for n, k, l in defs], "refs": dict(rc)}

def render(entries, budget, missing=()):
    """Two-layer render: ranked defs first, then the name-only layer.

    `budget` None is the DIRECTED query (REQ-271), and it drops the per-file and
    per-layer caps with the char cap: all three exist to fit the WHOLE repository
    into one excerpt, and a selection asked for by name is the opposite problem —
    trimming it would rebuild the failure the query was born to remove.

    `missing` is the third layer, and it only ever has content on that same
    query: paths the caller named and the base does not hold. Naming them is the
    same rule the name-only layer already obeys — silence about a file somebody
    ASKED for is the worst answer the map can give."""
    defines = defaultdict(set)
    def_rows, plain = {}, []
    ref_counts = defaultdict(lambda: defaultdict(int))
    for rel, e in entries.items():
        defs = [tuple(d) for d in (e.get("defs") or [])]
        if defs:
            def_rows[rel] = defs
            for name, kind, line in defs:
                defines[name].add(rel)
        else:
            # refs-only / fallback files stay VISIBLE in the name layer —
            # a map that hides files misleads.
            plain.append(rel)
        for name, c in (e.get("refs") or {}).items():
            ref_counts[name][rel] += c
    # Ranking (pluggable — v1: counting; documented upgrade: PageRank stdlib).
    # score(file) = own defs + references its idents receive from OTHER files.
    score = defaultdict(int)
    for rel, rows in def_rows.items():
        score[rel] += len(rows)
    for ident, files_ref in ref_counts.items():
        for definer in defines.get(ident, ()):
            score[definer] += sum(n for f, n in files_ref.items() if f != definer)
    out, used = [], 0
    def emit(line):
        nonlocal used
        if budget is not None and used + len(line) + 1 > budget:
            return False
        out.append(line)
        used += len(line) + 1
        return True
    # A layer opens with a blank separator only when something precedes it.
    def open_layer(header):
        return (not out or emit("")) and emit(header)
    for rel in sorted(def_rows, key=lambda r: (-score[r], r)):
        if not emit(f"{rel}:"):
            break
        rows = sorted(def_rows[rel], key=lambda t: t[2])
        for name, kind, line in (rows if budget is None else rows[:30]):
            if not emit(f"  {kind} {name} :{line}"):
                break
    if plain and open_layer("(no symbols / unmapped language:)"):
        names = sorted(plain)
        for rel in (names if budget is None else names[:100]):
            if not emit(f"  {rel}"):
                break
    if missing and open_layer("(not in the map base:)"):
        for rel in sorted(missing):
            if not emit(f"  {rel}"):
                break
    return "\n".join(out)

def selected_paths(spec):
    """The paths of --files, as the stored base keys them: relative to the root.

    The flag repeats and each occurrence takes a list, so the whole thing
    arrives as one comma-joined string. An absolute path under the root is
    accepted and folded back — the executor of a wave holds the trunk's absolute
    path in its prompt, and turning its own idiom into a "missing" verdict would
    be a lie the base can easily avoid telling."""
    out = []
    for raw in spec.split(","):
        rel = raw.strip()
        if not rel:
            continue
        if os.path.isabs(rel):
            rel = os.path.relpath(os.path.realpath(rel), ROOT)
        rel = os.path.normpath(rel)
        if rel not in out:
            out.append(rel)
    return out

def definitions_of(stored, name):
    """The base narrowed to the DEFINITIONS of one name (REQ-272).

    The comparison is `==` and never a substring, and that is the entire point
    of the query: `foo` may not drag `foobar` along, because a name that merely
    CONTAINS the one asked about is precisely the fog `grep` already returns.

    `refs` is dropped on the way out. A file that only MENTIONS the name does
    not define it, and carrying the mentions into the answer would quietly turn
    "where is this defined" back into the question the map exists to stop
    answering. Shaped as entries so the render below is the SAME render, and
    the answer is recognisable as coming from the same map."""
    picked = {}
    for rel, entry in stored.items():
        rows = [d for d in (entry.get("defs") or []) if d and d[0] == name]
        if rows:
            picked[rel] = {"defs": rows, "refs": {}}
    return picked

def sha1_file(rel):
    full = os.path.join(ROOT, rel)
    try:
        if os.path.getsize(full) > CAP:
            return "oversize"
        h = hashlib.sha1()
        with open(full, "rb") as f:
            h.update(f.read(CAP))
        return h.hexdigest()
    except OSError:
        return None

def atomic_write(path, text):
    """tmp + os.replace: readers see the old or the new file, never a half."""
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

def load_stored():
    if not os.path.isfile(FP_PATH):
        return {}
    try:
        with open(FP_PATH, encoding="utf-8") as f:
            return json.load(f).get("files", {})
    except Exception:
        return {}

def freshness(rels):
    """The verdict of `check`: no fingerprints on disk => absent; a tracked file
    added, removed or with a moved sha1 => stale; otherwise fresh.

    ONE implementation, read by `check` AND by the record `show` writes. Two
    copies would eventually answer differently about the same map, and a record
    that disagrees with the command the skill gates on is worse than no record.
    The price is one sha1 pass per `show` (capped at 200KB per file, same as
    every other read here) — paid by an OPTIONAL layer, never by the gate."""
    stored = load_stored()
    current = {rel: sha1_file(rel) for rel in rels} if stored else {}
    stale = set(current) != set(stored) or any(
        stored[r].get("sha1") != current[r] for r in current)
    return ("stale" if stale else "fresh") if stored else "absent"

def record(event, fields):
    """Append ONE map event to .helmit/run.jsonl (REQ-243, REQ-251).

    ONE writer for both map events, for the reason freshness() is one
    implementation: what follows is the entire safety argument of this layer,
    and a second copy of it is a second place for it to rot.

    OBSERVER, like commit-gate.sh writing gate_run: no stdout (it would corrupt
    the render the caller is reading), no exit code, every failure swallowed —
    missing run-log.sh, no .helmit/, unwritable disk. The map is the project's
    ONLY optional dependency (ADR-009); bookkeeping may never make it a gate.

    CLAUDE_PROJECT_DIR=ROOT because that is the ONE variable run-log.sh resolves
    its root from. A wave executor runs these commands from a worktree against
    the trunk path it was given, so the whole environment says "the project is
    over here" while the record has to land in the WAL of the root that was
    PASSED — the only WAL anybody reconciles (REQ-248)."""
    runlog = os.environ.get("RM_RUNLOG", "")
    if not runlog or not os.path.isfile(runlog):
        return
    try:
        subprocess.run(
            ["bash", runlog, "append", event] + fields,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except Exception:
        pass

def record_show(chars, verdict, scope):
    """The CONSUMPTION side: `show` handed its render over (REQ-243).

    WHY here and not in the skill: `show` is the only deterministic moment in
    the chain. The map could always prove it had been GENERATED and never that
    anybody read it, so "refreshed the map and then described the files in prose"
    left no trace at all. What this proves is exactly `show` ran and how much
    text it handed over, under which freshness — NOT that the excerpt reached a
    subagent, which only the orchestrator knows. That limit did not move; it is
    declared in the skill, where the excerpt is cut.

    `scope` says WHAT WAS DELIVERED (REQ-273): `full-map` for the whole-repo
    view, `files=<N>` for the N paths a directed query named, `symbol=<name>`
    for the name it asked to locate. It was the constant `full-map` while `show`
    had one answer to give; with the two directed queries a constant would say
    the same word about a consultation of one file and about the ranked view of
    the entire repository, and telling those apart is exactly the resolution the
    panel that counts generation against consumption was missing.

    Only what THIS command can know goes on the record, and the render budget
    still does not qualify — for two reasons now instead of one. The whole-repo
    view hands over the map.txt `refresh` already capped, so a `--budget` given
    to `show` never touched it; a directed query renders under no cap at all, by
    contract. Either way the number would be provenance the event cannot vouch
    for."""
    record("map_shown", ["freshness=%s" % verdict, "chars=%d" % chars,
                         "scope=%s" % scope])

def record_refresh(parsed, reused, chars):
    """The GENERATION side: `refresh` produced the map (REQ-251).

    Generating is not consuming — the distinction map_shown was born to protect
    — and recording both is what finally makes "generated N times, consumed M
    times" sayable. Until this event the WAL knew one half only, so a map
    regenerated on every wave and a map nobody had touched for hours read
    identically (measured 19/08: a single map_shown in the whole log and not one
    record of generation).

    `parsed`/`reused` are the incremental work (REQ-046) and `chars` the size of
    the render just persisted. No `freshness`: refresh MAKES it fresh, so the
    verdict would be a constant. No `scope`: nothing was handed to anybody."""
    record("map_refreshed", ["parsed=%d" % parsed, "reused=%d" % reused,
                            "chars=%d" % chars])

files = [f for f in repo_files()
         if not f.startswith(".helmit/") and not is_noise(f)]

if MODE == "scan":
    print(render({rel: extract_entry(rel) for rel in files}, BUDGET))

elif MODE == "check":
    print(freshness(files))

elif MODE == "show" and FILES_ARG:
    # DIRECTED query (REQ-271). The base the refresh already keeps on disk is
    # COMPLETE — every tracked file, ranked or not — so what the ranking decided
    # about these paths is beside the question, and so is the budget.
    if not os.path.isfile(FP_PATH):
        print("(map base absent — run refresh)", file=sys.stderr)
    else:
        stored = load_stored()
        wanted = selected_paths(FILES_ARG)
        picked = {rel: stored[rel] for rel in wanted if rel in stored}
        gone = [rel for rel in wanted if rel not in stored]
        rendered = render(picked, None, gone) + "\n"
        print(rendered, end="")
        # N is what was ASKED FOR, not what the base happened to hold: a query
        # for three paths that answers about one is still a query for three, and
        # a count that shrank with the misses would hide precisely the case the
        # third layer of the render exists to expose.
        record_show(len(rendered), freshness(files), "files=%d" % len(wanted))

elif MODE == "show" and SYMBOL_ARG:
    # DIRECTED query (REQ-272), the other half of the pair. Same base, same
    # render, other question: not "what is inside these files" but "where is
    # this name DEFINED" — the one `grep` answers with every mention.
    if not os.path.isfile(FP_PATH):
        print("(map base absent — run refresh)", file=sys.stderr)
    else:
        picked = definitions_of(load_stored(), SYMBOL_ARG)
        if picked:
            rendered = render(picked, None) + "\n"
        else:
            # An ANSWER, not an absence. The base WAS read and it defines this
            # name nowhere, which is exactly what the caller asked to learn, so
            # it goes out on stdout with the rest and exits 0. Sending it to
            # stderr would file a fact under "something went wrong".
            rendered = "(no definition of %s in the map base)\n" % SYMBOL_ARG
        print(rendered, end="")
        # The name goes on the record whether or not the base defines it: what
        # was delivered is the ANSWER about that name, and "nothing defines it"
        # is one of its two possible values.
        record_show(len(rendered), freshness(files), "symbol=%s" % SYMBOL_ARG)

elif MODE == "show":
    if os.path.isfile(MAP_PATH):
        with open(MAP_PATH, encoding="utf-8") as f:
            rendered = f.read()
        print(rendered, end="")
        record_show(len(rendered), freshness(files), "full-map")
    else:
        # Nothing was handed over, so nothing is recorded. That SILENCE is the
        # signal: it is what tells "the map was never consumed" apart from "the
        # map was consumed and happened to be empty".
        print("(map absent — run refresh)", file=sys.stderr)

else:  # refresh — incremental: re-parse ONLY changed/new files (REQ-046)
    stored = load_stored()
    entries, parsed, reused = {}, 0, 0
    for rel in files:
        h = sha1_file(rel)
        old = stored.get(rel)
        if old is not None and old.get("sha1") == h:
            entries[rel] = old
            reused += 1
        else:
            e = extract_entry(rel)
            e["sha1"] = h
            entries[rel] = e
            parsed += 1
    os.makedirs(MAP_DIR, exist_ok=True)
    atomic_write(FP_PATH, json.dumps({"version": 1, "files": entries}))
    atomic_write(MAP_PATH, render(entries, BUDGET) + "\n")
    print(f"repo-map: parsed {parsed}, reused {reused}, total {len(entries)}",
          file=sys.stderr)
    with open(MAP_PATH, encoding="utf-8") as f:
        rendered = f.read()
    print(rendered, end="")
    # Last, and only here: .helmit/ exists by then (makedirs above), and what is
    # counted is the render that actually reached disk.
    record_refresh(parsed, reused, len(rendered))
