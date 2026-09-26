# `/next` recovery branches

Load only the branch named by the routing snapshot. These procedures preserve
the worktree; none authorizes reset, discard, lock deletion, or re-running a
commit blindly.

## Interrupted implementation

Inspect the active task/CHG, staged and unstaged diffs, and the latest run-log
events. Finish or repair the partial outcome, run its focused verify, review the
selected staged diff, and commit logically. A clean tree requires checking for
an already-landed commit before re-executing work.

## Commit recovery or unknown lock

Run `commit-transaction.sh recover`. `LANDED` means only that HEAD advanced;
match the actual commit to the task and proof before recording completion.
`UNKNOWN_LOCK` preserves the index and stops until ownership is proved. Never
delete an index lock or repeat a commit based on elapsed time alone.

## Structural findings

Run `sanity.sh check` for exact artifact and line diagnostics. Anchor structured
edits on a unique whole-line heading verified by position. Repair only the
damaged section, keep a recoverable copy when history is at risk, then rerun the
full structural check. Sanity is advisory to unrelated delivery work.

## Failed proof

Read the named VALIDATION record and raw command output. Determine whether the
failure is product behavior, test/infrastructure, or missing requirement
evidence. Repair the smallest authorized scope and rerun the exact failed proof;
do not replace it with a weaker check.

## State disagreement

Compare the snapshot's artifact-derived workflow with STATE. If the artifacts
are unambiguous and repair is authorized, run `next-status.sh repair-state` and
then refresh the dashboard. If the artifacts disagree with each other, do not
repair STATE; resolve the owning artifact or ask for the material decision.
