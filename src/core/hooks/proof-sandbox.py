"""Materialize and run proof in an exact disposable Git tree."""

import contextlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


class ProofSandboxError(RuntimeError):
    pass


def _git(root, *args, input_text=None, check=True):
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and process.returncode:
        raise ProofSandboxError(
            process.stderr.strip() or process.stdout.strip() or "git command failed"
        )
    return process


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _base(root):
    return Path(root) / ".helmit" / "proof-worktrees"


def recover(root):
    """Remove only proof worktrees whose recorded owner process is gone."""
    root = Path(root).resolve()
    base = _base(root)
    if not base.is_dir():
        return []
    recovered = []
    for owner in sorted(base.glob("proof-*.owner.json")):
        try:
            data = json.loads(owner.read_text(encoding="utf-8"))
            path = Path(data["path"]).resolve()
            pid = int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if path.parent != base.resolve() or _pid_alive(pid):
            continue
        _git(root, "worktree", "remove", "--force", str(path), check=False)
        if path.exists():
            raise ProofSandboxError("cannot remove stale proof worktree %s" % path)
        owner.unlink(missing_ok=True)
        recovered.append(str(path))
    _git(root, "worktree", "prune", check=False)
    return recovered


def candidate_tree(root, source):
    if source == "staged":
        return _git(root, "write-tree").stdout.strip()
    if source == "head":
        return _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    raise ProofSandboxError("source must be staged or head")


def _commit_for_tree(root, source, tree):
    if source == "head":
        return _git(root, "rev-parse", "HEAD").stdout.strip()
    parent = _git(root, "rev-parse", "HEAD").stdout.strip()
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "HelmIt Proof",
        "GIT_AUTHOR_EMAIL": "proof@helmit.local",
        "GIT_COMMITTER_NAME": "HelmIt Proof",
        "GIT_COMMITTER_EMAIL": "proof@helmit.local",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    }
    process = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree, "-p", parent],
        input="HelmIt staged proof candidate\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    if process.returncode:
        raise ProofSandboxError(process.stderr.strip() or "cannot create proof commit")
    return process.stdout.strip()


@contextlib.contextmanager
def workspace(root, source):
    root = Path(root).resolve()
    if not (root / ".helmit").is_dir():
        raise ProofSandboxError(".helmit missing")
    recover(root)
    tree = candidate_tree(root, source)
    commit = _commit_for_tree(root, source, tree)
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    token = "proof-%d-%s" % (os.getpid(), uuid.uuid4().hex[:12])
    path = base / token
    owner = base / (token + ".owner.json")
    owner.write_text(
        json.dumps({"pid": os.getpid(), "path": str(path), "tree": tree}) + "\n",
        encoding="utf-8",
    )
    active_error = None
    try:
        added = _git(root, "worktree", "add", "--detach", "--quiet", str(path), commit,
                     check=False)
        if added.returncode:
            raise ProofSandboxError(added.stderr.strip() or "cannot create proof worktree")
        observed = _git(path, "rev-parse", "HEAD^{tree}").stdout.strip()
        if observed != tree:
            raise ProofSandboxError(
                "materialized tree mismatch: expected %s got %s" % (tree, observed)
            )
        yield path, tree
    except BaseException as error:
        active_error = error
        raise
    finally:
        removed = _git(root, "worktree", "remove", "--force", str(path), check=False)
        owner.unlink(missing_ok=True)
        _git(root, "worktree", "prune", check=False)
        if path.exists() or removed.returncode:
            message = removed.stderr.strip() or "proof worktree remains at %s" % path
            if active_error is None:
                raise ProofSandboxError(message)


def proof_environment(root, path, tree, source):
    environment = dict(os.environ)
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR", "GIT_PREFIX", "QR_ROOT", "PS_ROOT",
    ):
        environment.pop(name, None)
    environment.update({
        "CLAUDE_PROJECT_DIR": str(path),
        "HELMIT_PROOF_ORIGINAL_ROOT": str(Path(root).resolve()),
        "HELMIT_PROOF_ROOT": str(path),
        "HELMIT_PROOF_SOURCE": source,
        "HELMIT_PROOF_TREE": tree,
    })
    return environment


def main(argv):
    root = Path(os.environ.get("PS_ROOT") or os.getcwd()).resolve()
    if argv == ["recover"]:
        for path in recover(root):
            print(path)
        return 0
    if len(argv) < 3 or argv[0] not in ("staged", "head") or argv[1] != "--":
        print("usage: proof-sandbox.sh staged|head -- <command> [args...] | recover",
              file=sys.stderr)
        return 2
    source, command = argv[0], argv[2:]
    try:
        with workspace(root, source) as (path, tree):
            process = subprocess.run(
                command,
                cwd=path,
                env=proof_environment(root, path, tree, source),
            )
            return process.returncode
    except ProofSandboxError as error:
        print("error: proof-sandbox: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
