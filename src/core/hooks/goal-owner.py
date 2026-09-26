import os, sys

THREAD = os.environ.get("CODEX_THREAD_ID", "")
GOAL_ID = os.environ.get("HELMIT_GOAL_ID", "")
GOAL_THREAD = os.environ.get("HELMIT_GOAL_THREAD_ID", "")
GOAL_STATUS = os.environ.get("HELMIT_GOAL_STATUS", "")

def main(args):
    if args != ["status"]:
        print("goal-owner: REFUSE — uso: goal-owner.sh status", file=sys.stderr); raise SystemExit(2)
    if not THREAD:
        print("goal-owner: UNAVAILABLE — CODEX_THREAD_ID missing"); return
    if not GOAL_ID:
        print("goal-owner: ABSENT — no Goal for current task"); return
    if GOAL_THREAD != THREAD:
        print("goal-owner: REFUSE — Goal belongs to another task", file=sys.stderr); raise SystemExit(2)
    print("goal-owner: OWNED — id=%s status=%s" % (GOAL_ID, GOAL_STATUS or "unknown"))

main(sys.argv[1:])
