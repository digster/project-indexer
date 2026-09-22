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
- **Two views** — card grid and a sortable table, toggle persisted in
  `localStorage`.
- **Client-side search & pagination** — filter by name/description/path; choose
  10/25/50/100/all per page. Page buttons keep the pagination controls in place.
- **Column sorting** — click Name, Path, or Remote status to toggle ascending /
  descending order; Description is not sortable. Sorting applies to all results
  before pagination and carries over to cards. Text is case-insensitive and
  numbers sort naturally (`Project 2` before `Project 10`, `Ahead 2` before
  `Ahead 10`). Remote status sorts by its displayed label, with name/path ties.
- **Remote status filter** — combine the status dropdown with search in either
  view. Changing a filter or sort starts at page 1; empty results are announced.
- **Dark/light theme** — follows the OS `prefers-color-scheme`.
- **Remote sync status (table)** — shows whether each project's local git branch
  is in sync with its remote tracking branch.

## Usage

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then run
from this checkout. uv manages the Python environment and dependencies;
`.python-version` selects Python 3.12 for development (the script supports 3.9+).

```bash
uv sync --locked
uv run project_indexer.py [OPTIONS]
```

`uv.lock` is checked in for reproducible development installs. No manual virtual
environment activation or pip install is needed. Git is optional and is used
only to collect remote sync status.

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
uv run project_indexer.py

# Index a specific directory with a custom title
uv run project_indexer.py --root ~/projects --title "My Projects"

# Refresh remote-tracking refs over the network before computing sync status
uv run project_indexer.py --root ~/projects --fetch
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
uv sync --locked
uv run --locked pytest -q
uv lock --check
```

The git-status tests build real (but local, offline) repositories using a bare
repo as a stand-in remote, so no network access is required. HTML tests check
filter coverage, shared metadata, escaping, and accessible sorting controls.

For real-browser regression tests, generate and serve disposable fixtures:

```bash
uv run python -m tests.browser_fixture /tmp/project-indexer-ui
uv run python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/project-indexer-ui
```

Open [browser checks](http://127.0.0.1:8765/checks.html) to run the 11 interaction
checks and see their results, or [the sample index](http://127.0.0.1:8765/index.html)
to test manually. See [the browser checklist](tests/BROWSER_CHECKS.md) for
additional edge cases. Browser checks use native DOM APIs and require no extra
test dependencies.

Regenerate any existing index with `uv run project_indexer.py --root PATH` to
pick up UI changes; previously generated HTML is a static snapshot.

## License

MIT — see [LICENSE](LICENSE).
