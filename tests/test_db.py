import pytest

from oca_index import db
from oca_index.parse import ModelTouch, ModuleInfo, TouchKind

TREE_1 = "6b0f6bb78bf7244b6bf29452956b88d3294a9975"
TREE_2 = "9f1598a3ac13c62d43d09fc85e2287e2824a26fa"


def _module(name, **kwargs):
    return ModuleInfo(name=name, title=name.replace("_", " ").title(), **kwargs)


SALE_ORDER_TYPE = _module(
    "sale_order_type",
    summary="Sales order types",
    readme={"description": "Adds a typology for the sales orders."},
    depends=["sale_stock"],
    models=[
        ModelTouch("sale.order.type", TouchKind.DEFINE, "Model", "Sale type", "models/x.py"),
        ModelTouch("sale.order", TouchKind.INHERIT, "Model", None, "models/x.py"),
    ],
)
CONFIRM_MESSAGE = _module(
    "sale_order_type_confirm_message",
    depends=["sale_order_type"],
    models=[ModelTouch("sale.order.type", TouchKind.INHERIT, "Model", None, "models/x.py")],
)


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "oca.sqlite")
    db.record_branches(conn, "sale-workflow", {"16.0": TREE_1, "18.0": TREE_1})
    db.write_branch_modules(conn, "sale-workflow", "16.0", [(TREE_1, SALE_ORDER_TYPE)], [])
    db.write_branch_modules(
        conn, "sale-workflow", "18.0", [(TREE_1, SALE_ORDER_TYPE), (TREE_1, CONFIRM_MESSAGE)], []
    )
    return conn


def _count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_reparse_replaces_and_delete_removes(conn):
    changed = _module("sale_order_type", summary="Changed")
    db.write_branch_modules(
        conn, "sale-workflow", "18.0", [(TREE_2, changed)], ["sale_order_type_confirm_message"]
    )
    assert db.module_shas(conn, "sale-workflow", "18.0") == {"sale_order_type": TREE_2}
    summary = conn.execute(
        "SELECT summary FROM module WHERE version = '18.0' AND name = 'sale_order_type'"
    ).fetchone()[0]
    assert summary == "Changed"
    # Child rows go with their module: only the 16.0 copy's two touches are left
    assert _count(conn, "model_touch") == 2


def test_removing_a_branch_removes_its_modules(conn):
    db.record_branches(conn, "sale-workflow", {"16.0": None})
    assert db.module_shas(conn, "sale-workflow", "16.0") == {}
    assert db.branch_heads(conn) == {("sale-workflow", "18.0"): TREE_1}
    assert _count(conn, "module") == 2
