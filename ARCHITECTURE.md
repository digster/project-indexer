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

`generate_html()` emits one templated string. All interactivity (search, view
toggle, pagination) is vanilla JS embedded at the bottom and operates on `data-*`
attributes on each row/card (`data-name`, `data-summary`, `data-status`), so the
markup and the client logic stay decoupled. Theme is driven entirely by
`prefers-color-scheme` (no toggle), and view/per-page preferences persist in
`localStorage`.

## Tests

`tests/test_git_status.py` exercises every git state by constructing real
repositories in a temp dir with a local **bare** repo as the "remote" — fully
offline, including the `--fetch` path (fetching from a file path needs no
network). Run with `uv run pytest`.
