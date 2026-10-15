"""Keyword (BM25) search over a JSONL module file, standard library only.

This is the search a Claude Desktop skill could ship next to an uploaded summaries file: the
skill sandbox has no network and no embedding model, but plain Python works.

Usage:
    python bm25.py <modules.jsonl> "<query>" [--limit 30]
"""

import argparse
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence

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
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in words if w not in STOPWORDS]


class Bm25:
    def __init__(self, docs: Sequence[str]):
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = set(tokenize(query))
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            for t in terms:
                if f := doc.get(t):
                    score += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * length / self.avg))
            out.append(score)
        return out


def summary_doc(m: Mapping) -> str:
    """Text indexed per module: the name and title count twice, they're the strongest signal."""
    name = m["name"]
    return " ".join([name, name, m.get("title", ""), m["summary"], " ".join(m["keywords"])])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    modules = [json.loads(line) for line in open(args.file)]
    scores = Bm25([summary_doc(m) for m in modules]).scores(args.query)
    for i in sorted(range(len(modules)), key=lambda i: -scores[i])[: args.limit]:
        print(f"{scores[i]:6.2f}  {modules[i]['name']}: {modules[i]['summary']}")


if __name__ == "__main__":
    main()
