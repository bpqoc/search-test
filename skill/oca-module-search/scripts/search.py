"""Keyword (BM25) search over this skill's OCA module summaries. Standard library only.

Usage:
    python3 search.py <version> "<query>" [--limit 30]
    python3 search.py <version> --show <module> [<module> ...]
    python3 search.py --versions
"""

import argparse
import json
import math
import re
import sys
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
    scores = []
    for c, length in zip(counts, lengths, strict=True):
        score = 0.0
        for t in set(tokenize(query)):
            if f := c.get(t):
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * length / avg))
        scores.append(score)
    return scores


def load(version: str) -> list[dict]:
    path = DATA / f"oca_{version}.jsonl"
    if not path.exists():
        sys.exit(f"No data for {version}. Available: {', '.join(available())}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def available() -> list[str]:
    return sorted(p.stem.removeprefix("oca_") for p in DATA.glob("oca_*.jsonl"))


def link(m: dict, version: str) -> str:
    return f"https://github.com/OCA/{m['repo']}/tree/{version}/{m['name']}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--show", nargs="+", metavar="MODULE")
    parser.add_argument("--versions", action="store_true")
    args = parser.parse_args()

    if args.versions or not args.version:
        print("\n".join(available()))
        return
    modules = load(args.version)
    if args.show:
        by_name = {m["name"]: m for m in modules}
        for name in args.show:
            m = by_name.get(name)
            if m is None:
                print(f"{name}: not in {args.version}\n")
                continue
            print(f"{m['name']} ({m['repo']}): {m['title']}\n{link(m, args.version)}")
            print(f"{m['summary']}\nKeywords: {', '.join(m['keywords'])}\n")
        return
    scores = bm25([document(m) for m in modules], args.query or "")
    for i in sorted(range(len(modules)), key=lambda i: -scores[i])[: args.limit]:
        if scores[i] > 0:
            m = modules[i]
            print(f"{scores[i]:5.1f}  {m['name']} ({m['repo']}): {m['summary']}")


if __name__ == "__main__":
    main()
