---
name: oca-module-search
description: Find OCA (Odoo Community Association) modules that provide a feature, using plain-language summaries of OCA modules, and check whether a module is being migrated to a version. Use when someone asks whether an OCA module exists for some functionality, wants OCA alternatives to custom development, asks which OCA module does X, or asks about an OCA module's migration status.
---

# OCA module search

Find OCA modules that provide the functionality the user describes. Run
`scripts/search.py` from this skill's folder; it searches a summary of every OCA module
(what it does for a user, plus search phrases) across the Odoo versions listed by
`python3 scripts/search.py info`.

This is a lookup. Answer the question and stop: don't ask about hosting or setup, and don't
offer to build, install or configure anything.

## 1. Pick the version

Use the version the user names ("on 17", "18.0"). If they name none, search `--version all`
and say which versions each module exists in.

## 2. Gather candidates several ways

Search is keyword-based, so word choice matters and the first query is rarely enough:

- Write 3 or 4 rephrasings of the need, at least two in Odoo/OCA vocabulary. Common gaps:
  "credit limit" is "financial risk"; "approval" is often "tier validation";
  "customer"/"vendor" are "partner"; "delivery"/"receipt" are "picking"; "salesperson" is
  "user" or "sales team"; "bundle" is "pack"; "subscription" is often "contract".
- Also try 1 or 2 short keyword-only queries.
- For each: `python3 scripts/search.py search "<query>" --version <version>`
- If a result's repo looks like the right area, `python3 scripts/search.py repo <repo>
  --version <version>` lists that repo's modules in one line each.
- If there's no strong match in the user's version, always also search `--version all`
  (even when you have partial matches): the module may exist in another version, and `show`
  tells whether a migration is open.

## 3. Read the candidates

`python3 scripts/search.py show <module> [<module> ...]` prints the full summary, versions,
GitHub link and any open migration PRs. Read the most plausible candidates. Some features come
from a pair (a base module plus a glue module, e.g. `base_tier_validation` +
`purchase_tier_validation`); report the pair.

## 4. Decide, then answer

Judge each candidate against what the user actually asked:

- **strong**: it does what was asked, in the user's version.
- **partial**: it covers part of it, or does something close but different, or exists only
  in another version.
- Anything else is not a match: leave it out.

If there are strong matches, list them (at most 3), best first. If there are none, say plainly
"No OCA module does this" (for that version), then at most 2 partial matches with what's
missing. Don't pad the answer with weak candidates.

Format per module:

**<module>** (<repo>, <versions>): strong | partial
<1 or 2 sentences: what it does, from its summary>
Fit: <how it covers the need; what it doesn't>
Migration: <only if it isn't in the user's version: the open PR and its state, or "no
migration PR open">
Link: <GitHub link from show>

Keep it under 250 words and don't describe the search process. The summaries were generated
from each module's readme and code outline, so they can miss details: say once that the
GitHub link is the place to confirm.
