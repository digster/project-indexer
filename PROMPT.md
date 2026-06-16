# Prompt Log

## 2026-06-16

> In the table that's created, the indexer should also show a column where it
> shows if the local branch is up to date with the remote branch.

Outcome: added a "Remote status" column to the table view. Implemented git
sync-status collection (`get_git_status`, `collect_git_statuses`, `_run_git`),
a `--fetch` flag for true remote state, status badges with ahead/behind counts,
offline tests, and supporting docs.
