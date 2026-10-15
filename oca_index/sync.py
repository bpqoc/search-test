"""Fetch OCA and parse modules into the local SQLite index."""

import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import db
from .checkout import Paths, prune_version_dirs, sync_repo
from .config import Settings
from .discover import ORG, list_repos, remote_heads
from .gitcmd import GitError
from .index import index_all
from .plan import Action, plan_sync

# Repos fetched at once
PARALLEL = 8


def sync(settings: Settings) -> bool:
    """Bring the checkouts and index in line with OCA and the settings.

    Returns:
        True when every repo synced.
    """
    paths = Paths(settings.data_dir)
    paths.home.mkdir(parents=True, exist_ok=True)
    conn = db.connect(paths.db)
    stored = db.branch_heads(conn)
    listed = {r for r in list_repos(ORG) if settings.repo_selected(r)}
    # Stored repos missing from the listing stay in scope so their branches are removed
    scope = listed | {repo for repo, _ in stored}

    started = time.monotonic()
    remote, failed = {}, {}
    with ThreadPoolExecutor(PARALLEL) as pool:
        futures = {
            pool.submit(remote_heads, ORG, r, settings.versions): r for r in sorted(scope & listed)
        }
        for future in as_completed(futures):
            try:
                remote[futures[future]] = future.result()
            except GitError as e:
                failed[futures[future]] = str(e)
    for repo in scope - listed:
        remote[repo] = {}
    scope -= failed.keys()

    steps = plan_sync(
        settings.versions,
        {key: sha for key, sha in stored.items() if key[0] in scope},
        {repo: heads for repo, heads in remote.items() if repo in scope},
        only_versions=None,
        full=False,
    )
    by_repo = defaultdict(list)
    for step in steps:
        if step.action is not Action.UNCHANGED:
            by_repo[step.repo].append(step)
    print(f"Checked {len(scope)} repos, {len(by_repo)} changed", flush=True)

    with ThreadPoolExecutor(PARALLEL) as pool:
        futures = {
            pool.submit(sync_repo, paths, settings, repo, repo_steps): repo
            for repo, repo_steps in by_repo.items()
        }
        for done, future in enumerate(as_completed(futures), 1):
            repo = futures[future]
            try:
                db.record_branches(conn, repo, future.result())
            except GitError as e:
                failed[repo] = str(e)
            if done % 25 == 0:
                print(f"  synced {done}/{len(futures)}", flush=True)
    prune_version_dirs(paths)
    for repo, error in sorted(failed.items()):
        print(f"FAILED {repo}: {error}", file=sys.stderr)

    stats = index_all(conn, paths, settings)
    print(
        f"Synced in {time.monotonic() - started:.0f}s: {stats.parsed} modules parsed,"
        f" {stats.deleted} removed, {len(failed)} repos failed"
    )
    return not failed
