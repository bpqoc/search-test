import pytest

from oca_index.plan import (
    Action,
    BranchStep,
    ModuleIndexPlan,
    module_trees,
    plan_module_index,
    plan_sync,
)

TRACKED = ("17.0", "18.0")
SHA_A = "46ab77bf78b79f963ef5163530f23c88661e787b"
SHA_B = "91fed54d404eac384a0186fdf541d0e354a4171f"


@pytest.mark.parametrize(
    ("stored", "remote", "kwargs", "expected"),
    [
        pytest.param(
            {},
            {"sale-workflow": {"18.0": SHA_A}},
            {},
            [("sale-workflow", "18.0", Action.NEW)],
            id="first-sync",
        ),
        pytest.param(
            {("sale-workflow", "18.0"): SHA_A},
            {"sale-workflow": {"18.0": SHA_B}},
            {},
            [("sale-workflow", "18.0", Action.CHANGED)],
            id="head-moved",
        ),
        pytest.param(
            {("sale-workflow", "18.0"): SHA_A},
            {"sale-workflow": {"18.0": SHA_A}},
            {},
            [("sale-workflow", "18.0", Action.UNCHANGED)],
            id="head-same",
        ),
        pytest.param(
            {("sale-workflow", "18.0"): SHA_A},
            {"sale-workflow": {"18.0": SHA_A}},
            {"full": True},
            [("sale-workflow", "18.0", Action.CHANGED)],
            id="full-forces-checkout",
        ),
        pytest.param(
            {("sale-workflow", "17.0"): SHA_A},
            {"sale-workflow": {"18.0": SHA_B}},
            {},
            [("sale-workflow", "17.0", Action.GONE), ("sale-workflow", "18.0", Action.NEW)],
            id="branch-deleted-upstream",
        ),
        pytest.param(
            {("old-repo", "18.0"): SHA_A},
            {"old-repo": {}},
            {},
            [("old-repo", "18.0", Action.GONE)],
            id="repo-vanished",
        ),
        pytest.param(
            {("sale-workflow", "16.0"): SHA_A, ("sale-workflow", "18.0"): SHA_B},
            {"sale-workflow": {"18.0": SHA_B}},
            {},
            [("sale-workflow", "16.0", Action.DROP), ("sale-workflow", "18.0", Action.UNCHANGED)],
            id="version-untracked",
        ),
        pytest.param(
            {("sale-workflow", "16.0"): SHA_A, ("sale-workflow", "17.0"): SHA_A},
            {"sale-workflow": {"17.0": SHA_B, "18.0": SHA_B}},
            {"only_versions": ["18.0"]},
            [("sale-workflow", "18.0", Action.NEW)],
            id="partial-run-never-drops-or-touches-others",
        ),
        pytest.param(
            {},
            {"maintainer-tools": {}},
            {},
            [],
            id="repo-without-tracked-branches",
        ),
    ],
)
def test_plan_sync(stored, remote, kwargs, expected):
    steps = plan_sync(TRACKED, stored, remote, **kwargs)
    assert steps == [BranchStep(*e) for e in expected]


TREE_SALE_ORDER_TYPE = "6b0f6bb78bf7244b6bf29452956b88d3294a9975"
TREE_BLANKET = "9f1598a3ac13c62d43d09fc85e2287e2824a26fa"
BLOB = "1bfb38839921ecebc2bd6e1b98c5b49e9c4885c6"


def test_module_trees_keeps_only_directories_with_a_manifest():
    # Shape of `git ls-tree -r -t` on an OCA 16.0 branch.
    listing = [
        f"040000 tree {BLOB}\t.github",
        f"100644 blob {BLOB}\t.github/workflows/test.yml",
        f"100644 blob {BLOB}\tREADME.md",
        f"100644 blob {BLOB}\tpandoc-3.5-1-amd64.deb",
        f"040000 tree {BLOB}\tsetup",
        f"040000 tree {BLOB}\tsetup/sale_order_type",
        f"100644 blob {BLOB}\tsetup/sale_order_type/setup.py",
        f"040000 tree {TREE_SALE_ORDER_TYPE}\tsale_order_type",
        f"100644 blob {BLOB}\tsale_order_type/__init__.py",
        f"100644 blob {BLOB}\tsale_order_type/__manifest__.py",
        f"040000 tree {BLOB}\tsale_order_type/tests",
        f"100644 blob {BLOB}\tsale_order_type/tests/data/__manifest__.py",
        f"040000 tree {TREE_BLANKET}\tsale_blanket_order",
        f"100644 blob {BLOB}\tsale_blanket_order/__manifest__.py",
    ]
    assert module_trees(listing) == {
        "sale_blanket_order": TREE_BLANKET,
        "sale_order_type": TREE_SALE_ORDER_TYPE,
    }


@pytest.mark.parametrize(
    ("current", "stored", "force", "parse", "delete"),
    [
        pytest.param({"a": SHA_A}, {}, False, ["a"], [], id="new-module"),
        pytest.param({"a": SHA_B}, {"a": SHA_A}, False, ["a"], [], id="module-changed"),
        pytest.param({"a": SHA_A}, {"a": SHA_A}, False, [], [], id="module-unchanged"),
        pytest.param({"a": SHA_A}, {"a": SHA_A}, True, ["a"], [], id="forced"),
        pytest.param({}, {"a": SHA_A}, False, [], ["a"], id="module-removed-or-excluded"),
    ],
)
def test_plan_module_index(current, stored, force, parse, delete):
    assert plan_module_index(current, stored, force) == ModuleIndexPlan(parse, delete)
