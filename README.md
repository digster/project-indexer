# Project README Indexer

A dependency-free Python script that scans a directory tree for projects with
README files, extracts each project's name and summary, and generates a single
self-contained `index.html` with search, card/table views, pagination, and a
per-project **remote sync status**.

## Features

- **Zero dependencies** — pure Python 3 standard library; the output HTML uses
  vanilla CSS/JS (no frameworks, no build step).
- **Incremental scanning** — only re-parses READMEs whose `mtime`/`size` changed,
  via a JSON cache (`.project_index_cache.json`).
- **Two views** — card grid and a sortable-feeling table, toggle persisted in
  `localStorage`.
- **Client-side search & pagination** — filter by name/description/path; choose
  10/25/50/100/all per page.
- **Dark/light theme** — follows the OS `prefers-color-scheme`.
- **Remote sync status (table)** — shows whether each project's local git branch
  is in sync with its remote tracking branch.

## Usage

```bash
python3 project_indexer.py [OPTIONS]
```

| Option | Description |
| --- | --- |
| `--root, -r PATH` | Root directory to scan (default: current directory) |
| `--output, -o PATH` | Output HTML path (default: `index.html` in root) |
| `--cache, -c PATH` | Cache file path (default: `.project_index_cache.json` in root) |
| `--title, -t STRING` | Page title (default: `Project Index`) |
| `--exclude, -e DIRNAME` | Extra directory names to skip (repeatable) |
| `--fetch` | Run `git fetch` per repo before comparing (network; slower) |
| `--verbose, -v` | Print per-project scan and git results |

### Examples

```bash
# Index the current directory
python3 project_indexer.py

# Index a specific directory with a custom title
python3 project_indexer.py --root ~/projects --title "My Projects"

# Refresh remote-tracking refs over the network before computing sync status
python3 project_indexer.py --root ~/projects --fetch
```

## Remote sync status column

The table's **Remote status** column reports how each project's local branch
compares to its upstream (remote-tracking) branch:

| Badge | Meaning |
| --- | --- |
| `Up to date` | Local matches its remote branch |
| `Ahead N` | N local commits not yet pushed |
| `Behind N` | N remote commits not yet pulled |
| `Diverged ↑A ↓B` | Both sides have unique commits (needs merge/rebase) |
| `No remote` | Git repo with no configured upstream branch |
| `Detached` | Detached HEAD (not on a branch) |
| `—` | Not a git repository (or git unavailable) |

**Freshness:** by default the comparison is made against the *locally cached*
remote-tracking ref (`@{upstream}`), so it is instant and works offline — but it
is only as current as your last `git fetch`. Pass `--fetch` to fetch from each
remote first for true up-to-the-second status (slower, and may prompt for auth).

Git status is **recomputed on every run** (never cached), because it changes
independently of the README the incremental cache tracks. Status reflects the git
repository that *contains* each project directory.

## Development

Tests use [`uv`](https://docs.astral.sh/uv/) and `pytest`:

```bash
uv run pytest            # or: uv run --with pytest pytest -q
```

The git-status tests build real (but local, offline) repositories using a bare
repo as a stand-in remote, so no network access is required.

## License

MIT — see [LICENSE](LICENSE).
