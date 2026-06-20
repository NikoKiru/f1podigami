"""Output / HTML validation: the built site is complete and well-formed."""

import pytest

# page -> assets it must reference (and which must end up in dist/)
PAGES = {
    "index.html": ["podigami.css", "podigami.js", "theme.js"],
    "combos.html": ["index.css", "index.js", "theme.js"],
    "overdue.html": ["podigami.css", "theme.js"],
    "soulmates.html": ["soulmates.css", "theme.js"],
}

ALL_ASSETS = [
    "style.css", "index.css", "soulmates.css",
    "podigami.css", "index.js", "podigami.js", "theme.js",
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


def test_combos_has_nav_and_combo_rows(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert "<table" in html
    assert 'class="combo"' in html


def test_index_is_podigami_predictor(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert 'class="hero"' in html              # next-podigami hero
    assert 'id="tl-slider"' in html            # year-slider timeline
    assert 'id="podigami-data"' in html        # embedded slider data


@pytest.mark.parametrize("page", PAGES)
def test_page_has_theme_toggle_and_no_flash_script(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    # the nav toggle button drives the light/dark switch
    assert 'id="theme-toggle"' in html, f"{page} is missing the theme toggle"
    # a blocking inline script applies the stored/OS theme before first paint
    assert 'setAttribute("data-theme"' in html, f"{page} lacks the no-flash theme script"
    assert "prefers-color-scheme: light" in html, f"{page} should honour the OS preference"


def test_stylesheet_defines_light_theme(dist):
    css = (dist / "style.css").read_text(encoding="utf-8")
    assert '[data-theme="light"]' in css, "style.css must define a light theme"
    assert ".theme-toggle" in css, "style.css must style the theme toggle"


def test_overdue_has_two_ranked_lists(dist):
    html = (dist / "overdue.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert html.count('class="cand-list"') == 2          # all-time + current grid
    assert "All-time near-misses" in html
    assert 'class="cand-meta"' in html                   # "raced N times together"
