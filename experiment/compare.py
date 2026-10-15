"""Compare retrieval on the 18.0 benchmark pool: uploaded-file keyword search vs local embeddings.

Every arm ranks the same pool (see prepare.py) for the 18.0 benchmark cases, and is scored by
the rank of the first expected module, like oca_reference.benchmark.

Usage (after the summaries exist in work/summaries/):
    uv run --project ~/stuff/oca/oca-reference python experiment/compare.py [--show-misses]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from oca_reference import db
from oca_reference.benchmark import first_rank, load_cases, summarize
from oca_reference.config import data_home, load_config
from oca_reference.embed import Embedder, hub_prior
from oca_reference.parse import clean_markup
from oca_reference.sync import Paths

sys.path.insert(0, str(Path(__file__).parent))
from bm25 import Bm25, summary_doc  # noqa: E402

VERSION = "18.0"
BENCHMARK = Path.home() / "stuff/oca/oca-reference/research/benchmark_cases.toml"
WORK = Path(__file__).parent / "work"
DEPTH = 50
RRF_K = 60


def readme_doc(row) -> str:
    parts = [row["name"], row["name"], row["title"], row["summary"]]
    parts += [clean_markup(row[k]) for k in ("description", "usage", "configure") if row[k]]
    return " ".join(p for p in parts if p)


def summary_embed_text(row, summary: dict) -> str:
    return f"{row['title']} ({row['name']})\n{summary['summary']}\n{', '.join(summary['keywords'])}"


def top(scores: np.ndarray, names: list[str]) -> list[str]:
    return [names[i] for i in np.argsort(-scores)[:DEPTH]]


def rrf(*rankings: list[str]) -> list[str]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for i, name in enumerate(ranking):
            fused[name] = fused.get(name, 0) + 1 / (RRF_K + i + 1)
    return sorted(fused, key=lambda n: -fused[n])[:DEPTH]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()

    home = data_home()
    config, paths = load_config(home), Paths(home)
    conn = db.connect(paths.db, readonly=True)
    pool = set(json.loads((WORK / "pool.json").read_text()))
    summaries = {}
    for path in sorted((WORK / "summaries").glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                s = json.loads(line)
                summaries[s["name"]] = s
    missing = pool - summaries.keys()
    if missing:
        print(f"WARNING: {len(missing)} pool modules have no summary, e.g. {sorted(missing)[:5]}")

    rows, vectors = db.embedded_modules(conn, VERSION)
    keep = [i for i, r in enumerate(rows) if r["name"] in pool and r["name"] in summaries]
    rows, readme_vectors = [rows[i] for i in keep], vectors[keep]
    names = [r["name"] for r in rows]
    dependents = db.dependent_counts(conn, VERSION)
    prior = hub_prior([dependents.get((VERSION, n), 0) for n in names])

    embedder = Embedder(config.embed_model, paths.models)
    cache = WORK / "summary_vectors.npy"
    texts = [summary_embed_text(r, summaries[r["name"]]) for r in rows]
    if cache.exists() and np.load(cache).shape[0] == len(texts):
        summary_vectors = np.load(cache)
    else:
        print(f"embedding {len(texts)} summaries with {config.embed_model}...", flush=True)
        summary_vectors = np.stack(embedder.passages(texts))
        np.save(cache, summary_vectors)
    (WORK / "summary_vectors_names.json").write_text(json.dumps(names))

    full = {r["id"]: r for r in conn.execute("SELECT * FROM module WHERE version = ?", (VERSION,))}
    bm25_readme = Bm25([readme_doc(full[r["id"]]) for r in rows])
    bm25_summary = Bm25([summary_doc({**summaries[r["name"]], "title": r["title"]}) for r in rows])

    cases = [c for c in load_cases(BENCHMARK) if c.version == VERSION]
    arms = [
        "emb_readme+hub (current)",
        "bm25_readme",
        "bm25_summary (file)",
        "emb_summary+hub",
        "rrf(bm25_summary, emb_summary+hub)",
    ]
    ranks: dict[str, list] = {a: [] for a in arms}
    for case in cases:
        q = embedder.query(case.query)
        e_readme = top(readme_vectors @ q + prior, names)
        b_readme = top(np.array(bm25_readme.scores(case.query)), names)
        b_summary = top(np.array(bm25_summary.scores(case.query)), names)
        e_summary = top(summary_vectors @ q + prior, names)
        fused = rrf(b_summary, e_summary)
        line = []
        for arm, ranking in zip(arms, [e_readme, b_readme, b_summary, e_summary, fused], strict=True):
            r = first_rank(ranking, case.expected)
            ranks[arm].append(r)
            line.append(f"{r or '-':>4}")
        print(" ".join(line), " ", case.query[:70])
        if args.show_misses and not first_rank(b_summary, case.expected):
            print(f"       expected {case.expected}; bm25_summary top: {b_summary[:3]}")

    print(f"\n{len(cases)} cases, pool {len(names)} modules\n")
    print(f"{'arm':40} " + " ".join(f"{k:>7}" for k in ("hit@1", "hit@5", "hit@10", "hit@30", "mrr")))
    for arm in arms:
        s = summarize(ranks[arm])
        print(f"{arm:40} " + " ".join(f"{v:7.2f}" for v in s.values()))
    (WORK / "compare_ranks.json").write_text(json.dumps({a: ranks[a] for a in arms}, indent=1))


if __name__ == "__main__":
    main()
