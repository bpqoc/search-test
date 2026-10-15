"""Pure decisions about what a sync should do to each (repo, version) branch."""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    NEW = "new"  # tracked branch not stored yet: fetch and create a worktree
    CHANGED = "changed"  # remote head moved (or a full sync): fetch and check out
    UNCHANGED = "unchanged"  # nothing to do
    GONE = "gone"  # branch or whole repo no longer exists upstream (or repo now excluded)
    DROP = "drop"  # version removed from oca-index.toml's versions


REMOVING = frozenset({Action.GONE, Action.DROP})
FETCHING = frozenset({Action.NEW, Action.CHANGED})


@dataclass(frozen=True)
class BranchStep:
    repo: str
    version: str
    action: Action


def plan_sync(
    tracked: Collection[str],
    stored: Mapping[tuple[str, str], str],
    remote: Mapping[str, Mapping[str, str]],
    only_versions: Collection[str] | None = None,
    full: bool = False,
) -> list[BranchStep]:
    """Decide the action for every branch in scope.

    Scope is whatever the caller passes in: `stored` and `remote` must cover the same set of
    repos. A repo whose `ls-remote` failed must be left out of both, otherwise its stored branches
    would look deleted upstream and get removed. A repo that is stored but has vanished from the
    org listing (deleted, archived, or newly excluded) belongs in `remote` with no heads, which
    marks its branches GONE.

    Args:
        tracked: Versions listed in oca-index.toml.
        stored: (repo, version) -> head sha recorded by the last sync.
        remote: repo -> {version: head sha} from `ls-remote`, tracked versions only.
        only_versions: Restrict this run to refreshing these tracked versions. A restricted run
            never drops a version, so a quick partial refresh can't delete data.
        full: Treat every unchanged branch as changed (e.g. after editing sparse_exclude or
            exclude_modules).

    Returns:
        One step per branch, sorted by repo then version.
    """
    refreshing = set(tracked if only_versions is None else only_versions)
    branches = set(stored) | {(repo, v) for repo, heads in remote.items() for v in heads}
    steps = []
    for repo, version in sorted(branches):
        old = stored.get((repo, version))
        new = remote.get(repo, {}).get(version)
        if version not in tracked:
            if only_versions is None:
                steps.append(BranchStep(repo, version, Action.DROP))
            continue
        if version not in refreshing:
            continue
        if new is None:
            action = Action.GONE
        elif old is None:
            action = Action.NEW
        elif old != new or full:
            action = Action.CHANGED
        else:
            action = Action.UNCHANGED
        steps.append(BranchStep(repo, version, action))
    return steps


def module_trees(listing: Iterable[str]) -> dict[str, str]:
    """Pick the top-level directories that are Odoo modules out of a branch's tree listing.

    Repos also carry `.github/`, `.oca/`, `docs/`, `scripts/` and (16.0) `setup/`, plus root files
    such as committed 30 MB pandoc `.deb` packages, none of which belong in a module index.

    Args:
        listing: Lines of `git ls-tree -r -t <ref>`: "<mode> <type> <sha>\t<path>", where `-t`
            adds a line for every directory.

    Returns:
        Module directory name -> its git tree sha, for directories that directly contain a
        `__manifest__.py`, sorted by name. The tree sha changes whenever anything in the module
        does, so it tells which modules need parsing again.
    """
    trees, modules = {}, set()
    for line in listing:
        meta, path = line.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "tree" and "/" not in path:
            trees[path] = sha
        elif path.count("/") == 1 and path.endswith("/__manifest__.py"):
            modules.add(path.split("/")[0])
    return {name: trees[name] for name in sorted(modules)}


@dataclass(frozen=True)
class ModuleIndexPlan:
    parse: list[str]
    delete: list[str]


def plan_module_index(
    current: Mapping[str, str], stored: Mapping[str, str], force: bool = False
) -> ModuleIndexPlan:
    """Decide which of a branch's modules to parse again and which to delete from the index.

    Args:
        current: Module name -> tree sha in the checked-out branch, already filtered by
            `exclude_modules`, so a newly excluded module counts as deleted.
        stored: Module name -> tree sha recorded when the module was last parsed.
        force: Parse every current module, e.g. after the parser itself changed.

    Returns:
        Sorted module names to (re)parse and to delete.
    """
    parse = [m for m, sha in current.items() if force or stored.get(m) != sha]
    delete = [m for m in stored if m not in current]
    return ModuleIndexPlan(sorted(parse), sorted(delete))
