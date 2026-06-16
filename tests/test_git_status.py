"""
Tests for git remote-sync detection in project_indexer.

Every scenario is built from scratch in a temp directory using a local *bare*
repository as a stand-in "remote", so the whole suite is fully offline — even the
test that exercises the `--fetch` (network) code path, since fetching from a
file:// bare repo needs no network.
"""

import subprocess
from pathlib import Path

import pytest

from project_indexer import (
    collect_git_statuses,
    get_git_status,
    git_status_badge,
)


# --- git helpers -----------------------------------------------------------

def git(cwd: Path, *args: str) -> str:
    """Run a git command in `cwd` and return trimmed stdout (raises on failure)."""
    result = subprocess.run(
        ['git', '-C', str(cwd), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def init_repo(path: Path) -> None:
    """Create a git repo with deterministic identity and no GPG signing."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, 'init', '-q')
    # Local config keeps the repo independent of the host's global gitconfig.
    git(path, 'config', 'user.email', 'test@example.com')
    git(path, 'config', 'user.name', 'Test User')
    git(path, 'config', 'commit.gpgsign', 'false')


def commit(path: Path, filename: str, content: str) -> str:
    """Write a file, commit it, and return the new commit hash."""
    (path / filename).write_text(content)
    git(path, 'add', '-A')
    git(path, 'commit', '-q', '-m', f'add {filename}')
    return git(path, 'rev-parse', 'HEAD')


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A bare repository acting as the shared 'origin' remote."""
    bare = tmp_path / 'origin.git'
    bare.mkdir()
    git(bare, 'init', '--bare', '-q')
    return bare


def make_tracking_repo(tmp_path: Path, remote: Path, name: str) -> Path:
    """Create a repo wired to `remote` with an initial pushed commit (up to date)."""
    repo = tmp_path / name
    init_repo(repo)
    commit(repo, 'README.md', '# Project\n')
    git(repo, 'remote', 'add', 'origin', str(remote))
    branch = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
    git(repo, 'push', '-q', '-u', 'origin', branch)
    return repo


# --- state detection -------------------------------------------------------

def test_not_a_repo(tmp_path: Path):
    plain = tmp_path / 'plain'
    plain.mkdir()
    assert get_git_status(plain)['state'] == 'not_repo'


def test_no_upstream(tmp_path: Path):
    repo = tmp_path / 'lonely'
    init_repo(repo)
    commit(repo, 'README.md', '# Lonely\n')
    status = get_git_status(repo)
    assert status['state'] == 'no_remote'
    assert status['branch']  # branch name is still reported


def test_up_to_date(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'synced')
    status = get_git_status(repo)
    assert status['state'] == 'up_to_date'
    assert status['ahead'] == 0 and status['behind'] == 0
    assert status['upstream']  # e.g. origin/main


def test_ahead(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'ahead')
    commit(repo, 'extra.txt', 'local only\n')  # unpushed
    status = get_git_status(repo)
    assert status['state'] == 'ahead'
    assert status['ahead'] == 1 and status['behind'] == 0


def test_behind(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'behind')
    # A second clone pushes a new commit to the shared remote...
    other = tmp_path / 'other'
    git(tmp_path, 'clone', '-q', str(remote), str(other))
    git(other, 'config', 'user.email', 'test@example.com')
    git(other, 'config', 'user.name', 'Test User')
    git(other, 'config', 'commit.gpgsign', 'false')
    commit(other, 'remote.txt', 'from elsewhere\n')
    git(other, 'push', '-q')
    # ...and our repo updates its remote-tracking ref WITHOUT merging (offline).
    git(repo, 'fetch', '-q')
    status = get_git_status(repo)
    assert status['state'] == 'behind'
    assert status['behind'] == 1 and status['ahead'] == 0


def test_diverged(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'diverged')
    commit(repo, 'local.txt', 'mine\n')  # local-only commit
    # Remote advances independently via a second clone.
    other = tmp_path / 'other2'
    git(tmp_path, 'clone', '-q', str(remote), str(other))
    git(other, 'config', 'user.email', 'test@example.com')
    git(other, 'config', 'user.name', 'Test User')
    git(other, 'config', 'commit.gpgsign', 'false')
    commit(other, 'theirs.txt', 'theirs\n')
    git(other, 'push', '-q')
    git(repo, 'fetch', '-q')
    status = get_git_status(repo)
    assert status['state'] == 'diverged'
    assert status['ahead'] == 1 and status['behind'] == 1


def test_detached_head(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'detached')
    first = commit(repo, 'second.txt', 'second\n')  # noqa: F841
    head = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-q', head)  # detach onto the commit hash
    assert get_git_status(repo)['state'] == 'detached'


def test_fetch_path_updates_state(tmp_path: Path, remote: Path):
    """do_fetch=True must pull new remote commits into the comparison."""
    repo = make_tracking_repo(tmp_path, remote, 'needs-fetch')
    other = tmp_path / 'other3'
    git(tmp_path, 'clone', '-q', str(remote), str(other))
    git(other, 'config', 'user.email', 'test@example.com')
    git(other, 'config', 'user.name', 'Test User')
    git(other, 'config', 'commit.gpgsign', 'false')
    commit(other, 'pushed.txt', 'new\n')
    git(other, 'push', '-q')
    # Without fetching, our repo still thinks it is up to date...
    assert get_git_status(repo, do_fetch=False)['state'] == 'up_to_date'
    # ...but get_git_status with do_fetch=True should discover it is behind.
    status = get_git_status(repo, do_fetch=True)
    assert status['state'] == 'behind'
    assert status['behind'] == 1


# --- aggregation & presentation -------------------------------------------

def test_collect_git_statuses_preserves_keys(tmp_path: Path, remote: Path):
    repo = make_tracking_repo(tmp_path, remote, 'agg')
    plain = tmp_path / 'plain'
    plain.mkdir()
    statuses = collect_git_statuses({'agg': repo, 'plain': plain})
    assert set(statuses) == {'agg', 'plain'}
    assert statuses['agg']['state'] == 'up_to_date'
    assert statuses['plain']['state'] == 'not_repo'


def test_collect_git_statuses_empty():
    assert collect_git_statuses({}) == {}


@pytest.mark.parametrize('git_data, expected', [
    ({'state': 'up_to_date'}, ('up_to_date', 'Up to date')),
    ({'state': 'ahead', 'ahead': 2}, ('ahead', 'Ahead 2')),
    ({'state': 'behind', 'behind': 3}, ('behind', 'Behind 3')),
    ({'state': 'diverged', 'ahead': 1, 'behind': 2}, ('diverged', 'Diverged ↑1 ↓2')),
    ({'state': 'no_remote'}, ('no_remote', 'No remote')),
    ({'state': 'detached'}, ('detached', 'Detached')),
    ({'state': 'not_repo'}, ('not_repo', '—')),
    ({'state': 'error'}, ('error', '—')),
    ({}, ('not_repo', '—')),
])
def test_git_status_badge(git_data, expected):
    assert git_status_badge(git_data) == expected
