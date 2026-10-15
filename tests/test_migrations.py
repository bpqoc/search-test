from oca_index.migrations import pending_records, pr_modules


def pr(number, files, title="[19.0][MIG] x"):
    """A PR node shaped like the GraphQL QUERY's output."""
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/OCA/sale-workflow/pull/{number}",
        "isDraft": False,
        "updatedAt": "2026-10-13T08:00:00Z",
        "reviewDecision": "APPROVED",
        "author": {"login": "someone"},
        "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "FAILURE"}}}]},
        "files": {"nodes": [{"path": p, "changeType": c} for p, c in files]},
    }


def test_pr_modules_only_new_module_folders():
    files = [
        {"path": "sale_mrp_bom/__manifest__.py", "changeType": "ADDED"},
        {"path": "sale_mrp_bom/models/sale.py", "changeType": "ADDED"},
        {"path": "sale_order_line_remove/models/x.py", "changeType": "ADDED"},  # already there
        {"path": "setup/sale_mrp_bom/setup.py", "changeType": "ADDED"},
        {"path": ".github/workflows/test.yml", "changeType": "ADDED"},
        {"path": "requirements.txt", "changeType": "ADDED"},
        {"path": "sale_other/__init__.py", "changeType": "MODIFIED"},
    ]
    assert pr_modules(files, existing={"sale_order_line_remove"}) == ["sale_mrp_bom"]


def test_pending_records_classifies_migration_vs_new():
    prs = [
        # Title without version or [MIG]: the base branch and files decide
        pr(4213, [("sale_mrp_bom/__manifest__.py", "ADDED")], title="mig sale mrp bom"),
        pr(4636, [("sale_readonly/__manifest__.py", "ADDED")], title="[19.0][ADD] sale_readonly"),
    ]
    records = pending_records(
        "sale-workflow", "19.0", prs, existing=set(), known_elsewhere={"sale_mrp_bom"}
    )
    assert [(r["module"], r["kind"], r["pr"], r["ci"]) for r in records] == [
        ("sale_mrp_bom", "migration", 4213, "FAILURE"),
        ("sale_readonly", "new", 4636, "FAILURE"),
    ]
