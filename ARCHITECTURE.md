# Architecture

## Overview

The entire tool is a single script, [`project_indexer.py`](project_indexer.py).
It scans a directory tree, builds a metadata cache from README files, layers on
live git status, and emits a self-contained `index.html`. There is no server,
build step, or runtime dependency beyond the Python standard library and the
`git` CLI (which is optional — its absence degrades gracefully).

## Data flow

```
discover_projects(root)        # os.walk, find dirs with a README (skips DEFAULT_EXCLUDES)
        │  {project_path -> readme_path}
        ▼
load_cache() + needs_update()  # reuse cached entry unless README mtime/size changed
        │
process_project()              # parse name + summary from the README
        │  {project_path -> {readme_*, name, summary}}
        ▼
save_cache()                   # persist README metadata ONLY (.project_index_cache.json)
        │
collect_git_statuses()         # fresh, every run, concurrent; attaches entry['git']
        │  uses get_git_status() per repo
        ▼
generate_html()                # render cards + table (with status badges) -> index.html
```

## Key design decisions

### Git status is recomputed every run, never cached
The incremental cache keys off README `mtime`/`size`. Git sync state changes
independently of the README (you commit, push, or fetch without touching it), so
caching it would show stale data. The git pass therefore runs **after**
`save_cache()` and mutates the in-memory dict only — the on-disk cache stays
README-only, while the HTML always reflects current git state. See the wiring in
`main()` and `collect_git_statuses()` / `get_git_status()`.

### Local compare by default, network fetch opt-in
`get_git_status()` compares `HEAD` against the locally stored remote-tracking ref
(`@{upstream}`) in a single `git rev-list --left-right --count @{u}...HEAD` call
(left = behind, right = ahead). This is instant and offline. `--fetch` runs
`git fetch` per repo first for true remote state. All git calls go through
`_run_git()`, which collapses every failure mode (git missing, non-zero exit,
timeout) into `(False, '')` so a single repo can never abort the whole run.

### Concurrency
Git status collection is I/O-bound (subprocess + optional network), so
`collect_git_statuses()` fans out over a `ThreadPoolExecutor` (stdlib, preserving
the zero-dependency property). Worker count is capped at 16.

### Presentation split
`get_git_status()` returns raw state + counts; `git_status_badge()` maps that to a
`(css_state, label)` pair. The label encodes magnitude (`Ahead 2`, `Diverged ↑1
↓2`); the `css_state` becomes a `status-<state>` class. Badge colors are defined
as CSS variables in both the `:root` (dark) and `@media (prefers-color-scheme:
light)` blocks, with translucent fills via `color-mix()`.

## Output HTML

`generate_html()` emits one templated string. All interactivity (search, status
filtering, column sorting, view toggle, pagination) is vanilla JS embedded at the
bottom. Cards and rows receive the same escaped `data-name`, `data-summary`,
`data-path`, `data-status`, and `data-status-label` attributes. The client pairs
them into one project collection in their initial generated order, so both
views always share the same filtering, ordering, and page slice.

Sorting reorders the complete collection and both DOM containers only when the
sort changes. `Intl.Collator` supplies case-insensitive natural ordering;
status sorts by the visible badge label (including numeric counts), then name
and path break ties. Description has no sort control. Search and exact status
filters combine with AND; changes to search, status, sort, or page size reset
the current page. Header buttons expose the current direction through
`aria-sort`, and a live region reports filtered counts.

Page-button clicks preserve the pagination container's viewport position by
measuring it before/after rendering and adjusting the scroll by the difference.
This accounts for browser scroll anchoring and pages with unequal heights;
native viewport limits still apply when a page is too short to scroll. Rebuilt
pagination restores focus to the current-page button with `preventScroll`.
Global keyboard shortcuts ignore form controls so dropdown arrow keys work.

Theme is driven entirely by
`prefers-color-scheme` (no toggle), and view/per-page preferences persist in
`localStorage` (including the `all` page-size value). Sort and filter state are
session-only and reset on reload.

## Python environment

uv owns the local `.venv`; `.python-version` selects Python 3.12 by default and
`pyproject.toml` retains compatibility with 3.9+. `package = false` keeps the
single script un-packaged, with no runtime dependencies; pytest lives in the
default dev dependency group. Use `uv sync --locked` to install the checked-in
`uv.lock`, `uv run project_indexer.py` to scan, and `uv lock --check` to validate
dependency metadata. The script's shebang also uses uv for direct execution.

## Tests

`tests/test_git_status.py` exercises every git state by constructing real
repositories in a temp dir with a local **bare** repo as the "remote" — fully
offline, including the `--fetch` path (fetching from a file path needs no
network). Run with `uv run --locked pytest -q`.

`tests/test_html.py` parses generated output with `html.parser` to test escaped
shared metadata, filter coverage for all git states, empty indexes, and
accessible sorting controls. `tests/browser_fixture.py` builds disposable HTML
fixtures, including a copy with `tests/browser_checks.js` appended. That test
runner exercises the real generated DOM, sorting/filter interactions, focus,
and scrolling using native browser APIs; it never ships in production output.
See `tests/BROWSER_CHECKS.md` for commands and extra manual coverage.
