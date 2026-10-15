---
name: update-oca-index
description: Refresh the OCA module search data and rebuild the oca-module-search skill zip. Use when asked to update, refresh or rebuild the OCA index, summaries or skill.
---

# Update the OCA index

1. Run `uv run oca-index update` (timeout 15 minutes). If it finishes with a zip, skip to 4.
2. If it stops because modules need summaries:
   - `uv run oca-index agent-prompts` prints one prompt per batch in `work/pending/`.
   - Start one subagent per batch with `model: haiku`, passing its prompt unchanged, in the
     background. Run at most 10 at a time and start the next as each finishes.
   - When all are done, run `uv run oca-index ingest`. It lists any batch with problems
     (missing or malformed lines) and keeps that batch pending: rerun a subagent for just that
     batch, then ingest again.
3. Run `uv run oca-index update` again. It should now build the zip.
4. Report: modules in the zip, summaries added, migration PRs found, any failures. Then
   remind the user to commit and push `data/` and to upload
   `skill/dist/oca-module-search.zip` in Claude. Don't commit or push without being asked.
