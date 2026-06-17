# Prompt Log

## 2026-06-16

> In the table that's created, the indexer should also show a column where it
> shows if the local branch is up to date with the remote branch.

Outcome: added a "Remote status" column to the table view. Implemented git
sync-status collection (`get_git_status`, `collect_git_statuses`, `_run_git`),
a `--fetch` flag for true remote state, status badges with ahead/behind counts,
offline tests, and supporting docs.

> A scroll bar is getting added in the table view. Suggest a solution.

Outcome: fixed the horizontal scrollbar. Root cause was the space-free path in
`.col-path` (no wrapping rule) inflating the column's min-content width under
default `table-layout: auto`, pushing the table past the `1200px` container.
Added `overflow-wrap: anywhere;` to `.col-path` (and `.col-summary` as a guard).
Playwright-verified no overflow; long paths now wrap.
