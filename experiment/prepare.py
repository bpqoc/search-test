"""Write the summarization input for the benchmark pool as batch files for Haiku subagents.

The pool is every installable 18.0 module in a repo that holds at least one expected benchmark
answer, so near-miss neighbours (other sale-workflow modules, etc.) stay in as distractors.

Usage (from the repo root, using the oca-reference environment and its local index):
    uv run --project ~/stuff/oca/oca-reference python experiment/prepare.py
"""

import json
import tomllib
from pathlib import Path

from oca_reference import db
from oca_reference.config import data_home
from oca_reference.parse import clean_markup
from oca_reference.sync import Paths

VERSION = "18.0"
BENCHMARK = Path.home() / "stuff/oca/oca-reference/research/benchmark_cases.toml"
WORK = Path(__file__).parent / "work"
BATCHES = 10
# Caps per section keep one module's input around 600 tokens, so a batch fits a subagent easily.
MAX_DESCRIPTION = 1500
MAX_EXTRA = 400
MAX_FIELDS_PER_MODEL = 10


def pool_modules(conn) -> list:
    cases = tomllib.loads(BENCHMARK.read_text())["case"]
    expected = sorted({m for c in cases if c["version"] == VERSION for m in c["expected"]})
    marks = ",".join("?" * len(expected))
    repos = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT repo FROM module WHERE version = ? AND name IN ({marks})",
            [VERSION, *expected],
        )
    ]
    marks = ",".join("?" * len(repos))
    return conn.execute(
        f"SELECT * FROM module WHERE version = ? AND installable AND repo IN ({marks})"
        " ORDER BY repo, name",
        [VERSION, *repos],
    ).fetchall()


def model_outline(conn, module_id: int) -> list[str]:
    """One line per model the module defines or extends, with the fields it adds."""
    lines = []
    touches = conn.execute(
        "SELECT model, kind, description FROM model_touch WHERE module_id = ?"
        " AND kind IN ('define', 'inherit') ORDER BY kind, model",
        (module_id,),
    ).fetchall()
    for touch in touches:
        fields = conn.execute(
            "SELECT name, type, string FROM model_field WHERE module_id = ? AND model = ?",
            (module_id, touch["model"]),
        ).fetchall()
        shown = [f"{f['name']} ({f['type']}{', ' + f['string'] if f['string'] else ''})" for f in fields]
        more = len(shown) - MAX_FIELDS_PER_MODEL
        listed = ", ".join(shown[:MAX_FIELDS_PER_MODEL]) + (f", +{more} more" if more > 0 else "")
        label = f" \"{touch['description']}\"" if touch["description"] else ""
        lines.append(f"- {touch['kind']} {touch['model']}{label}: {listed or 'no new fields'}")
    return lines


def module_block(conn, m) -> str:
    def clip(text, limit):
        text = clean_markup(text or "").strip()
        return text if len(text) <= limit else text[:limit] + " [...]"

    depends = [r[0] for r in conn.execute(
        "SELECT depends_on FROM module_depend WHERE module_id = ?", (m["id"],)
    )]
    parts = [
        f"### {m['name']}",
        f"Repo: {m['repo']} | Title: {m['title']} | Category: {m['category'] or '-'}",
        f"Manifest summary: {m['summary'] or '-'}",
        f"Depends: {', '.join(depends) or '-'}",
        f"Description: {clip(m['description'], MAX_DESCRIPTION) or '-'}",
    ]
    if m["usage"]:
        parts.append(f"Usage: {clip(m['usage'], MAX_EXTRA)}")
    if m["configure"]:
        parts.append(f"Configure: {clip(m['configure'], MAX_EXTRA)}")
    if outline := model_outline(conn, m["id"]):
        parts.append("Models:\n" + "\n".join(outline))
    return "\n".join(parts)


def main() -> None:
    conn = db.connect(Paths(data_home()).db, readonly=True)
    modules = pool_modules(conn)
    batch_dir = WORK / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    size = -(-len(modules) // BATCHES)
    for i in range(BATCHES):
        chunk = modules[i * size : (i + 1) * size]
        text = "\n\n".join(module_block(conn, m) for m in chunk)
        (batch_dir / f"batch_{i:02d}.md").write_text(text + "\n")
        print(f"batch_{i:02d}: {len(chunk)} modules, {len(text):,} chars")
    (WORK / "pool.json").write_text(json.dumps([m["name"] for m in modules]))
    print(f"{len(modules)} modules in pool")


if __name__ == "__main__":
    main()
