import pytest

from oca_index.summaries import (
    MODULE_MARK,
    ModuleText,
    batch_keys,
    check_results,
    module_block,
    select_pending,
    summary_key,
)

MODULE = {
    "name": "sale_financial_risk",
    "repo": "credit-control",
    "title": "Sale Financial Risk",
    "category": "Sales",
    "summary": "Manage partner risk in sales orders",
    "description": "Extends partner risk to sale orders.\n\n### Notes\nA heading in the readme.",
    "usage": None,
    "configure": None,
}


def test_summary_key_ignores_version_but_not_text():
    key = summary_key("m", "T", "s", "d")
    assert key == summary_key("m", "T", "s", "d")
    assert key != summary_key("m", "T", "s", "d changed")


def test_select_pending_skips_cached_and_keeps_newest_version():
    modules = [
        ModuleText("k1", "a", "16.0", "a 16"),
        ModuleText("k1", "a", "18.0", "a 18"),
        ModuleText("k1", "a", "17.0", "a 17"),
        ModuleText("k2", "b", "18.0", "b 18"),
    ]
    assert select_pending(modules, cached={"k2"}) == [ModuleText("k1", "a", "18.0", "a 18")]


def test_batch_keys_ignores_readme_headings():
    text = "\n\n".join(
        [
            module_block(MODULE, ["account_financial_risk"], [], "abc123"),
            module_block(
                {**MODULE, "name": "other"}, [], ["- inherit sale.order: x (Char)"], "def456"
            ),
        ]
    )
    assert batch_keys(text) == {"abc123": "sale_financial_risk", "def456": "other"}
    assert text.count(MODULE_MARK) == 2


@pytest.mark.parametrize(
    ("rows", "accepted", "problems"),
    [
        pytest.param(
            [{"key": "k1", "name": "a", "summary": "S", "keywords": ["x"]}],
            1,
            1,
            id="missing-module",
        ),
        pytest.param(
            [
                {"key": "k1", "name": "a", "summary": "S", "keywords": ["x"]},
                {"key": "k2", "name": "b", "summary": "S", "keywords": ["y"]},
                {"key": "zz", "name": "Readme Heading", "summary": "S", "keywords": ["y"]},
            ],
            2,
            1,
            id="stray-entry",
        ),
        pytest.param(
            [
                {"key": "k1", "name": "a", "summary": "", "keywords": ["x"]},
                {"key": "k2", "name": "b", "summary": "S", "keywords": ["y"]},
            ],
            1,
            2,
            id="empty-summary",
        ),
    ],
)
def test_check_results(rows, accepted, problems):
    ok, issues = check_results(rows, {"k1": "a", "k2": "b"})
    assert (len(ok), len(issues)) == (accepted, problems)
