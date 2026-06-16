"""Output / HTML validation: the built site is complete and well-formed."""

import pytest

# page -> assets it must reference (and which must end up in dist/)
PAGES = {
    "index.html": ["index.css", "index.js"],
    "seasons.html": ["seasons.css", "seasons.js"],
    "soulmates.html": ["soulmates.css"],
    "charts.html": ["charts.css"],
}

ALL_ASSETS = [
    "style.css", "index.css", "seasons.css", "soulmates.css", "charts.css",
    "index.js", "seasons.js",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_built_and_nonempty(dist, page):
    f = dist / page
    assert f.is_file(), f"{page} was not generated"
    assert f.stat().st_size > 500, f"{page} looks suspiciously small"


@pytest.mark.parametrize("page", PAGES)
def test_page_head_essentials(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'name="viewport"' in html
    assert "width=device-width, initial-scale=1.0" in html
    assert '<link rel="stylesheet" href="style.css">' in html


@pytest.mark.parametrize("page,assets", PAGES.items())
def test_page_assets_referenced_and_copied(dist, page, assets):
    html = (dist / page).read_text(encoding="utf-8")
    for asset in assets:
        assert asset in html, f"{page} should reference {asset}"
        assert (dist / asset).is_file(), f"{asset} should be copied into dist/"


def test_all_assets_copied(dist):
    for asset in ALL_ASSETS:
        assert (dist / asset).is_file(), f"missing asset in dist/: {asset}"


def test_index_has_nav_and_combo_rows(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert "<table" in html
    assert 'class="combo"' in html


def test_seasons_has_cards(dist):
    html = (dist / "seasons.html").read_text(encoding="utf-8")
    assert "season-card" in html
    assert "races-table" in html
