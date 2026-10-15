"""Parse checked-out modules into the database, reparsing only what changed."""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import db
from .checkout import Paths, branch_modules
from .config import Settings
from .parse import PARSER_VERSION, ModuleInfo, is_model_source, parse_module
from .plan import plan_module_index


@dataclass
class IndexStats:
    parsed: int = 0
    deleted: int = 0
    with_errors: int = 0


def _read(path: Path) -> str:
    # utf-8-sig drops a leading byte-order mark, which `ast.parse` rejects as a syntax error
    # (seen in stock_move_line_lock_qty_done 16.0).
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _long_path(path: Path) -> Path:
    # Windows refuses paths over 260 characters unless they carry the \\?\ prefix (or the
    # machine has LongPathsEnabled set), and module files under %LOCALAPPDATA% can get there.
    return Path("\\\\?\\" + str(path.resolve())) if os.name == "nt" else path


def read_and_parse(module_dir: Path) -> ModuleInfo:
    """Read one checked-out module's files and parse them."""
    module_dir = _long_path(module_dir)
    readme_dir = module_dir / "readme"
    readme = (
        {p.name: _read(p) for p in readme_dir.iterdir() if p.is_file()}
        if readme_dir.is_dir()
        else {}
    )
    readme_rst = module_dir / "README.rst"
    python = {}
    for path in module_dir.rglob("*.py"):
        relpath = path.relative_to(module_dir).as_posix()
        if is_model_source(relpath):
            python[relpath] = _read(path)
    return parse_module(
        module_dir.name,
        _read(module_dir / "__manifest__.py"),
        readme,
        _read(readme_rst) if readme_rst.is_file() else None,
        python,
    )


def index_branch(
    conn: sqlite3.Connection, paths: Paths, config: Settings, repo: str, version: str, force: bool
) -> IndexStats:
    """Bring one branch's modules in the database in line with its worktree."""
    gitdir = paths.bare(repo)
    current = branch_modules(gitdir, version, config) if gitdir.exists() else {}
    plan = plan_module_index(current, db.module_shas(conn, repo, version), force)
    worktree = paths.worktree(version, repo)
    parsed = [(current[name], read_and_parse(worktree / name)) for name in plan.parse]
    db.write_branch_modules(conn, repo, version, parsed, plan.delete)
    return IndexStats(
        parsed=len(parsed),
        deleted=len(plan.delete),
        with_errors=sum(1 for _, info in parsed if info.errors),
    )


def index_all(
    conn: sqlite3.Connection, paths: Paths, config: Settings, force: bool = False
) -> IndexStats:
    """Index every stored branch.

    Unchanged modules cost one `git ls-tree` per branch (local) and a sha comparison, so this
    runs over everything rather than tracking which branches the last sync touched. A parser
    change (PARSER_VERSION) forces a full reparse.
    """
    force = force or db.get_meta(conn, db.PARSER_VERSION_KEY) != str(PARSER_VERSION)
    total = IndexStats()
    for repo, version in sorted(db.branch_heads(conn)):
        stats = index_branch(conn, paths, config, repo, version, force)
        total.parsed += stats.parsed
        total.deleted += stats.deleted
        total.with_errors += stats.with_errors
    db.set_meta(conn, db.PARSER_VERSION_KEY, str(PARSER_VERSION))
    return total
