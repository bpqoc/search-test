"""Find repos in the org and their current branch heads."""

import json
import os
import urllib.request
from collections.abc import Collection

from .gitcmd import git

ORG = "OCA"
API_PAGE_SIZE = 100  # GitHub's maximum per page
# Optional: raises GitHub's API limit from 60 to 5,000 requests/hour. A sync needs 3 (one per
# 100 OCA repos), so it's only useful on a shared IP that already burned through the 60.
TOKEN_ENVS = ("GITHUB_TOKEN", "GH_TOKEN")


def repo_url(org: str, repo: str) -> str:
    return f"https://github.com/{org}/{repo}"


def parse_repo_page(page: list[dict]) -> list[str]:
    """Names of the non-archived repos in one page of GitHub's `GET /orgs/{org}/repos`."""
    return [repo["name"] for repo in page if not repo["archived"]]


def list_repos(org: str) -> list[str]:
    """List the org's non-archived public repos through GitHub's REST API.

    Uses the public API rather than `gh` so a sync needs no GitHub login. Every page is fetched:
    a listing cut short would make the missing repos look deleted, and sync would remove them,
    so any failed request aborts instead.

    Args:
        org: GitHub organisation, e.g. "OCA".

    Returns:
        Repo names.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token := next((os.environ[e] for e in TOKEN_ENVS if os.environ.get(e)), None):
        headers["Authorization"] = f"Bearer {token}"
    names, page = [], 1
    while True:
        url = (
            f"https://api.github.com/orgs/{org}/repos"
            f"?type=public&per_page={API_PAGE_SIZE}&page={page}"
        )
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
            repos = json.load(response)
        names += parse_repo_page(repos)
        if len(repos) < API_PAGE_SIZE:
            return names
        page += 1


def parse_ls_remote(output: str, versions: Collection[str]) -> dict[str, str]:
    """Pick tracked version branches out of `git ls-remote --heads` output.

    Args:
        output: Lines of "<sha>\\trefs/heads/<branch>".
        versions: Tracked versions; other branches are ignored.

    Returns:
        version -> head sha, only for versions the repo has.
    """
    heads = {}
    for line in output.splitlines():
        sha, ref = line.split("\t")
        branch = ref.removeprefix("refs/heads/")
        if branch in versions:
            heads[branch] = sha
    return heads


def remote_heads(org: str, repo: str, versions: Collection[str]) -> dict[str, str]:
    """Fetch the repo's tracked version heads with one `git ls-remote` call."""
    refs = [f"refs/heads/{v}" for v in versions]
    return parse_ls_remote(git(None, "ls-remote", "--heads", repo_url(org, repo), *refs), versions)
