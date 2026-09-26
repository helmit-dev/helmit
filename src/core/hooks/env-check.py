import hashlib, json, os, re, subprocess

ROOT = os.environ.get("EC_ROOT") or os.getcwd()
SETUP = os.environ.get("EC_SETUP") or ""
PRE_REF = os.environ.get("EC_PRE") or ""
TPL = os.environ.get("EC_TPL") or ""
PLUGIN = os.environ.get("EC_PLUGIN") or ""

FIX = " — run /helmit:env"
FENCE = chr(96) * 3  # a fenced block delimiter, built to survive shell quoting

# The one normalization of the /env rule: the version-marker line is stripped
# before hashing, because dev-sync.sh rewrites it on EVERY release — hashing it
# would declare every project stale at every bump with the bytes identical.
MARKER = re.compile(r"^.*helmit-(?:pre-commit|lease)-version:.*$\n?", re.M)
LEASE = re.compile(r"<!--\s*helmit:start\s*-->.*?<!--\s*helmit:end\s*-->", re.S)
LOCAL = re.compile(r"# helmit:local-state:start\n(.*?)# helmit:local-state:end",
                   re.S)


def digest(text):
    return hashlib.sha256(MARKER.sub("", text).encode("utf-8")).hexdigest()


def read(path):
    """File content, or None when missing/unreadable (fail-open: silence)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def fenced_block(text, needle):
    """The ONE fenced block of setup/SKILL.md carrying the needle — the single
    source of that reference (REQ-110). Not exactly one: no verdict (None)."""
    blocks = [b for b in re.findall(FENCE + r"[a-z]*\n(.*?)" + FENCE, text, re.S)
              if needle in b]
    return blocks[0] if len(blocks) == 1 else None


findings = []  # in check order 1..6 — what makes two runs byte-identical

# The session adapter supplies EC_HARNESS when it needs the native context
# contract as part of its pre-routing gate. Keeping it opt-in preserves this
# hook's historical role as a platform-neutral, fail-open informer.
try:
    harness = os.environ.get("EC_HARNESS")
    contract = os.path.join(os.path.dirname(__file__), "context-contract.py")
    if harness in ("codex", "claude-code") and os.path.isfile(contract):
        out = subprocess.run([os.environ.get("EC_PYTHON") or "python3", contract,
                              "check", harness], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=15,
                             env=dict(os.environ, CC_ROOT=ROOT, CC_SETUP=SETUP))
        findings.extend(line for line in out.stdout.decode("utf-8", "replace").splitlines()
                        if line.strip())
except Exception:
    pass

setup = read(SETUP)

# --- 1. leased section of the host context file(s), by normalized hash --------
try:
    ref = LEASE.search(fenced_block(setup, "<!-- helmit:start -->") or "") \
        if setup else None
    if ref:
        want = digest(ref.group(0))
        for host in ("CLAUDE.md", "AGENTS.md"):
            text = read(os.path.join(ROOT, host))
            if text is None:
                continue
            m = LEASE.search(text)
            # Absent or broken markers: no boundary to hash — /env territory.
            if m and digest(m.group(0)) != want:
                findings.append("%s: leased HelmIt section outdated%s"
                                % (host, FIX))
except Exception:
    pass

# --- 2. pre-commit floor, by hash of the marker-stripped body -----------------
# REQ-210, the layout question first: a chained dispatcher invokes the verbatim
# copy BY PATH (a `/helmit-pre-commit` token), while a direct install of the
# gate only ever NAMES itself in comments and in the marker line (no slash) —
# so the path reference is what tells the two layouts apart. Chained → hash the
# copy; reference present but copy unreadable → no boundary to hash, /env
# territory, silence (fail-open). Direct → hash the installed hook as before.
try:
    ref = read(PRE_REF)
    hooks = os.path.join(ROOT, ".git", "hooks")
    installed = read(os.path.join(hooks, "pre-commit"))
    if ref and installed:
        target, label = None, None
        if re.search(r"/helmit-pre-commit(?![\w-])", installed):
            copy = read(os.path.join(hooks, "helmit-pre-commit"))
            if copy is not None:
                target, label = copy, ".git/hooks/helmit-pre-commit"
        elif "helmit" in installed.lower():
            target, label = installed, ".git/hooks/pre-commit"
        if target is not None and digest(target) != digest(ref):
            findings.append("%s: HelmIt pre-commit floor outdated%s"
                            % (label, FIX))
except Exception:
    pass

# --- 3. .gitignore local-state block, by hash of the body (REQ-127) -----------
ref_body = None
try:
    m = LOCAL.search(fenced_block(setup, "# helmit:local-state:start") or "") \
        if setup else None
    if m:
        ref_body = m.group(1)
        text = read(os.path.join(ROOT, ".gitignore"))
        got = LOCAL.search(text) if text else None
        if got and hashlib.sha256(got.group(1).encode("utf-8")).hexdigest() \
                != hashlib.sha256(ref_body.encode("utf-8")).hexdigest():
            findings.append(".gitignore: helmit:local-state block outdated"
                            + FIX)
except Exception:
    pass

# --- 4. tracked local state (REQ-112): paths DERIVED from the same block ------
try:
    paths = [l.strip() for l in (ref_body or "").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    if paths and os.path.exists(os.path.join(ROOT, ".git")):
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "--"] + paths,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=15)
        if out.returncode == 0:
            for p in out.stdout.decode("utf-8", "replace").split("\n"):
                if p.strip():
                    findings.append("%s: machine-local state tracked by git%s"
                                    % (p.strip(), FIX))
except Exception:
    pass

# --- 5. version gap (REQ-208): the version decides WHEN, never the verdict ----
# helmit_version is the last plugin version whose DEEP toolchain check this
# project passed; /env writes it after that check, this hook only reads it.
# A gap therefore means exactly one thing — the deep check is due — so the line
# says that and nothing else, and it appears even with checks 1..4 all silent.
try:
    seen = json.loads(read(os.path.join(ROOT, ".helmit", "config.json")) or "") \
        .get("helmit_version")
    plug = json.loads(read(PLUGIN) or "").get("version")
    if isinstance(seen, str) and isinstance(plug, str) and seen and plug \
            and seen != plug:
        findings.append("helmit_version: %s seen, plugin is %s — deep check "
                        "due; run /helmit:env" % (seen, plug))
except Exception:
    pass

# --- 6. orphan top-level keys (REQ-209): a removed field needs a migration ----
# The template is the canonical key set of config.json — the PRIMARY source
# of the format, artifact_language included since REQ-214. The wizard
# derivation stays as DELIBERATE redundancy: the legal set adds the keys
# setup/SKILL.md itself says it persists (`config.json.<key>` mentions) —
# derived from the one source that writes them, like check 4 derives its
# paths, never a hand-copied allowlist that drifts — the net for the next key
# the wizard gains before the template does. `$`-prefixed keys are the
# file documenting itself, ignored on both sides. What remains is a key that
# LEFT the template — and it is not inert: the REQ-118 `yolo` removal left a
# leftover an agent read as a mandate nobody gave (02/08). PURE READ: this
# hook lists the orphan; the offer, the reason and the removal are /env's,
# under explicit confirmation. No config, broken JSON, no template: silence.
try:
    tpl = json.loads(read(TPL) or "")
    cfg = json.loads(read(os.path.join(ROOT, ".helmit", "config.json")) or "")
    if isinstance(tpl, dict) and isinstance(cfg, dict) and setup:
        wizard = {m.split(".")[0] for m in
                  re.findall(r"config\.json\.([A-Za-z_][A-Za-z_.]*)", setup)}
        for key in cfg:
            if key.startswith("$") or key in tpl or key in wizard:
                continue
            findings.append('config.json: orphan top-level key "%s" — removed '
                            'from the template; run /helmit:env to migrate'
                            % key)
except Exception:
    pass

# REQ-108: the content decides IF we speak — zero pendencies means zero output.
for line in findings:
    print(line)
