"""Commit checkpoint policy. The sibling shell owns interpreter selection."""
import json
import importlib.util
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

RAW = sys.stdin.read()
SHELLS = ("bash", "sh", "zsh", "ksh", "dash")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEP = re.compile(r"(\|\||&&|[;&|\n])")
DASH_C = re.compile(r"^-[A-Za-z]*c$")
GIT = re.compile(r"(^|[;&|\s(])git(\s+-[^\s]+(\s+[^\s]+)?)*\s+commit(?=\s|$)")
BYPASS = re.compile(r"(^|[;&|\s(])git(\s+-[^\s]+(\s+[^\s]+)?)*\s+commit[^;&|]*\s(--no-verify|-n)(?=\s|$)")
TASK_REF = re.compile(
    r"\[([A-Za-z0-9_-]+\.[0-9]+)\s+(?:satisfies|supports|covers):\s*REQ-[0-9]+"
)
CHG_REF = re.compile(r"\[(CHG-[0-9]{3,}\.1)\]")
REQ_REF = re.compile(r"\[[^]]*(?:satisfies|supports|covers):\s*REQ-[0-9]+")
# Legacy public name retained for old fixtures and third-party checks.
COVERS_REF = re.compile(r"\[[^]]*covers:\s*REQ-[0-9]+")

try:
    DATA = json.loads(RAW)
    if not isinstance(DATA, dict): DATA = {}
except Exception:
    DATA = {}
CMD = (DATA.get("tool_input") or {}).get("command") or ""

def leading(text):
    for token in SEP.split(text)[-1].split():
        if not ASSIGN.match(token): return token.rsplit("/", 1)[-1]
    return ""

def inline(part):
    if leading(part) not in SHELLS: return None
    try: words = shlex.split(part)
    except ValueError: return None
    for n, word in enumerate(words[:-1]):
        if DASH_C.match(word): return words[n + 1]
    return None

def executable(raw, nesting=0):
    lines, kept, i = raw.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]; i += 1
        if line.lstrip().startswith("#"): continue
        kept.append(line); marker = HEREDOC.search(line)
        if not marker: continue
        runs = leading(line.split("<<")[0]) in SHELLS
        while i < len(lines) and lines[i].strip() != marker.group(2):
            if runs: kept.append(lines[i])
            i += 1
        i += 1
    out = []
    for part in SEP.split("\n".join(kept)):
        if leading(part) in ("echo", "printf"): continue
        script = inline(part) if nesting < 3 else None
        out.append(part if script is None else "\n" + executable(script, nesting + 1) + "\n")
    return "".join(out)

EXEC = executable(CMD)
if not GIT.search(EXEC): raise SystemExit(0)
if BYPASS.search(EXEC):
    print("HelmIt: '--no-verify' (or -n) is forbidden — the commit gate must run (KEEL hard rule).", file=sys.stderr)
    print("Re-run the commit without it.", file=sys.stderr)
    raise SystemExit(2)

def usable_cwd(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        path = Path(value).resolve(strict=True)
        return str(path) if path.is_dir() else ""
    except (OSError, RuntimeError, ValueError):
        return ""


PROJ = (
    usable_cwd(DATA.get("cwd"))
    or usable_cwd(os.environ.get("CLAUDE_PROJECT_DIR"))
    or os.getcwd()
)
CONFIG = Path(PROJ) / ".helmit" / "config.json"
if not CONFIG.is_file(): raise SystemExit(0)

def session_id():
    value = (
        os.environ.get("HELMIT_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("CODEX_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or DATA.get("session_id")
        or ""
    )
    return value if re.fullmatch(r"[A-Za-z0-9._-]+", value) else ""

def append_gate_record(args):
    runlog = Path(os.environ.get("CG_SELF_DIR") or Path(__file__).parent) / "run-log.sh"
    if not runlog.is_file(): return
    sid = session_id()
    if sid: args.append("session=" + sid)
    try: subprocess.run(["bash", str(runlog), "append", "gate_run", *args], cwd=PROJ, env={**os.environ, "CLAUDE_PROJECT_DIR": PROJ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass

def message(raw):
    try: parts = shlex.split(raw)
    except Exception: parts = raw.split()
    result, i = [], 0
    while i < len(parts):
        p = parts[i]
        if p in ("-m", "--message") and i + 1 < len(parts): result.append(parts[i + 1]); i += 1
        elif p.startswith("--message="): result.append(p.split("=", 1)[1])
        elif p.startswith("-m") and len(p) > 2 and not p.startswith("--"): result.append(p[2:])
        elif p in ("-F", "--file") and i + 1 < len(parts):
            try: result.append(Path(parts[i + 1]).read_text(encoding="utf-8", errors="replace"))
            except OSError: pass
            i += 1
        elif p.startswith("--file="):
            try: result.append(Path(p.split("=", 1)[1]).read_text(encoding="utf-8", errors="replace"))
            except OSError: pass
        i += 1
    return "\n".join(result)

MSG = message(EXEC)
# Honest limit, declared: an editor-driven commit with no message in the
# command has nothing this PreToolUse hook can charge to a chart task. The
# independent git quick floor still runs and protects the staged snapshot.
if MSG and not MSG.startswith(("Merge ", "Revert ")):
    staged = subprocess.run(["git", "-C", PROJ, "diff", "--cached", "--name-only"], text=True, capture_output=True).stdout
    if any(x in EXEC for x in (" -a", " --all", " -am")):
        staged += subprocess.run(["git", "-C", PROJ, "diff", "--name-only"], text=True, capture_output=True).stdout
    if re.search(r"^(src|tests)/", staged, re.M):
        if CHG_REF.search(MSG):
            staged = ""
        elif not REQ_REF.search(MSG):
            print("HelmIt commit gate BLOCKED this commit: it touches src/ or tests/ and its", file=sys.stderr)
            print("message carries no REQ reference (REQ-195).", file=sys.stderr)
        elif not TASK_REF.search(MSG):
            print("HelmIt commit gate BLOCKED this commit: a REQ relation is present, but the", file=sys.stderr)
            print("message has no complete task identity whose verify: can be resolved.", file=sys.stderr)
        else:
            staged = ""
        if staged:
            print("\nUse ONE of these, in the subject line:", file=sys.stderr)
            print("  [<phase>.<task> satisfies: REQ-xxx] e.g. feat(auth): login [3.2 satisfies: REQ-012]", file=sys.stderr)
            print("  [<phase>.<task> supports: REQ-xxx]  e.g. refactor(auth): helper [3.3 supports: REQ-012]", file=sys.stderr)
            print("  Legacy charts may still use [<phase>.<task> covers: REQ-xxx].", file=sys.stderr)
            raise SystemExit(2)

def task_artifact(task):
    if task.startswith("B"):
        return Path(PROJ) / "docs" / "PLAN.md"
    phase = task.split(".", 1)[0]
    return Path(PROJ) / ".helmit" / "phases" / phase / "CHART.md"


def task_verify(task):
    if task.startswith("CHG-"):
        ledger = Path(PROJ) / ".helmit" / "CHANGES.md"
        lines = git_blob(candidate_tree, ledger).splitlines()
        identity = task.rsplit(".", 1)[0]
        for line in lines:
            if not line.startswith("| " + identity + " |"):
                continue
            cells = [cell.strip().replace(r"\|", "|").replace(r"\\", "\\")
                     for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
            return (task, cells[6]) if len(cells) == 9 else (task, "")
        return task, ""
    artifact = task_artifact(task)
    lines = git_blob(candidate_tree, artifact).splitlines()
    if task.startswith("B"):
        prefix = re.compile(r"^- \[[ xX>]\]\s+\*\*" + re.escape(task) + r"(?:\s|—)")
    else:
        prefix = re.compile(r"^- \[[ xX>]\]\s+" + re.escape(task) + r"(?:\s|$)")
    for line in lines:
        if not prefix.search(line): continue
        match = re.search(r"\s·\sverify:\s*(.*?)(?:\s·\sfiles:|$)", line)
        if not match: return task, ""
        return task, re.sub(r"\s+\([^()]*\)\s*$", "", match.group(1)).strip()
    return task, ""


def git_blob(revision, path):
    try:
        rel = str(path.relative_to(PROJ))
    except ValueError:
        return ""
    done = subprocess.run(
        ["git", "-C", PROJ, "show", revision + ":" + rel],
        text=True, capture_output=True,
    )
    return done.stdout if done.returncode == 0 else ""


def task_mark(text, task):
    if task.startswith("B"):
        pattern = re.compile(r"^- \[([ xX>])\]\s+\*\*" + re.escape(task) + r"(?:\s|—)", re.M)
    else:
        pattern = re.compile(r"^- \[([ xX>])\]\s+" + re.escape(task) + r"(?:\s|$)", re.M)
    match = pattern.search(text)
    return match.group(1).lower() if match else ""


def completes_task(task):
    if task.startswith("CHG-"):
        return True
    artifact = task_artifact(task)
    before = task_mark(git_blob("HEAD", artifact), task)
    after = task_mark(git_blob(candidate_tree, artifact), task)
    return before != "x" and after == "x"

def staged_blobs():
    names = subprocess.run(["git", "-C", PROJ, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], capture_output=True)
    if names.returncode != 0: return []
    return [p.decode("utf-8", "surrogateescape") for p in names.stdout.split(b"\0") if p]

def quick_floor():
    problems = []
    inside = subprocess.run(
        ["git", "-C", PROJ, "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if inside.returncode != 0: return problems
    check = subprocess.run(["git", "-C", PROJ, "diff", "--cached", "--check"], text=True, capture_output=True)
    if check.returncode not in (0, 128): problems.append(check.stdout.strip() or check.stderr.strip() or "staged diff check failed")
    for path in staged_blobs():
        blob = subprocess.run(["git", "-C", PROJ, "show", ":" + path], capture_output=True)
        if blob.returncode != 0: continue
        try:
            if path.endswith(".py"):
                compile(blob.stdout.decode("utf-8"), path, "exec")
            elif path.endswith(".json"):
                json.loads(blob.stdout.decode("utf-8"))
            elif path.endswith(".sh") or path.endswith("/pre-commit"):
                parsed = subprocess.run(["bash", "-n"], input=blob.stdout, capture_output=True)
                if parsed.returncode: problems.append("%s: %s" % (path, parsed.stderr.decode("utf-8", "replace").strip()))
        except (SyntaxError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append("%s: %s" % (path, exc))
    return problems

task_ids = list(dict.fromkeys(match.group(1) for match in TASK_REF.finditer(MSG)))
change_matches = list(dict.fromkeys(match.group(1) for match in CHG_REF.finditer(MSG)))
if change_matches and task_ids:
    print("HelmIt commit gate BLOCKED this commit: a CHG correction cannot share a commit with planned delivery tasks.", file=sys.stderr)
    raise SystemExit(2)
if len(change_matches) > 1:
    print("HelmIt commit gate BLOCKED this commit: close one CHG correction per commit.", file=sys.stderr)
    raise SystemExit(2)
if change_matches:
    task_ids = change_matches

candidate_tree = ""
if task_ids:
    candidate = subprocess.run(["git", "-C", PROJ, "write-tree"], text=True, capture_output=True)
    if candidate.returncode:
        print("HelmIt commit gate BLOCKED: cannot resolve candidate tree.", file=sys.stderr)
        raise SystemExit(2)
    candidate_tree = candidate.stdout.strip()

task_records = [task_verify(task) for task in task_ids]
missing = [task for task, verify in task_records if not verify]
if missing:
    print("HelmIt commit gate BLOCKED this commit: these tasks have no resolvable verify: in their task artifact:", file=sys.stderr)
    for task in missing:
        print("  " + task, file=sys.stderr)
    raise SystemExit(2)

if change_matches:
    task = change_matches[0]
    identity = task.rsplit(".", 1)[0]
    subject = MSG.splitlines()[0]
    change = Path(os.environ.get("CG_SELF_DIR") or Path(__file__).parent) / "change.sh"
    checked = subprocess.run(["bash", str(change), "candidate", "--id", identity,
                              "--subject", subject], cwd=PROJ,
                             env={**os.environ, "CLAUDE_PROJECT_DIR": PROJ})
    if checked.returncode:
        print("HelmIt commit gate BLOCKED this CHG candidate.", file=sys.stderr)
        raise SystemExit(2)

completing = [(task, verify) for task, verify in task_records if completes_task(task)]
started = int(time.time() * 1000); steps, failed, fields = [], "", []
seen_verifies = set()
verify_ms = 0
cases_passed = 0
cases_failed = 0


def proof_sandbox():
    path = Path(os.environ.get("CG_SELF_DIR") or Path(__file__).parent) / "proof-sandbox.py"
    spec = importlib.util.spec_from_file_location("helmit_proof_sandbox", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load proof-sandbox.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report_verify_failure(task, verify, output):
    print("HelmIt commit gate BLOCKED task %s: verify: failed." % task, file=sys.stderr)
    print("Command: %s" % verify, file=sys.stderr)
    hits = [
        "%d:%s" % (i, line)
        for i, line in enumerate(output.splitlines(), 1)
        if re.match(r"^[ \t]*(FAIL|FAILED|ERROR|not ok|--- FAIL|panic:|AssertionError|Traceback|✗|✘)", line)
    ][:40]
    if hits:
        print("--- lines that look like the failure (line numbers from the output) ---", file=sys.stderr)
        print("\n".join(hits), file=sys.stderr)
    else:
        print("--- no line matched a failure marker: the tail below is ALL there is,", file=sys.stderr)
        print("    and it may not contain the failure. Re-run the command directly.", file=sys.stderr)
    print("--- output (tail) ---", file=sys.stderr)
    print("\n".join(output.splitlines()[-40:]), file=sys.stderr)


if completing:
    try:
        sandbox = proof_sandbox()
        with sandbox.workspace(PROJ, "staged") as (proof_root, proof_tree):
            if proof_tree != candidate_tree:
                raise RuntimeError("candidate changed after verification contract resolution")
            fields.extend(("proof_source=staged", "proof_tree=" + proof_tree))
            proof_env = sandbox.proof_environment(PROJ, proof_root, proof_tree, "staged")
            for task, verify in completing:
                if verify in seen_verifies:
                    continue
                seen_verifies.add(verify)
                at = int(time.time() * 1000)
                done = subprocess.run(
                    ["bash", "-c", verify], cwd=proof_root, env=proof_env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True,
                )
                verify_ms += int(time.time() * 1000) - at
                summary = re.search(r"passed:\s*([0-9]+)\s*[^\n]*failed:\s*([0-9]+)", done.stdout)
                if summary:
                    cases_passed += int(summary.group(1))
                    cases_failed += int(summary.group(2))
                if done.returncode:
                    failed = "verify"
                    report_verify_failure(task, verify, done.stdout)
    except Exception as error:
        failed = "verify-isolation"
        print("HelmIt commit gate BLOCKED: candidate proof isolation failed: %s" % error,
              file=sys.stderr)

if seen_verifies:
    steps.append("verify")
    fields.extend(("verify_ms=" + str(verify_ms), "verify_commands=" + str(len(seen_verifies))))
    if cases_passed or cases_failed:
        fields.extend(("cases_passed=" + str(cases_passed), "cases_failed=" + str(cases_failed)))

at = int(time.time() * 1000); floor_problems = quick_floor()
fields.append("quick_floor_ms=" + str(int(time.time() * 1000) - at)); steps.append("quick-floor")
if floor_problems:
    failed = failed or "quick-floor"
    print("HelmIt commit gate BLOCKED this commit: quick floor failed.", file=sys.stderr)
    for problem in floor_problems[:40]: print(problem, file=sys.stderr)
if candidate_tree:
    current = subprocess.run(["git", "-C", PROJ, "write-tree"], text=True, capture_output=True)
    if current.returncode or current.stdout.strip() != candidate_tree:
        failed = failed or "candidate-changed"
        print("HelmIt commit gate BLOCKED: candidate changed during verification.", file=sys.stderr)
ended = int(time.time() * 1000)

def record():
    args = ["verdict=" + ("blocked" if failed else "passed"), "steps=" + ",".join(steps), "layer=pretooluse", "duration_ms=" + str(ended - started), *fields]
    if task_ids:
        args.append("tasks=" + ",".join(task_ids))
        if len(task_ids) == 1: args.append("task=" + task_ids[0])
    if completing: args.append("completes=" + ",".join(task for task, _ in completing))
    if failed: args.append("failed_step=" + failed)
    append_gate_record(args)

record()
if failed:
    print("Fix the failure, then commit again. Never bypass the gate.", file=sys.stderr)
    raise SystemExit(2)
