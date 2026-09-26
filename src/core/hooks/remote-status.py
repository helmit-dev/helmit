import json
import os
import subprocess
import sys


ROOT = os.path.abspath(os.environ.get("REMOTE_ROOT") or os.getcwd())


def git(*args):
    try:
        result = subprocess.run(["git", "-C", ROOT] + list(args), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def status():
    base = {"available": False, "branch": "", "upstream": "", "head": "",
            "ahead": 0, "behind": 0, "oldest_local_commit": "",
            "tracking": "local-ref", "network_refreshed": False, "reason": ""}
    head = git("rev-parse", "HEAD")
    if not head:
        base["reason"] = "not-a-git-repository"
        return base
    base["head"] = head
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        base["reason"] = "detached-head"
        return base
    base["branch"] = branch
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not upstream:
        base["reason"] = "no-upstream"
        return base
    base["upstream"] = upstream
    counts = git("rev-list", "--left-right", "--count", upstream + "...HEAD")
    if not counts:
        base["reason"] = "unreadable-upstream"
        return base
    try:
        behind, ahead = (int(value) for value in counts.split())
    except (TypeError, ValueError):
        base["reason"] = "unreadable-upstream"
        return base
    oldest = git("log", "--reverse", "--format=%cI", upstream + "..HEAD") or ""
    base.update({"available": True, "ahead": ahead, "behind": behind,
                 "oldest_local_commit": oldest.splitlines()[0] if oldest else "",
                 "reason": "none"})
    return base


def main(argv):
    if argv not in ([], ["show"]):
        print("usage: remote-status.sh [show]", file=sys.stderr)
        return 2
    print(json.dumps(status(), ensure_ascii=False, sort_keys=True))
    return 0


sys.exit(main(sys.argv[1:]))
