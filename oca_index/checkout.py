"""Execute a repo's planned branch steps against the local partial clone and worktrees."""

import shutil
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .discover import ORG, repo_url
from .gitcmd import git
from .plan import FETCHING, REMOVING, BranchStep, module_trees

# Translations and screenshots: most of each repo's size, no use for summaries
SPARSE_EXCLUDE = ("/*/i18n/", "/*/static/description/")


@dataclass(frozen=True)
class Paths:
    """Layout of the data folder (`data_dir` in oca-index.toml)."""

    home: Path

    @property
    def db(self) -> Path:
        return self.home / "oca.sqlite"

    @property
    def addons(self) -> Path:
        return self.home / "addons"

    def bare(self, repo: str) -> Path:
        return self.home / "repos" / f"{repo}.git"

    def worktree(self, version: str, repo: str) -> Path:
        return self.addons / version / repo


def _ref(version: str) -> str:
    return f"refs/remotes/origin/{version}"


def _ensure_bare(gitdir: Path, url: str) -> None:
    if gitdir.exists():
        return
    gitdir.parent.mkdir(parents=True, exist_ok=True)
    git(None, "init", "--quiet", "--bare", gitdir)
    git(gitdir, "remote", "add", "origin", url)
    git(gitdir, "config", "remote.origin.promisor", "true")
    git(gitdir, "config", "remote.origin.partialclonefilter", "blob:none")
    # Housekeeping is explicit (gc after each sync of the repo) instead of git deciding mid-run.
    git(gitdir, "config", "gc.auto", "0")
    # Windows: module paths under %LOCALAPPDATA% can pass the 260-character limit. No effect
    # elsewhere. Worktrees share this config.
    git(gitdir, "config", "core.longpaths", "true")


def branch_modules(gitdir: Path, version: str, config: Settings) -> dict[str, str]:
    """Module name -> tree sha for the fetched branch, minus `exclude_modules`.

    Reads only the fetched tree, which is local even though file contents aren't.
    """
    listing = git(gitdir, "ls-tree", "-r", "-t", _ref(version)).splitlines()
    return {m: sha for m, sha in module_trees(listing).items() if config.module_selected(m)}


def _check_out(gitdir: Path, worktree: Path, version: str, config: Settings) -> None:
    """Point the version's worktree at the freshly fetched head, creating it if needed.

    The checkout is what pulls file contents, in one batched request. Reading files straight from
    the partial clone instead (`git show`, `cat-file`) fetches one object per request, which
    took 5 minutes for a single repo in testing until GitHub refused connections.

    Only module directories are checked out. A branch with no modules yet gets no worktree:
    sparse checkout with no patterns falls back to the repo's root files.
    """
    modules = branch_modules(gitdir, version, config)
    if not modules:
        _remove_worktree(gitdir, worktree)
        return
    if not (worktree / ".git").exists():
        git(gitdir, "worktree", "prune")
        worktree.parent.mkdir(parents=True, exist_ok=True)
        git(
            gitdir,
            "worktree",
            "add",
            "--quiet",
            "--no-checkout",
            "--detach",
            worktree,
            _ref(version),
        )
    patterns = [f"/{m}/" for m in modules] + [f"!{p}" for p in SPARSE_EXCLUDE]
    git(worktree, "sparse-checkout", "set", "--no-cone", *patterns)
    git(worktree, "checkout", "--quiet", "--detach", _ref(version))


def _remove_worktree(gitdir: Path, worktree: Path) -> None:
    if gitdir.exists() and worktree.exists():
        git(gitdir, "worktree", "remove", "--force", worktree)
    shutil.rmtree(worktree, ignore_errors=True)


def _remove(gitdir: Path, worktree: Path, version: str) -> None:
    _remove_worktree(gitdir, worktree)
    if gitdir.exists():
        git(gitdir, "update-ref", "-d", _ref(version))


def sync_repo(
    paths: Paths, config: Settings, repo: str, steps: Collection[BranchStep]
) -> dict[str, str | None]:
    """Fetch, check out or remove the repo's branches as planned.

    Args:
        paths: Data directory layout.
        config: Module filters and sparse excludes.
        repo: Repo name.
        steps: This repo's steps; UNCHANGED steps are ignored.

    Returns:
        version -> head sha now checked out, or None for a removed branch. The sha is read back
        from the fetched ref, not taken from `ls-remote`, since a push can land in between.
    """
    gitdir = paths.bare(repo)
    fetch = [s.version for s in steps if s.action in FETCHING]
    remove = [s.version for s in steps if s.action in REMOVING]
    results: dict[str, str | None] = {}
    if fetch:
        _ensure_bare(gitdir, repo_url(ORG, repo))
        git(
            gitdir,
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            *(f"+refs/heads/{v}:{_ref(v)}" for v in fetch),
        )
        for version in fetch:
            _check_out(gitdir, paths.worktree(version, repo), version, config)
            results[version] = git(gitdir, "rev-parse", _ref(version)).strip()
    for version in remove:
        _remove(gitdir, paths.worktree(version, repo), version)
        results[version] = None
    if results and gitdir.exists():
        if git(gitdir, "for-each-ref", "refs/remotes/origin/").strip():
            # Drops the previous shallow commits and anything only removed branches used.
            git(gitdir, "gc", "--quiet", "--prune=now")
        else:
            shutil.rmtree(gitdir)
    return results


def prune_version_dirs(paths: Paths) -> None:
    """Remove `addons/<version>/` directories left empty after their last repo was removed."""
    addons = paths.addons
    if addons.exists():
        for version_dir in addons.iterdir():
            if not any(version_dir.iterdir()):
                version_dir.rmdir()
