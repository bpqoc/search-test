# Search eval: skill search vs reading the whole catalog

Run 2026-10-15 on the full 16.0 to 19.0 data (4,000 modules), Haiku driving both arms.

- `cases.toml`: 43 requests. 28 where a module does it in the asked version, 7 where one exists
  only in another version, 8 where no OCA module does it (checked by keyword and embedding
  search over the full index; one case first written as absent turned out to exist in 16.0 and
  was moved).
- Search arm: the `oca-module-search` skill as shipped (keyword search, `show`, `repo`).
- Catalog arm: the agent reads a one-line-per-module catalog of everything (about 152k tokens),
  then may `show` candidates.
- Four mixed shards per arm; answers in `answers/`, graded by `grade.py`.

| | Search (skill) | Read whole catalog |
|---|---|---|
| Exists, found as strong match | 27 / 28 | 27 / 28 |
| Exists, rated only partial | 1 / 28 | 1 / 28 |
| Exists elsewhere, pointed to it | 6 / 7 | 7 / 7 |
| Exists elsewhere, just said no | 1 / 7 | 0 / 7 |
| Doesn't exist, said so | 8 / 8 | 8 / 8 |
| Doesn't exist, claimed a match | 0 / 8 | 0 / 8 |
| Tokens per agent (10 to 11 cases) | 106k to 131k | 274k to 278k |

- The miss shared by both is a judgement call: `hotel_restaurant` books restaurant tables, but
  inside the hotel app, so both rated it partial.
- Search's other miss (order minimums on 19.0) stopped at partial matches without checking
  other versions; SKILL.md now always checks `--version all` when nothing is strong.
- Cost per question, not per agent: the catalog is re-read for every question (about 152k
  tokens) while search spends about 11k, so search is about 15 times cheaper for the same
  accuracy.
