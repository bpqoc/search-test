"""Embedding search over the pool's Haiku summaries (the local-database arm of the comparison).

Usage:
    uv run --project ~/stuff/oca/oca-reference python experiment/emb_search.py "<query>" [--limit 30]
"""

import argparse
import json
from pathlib import Path

import numpy as np
from oca_reference import db
from oca_reference.config import data_home, load_config
from oca_reference.embed import Embedder, hub_prior
from oca_reference.sync import Paths

WORK = Path(__file__).parent / "work"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    home = data_home()
    config, paths = load_config(home), Paths(home)
    names = json.loads((WORK / "summary_vectors_names.json").read_text())
    vectors = np.load(WORK / "summary_vectors.npy")
    summaries = {}
    for path in (WORK / "summaries").glob("*.jsonl"):
        for line in path.read_text().splitlines():
            s = json.loads(line)
            summaries[s["name"]] = s
    dependents = db.dependent_counts(db.connect(paths.db, readonly=True), "18.0")
    prior = hub_prior([dependents.get(("18.0", n), 0) for n in names])
    scores = vectors @ Embedder(config.embed_model, paths.models).query(args.query) + prior
    for i in np.argsort(-scores)[: args.limit]:
        print(f"{scores[i]:.3f}  {names[i]}: {summaries[names[i]]['summary']}")


if __name__ == "__main__":
    main()
