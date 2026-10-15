"""Build the uploadable skill zip: summaries plus repo/title from the oca-reference index.

Usage:
    uv run --project ~/stuff/oca/oca-reference python skill/build.py
"""

import json
import zipfile
from pathlib import Path

from oca_reference import db
from oca_reference.config import data_home
from oca_reference.sync import Paths

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / "oca-module-search"
SUMMARIES = ROOT.parent / "experiment/work/summaries"
DIST = ROOT / "dist"
VERSION = "18.0"


def main() -> None:
    conn = db.connect(Paths(data_home()).db, readonly=True)
    modules = {
        r["name"]: r
        for r in conn.execute("SELECT name, repo, title FROM module WHERE version = ?", (VERSION,))
    }
    records = []
    for path in sorted(SUMMARIES.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            s = json.loads(line)
            # Skips stray entries a summarizer wrote for readme sub-headings
            if m := modules.get(s["name"]):
                records.append({"name": s["name"], "repo": m["repo"], "title": m["title"],
                                "summary": s["summary"], "keywords": s["keywords"]})
    data = SKILL / "data"
    data.mkdir(exist_ok=True)
    (data / f"oca_{VERSION}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    )

    DIST.mkdir(exist_ok=True)
    target = DIST / f"{SKILL.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, path.relative_to(ROOT))
    print(f"{len(records)} modules -> {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
