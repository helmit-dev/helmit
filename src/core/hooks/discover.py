import json, os, re, sys

# Preserve the former shell contract: `scan` is optional, while any other
# first token is treated as the project path and is rejected below if invalid.
argv = sys.argv[1:]
if argv and argv[0] == "scan":
    argv = argv[1:]
PROJ = argv[0] if argv else os.getcwd()
if not os.path.isdir(PROJ):
    sys.stderr.write("discover.sh: not a directory: %s\n" % PROJ)
    sys.exit(1)

ROOT = os.path.realpath(PROJ)
CAP = 100 * 1024  # bounded read per file

def rel(p):
    return os.path.relpath(p, ROOT)

def read(p):
    try:
        if os.path.getsize(p) > CAP:
            return ""
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(CAP)
    except OSError:
        return ""

def exists(*names):
    for n in names:
        p = os.path.join(ROOT, n)
        if os.path.exists(p):
            return p
    return None

stack, conventions = [], []
commands = {"test": [], "build": [], "lint": []}

def add_stack(value, ev):
    stack.append({"value": value, "evidence": rel(ev)})

def add_cmd(kind, value, ev):
    e = {"value": value, "evidence": rel(ev)}
    if e not in commands[kind]:
        commands[kind].append(e)

def add_conv(value, ev):
    e = {"value": value, "evidence": rel(ev)}
    if e not in conventions:
        conventions.append(e)

# --- tracked file count (trivial-repo check; git first, bounded walk fallback)
tracked = 0
try:
    import subprocess
    out = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True,
                         text=True, timeout=10)
    if out.returncode == 0 and out.stdout.strip():
        tracked = len(out.stdout.strip().splitlines())
except Exception:
    pass
if tracked == 0:
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in
                   (".git", "node_modules", ".venv", "venv", "bin", "obj",
                    "dist", "build", "__pycache__")]
        tracked += len(files)
        if tracked > 200:
            break

# --- Node / TypeScript ------------------------------------------------------
pkg = exists("package.json")
if pkg:
    add_stack("node", pkg)
    try:
        data = json.loads(read(pkg) or "{}")
    except Exception:
        data = {}
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    ts = exists("tsconfig.json")
    if ts or "typescript" in deps:
        add_stack("typescript", ts or pkg)
    for fw in ("react", "vue", "next", "express", "fastify"):
        if fw in deps:
            add_stack(fw, pkg)
    scripts = data.get("scripts", {}) or {}
    for name, kind in (("test", "test"), ("build", "build"), ("lint", "lint")):
        if name in scripts:
            run = "npm test" if name == "test" else f"npm run {name}"
            add_cmd(kind, run, pkg)
    for mgr, lock in (("pnpm", "pnpm-lock.yaml"), ("yarn", "yarn.lock"),
                      ("npm", "package-lock.json")):
        if exists(lock):
            add_conv(f"package manager: {mgr}", exists(lock))
            break
    for tool, cfgs in (("jest", ("jest.config.js", "jest.config.ts")),
                       ("vitest", ("vitest.config.ts", "vitest.config.js"))):
        c = exists(*cfgs)
        if c or tool in deps:
            add_conv(f"test framework: {tool}", c or pkg)
    esl = exists(".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs",
                 "eslint.config.js", "eslint.config.mjs")
    if esl or "eslint" in deps:
        add_conv("linter: eslint", esl or pkg)
        if not commands["lint"]:
            add_cmd("lint", "npx eslint .", esl or pkg)
    pre = exists(".prettierrc", ".prettierrc.json", "prettier.config.js")
    if pre or "prettier" in deps:
        add_conv("formatter: prettier", pre or pkg)

# --- Python -----------------------------------------------------------------
pyproj = exists("pyproject.toml")
reqs = exists("requirements.txt", "setup.py", "setup.cfg", "Pipfile")
if pyproj or reqs:
    add_stack("python", pyproj or reqs)
    body = read(pyproj) if pyproj else ""
    if pyproj and ("[tool.pytest" in body or "pytest" in body):
        add_cmd("test", "pytest", pyproj)
        add_conv("test framework: pytest", pyproj)
    elif exists("tests", "test"):
        add_cmd("test", "pytest", exists("tests", "test"))
    if pyproj and "[tool.ruff" in body:
        add_cmd("lint", "ruff check .", pyproj)
        add_conv("linter: ruff", pyproj)
    rf = exists("ruff.toml", ".ruff.toml")
    if rf:
        add_cmd("lint", "ruff check .", rf)
        add_conv("linter: ruff", rf)
    if pyproj and "[tool.black" in body:
        add_conv("formatter: black", pyproj)
    if pyproj and ("[tool.poetry" in body):
        add_conv("package manager: poetry", pyproj)
    if pyproj and ("[build-system]" in body) and ("setuptools" in body):
        add_cmd("build", "python -m build", pyproj)

# --- .NET / C# --------------------------------------------------------------
csproj = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "bin", "obj")]
    if base.count(os.sep) - ROOT.count(os.sep) > 3:
        dirs[:] = []
        continue
    csproj += [os.path.join(base, f) for f in files
               if f.endswith((".csproj", ".sln"))]
    if len(csproj) >= 20:
        break
if csproj:
    first = sorted(csproj)[0]
    add_stack("dotnet", first)
    tf = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", read(first))
    if tf:
        add_stack(f"dotnet:{tf.group(1)}", first)
    add_cmd("test", "dotnet test", first)
    add_cmd("build", "dotnet build", first)
    tests = [p for p in csproj if ".Tests" in p or ".Test" in p]
    if tests:
        add_conv("test projects: *.Tests per module", sorted(tests)[0])
        body = read(sorted(tests)[0])
        for fw in ("xunit", "nunit", "MSTest"):
            if fw.lower() in body.lower():
                add_conv(f"test framework: {fw}", sorted(tests)[0])
                break

# --- Go / Rust (stack only — commands are convention-standard) --------------
if exists("go.mod"):
    add_stack("go", exists("go.mod"))
    add_cmd("test", "go test ./...", exists("go.mod"))
    add_cmd("build", "go build ./...", exists("go.mod"))
if exists("Cargo.toml"):
    add_stack("rust", exists("Cargo.toml"))
    add_cmd("test", "cargo test", exists("Cargo.toml"))
    add_cmd("build", "cargo build", exists("Cargo.toml"))

# --- Makefile targets -------------------------------------------------------
mk = exists("Makefile", "makefile")
if mk:
    body = read(mk)
    for kind in ("test", "build", "lint"):
        if re.search(rf"^{kind}:", body, re.M):
            add_cmd(kind, f"make {kind}", mk)

# --- CI workflows (command candidates with evidence) -------------------------
ci_dir = os.path.join(ROOT, ".github", "workflows")
if os.path.isdir(ci_dir):
    for f in sorted(os.listdir(ci_dir))[:10]:
        if not f.endswith((".yml", ".yaml")):
            continue
        p = os.path.join(ci_dir, f)
        for line in read(p).splitlines():
            m = re.search(r"run:\s*(.+)$", line.strip())
            if not m:
                continue
            run = m.group(1).strip().strip('"')
            low = run.lower()
            if len(run) > 120 or low.startswith("echo"):
                continue
            if "lint" in low or "eslint" in low or "ruff" in low:
                add_cmd("lint", run, p)
            elif "test" in low:
                add_cmd("test", run, p)
            elif "build" in low:
                add_cmd("build", run, p)

# --- Cross-stack conventions --------------------------------------------------
if exists(".editorconfig"):
    add_conv("editorconfig present", exists(".editorconfig"))
td = exists("tests", "test", "spec")
if td:
    add_conv(f"tests directory: {os.path.basename(td)}/", td)
if exists(".pre-commit-config.yaml"):
    add_conv("pre-commit hooks configured", exists(".pre-commit-config.yaml"))

print(json.dumps({
    "stack": stack,
    "commands": commands,
    "conventions": conventions,
    "meta": {"trivial": tracked < 5, "tracked_files": tracked},
}, ensure_ascii=False))
