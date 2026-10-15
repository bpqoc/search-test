import pytest

from oca_index.parse import (
    FieldDef,
    ModelTouch,
    TouchKind,
    clean_markup,
    is_model_source,
    parse_module,
)

MANIFEST = """
# Copyright 2015 Example
{
    "name": "Sale Order Type",
    "version": "18.0.1.2.0",
    "category": "Sales Management",
    "author": "Grupo Vermon, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/sale-workflow",
    "license": "AGPL-3",
    "depends": ["sale_stock", "account"],
    "external_dependencies": {"python": ["openupgradelib"], "bin": ["wkhtmltopdf"]},
    "maintainers": ["rafaelbn"],
    "development_status": "Production/Stable",
    "auto_install": ["sale", "stock"],
    "Summary": "Sales order types",
    "data": ["views/sale_order_type_views.xml"],
}
"""


def _parse(manifest=MANIFEST, readme=None, readme_rst=None, python=None):
    return parse_module("sale_order_type", manifest, readme or {}, readme_rst, python or {})


def test_manifest_fields():
    info = _parse()
    assert info.title == "Sale Order Type"
    assert info.summary == "Sales order types"
    assert info.depends == ["sale_stock", "account"]
    assert info.python_deps == ["openupgradelib"]
    assert info.bin_deps == ["wkhtmltopdf"]
    assert info.maintainers == ["rafaelbn"]
    assert info.installable is True
    assert info.auto_install is True
    assert info.errors == []


def test_uninstallable_module():
    info = _parse(manifest='{"name": "Old", "installable": False}')
    assert info.installable is False


def test_broken_manifest_still_yields_a_module():
    info = _parse(manifest="{'name': 'x',")
    assert info.title == "sale_order_type"
    assert len(info.errors) == 1


def test_readme_sections():
    info = _parse(
        readme={
            "DESCRIPTION.md": "Adds a typology for sales orders.\n",
            "USAGE.rst": "Pick a type on the order.",
            "CONFIGURE.md": "  \n",
            "CONTRIBUTORS.md": "- Someone",
        }
    )
    assert info.readme == {
        "description": "Adds a typology for sales orders.",
        "usage": "Pick a type on the order.",
    }


def test_readme_rst_fallback_drops_boilerplate():
    rst = "Stock Landed Costs Analytic\n===\n\nAdds analytic accounts.\n\nBug Tracker\n===\nBugs..."
    info = _parse(readme={"CONTRIBUTORS.md": "- Someone"}, readme_rst=rst)
    assert info.readme["description"] == "Stock Landed Costs Analytic\n\nAdds analytic accounts."


def test_readme_rst_ignored_when_description_exists():
    info = _parse(readme={"DESCRIPTION.md": "Real description"}, readme_rst="Generated")
    assert info.readme["description"] == "Real description"


MODEL = TouchKind


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "class SaleOrder(models.Model):\n    _inherit = 'sale.order'\n",
            [("sale.order", MODEL.INHERIT, "Model", None)],
            id="extend-existing",
        ),
        pytest.param(
            "class SaleOrderType(models.Model):\n"
            "    _name = 'sale.order.type'\n"
            "    _description = 'Type of sale order'\n"
            "    _inherit = ['mail.thread', 'mail.activity.mixin']\n",
            [
                ("sale.order.type", MODEL.DEFINE, "Model", "Type of sale order"),
                ("mail.thread", MODEL.MIXIN, "Model", None),
                ("mail.activity.mixin", MODEL.MIXIN, "Model", None),
            ],
            id="new-model-with-mixins",
        ),
        pytest.param(
            "class ResPartner(models.Model):\n    _inherit = ['res.partner', 'mail.thread']\n",
            [
                ("res.partner", MODEL.INHERIT, "Model", None),
                ("mail.thread", MODEL.MIXIN, "Model", None),
            ],
            id="inherit-list-first-is-the-model",
        ),
        pytest.param(
            "class X(models.Model):\n    _name = 'res.partner'\n    _inherit = 'res.partner'\n",
            [("res.partner", MODEL.INHERIT, "Model", None)],
            id="name-equal-to-inherit",
        ),
        pytest.param(
            "class Product(models.Model):\n"
            "    _name = 'product.pack.line'\n"
            "    _inherits = {'product.product': 'product_id'}\n",
            [
                ("product.pack.line", MODEL.DEFINE, "Model", None),
                ("product.product", MODEL.DELEGATE, "Model", None),
            ],
            id="delegation",
        ),
        pytest.param(
            "class Wizard(models.TransientModel):\n    _name = 'sale.order.type.wizard'\n",
            [("sale.order.type.wizard", MODEL.DEFINE, "TransientModel", None)],
            id="wizard",
        ),
        pytest.param(
            "class Mixin(AbstractModel):\n    _name = 'x.mixin'\n",
            [("x.mixin", MODEL.DEFINE, "AbstractModel", None)],
            id="bare-imported-base",
        ),
        pytest.param(
            "class Listener(Component):\n    _name = 'sale.order.listener'\n",
            [],
            id="connector-component-is-not-a-model",
        ),
        pytest.param(
            "class Helper(models.Model):\n    _order = 'name'\n",
            [],
            id="no-name-or-inherit",
        ),
    ],
)
def test_model_touches(source, expected):
    info = _parse(python={"models/x.py": source})
    assert info.models == [ModelTouch(*e, "models/x.py") for e in expected]


FIELDS_SOURCE = """
class SaleOrder(models.Model):
    _inherit = "sale.order"

    type_id = fields.Many2one("sale.order.type", "Type", ondelete="restrict")
    line_ids = fields.One2many("sale.order.type.line", "order_id", "Type Lines")
    tag_ids = fields.Many2many(comodel_name="crm.tag", string="Tags")
    state = fields.Selection([("a", "A")], "Status")
    note: str = fields.Text(string="Note", compute="_compute_note")
    type_name = fields.Char(related="type_id.name")
    lines = fields.Command.create({})
    _order = "name"
"""


def test_fields():
    info = _parse(python={"models/sale_order.py": FIELDS_SOURCE})
    assert info.fields == [
        FieldDef("sale.order", "type_id", "Many2one", "sale.order.type", "Type", False, False),
        FieldDef(
            "sale.order", "line_ids", "One2many", "sale.order.type.line", "Type Lines", False, False
        ),
        FieldDef("sale.order", "tag_ids", "Many2many", "crm.tag", "Tags", False, False),
        FieldDef("sale.order", "state", "Selection", None, "Status", False, False),
        FieldDef("sale.order", "note", "Text", None, "Note", False, True),
        FieldDef("sale.order", "type_name", "Char", None, None, True, False),
    ]


def test_syntax_error_skips_only_that_file():
    info = _parse(
        python={
            "models/broken.py": "class X(models.Model:\n",
            "models/ok.py": "class Y(models.Model):\n    _inherit = 'res.partner'\n",
        }
    )
    assert [t.model for t in info.models] == ["res.partner"]
    assert len(info.errors) == 1


@pytest.mark.parametrize(
    ("relpath", "expected"),
    [
        pytest.param("models/sale_order.py", True, id="models"),
        pytest.param("wizards/wizard.py", True, id="wizards"),
        pytest.param("hooks.py", True, id="module-root"),
        pytest.param("tests/test_sale.py", False, id="tests"),
        pytest.param("migrations/18.0.1.0.0/pre-migration.py", False, id="migrations"),
        pytest.param("static/description/index.html", False, id="not-python"),
    ],
)
def test_is_model_source(relpath, expected):
    assert is_model_source(relpath) is expected


GENERATED_README = """============
Product Pack
============

..
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   !! This file is generated by oca-gen-addon-readme !!
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta

|badge1| |badge2|

This module allows you to define a product as a *Product Pack*.

**Table of contents**

.. contents::

Bug Tracker
===========
"""


def test_generated_readme_fallback_keeps_only_the_description():
    info = _parse(readme={}, readme_rst=GENERATED_README)
    assert info.readme["description"] == (
        "Product Pack\n\nThis module allows you to define a product as a *Product Pack*."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("![screenshot](static/img.png)Adds X.", "Adds X.", id="md-image"),
        pytest.param("See [the docs](https://x.org).", "See the docs.", id="md-link-keeps-text"),
        pytest.param("See `site <https://x.org>`_.", "See site.", id="rst-link-keeps-text"),
        pytest.param("<p>Adds <b>X</b></p>", "Adds  X", id="html"),
        pytest.param("Config at https://x.org/y", "Config at", id="url"),
        pytest.param(".. image:: a.png\n   :alt: A\n\nText", "Text", id="rst-directive"),
    ],
)
def test_clean_markup(text, expected):
    assert clean_markup(text) == expected
