"""Fetch OCA and parse modules into the local SQLite index, through oca-reference's library.

Same steps as `oca-ref sync`, minus its embedding pass and skill install, which this data
doesn't use.
"""

import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from oca_reference import db
from oca_reference.discover import list_repos, remote_heads
from oca_reference.gitcmd import GitError
from oca_reference.index import index_all
from oca_reference.plan import Action, plan_sync
from oca_reference.sync import Paths, prune_version_dirs, sync_repo

from .config import Settings


def sync(settings: Settings) -> bool:
    """Bring the checkouts and index in line with OCA and the settings.

    Returns:
        True when every repo synced.
    """
    config, paths = settings.ref_config(), Paths(settings.data_dir)
    paths.home.mkdir(parents=True, exist_ok=True)
    conn = db.connect(paths.db)
    stored = db.branch_heads(conn)
    listed = {r for r in list_repos(config.org) if config.repo_selected(r)}
    # Stored repos missing from the listing stay in scope so their branches are removed
    scope = listed | {repo for repo, _ in stored}

    started = time.monotonic()
    remote, failed = {}, {}
    with ThreadPoolExecutor(config.parallel) as pool:
        futures = {
            pool.submit(remote_heads, config.org, r, config.versions): r
            for r in sorted(scope & listed)
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
        config.versions,
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

    with ThreadPoolExecutor(config.parallel) as pool:
        futures = {
            pool.submit(sync_repo, paths, config, repo, repo_steps): repo
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

    stats = index_all(conn, paths, config)
    print(
        f"Synced in {time.monotonic() - started:.0f}s: {stats.parsed} modules parsed,"
        f" {stats.deleted} removed, {len(failed)} repos failed"
    )
    return not failed
