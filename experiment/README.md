# Summary file vs local embeddings: OCA search experiment

Question: is an uploaded summary file, searched by a plain-Python script inside a Claude
Desktop skill, good enough, or does a local database with embeddings search noticeably better?

Run 2026-10-15 against the oca-reference index (`~/stuff/oca/oca-reference`).

## Setup

- **Pool:** every installable 18.0 module in the 29 OCA repos that hold a benchmark answer,
  1,356 modules (half of 18.0). Neighbours of each answer (other sale-workflow modules, etc.)
  stay in as distractors. Both approaches rank the same pool.
- **Cases:** the 35 18.0 cases of oca-reference's benchmark (`research/benchmark_cases.toml`),
  requests phrased the way a non-technical user asks.
- **Summaries:** `prepare.py` writes one input block per module (manifest, cleaned readme,
  models and fields it adds). Ten Haiku subagents turned them into `{name, summary, keywords}`
  JSONL (2 to 3 plain-language sentences plus 8 to 15 search phrases).
- **Arms:** `compare.py` scores single-query retrieval. `bm25.py` is the stdlib-only keyword
  search a skill could ship; `emb_search.py` is the embedding equivalent (arctic-embed-m, local).

## Results

### Single query, rank of the expected module (35 cases)

| Arm | hit@1 | hit@5 | hit@10 | hit@30 | MRR |
|---|---|---|---|---|---|
| Embeddings of readme (current prototype) | 0.63 | 0.80 | 0.89 | 0.94 | 0.71 |
| Keyword search over readme | 0.29 | 0.37 | 0.57 | 0.71 | 0.36 |
| **Keyword search over Haiku summaries (the file)** | 0.57 | 0.83 | 0.89 | **1.00** | 0.69 |
| Embeddings of Haiku summaries | 0.74 | 0.91 | 0.97 | 1.00 | 0.81 |
| Fusion of the two summary arms | 0.69 | 0.91 | 1.00 | 1.00 | 0.80 |

- Summaries are what make the file approach work: keyword MRR goes from 0.36 to 0.69, level
  with the current embedding prototype, and every answer is in the top 30.
- Embeddings over the same summaries rank better on a single query (MRR 0.81).

### End to end, simulating the skill (9 hardest cases)

A Haiku agent per arm got the 9 cases where single-query keyword search ranked the answer
lowest (5th to 18th). Each rephrased every request 3 or 4 ways, searched, read the summaries,
and picked up to 3 modules.

| | Answer 1st | Answer in top 3 | Searches run |
|---|---|---|---|
| Summary file + keyword search | 8 / 9 | 9 / 9 | 31 |
| Summary embeddings | 8 / 9 | 9 / 9 | 36 |

Both picked nearly the same modules; the one non-first pick in both is `contract` behind
`subscription_oca`, which is a reasonable answer to that request too. The ranking advantage
of embeddings disappears once the agent rephrases and reads candidates.

### Size and speed

- Summary file: 697 KB for 1,356 modules (about 0.5 KB each), so about 1.4 MB per version
  and about 4.3 MB for 16.0 to 19.0. A keyword search over it takes 0.06 s.
- Embedding arm: 4.2 MB of vectors for the pool, plus the 0.43 GB model and fastembed on every
  user's machine to embed the query.
- Haiku summarization took about 1.5M subagent tokens for 1,356 modules (about 1.1k each, with
  overhead).

## Caveats

- One version, half its modules, 35 cases, one run per arm (no variance measured).
- The summarization prompt used "credit limit"/"financial risk" and "approval"/"tier
  validation" as keyword examples, which matches 2 benchmark cases. They still ranked 18th and
  5th on a single keyword query, and the module readmes use those words too.
- No "nothing in OCA does this" cases, so false positives aren't measured.
- Haiku drove the end-to-end runs; a Desktop user's Sonnet or Opus should do at least as well.

## Rerun

```
uv run --project ~/stuff/oca/oca-reference python experiment/prepare.py
# summarize work/batches/*.md into work/summaries/*.jsonl (Haiku subagents or the Batch API)
uv run --project ~/stuff/oca/oca-reference python experiment/compare.py --show-misses
```
