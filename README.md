# doofus

searching stuff for Odoo and related things

## OCA module search

Builds the data behind the `oca-module-search` Claude skill: a plain-language summary of every
OCA module for the configured Odoo versions, plus open migration pull requests, searched by a
small script inside the skill.

### Updating (about once a month)

Needs [uv](https://docs.astral.sh/uv/), git, and the GitHub CLI signed in (`gh auth login`).

1. Edit `oca-index.toml` if the versions or included repos/modules should change.
2. Open Claude Code in this folder and say **"update the OCA index"**. It runs
   `uv run oca-index update`, summarizes any new or changed modules with Haiku subagents, and
   builds `skill/dist/oca-module-search.zip`.
   - With an `ANTHROPIC_API_KEY` set, `uv run oca-index update` does the summaries itself
     through the Batch API (a few dollars for a full rebuild, cents for a monthly update), so
     Claude Code isn't needed.
3. Commit and push `data/`. The skill downloads `data/migrations.jsonl` from GitHub when it
   runs, so pushing alone refreshes migration status for everyone.
4. Upload the new zip in Claude: Customize > Skills > oca-module-search > replace (or, for an
   org skill, publish the new version).

A first run fetches all of OCA (about 3 GB in `data_dir`, 3 to 5 minutes). Later runs only fetch
and summarize what changed.

### Commands

`uv run oca-index <command>`:

| Command | What it does |
|---|---|
| `update` | All steps below in order; stops if summaries are needed and there's no API key |
| `sync` | Fetch OCA and parse modules into the local index |
| `prepare` | Write `work/pending/` batch files for modules without a summary |
| `summarize` | Summarize pending batches with the Batch API (needs `ANTHROPIC_API_KEY`) |
| `agent-prompts` | Print one Claude Code subagent prompt per pending batch |
| `ingest` | Check finished `work/results/` and add them to `data/summaries.jsonl` |
| `migrations` | Scan open OCA PRs for modules being migrated to a tracked version |
| `build` | Write the skill data and `skill/dist/oca-module-search.zip` |

### Technical

- Summaries are keyed by a hash of the module's name, title and readme text, so a module that
  didn't change (or is identical across versions) is never summarized twice.
- Migration PRs are found by the module folders a PR adds on its target branch, not by title:
  titles are inconsistent ("mig sale rental", missing version tags).
- Fetching (blobless clones with sparse worktrees of module folders only) and parsing
  (manifest, readme, models and fields via `ast`) came from the oca-reference prototype,
  without its embedding search.
- `experiment/` and `eval/` hold the search comparisons that led to this design. The
  `experiment/` scripts still need the oca-reference prototype, for its embeddings.

### Known Issues

- The Batch API path (`summarize`) hasn't been run yet; every summary so far came from Claude
  Code subagents.
- New modules that only exist in an open PR aren't searchable, since there's no summary for
  them; their PRs are still recorded in `data/migrations.jsonl`.
