"""Search this skill's OCA module summaries. Standard library only.

Usage:
    python3 search.py info
    python3 search.py search "<query>" [--version 18.0|all] [--limit 20]
    python3 search.py show <module> [<module> ...]
    python3 search.py repo <repo> [--version 18.0|all]
"""

import argparse
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
K1 = 1.2
B = 0.75
STOPWORDS = frozenset(
    "a an and are as at be by can do for from has have how i in is it its of on or our so"
    " that the their them they this to us we what when which who will with you your"
    " should must need want".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase words with a crude plural strip, so "orders" matches "order"."""
    words = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return [
        w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
        for w in words
        if w not in STOPWORDS
    ]


def document(m: dict) -> str:
    # Name counted twice: it's the strongest signal
    return " ".join([m["name"], m["name"], m["title"], m["summary"], " ".join(m["keywords"])])


def bm25(docs: list[str], query: str) -> list[float]:
    counts = [Counter(tokenize(d)) for d in docs]
    lengths = [sum(c.values()) for c in counts]
    avg = sum(lengths) / len(lengths)
    df = Counter(t for c in counts for t in c)
    n = len(docs)
    terms = set(tokenize(query))
    scores = []
    for c, length in zip(counts, lengths, strict=True):
        score = 0.0
        for t in terms:
            if f := c.get(t):
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * length / avg))
        scores.append(score)
    return scores


def load_meta() -> dict:
    return json.loads((DATA / "meta.json").read_text())


def load_modules(version: str) -> list[dict]:
    rows = [json.loads(line) for line in (DATA / "oca_modules.jsonl").read_text().splitlines()]
    if version == "all":
        return rows
    if version not in load_meta()["versions"]:
        raise SystemExit(f"{version} isn't in the data; available: {load_meta()['versions']}")
    return [m for m in rows if version in m["versions"]]


def live_pending(meta: dict) -> tuple[dict[str, list[dict]] | None, str | None]:
    """Current migration PRs from the published file, or (None, None) if unreachable."""
    url = meta.get("migrations_url")
    if not url:
        return None, None
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            lines = response.read().decode().splitlines()
    except OSError:
        return None, None
    header, *rows = [json.loads(line) for line in lines if line]
    pending: dict[str, list[dict]] = {}
    for row in rows:
        if row["kind"] == "migration":
            pending.setdefault(row["module"], []).append(row)
    return pending, header.get("scanned_at")


def link(m: dict) -> str:
    return f"https://github.com/OCA/{m['repo']}/tree/{m['versions'][-1]}/{m['name']}"


def describe_pending(prs: list[dict]) -> str:
    parts = []
    for p in prs:
        state = ", ".join(
            s for s in [
                "draft" if p["draft"] else "",
                {"APPROVED": "approved", "CHANGES_REQUESTED": "changes requested"}.get(
                    p["review"] or "", "not yet reviewed"
                ),
                f"CI {p['ci'].lower()}" if p["ci"] else "",
                f"updated {p['updated']}",
            ] if s
        )
        parts.append(f"  {p['version']}: PR #{p['pr']} ({state}) {p['url']}")
    return "\n".join(parts)


def cmd_info(args) -> None:
    meta = load_meta()
    print(f"Versions: {', '.join(meta['versions'])}\nModules: {meta['modules']}")
    print(f"Data built: {meta['built'][:10]}; migrations scanned: {meta['migrations_scanned']}")


def cmd_search(args) -> None:
    modules = load_modules(args.version)
    scores = bm25([document(m) for m in modules], args.query)
    for i in sorted(range(len(modules)), key=lambda i: -scores[i])[: args.limit]:
        if scores[i] > 0:
            m = modules[i]
            versions = ",".join(v.removesuffix(".0") for v in m["versions"])
            print(f"{scores[i]:5.1f}  {m['name']} ({m['repo']}; {versions}): {m['summary']}")


def cmd_show(args) -> None:
    meta = load_meta()
    by_name = {m["name"]: m for m in load_modules("all")}
    pending, scanned = live_pending(meta)
    if pending is None:
        scanned = f"{meta['migrations_scanned'][:10]} (bundled copy)"
    for name in args.modules:
        m = by_name.get(name)
        if m is None:
            print(f"{name}: not found in any version\n")
            continue
        print(f"{m['name']} ({m['repo']}): {m['title']}")
        print(f"Versions: {', '.join(m['versions'])}\n{link(m)}")
        print(f"{m['summary']}\nKeywords: {', '.join(m['keywords'])}")
        prs = (pending or {}).get(name, []) if pending is not None else m.get("pending", [])
        if prs:
            print(f"Open migration PRs (as of {scanned}):\n{describe_pending(prs)}")
        print()


def cmd_repo(args) -> None:
    for m in sorted(load_modules(args.version), key=lambda m: m["name"]):
        if m["repo"] == args.repo:
            print(f"{m['name']}: {m['summary'].split('. ')[0]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info").set_defaults(func=cmd_info)
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--version", default="all")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("show")
    p.add_argument("modules", nargs="+")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("repo")
    p.add_argument("repo")
    p.add_argument("--version", default="all")
    p.set_defaults(func=cmd_repo)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
