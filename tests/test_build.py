from oca_index.build import build_records
from oca_index.summaries import summary_key


def row(name, version, description="Does X.", repo="sale-workflow"):
    return {
        "name": name,
        "version": version,
        "repo": repo,
        "title": name.title(),
        "summary": None,
        "description": description,
    }


def cached(r, summary):
    key = summary_key(r["name"], r["title"], r["summary"], r["description"])
    return key, {"key": key, "name": r["name"], "summary": summary, "keywords": ["k"]}


def test_build_records_merges_versions_and_attaches_migrations():
    old = row("sale_mrp_bom", "17.0", description="Old text.")
    new = row("sale_mrp_bom", "18.0", description="New text.")
    other = row("sale_readonly", "18.0")
    summaries = dict([cached(old, "old summary"), cached(new, "new summary")])
    pending = [
        {
            "module": "sale_mrp_bom",
            "version": "19.0",
            "kind": "migration",
            "pr": 4107,
            "url": "u",
            "draft": False,
            "review": None,
            "ci": "FAILURE",
            "updated": "2026-10-12",
        },
        {
            "module": "sale_brand_new",
            "version": "19.0",
            "kind": "new",
            "pr": 4636,
            "url": "u",
            "draft": False,
            "review": None,
            "ci": None,
            "updated": "2026-10-13",
        },
    ]
    records, unsummarized = build_records([new, old, other], summaries, pending)

    assert unsummarized == ["sale_readonly"]
    (record,) = records
    assert record["versions"] == ["17.0", "18.0"]
    assert record["summary"] == "new summary"
    assert [p["pr"] for p in record["pending"]] == [4107]


def test_build_records_falls_back_to_older_summary():
    old = row("auditlog", "17.0", description="Old text.")
    new = row("auditlog", "18.0", description="Changed text, not summarized yet.")
    records, _ = build_records([old, new], dict([cached(old, "old summary")]), [])
    assert records[0]["summary"] == "old summary"
