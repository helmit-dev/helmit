"""Record and verify quality evidence bound to the current product snapshot."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True


ROOT = os.path.abspath(os.environ.get("QR_ROOT") or os.getcwd())
HELMIT = os.path.join(ROOT, ".helmit")
RECEIPT = os.path.join(HELMIT, "quality-receipt.json")
PROOF_RANK = {"structural": 1, "mechanism": 2, "behavior": 3}
PROOF_LEVELS = tuple(PROOF_RANK) + ("human",)


def fail(message):
    print("error: quality-receipt: " + message, file=sys.stderr)
    raise SystemExit(2)


def git(*args, binary=False):
    process = subprocess.run(
        ["git", "-C", ROOT, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if process.returncode != 0:
        detail = process.stderr.decode(errors="replace") if binary else process.stderr
        fail(detail.strip() or "git command failed")
    return process.stdout if binary else process.stdout.strip()


def frame(digest, label, value):
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def product_fingerprint():
    """Fingerprint the committed product tree, never ambient worktree bytes."""
    digest = hashlib.sha256(b"helmit-product-v2\0")
    raw = git("ls-tree", "-rz", "--full-tree", "HEAD", binary=True)
    for record in raw.rstrip(b"\0").split(b"\0") if raw else ():
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            fail("cannot parse committed tree entry")
        mode, kind, object_id = fields
        if path == b".helmit" or path.startswith(b".helmit/"):
            continue
        frame(digest, b"path\0", path)
        frame(digest, b"mode\0", mode)
        frame(digest, b"kind\0", kind)
        if kind == b"blob":
            data = git("cat-file", "blob", object_id.decode("ascii"), binary=True)
        else:
            data = object_id
        frame(digest, b"data\0", data)
    return digest.hexdigest()


def snapshot():
    return {
        "commit": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
    }


def timestamp(value):
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("timestamp must be ISO 8601")
    if parsed.tzinfo is None:
        fail("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_receipt(receipt):
    os.makedirs(HELMIT, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".quality-receipt.", dir=HELMIT)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, RECEIPT)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_receipt():
    try:
        with open(RECEIPT, encoding="utf-8") as handle:
            receipt = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        fail("cannot read receipt: %s" % error)
    if not isinstance(receipt, dict) or receipt.get("version") != 1:
        fail("unsupported receipt schema")
    return receipt


def receipt(scope, commands, recorded_at=None, execution=None):
    value = {
        "version": 1,
        "snapshot": snapshot(),
        "product_fingerprint": product_fingerprint(),
        "scope": scope,
        "commands": commands,
        "result": "passed" if all(item["result"] == "passed" for item in commands) else "failed",
        "timestamp": timestamp(recorded_at),
    }
    if execution is not None:
        value["execution"] = execution
    return value


def configured_commands():
    config_path = os.path.join(HELMIT, "config.json")
    try:
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        fail("cannot read config.json: %s" % error)
    configured = config.get("commands", {})
    if not isinstance(configured, dict):
        fail("config.json commands must be an object")
    return [(name, configured.get(name) or "") for name in ("test", "build", "lint")]


def proof_sandbox():
    path = os.path.join(os.path.dirname(__file__), "proof-sandbox.py")
    spec = importlib.util.spec_from_file_location("helmit_proof_sandbox", path)
    if spec is None or spec.loader is None:
        fail("cannot load proof-sandbox.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_configured_suite():
    runs = []
    sandbox = proof_sandbox()
    try:
        with sandbox.workspace(ROOT, "head") as (proof_root, proof_tree):
            environment = sandbox.proof_environment(ROOT, proof_root, proof_tree, "head")
            for _name, command in configured_commands():
                if not command:
                    continue
                started = time.monotonic_ns()
                process = subprocess.run(
                    command, cwd=proof_root, env=environment, shell=True
                )
                duration_ms = (time.monotonic_ns() - started) // 1_000_000
                runs.append({
                    "command": command,
                    "result": "passed" if process.returncode == 0 else "failed",
                    "duration_ms": duration_ms,
                })
    except sandbox.ProofSandboxError as error:
        fail("proof isolation failed: %s" % error)
    return runs, {
        "source": "head",
        "tree": proof_tree,
        "isolated": True,
    }


def is_full_suite_scope(scope):
    return (scope.startswith("validate:")
            or scope.startswith("ship:")
            or (scope.startswith("implement:") and ":integration:" in scope))


def require_configured_suite(scope, runs):
    if not is_full_suite_scope(scope):
        return
    expected = [command for _name, command in configured_commands() if command]
    observed = [item["command"] for item in runs]
    if observed != expected:
        fail("full-suite scope %s requires the complete configured commands in order" % scope)


def record(args):
    if not os.path.isdir(HELMIT):
        fail(".helmit missing")
    runs = []
    for command, result, duration in args.run:
        if result not in ("passed", "failed"):
            fail("run result must be passed or failed")
        try:
            duration_ms = int(duration)
        except ValueError:
            fail("run duration must be a non-negative integer in milliseconds")
        if duration_ms < 0:
            fail("run duration must be a non-negative integer in milliseconds")
        runs.append({"command": command, "result": result, "duration_ms": duration_ms})
    require_configured_suite(args.scope, runs)
    write_receipt(receipt(args.scope, runs, args.timestamp))
    print(RECEIPT)


def integration(args):
    if not os.path.isdir(HELMIT):
        fail(".helmit missing")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.reason):
        fail("integration reason must be a stable slug")
    runs, execution = run_configured_suite()
    integration_receipt = receipt(
        "implement:%s:integration:%s" % (args.phase, args.reason), runs,
        execution=execution,
    )
    write_receipt(integration_receipt)
    print(RECEIPT)
    if integration_receipt["result"] != "passed":
        raise SystemExit(1)


def final_suite(args, owner):
    if not os.path.isdir(HELMIT):
        fail(".helmit missing")
    existing = load_receipt()
    expected = [command for _name, command in configured_commands() if command]
    observed = [item.get("command") for item in (existing or {}).get("commands", [])]
    if (existing is not None
            and is_full_suite_scope(existing.get("scope", ""))
            and existing.get("result") == "passed"
            and observed == expected
            and existing.get("product_fingerprint") == product_fingerprint()):
        print("REUSED scope=%s" % existing.get("scope"))
        return
    runs, execution = run_configured_suite()
    final_receipt = receipt(
        "%s:%s" % (owner, args.phase), runs, execution=execution
    )
    write_receipt(final_receipt)
    print("RAN scope=%s:%s" % (owner, args.phase))
    if final_receipt["result"] != "passed":
        raise SystemExit(1)


def validate(args):
    final_suite(args, "validate")


def ship(args):
    final_suite(args, "ship")


def match(_args):
    receipt = load_receipt()
    if receipt is None:
        print("MISSING")
        raise SystemExit(1)
    if receipt.get("product_fingerprint") == product_fingerprint():
        print("MATCH")
        return
    print("STALE")
    raise SystemExit(1)


def show(_args):
    receipt = load_receipt()
    if receipt is None:
        fail("receipt missing")
    json.dump(receipt, sys.stdout, indent=2, sort_keys=True)
    print()


def proof(args):
    evidence = set(args.evidence)
    if args.required == "human":
        sufficient = "human" in evidence
    else:
        strongest = max((PROOF_RANK.get(level, 0) for level in evidence), default=0)
        sufficient = strongest >= PROOF_RANK[args.required]
    verdict = "SUFFICIENT" if sufficient else "INSUFFICIENT"
    print("%s required=%s evidence=%s" %
          (verdict, args.required, ",".join(sorted(evidence))))
    if not sufficient:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(prog="quality-receipt.sh")
    commands = parser.add_subparsers(dest="action", required=True)
    record_parser = commands.add_parser("record")
    record_parser.add_argument("--scope", required=True)
    record_parser.add_argument("--run", nargs=3, action="append", required=True,
                               metavar=("COMMAND", "RESULT", "DURATION_MS"))
    record_parser.add_argument("--timestamp")
    record_parser.set_defaults(handler=record)
    integration_parser = commands.add_parser("integration")
    integration_parser.add_argument("--phase", required=True)
    integration_parser.add_argument("--reason", required=True)
    integration_parser.set_defaults(handler=integration)
    ship_parser = commands.add_parser("ship")
    ship_parser.add_argument("--phase", required=True)
    ship_parser.set_defaults(handler=ship)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--phase", required=True)
    validate_parser.set_defaults(handler=validate)
    match_parser = commands.add_parser("match")
    match_parser.set_defaults(handler=match)
    show_parser = commands.add_parser("show")
    show_parser.set_defaults(handler=show)
    proof_parser = commands.add_parser("proof")
    proof_parser.add_argument("--required", choices=PROOF_LEVELS, required=True)
    proof_parser.add_argument("--evidence", choices=PROOF_LEVELS, action="append", required=True)
    proof_parser.set_defaults(handler=proof)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
