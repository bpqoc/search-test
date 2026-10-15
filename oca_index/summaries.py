"""Plain-language module summaries: what still needs one, batch files, and the summary cache.

A summary is keyed by the module's name and readme text, so a module unchanged across versions
(or across updates) is summarized once. The pure functions build and check batches; `prepare`,
`ingest` and `summarize_api` are the I/O around them.
"""

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from oca_reference import db
from oca_reference.parse import clean_markup
from oca_reference.sync import Paths

from .config import SUMMARIES_PATH, WORK, Settings

PENDING = WORK / "pending"
RESULTS = WORK / "results"
MAX_DESCRIPTION = 1500
MAX_EXTRA = 400
MAX_FIELDS_PER_MODEL = 10
# Can't be confused with a heading inside a module's readme
MODULE_MARK = "=== MODULE"

PROMPT = """\
You are building a search index of Odoo OCA modules for non-technical business users. For each
module below (manifest, readme excerpt, and the models and fields it defines or extends) write:
- "summary": 2 to 3 plain-English sentences: what problem it solves, what a user can now do or
  see, and where in Odoo (which app or screen) it shows up. Use the models and fields to infer
  the functionality when the description is thin. Don't invent features you have no evidence
  for; if it's a technical or base module, say so.
- "keywords": 8 to 15 short search phrases someone might type to find this feature: plain
  business wording AND the Odoo/OCA terms for the same things.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "keywords"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ModuleText:
    key: str
    name: str
    version: str
    block: str


def summary_key(name: str, title: str | None, summary: str | None, description: str | None) -> str:
    """Identify the text a summary is written from; versions with the same readme share it."""
    text = "\0".join([name, title or "", summary or "", description or ""])
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def module_block(module: Mapping, depends: Sequence[str], outline: Sequence[str], key: str) -> str:
    """The input text for one module's summary."""

    def clip(text, limit):
        text = clean_markup(text or "").strip()
        return text if len(text) <= limit else text[:limit] + " [...]"

    parts = [
        f"{MODULE_MARK} {key} {module['name']} ===",
        f"Repo: {module['repo']} | Title: {module['title']}",
        f"Category: {module['category'] or '-'}",
        f"Manifest summary: {module['summary'] or '-'}",
        f"Depends: {', '.join(depends) or '-'}",
        f"Description: {clip(module['description'], MAX_DESCRIPTION) or '-'}",
    ]
    if module["usage"]:
        parts.append(f"Usage: {clip(module['usage'], MAX_EXTRA)}")
    if module["configure"]:
        parts.append(f"Configure: {clip(module['configure'], MAX_EXTRA)}")
    if outline:
        parts.append("Models:\n" + "\n".join(outline))
    return "\n".join(parts)


def select_pending(modules: Iterable[ModuleText], cached: set[str]) -> list[ModuleText]:
    """One module text per key not yet summarized, from the newest version that has it."""
    newest: dict[str, ModuleText] = {}
    for m in modules:
        if m.key not in cached and (
            m.key not in newest or _version_key(m.version) > _version_key(newest[m.key].version)
        ):
            newest[m.key] = m
    return sorted(newest.values(), key=lambda m: (m.name, m.key))


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def batch_keys(text: str) -> dict[str, str]:
    """key -> module name for every module in a batch file."""
    pattern = rf"^{MODULE_MARK} (\w+) (\S+) ===$"
    return {m[1]: m[2] for m in re.finditer(pattern, text, re.MULTILINE)}


def check_results(rows: Iterable[Mapping], expected: Mapping[str, str]) -> tuple[list, list]:
    """Split summarizer output into valid summaries and problems.

    Args:
        rows: Parsed result objects with key, name, summary and keywords.
        expected: key -> module name of the batch they answer.

    Returns:
        (accepted summaries, problem descriptions).
    """
    accepted, problems = [], []
    for row in rows:
        key = row.get("key")
        if expected.get(key) != row.get("name"):
            problems.append(f"unexpected key/name {key} {row.get('name')}")
        elif not row.get("summary") or not row.get("keywords"):
            problems.append(f"empty summary or keywords for {row['name']}")
        else:
            accepted.append({k: row[k] for k in ("key", "name", "summary", "keywords")})
    missing = expected.keys() - {r["key"] for r in accepted}
    problems += [f"no summary for {expected[k]} ({k})" for k in sorted(missing)]
    return accepted, problems


def agent_instructions(batch: Path, result: Path) -> str:
    """Prompt for a Claude Code subagent summarizing one batch file."""
    return (
        f"{PROMPT}\nRead {batch}. Each module starts with a line `{MODULE_MARK} <key> <name> ===`."
        f" For every module write one JSON object per line to {result} with keys"
        ' "key", "name", "summary", "keywords" (key and name copied exactly from its line).'
        " One line per module, valid JSON, nothing else in the file; write it in chunks with"
        " Bash appends if it's long. Then check the line count equals"
        f" `grep -c '^{MODULE_MARK} ' {batch}` and fix any gap. Reply with the two counts."
    )


# I/O


def load_cache(path: Path = SUMMARIES_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {row["key"]: row for row in map(json.loads, path.read_text().splitlines()) if row}


def save_cache(cache: Mapping[str, dict], path: Path = SUMMARIES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(cache.values(), key=lambda r: (r["name"], r["key"]))
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _outline(conn: sqlite3.Connection, module_id: int) -> list[str]:
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
        shown = [
            f"{f['name']} ({f['type']}{', ' + f['string'] if f['string'] else ''})" for f in fields
        ]
        more = len(shown) - MAX_FIELDS_PER_MODEL
        listed = ", ".join(shown[:MAX_FIELDS_PER_MODEL]) + (f", +{more} more" if more > 0 else "")
        label = f' "{touch["description"]}"' if touch["description"] else ""
        lines.append(f"- {touch['kind']} {touch['model']}{label}: {listed or 'no new fields'}")
    return lines


def collect_modules(settings: Settings) -> list[ModuleText]:
    conn = db.connect(Paths(settings.data_dir).db, readonly=True)
    marks = ",".join("?" * len(settings.versions))
    rows = conn.execute(
        f"SELECT * FROM module WHERE installable AND version IN ({marks})", settings.versions
    ).fetchall()
    out = []
    for m in rows:
        key = summary_key(m["name"], m["title"], m["summary"], m["description"])
        depends = [
            r[0]
            for r in conn.execute(
                "SELECT depends_on FROM module_depend WHERE module_id = ?", (m["id"],)
            )
        ]
        out.append(
            ModuleText(
                key, m["name"], m["version"], module_block(m, depends, _outline(conn, m["id"]), key)
            )
        )
    return out


def prepare(settings: Settings) -> list[Path]:
    """Write a batch file per `batch_size` modules that have no summary yet."""
    pending = select_pending(collect_modules(settings), set(load_cache()))
    PENDING.mkdir(parents=True, exist_ok=True)
    for old in PENDING.glob("batch_*.md"):
        old.unlink()
    paths = []
    size = settings.batch_size
    for i in range(0, len(pending), size):
        path = PENDING / f"batch_{i // size:03d}.md"
        path.write_text("\n\n".join(m.block for m in pending[i : i + size]) + "\n")
        paths.append(path)
    return paths


def ingest() -> tuple[int, list[str]]:
    """Move valid results into the cache; drop batch files that are fully summarized.

    Returns:
        (summaries added, problems).
    """
    cache, added, problems = load_cache(), 0, []
    for batch in sorted(PENDING.glob("batch_*.md")):
        result = RESULTS / f"{batch.stem}.jsonl"
        if not result.exists():
            continue
        rows = []
        for n, line in enumerate(result.read_text().splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    problems.append(f"{result.name}:{n} is not valid JSON")
        accepted, batch_problems = check_results(rows, batch_keys(batch.read_text()))
        problems += [f"{batch.name}: {p}" for p in batch_problems]
        for row in accepted:
            added += row["key"] not in cache
            cache[row["key"]] = row
        if not batch_problems:
            batch.unlink()
            result.unlink()
    save_cache(cache)
    return added, problems


def summarize_api(settings: Settings) -> int:
    """Summarize every pending module through the Message Batches API (needs ANTHROPIC_API_KEY).

    Writes results where `ingest` expects them; returns the number of failed requests.
    """
    import time

    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    blocks = {}
    for batch in sorted(PENDING.glob("batch_*.md")):
        for block in batch.read_text().split(f"\n\n{MODULE_MARK} "):
            block = block if block.startswith(MODULE_MARK) else f"{MODULE_MARK} {block}"
            ((key, name),) = batch_keys(block).items()
            blocks[key] = (batch.stem, name, block)
    if not blocks:
        return 0
    requests = [
        Request(
            custom_id=key,
            params=MessageCreateParamsNonStreaming(
                model=settings.summary_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": f"{PROMPT}\n{block}"}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            ),
        )
        for key, (_, _, block) in blocks.items()
    ]
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted {len(requests)} modules as batch {batch.id}", flush=True)
    while (batch := client.messages.batches.retrieve(batch.id)).processing_status != "ended":
        print(f"  {batch.request_counts.processing} still processing", flush=True)
        time.sleep(60)

    RESULTS.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, list[str]] = {}
    failed = 0
    for result in client.messages.batches.results(batch.id):
        stem, name, _ = blocks[result.custom_id]
        if result.result.type != "succeeded":
            failed += 1
            continue
        text = next((b.text for b in result.result.message.content if b.type == "text"), "")
        row = {"key": result.custom_id, "name": name, **json.loads(text)}
        by_file.setdefault(stem, []).append(json.dumps(row, ensure_ascii=False))
    for stem, lines in by_file.items():
        (RESULTS / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")
    return failed
