"""Assemble the skill's data file and zip from the index, summary cache and migration scan."""

import json
import zipfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from . import db
from .checkout import Paths
from .config import MIGRATIONS_PATH, ROOT, Settings
from .summaries import load_cache, summary_key

SKILL = ROOT / "skill" / "oca-module-search"
DIST = ROOT / "skill" / "dist"
PENDING_FIELDS = ("version", "kind", "pr", "url", "draft", "review", "ci", "updated")


def build_records(
    modules: Iterable[Mapping], summaries: Mapping[str, Mapping], pending: Iterable[Mapping]
) -> tuple[list[dict], list[str]]:
    """One search record per module name, across versions.

    Args:
        modules: Installable module rows (name, version, repo, title, summary, description).
        summaries: Summary cache by key.
        pending: Migration records (see migrations.pending_records).

    Returns:
        (records sorted by name, names left out for lack of a summary).
    """
    by_name: dict[str, list[Mapping]] = {}
    for m in modules:
        by_name.setdefault(m["name"], []).append(m)
    open_prs: dict[str, list[dict]] = {}
    for p in pending:
        if p["kind"] == "migration":
            open_prs.setdefault(p["module"], []).append({k: p[k] for k in PENDING_FIELDS})

    records, unsummarized = [], []
    for name, rows in sorted(by_name.items()):
        rows = sorted(rows, key=lambda r: tuple(int(p) for p in r["version"].split(".")))
        # Newest version's text first, falling back to older ones that were summarized
        summary = next(
            (
                summaries[k]
                for r in reversed(rows)
                if (k := summary_key(r["name"], r["title"], r["summary"], r["description"]))
                in summaries
            ),
            None,
        )
        if summary is None:
            unsummarized.append(name)
            continue
        newest = rows[-1]
        record = {
            "name": name,
            "repo": newest["repo"],
            "title": newest["title"],
            "versions": [r["version"] for r in rows],
            "summary": summary["summary"],
            "keywords": summary["keywords"],
        }
        if prs := open_prs.get(name):
            record["pending"] = sorted(prs, key=lambda p: (p["version"], p["pr"]))
        records.append(record)
    return records, unsummarized


def load_pending(path: Path = MIGRATIONS_PATH) -> tuple[dict, list[dict]]:
    if not path.exists():
        return {}, []
    header, *rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    return header, rows


def build(settings: Settings) -> tuple[Path, int, list[str]]:
    """Write the skill data and zip.

    Returns:
        (zip path, modules included, modules left out for lack of a summary).
    """
    conn = db.connect(Paths(settings.data_dir).db, readonly=True)
    marks = ",".join("?" * len(settings.versions))
    modules = conn.execute(
        "SELECT name, version, repo, title, summary, description FROM module"
        f" WHERE installable AND version IN ({marks})",
        settings.versions,
    ).fetchall()
    header, pending = load_pending()
    records, unsummarized = build_records(modules, load_cache(), pending)

    data = SKILL / "data"
    data.mkdir(parents=True, exist_ok=True)
    for old in data.glob("*.jsonl"):
        old.unlink()
    (data / "oca_modules.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    )
    meta = {
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "versions": list(settings.versions),
        "modules": len(records),
        "migrations_scanned": header.get("scanned_at"),
        "migrations_url": settings.migrations_url,
    }
    (data / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")

    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / f"{SKILL.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, path.relative_to(SKILL.parent))
    return target, len(records), unsummarized
