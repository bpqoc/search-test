"""Open OCA pull requests that bring a module to a version: migrations and new modules.

PR titles are unreliable ("mig sale rental", missing version tags), so a PR counts for a module
when it adds files under a module folder that doesn't exist yet on its target branch. The target
version is the PR's base branch.
"""

import json
import subprocess
import sys
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from oca_reference import db
from oca_reference.sync import Paths

from .config import MIGRATIONS_PATH, Settings

# Top-level folders in OCA repos that aren't modules
NOT_MODULES = frozenset({"setup", ".github", "docs", "scripts"})

# 40 PRs and 60 files per page: bigger pages made GitHub time out (HTTP 502)
QUERY = """
query($repo: String!, $base: String!, $after: String) {
  repository(owner: "OCA", name: $repo) {
    pullRequests(states: OPEN, baseRefName: $base, first: 40, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url isDraft updatedAt reviewDecision
        author { login }
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        files(first: 60) { nodes { path changeType } }
      }
    }
  }
}
"""


def pr_modules(files: Iterable[Mapping], existing: set[str]) -> list[str]:
    """Module folders a PR adds files to that the target branch doesn't have yet."""
    added = {
        f["path"].split("/")[0] for f in files if f["changeType"] == "ADDED" and "/" in f["path"]
    }
    return sorted(m for m in added - existing if m not in NOT_MODULES and not m.startswith("."))


def pending_records(
    repo: str,
    version: str,
    prs: Iterable[Mapping],
    existing: set[str],
    known_elsewhere: set[str],
) -> list[dict]:
    """One record per (module, PR) bringing a module to `version`.

    Args:
        repo: Repo the PRs are from.
        version: Their target branch.
        prs: PR nodes as returned by QUERY.
        existing: Modules already on that branch.
        known_elsewhere: Modules that exist in another tracked version, which makes a PR a
            migration rather than a new module.
    """
    records = []
    for pr in prs:
        commit = pr["commits"]["nodes"][0]["commit"] if pr["commits"]["nodes"] else {}
        for module in pr_modules(pr["files"]["nodes"], existing):
            records.append(
                {
                    "module": module,
                    "version": version,
                    "repo": repo,
                    "kind": "migration" if module in known_elsewhere else "new",
                    "pr": pr["number"],
                    "url": pr["url"],
                    "title": pr["title"],
                    "author": (pr["author"] or {}).get("login"),
                    "draft": pr["isDraft"],
                    "review": pr["reviewDecision"],
                    "ci": (commit.get("statusCheckRollup") or {}).get("state"),
                    "updated": pr["updatedAt"][:10],
                }
            )
    return records


# I/O


def fetch_prs(repo: str, version: str) -> list[dict]:
    prs, after = [], None
    while True:
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={QUERY}",
            "-F",
            f"repo={repo}",
            "-F",
            f"base={version}",
        ]
        if after:
            args += ["-F", f"after={after}"]
        out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
        page = json.loads(out)["data"]["repository"]["pullRequests"]
        prs += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return prs
        after = page["pageInfo"]["endCursor"]


def scan(settings: Settings) -> tuple[int, list[str]]:
    """Scan every synced repo and version; write MIGRATIONS_PATH.

    Returns:
        (records written, repos/versions that failed).
    """
    conn = db.connect(Paths(settings.data_dir).db, readonly=True)
    on_branch: dict[tuple[str, str], set[str]] = {}
    for row in conn.execute("SELECT repo, version, name FROM module"):
        on_branch.setdefault((row["repo"], row["version"]), set()).add(row["name"])
    by_version: dict[str, set[str]] = {}
    for (_, version), names in on_branch.items():
        by_version.setdefault(version, set()).update(names)
    elsewhere = {
        v: set().union(*(n for other, n in by_version.items() if other != v))
        for v in settings.versions
    }
    repos = sorted({repo for repo, _ in db.branch_heads(conn)})
    jobs = [(r, v) for r in repos for v in settings.versions]

    records, failed = [], []
    with ThreadPoolExecutor(8) as pool:
        futures = {pool.submit(fetch_prs, r, v): (r, v) for r, v in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            repo, version = futures[future]
            try:
                prs = future.result()
            except (subprocess.CalledProcessError, KeyError, TypeError) as e:
                failed.append(f"{repo} {version}: {e}")
                continue
            records += pending_records(
                repo, version, prs, on_branch.get((repo, version), set()), elsewhere[version]
            )
            if done % 100 == 0:
                print(f"  scanned {done}/{len(jobs)}", flush=True)
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    records.sort(key=lambda r: (r["module"], r["version"], r["pr"]))
    MIGRATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = {"scanned_at": datetime.now(UTC).isoformat(timespec="seconds")}
    MIGRATIONS_PATH.write_text(
        json.dumps(header) + "\n" + "".join(json.dumps(r) + "\n" for r in records)
    )
    return len(records), failed
