import pytest

from oca_index.config import CONFIG_PATH, load_settings, parse_settings
from oca_index.discover import parse_ls_remote, parse_repo_page

# Real `git ls-remote --heads https://github.com/OCA/sale-workflow` output shape.
LS_REMOTE = (
    "46ab77bf78b79f963ef5163530f23c88661e787b\trefs/heads/16.0\n"
    "91fed54d404eac384a0186fdf541d0e354a4171f\trefs/heads/18.0\n"
    "45524eff9ce21e686eaaf9b224af8f6b852be7da\trefs/heads/18.0-mig-sale_order_type\n"
)


def test_parse_ls_remote_keeps_only_tracked_versions():
    assert parse_ls_remote(LS_REMOTE, ("17.0", "18.0")) == {
        "18.0": "91fed54d404eac384a0186fdf541d0e354a4171f"
    }


def test_parse_repo_page_skips_archived():
    # Shape of GitHub's GET /orgs/OCA/repos items (trimmed to the fields used).
    page = [
        {"name": "sale-workflow", "archived": False},
        {"name": "connector-magento", "archived": True},
    ]
    assert parse_repo_page(page) == ["sale-workflow"]


def test_team_config_loads():
    assert load_settings(CONFIG_PATH).versions


FILTERS = parse_settings(
    {
        "versions": ["18.0"],
        "data_dir": "/tmp/oca-index",
        "exclude_repos": ["OCB", "l10n-*"],
        "keep_repos": ["l10n-usa"],
        "exclude_modules": ["*_demo"],
    }
)


@pytest.mark.parametrize(
    ("repo", "selected"),
    [
        pytest.param("sale-workflow", True, id="not-excluded"),
        pytest.param("OCB", False, id="excluded-by-name"),
        pytest.param("l10n-brazil", False, id="excluded-by-glob"),
        pytest.param("l10n-usa", True, id="kept-despite-glob"),
        pytest.param("ocb", True, id="case-sensitive"),
    ],
)
def test_repo_selected(repo, selected):
    assert FILTERS.repo_selected(repo) is selected


@pytest.mark.parametrize(
    ("module", "selected"),
    [
        pytest.param("sale_order_type", True, id="not-excluded"),
        pytest.param("fieldservice_demo", False, id="excluded-by-glob"),
    ],
)
def test_module_selected(module, selected):
    assert FILTERS.module_selected(module) is selected
