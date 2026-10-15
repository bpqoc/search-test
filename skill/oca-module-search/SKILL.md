---
name: oca-module-search
description: Find OCA (Odoo Community Association) modules that provide a feature, using plain-language summaries of OCA modules. Use when someone asks whether an OCA module exists for some functionality, wants OCA alternatives to custom development, or asks which OCA module does X.
---

# OCA module search

Find OCA modules that provide the functionality the user describes. The data is a summary of
each module (what it does for a user, plus search phrases), searched with
`scripts/search.py` in this skill's folder. Run commands from this skill's folder.

**Pilot data:** this version only covers part of Odoo 18.0 (29 OCA repos, 1,356 modules).
Mention that in your answer, so "nothing found" isn't read as "nothing exists in OCA".

## 1. Pick the version

Use the version the user names ("on 17", "18.0"). `python3 scripts/search.py --versions`
lists what's available. If they name none, use the only available one and say which.

## 2. Gather candidates several ways

Search is keyword-based, so word choice matters and the first query is rarely enough:

- Write 3 or 4 rephrasings of the need, at least two in Odoo/OCA vocabulary. Common gaps:
  "credit limit" is "financial risk"; "approval" is often "tier validation";
  "customer"/"vendor" are "partner"; "delivery"/"receipt" are "picking"; "salesperson" is
  "user" or "sales team"; "bundle" is "pack"; "subscription" is often "contract".
- Also try 1 or 2 short keyword-only queries.
- For each: `python3 scripts/search.py <version> "<query>"`
- Collect the distinct modules that look plausible.

## 3. Read the candidates

`python3 scripts/search.py <version> --show <module> [<module> ...]` prints the full summary,
keywords and GitHub link for each. Read the 8 to 12 most plausible. Some features come from a
pair (a base module plus a glue module, e.g. `base_tier_validation` +
`purchase_tier_validation`); report the pair.

## 4. Answer

At most 5 modules, best first:

**<module>** (<repo>): strong | partial match
<1 or 2 sentences: what it does, from its summary>
Fit: <how it covers the need; what it doesn't cover>
Link: <GitHub link from --show>

Then one line "Also looked at: <names>" for rejected candidates. If nothing fits, say so
plainly and name the closest options and what's missing. Keep it under 300 words and don't
describe the search process.

The summaries were generated from each module's readme and code outline, so they can miss
details: suggest checking the GitHub link before relying on a module. Describe what modules
do; don't give installation or configuration steps unless asked.
