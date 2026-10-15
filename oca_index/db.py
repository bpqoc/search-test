"""SQLite storage: branch heads and parsed modules."""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .parse import README_SECTIONS, ModuleInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS branch (
    repo      TEXT NOT NULL,
    version   TEXT NOT NULL,
    head_sha  TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (repo, version)
);
CREATE TABLE IF NOT EXISTS module (
    id                 INTEGER PRIMARY KEY,
    repo               TEXT NOT NULL,
    version            TEXT NOT NULL,
    name               TEXT NOT NULL,
    tree_sha           TEXT NOT NULL,
    title              TEXT NOT NULL,
    summary            TEXT,
    description        TEXT,
    usage              TEXT,
    configure          TEXT,
    roadmap            TEXT,
    context            TEXT,
    category           TEXT,
    license            TEXT,
    author             TEXT,
    website            TEXT,
    module_version     TEXT,
    development_status TEXT,
    installable        INTEGER NOT NULL,
    application        INTEGER NOT NULL,
    auto_install       INTEGER NOT NULL,
    parse_errors       TEXT,
    UNIQUE (repo, version, name)
);
CREATE INDEX IF NOT EXISTS module_version_name ON module (version, name);
CREATE TABLE IF NOT EXISTS module_depend (
    module_id  INTEGER NOT NULL REFERENCES module ON DELETE CASCADE,
    depends_on TEXT NOT NULL  -- a name, not a FK: may be core, enterprise, or another repo
);
CREATE INDEX IF NOT EXISTS module_depend_module ON module_depend (module_id);
CREATE INDEX IF NOT EXISTS module_depend_target ON module_depend (depends_on);
CREATE TABLE IF NOT EXISTS module_ext_dep (
    module_id INTEGER NOT NULL REFERENCES module ON DELETE CASCADE,
    kind      TEXT NOT NULL,  -- python | bin
    name      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS module_ext_dep_module ON module_ext_dep (module_id);
CREATE TABLE IF NOT EXISTS module_maintainer (
    module_id INTEGER NOT NULL REFERENCES module ON DELETE CASCADE,
    login     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS module_maintainer_module ON module_maintainer (module_id);
CREATE TABLE IF NOT EXISTS model_touch (
    module_id   INTEGER NOT NULL REFERENCES module ON DELETE CASCADE,
    model       TEXT NOT NULL,
    kind        TEXT NOT NULL,  -- define | inherit | mixin | delegate
    model_type  TEXT NOT NULL,  -- Model | TransientModel | AbstractModel
    description TEXT,
    file        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS model_touch_module ON model_touch (module_id);
CREATE INDEX IF NOT EXISTS model_touch_model ON model_touch (model);
CREATE TABLE IF NOT EXISTS model_field (
    module_id   INTEGER NOT NULL REFERENCES module ON DELETE CASCADE,
    model       TEXT NOT NULL,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    comodel     TEXT,
    string      TEXT,
    is_related  INTEGER NOT NULL,
    is_computed INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS model_field_module ON model_field (module_id);
CREATE INDEX IF NOT EXISTS model_field_model ON model_field (model);
CREATE INDEX IF NOT EXISTS model_field_comodel ON model_field (comodel);
"""

PARSER_VERSION_KEY = "parser_version"


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# --- branches ---------------------------------------------------------------------------------


def branch_heads(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """Return (repo, version) -> head sha for every stored branch."""
    rows = conn.execute("SELECT repo, version, head_sha FROM branch")
    return {(r["repo"], r["version"]): r["head_sha"] for r in rows}


def record_branches(conn: sqlite3.Connection, repo: str, results: dict[str, str | None]) -> None:
    """Store a repo's sync results: upsert synced heads, delete removed branches and modules."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with conn:
        for version, sha in results.items():
            if sha is None:
                _delete_modules(conn, _module_ids(conn, repo, version))
                conn.execute("DELETE FROM branch WHERE repo = ? AND version = ?", (repo, version))
            else:
                conn.execute(
                    "INSERT INTO branch (repo, version, head_sha, synced_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (repo, version) DO UPDATE"
                    " SET head_sha = excluded.head_sha, synced_at = excluded.synced_at",
                    (repo, version, sha, now),
                )


# --- modules ----------------------------------------------------------------------------------


def module_shas(conn: sqlite3.Connection, repo: str, version: str) -> dict[str, str]:
    """Return module name -> tree sha as last indexed for one branch."""
    rows = conn.execute(
        "SELECT name, tree_sha FROM module WHERE repo = ? AND version = ?", (repo, version)
    )
    return {r["name"]: r["tree_sha"] for r in rows}


def _module_ids(
    conn: sqlite3.Connection, repo: str, version: str, names: Iterable[str] | None = None
) -> list[int]:
    """Return ids of a branch's modules, all of them or only those named."""
    wanted = None if names is None else set(names)
    rows = conn.execute(
        "SELECT id, name FROM module WHERE repo = ? AND version = ?", (repo, version)
    )
    return [r["id"] for r in rows if wanted is None or r["name"] in wanted]


def _delete_modules(conn: sqlite3.Connection, ids: Iterable[int]) -> None:
    for module_id in ids:
        conn.execute("DELETE FROM module WHERE id = ?", (module_id,))


def write_branch_modules(
    conn: sqlite3.Connection,
    repo: str,
    version: str,
    parsed: Iterable[tuple[str, ModuleInfo]],
    deleted: Iterable[str],
) -> None:
    """Replace re-parsed modules and delete removed ones for one branch, in one transaction.

    Args:
        conn: Database connection.
        repo: Repo name.
        version: Branch version.
        parsed: (tree sha, parsed module) pairs to insert, replacing any stored row.
        deleted: Names of modules to delete.
    """
    parsed = list(parsed)
    with conn:
        _delete_modules(
            conn, _module_ids(conn, repo, version, [*deleted, *(i.name for _, i in parsed)])
        )
        for tree_sha, info in parsed:
            _insert_module(conn, repo, version, tree_sha, info)


def _insert_module(
    conn: sqlite3.Connection, repo: str, version: str, tree_sha: str, info: ModuleInfo
) -> None:
    sections = {s: info.readme.get(s) for s in README_SECTIONS}
    module_id = conn.execute(
        "INSERT INTO module (repo, version, name, tree_sha, title, summary, description, usage,"
        " configure, roadmap, context, category, license, author, website, module_version,"
        " development_status, installable, application, auto_install, parse_errors)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            repo,
            version,
            info.name,
            tree_sha,
            info.title,
            info.summary,
            sections["description"],
            sections["usage"],
            sections["configure"],
            sections["roadmap"],
            sections["context"],
            info.category,
            info.license,
            info.author,
            info.website,
            info.module_version,
            info.development_status,
            info.installable,
            info.application,
            info.auto_install,
            "\n".join(info.errors) or None,
        ),
    ).lastrowid
    conn.executemany(
        "INSERT INTO module_depend (module_id, depends_on) VALUES (?, ?)",
        [(module_id, d) for d in info.depends],
    )
    conn.executemany(
        "INSERT INTO module_ext_dep (module_id, kind, name) VALUES (?, ?, ?)",
        [(module_id, "python", d) for d in info.python_deps]
        + [(module_id, "bin", d) for d in info.bin_deps],
    )
    conn.executemany(
        "INSERT INTO module_maintainer (module_id, login) VALUES (?, ?)",
        [(module_id, m) for m in info.maintainers],
    )
    conn.executemany(
        "INSERT INTO model_touch (module_id, model, kind, model_type, description, file)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(module_id, t.model, t.kind, t.model_type, t.description, t.file) for t in info.models],
    )
    conn.executemany(
        "INSERT INTO model_field (module_id, model, name, type, comodel, string, is_related,"
        " is_computed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (module_id, f.model, f.name, f.type, f.comodel, f.string, f.is_related, f.is_computed)
            for f in info.fields
        ],
    )
