import os
import sys
import tempfile
from datetime import datetime, timezone

root = os.environ.get("HD_ROOT") or os.getcwd()
hooks = os.environ.get("HD_DIR") or os.path.dirname(__file__)
command = sys.argv[1] if len(sys.argv) > 1 else ""
if command not in ("render", "write"):
    print("usage: handoff.sh {render | write [--if-session-end]}  (write: narrative on stdin)", file=sys.stderr)
    raise SystemExit(2)
if command == "render":
    import json, os, re, subprocess, sys
    from datetime import datetime, timezone

    ROOT = os.environ.get("HD_ROOT") or os.getcwd()
    HELMIT = os.path.join(ROOT, ".helmit")
    DIRTY_CAP = 20                      # max dirty paths listed


    def read_text(path):
        """File content, or None when missing/unreadable (reads never break)."""
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None


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


    def run_entries():
        """Valid run.jsonl entries, tolerant like run-log.sh: garbage mid-file and
        a final line without \n (an interrupted write by construction) are dropped."""
        data = read_text(os.path.join(HELMIT, "run.jsonl"))
        if data is None:
            return []
        lines = data.split("\n")
        if lines:
            lines.pop()  # fragment or the empty tail after the last complete append
        entries = []
        for line in lines:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("event"), str):
                entries.append(obj)
        return entries


    def next_facts():
        """Shared phase/route/CHG derivation; handoff adds only narrative facts."""
        try:
            proc = subprocess.run(
                ["bash", os.path.join(hooks, "next-status.sh"), "facts", "--json"],
                cwd=ROOT, env=dict(os.environ, CLAUDE_PROJECT_DIR=ROOT),
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(proc.stdout)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


    out = []
    if not os.path.isdir(HELMIT):
        print("handoff render: no .helmit/ in %s — not a HelmIt project, nothing to derive" % ROOT)
        sys.exit(0)

    # --- fixed core: the same derivation /next and dashboard consume ------------
    facts = next_facts()
    if facts:
        phase = facts.get("phase")
        if phase:
            out.append("position: %s" % facts.get("position", "phase %s" % phase))
        elif facts.get("dependency_blocks"):
            out.append("position: roadmap blocked — %s" % "; ".join(facts["dependency_blocks"]))
        else:
            out.append("position: complete")
        out.append("workflow: %s (%s)" % (
            facts.get("workflow", "unknown"), facts.get("workflow_source", "unknown")
        ))
    else:
        out.append("position: unavailable — shared next-status derivation failed")
        out.append("workflow: unavailable")

    # --- fixed core: temporal marker ---------------------------------------------
    entries = run_entries()
    stops = [e for e in entries if e.get("event") == "session_stop"]
    if stops:
        last = stops[-1]
        out.append("last stop: %s (reason=%s)" % (last.get("ts", "?"), last.get("reason", "?")))
    else:
        out.append("last stop: no typed stop recorded")

    # --- pendency: dirty working tree (absent = silence) --------------------------
    # Only when ROOT is itself the repo toplevel: from a fixture nested inside a
    # bigger repo, git would report the ENCLOSING repo and leak foreign pendency.
    try:
        top = subprocess.run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        porcelain = ""
        if top.returncode == 0 and os.path.realpath(top.stdout.strip()) == os.path.realpath(ROOT):
            st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                                capture_output=True, text=True, timeout=10)
            if st.returncode == 0:
                porcelain = st.stdout
    except Exception:
        porcelain = ""  # no git, no repo, no time: fail open, say nothing
    paths = [l for l in porcelain.split("\n") if l.strip()]
    if paths:
        out.append("")
        out.append("dirty working tree (%d path(s)):" % len(paths))
        for l in paths[:DIRTY_CAP]:
            out.append("  " + l)
        if len(paths) > DIRTY_CAP:
            out.append("  ... and %d more" % (len(paths) - DIRTY_CAP))

    # --- pendency: open CHG / legacy corr / INBOX from the shared facts ----------
    if facts.get("open_changes"):
        out.append("")
        out.append("open CHG route(s):")
        for change in facts["open_changes"]:
            out.append("  %s (%s) — %s" % (
                change.get("id", "?"), change.get("task", "?"), change.get("intent", "")
            ))
    if facts.get("legacy_corrections"):
        out.append("")
        out.append("open corr: route(s) with REQs still todo:")
        for correction in facts["legacy_corrections"]:
            out.append("  %s — %s" % (
                correction.get("route", "?"), ", ".join(correction.get("requirements", []))
            ))
    inbox = facts.get("inbox", {})
    if inbox.get("open"):
        out.append("")
        out.append("INBOX: %d open item(s) awaiting triage" % inbox["open"])

    # --- the written handoff (REQ-133 freshness) ----------------------------------
    hand = read_text(os.path.join(HELMIT, "HANDOFF.md"))
    if hand is not None:
        lines = hand.split("\n")
        first = lines[0] if lines else ""
        narrative = "\n".join(lines[1:]).strip("\n")
        m = re.match(r"^written_at:\s*(\S+)\s*$", first)
        written = parse_iso(m.group(1)) if m else None
        ended = None
        out.append("")
        if written is None:
            out.append("handoff: unreadable written_at header in .helmit/HANDOFF.md — freshness unknown")
            narrative = hand.strip("\n")  # show everything: the header is not a header
        else:
            # ONLY reason=clean is a session end; gate/awaiting_input are in-turn
            # pauses and never supersede (user decision at the spec gate).
            for e in stops:
                if e.get("reason") != "clean":
                    continue
                ts = parse_iso(e.get("ts"))
                if ts is not None and ts > written:
                    ended = e.get("ts")
                    break  # the FIRST clean stop after written_at is the superseding end
            if ended is None:
                out.append("handoff: current (written %s)" % m.group(1))
            else:
                out.append("handoff: SUPERSEDED by a later session end (written %s, session ended %s)"
                           % (m.group(1), ended))
        # REQ-134: size warning on the WRITTEN part (lines after the header).
        # stderr only, exit 0 always — the size is a thermometer, never a gate.
        body = lines[1:] if written is not None else lines
        if body and body[-1] == "":
            body = body[:-1]  # the trailing newline is not a phantom line
        if len(body) > 60:
            sys.stderr.write(
                "WARNING: handoff narrative is %d lines (over 60). A handoff this "
                "big means the CONTINUOUS CAPTURE failed during the session: "
                "decisions and scope should have been persisted to the "
                "INBOX/REQUIREMENTS/design records WHEN they happened, not swept "
                "up at the end. Nothing was truncated and nothing fails — the "
                "size is a thermometer, never a gate.\n" % len(body))
        # Superseded prose is diagnostic history, never active resume guidance.
        if narrative and ended is None:
            out.append(narrative)

    print("\n".join(out))
    sys.exit(0)


if command == "write":
    if any(arg != "--if-session-end" for arg in sys.argv[2:]):
        print("usage: handoff.sh {render | write [--if-session-end]}  (write: narrative on stdin)", file=sys.stderr); raise SystemExit(2)
    helmit = os.path.join(root, ".helmit")
    target = os.path.join(helmit, "HANDOFF.md")
    if not os.path.isdir(helmit):
        print("handoff: no .helmit/ in %s — not a HelmIt project, nothing to write" % root, file=sys.stderr); raise SystemExit(0)
    body = sys.stdin.read()
    if not body.strip(): print("handoff: nothing to write (empty narrative)"); raise SystemExit(0)
    if "--if-session-end" in sys.argv[2:]:
        reason = ""
        try:
            data = open(os.path.join(helmit, "run.jsonl"), encoding="utf-8", errors="replace").read().split("\n")[:-1]
            import json
            for line in data:
                try: item = json.loads(line)
                except Exception: continue
                if isinstance(item, dict) and item.get("event") == "session_stop": reason = item.get("reason", "")
        except OSError: pass
        if reason in ("gate", "awaiting_input"):
            print("handoff: write refused — last session_stop reason=%s is an in-turn pause, not a session end; the session continues, nothing written" % reason); raise SystemExit(0)
    lock = os.path.join(hooks, "lock.sh")
    held = False
    if os.path.isfile(lock):
        import subprocess
        if subprocess.run(["bash", lock, "acquire"], stdout=sys.stderr, stderr=sys.stderr).returncode:
            print("handoff: write refused — tree lock held by another session (see above); nothing written", file=sys.stderr); raise SystemExit(0)
        held = True
    else: print("WARNING: handoff write proceeding WITHOUT the tree lock — lock.sh not found at %s (fail open)." % lock, file=sys.stderr)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = False
    try:
        fd, tmp = tempfile.mkstemp(prefix=".HANDOFF.md.tmp.", dir=helmit, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as out: out.write("written_at: %s\n%s" % (stamp, body))
        os.replace(tmp, target); ok = True
    finally:
        if held: subprocess.run(["bash", lock, "release"], stdout=sys.stderr, stderr=sys.stderr)
    if not ok: print("error: handoff: could not write %s" % target, file=sys.stderr); raise SystemExit(1)
    count = len(body.splitlines())
    print("handoff: written %s (written_at %s, %d narrative line(s))" % (target, stamp, count))
    if count > 60: print("WARNING: handoff narrative is %d lines (over 60). A handoff this big means the CONTINUOUS CAPTURE failed during the session: decisions and scope should have been persisted to the INBOX/REQUIREMENTS/design records WHEN they happened, not swept up at the end. Nothing was truncated and nothing fails — the size is a thermometer, never a gate." % count, file=sys.stderr)
