"""Unit tests for the shared page-chrome helpers in build/_layout.py."""

import hashlib
import re
from pathlib import Path

from build._layout import (
    FOOTER,
    NAV_LINKS,
    SITE_URL,
    asset,
    breadcrumb_schema,
    head,
    nav,
    organization_schema,
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def test_asset_appends_content_hash_version():
    out = asset("style.css")
    expected = hashlib.sha1((ASSETS / "style.css").read_bytes()).hexdigest()[:8]
    assert out == f"style.css?v={expected}"


def test_asset_version_is_per_file():
    # distinct files get distinct cache-busting tokens (content-based)
    assert asset("style.css") != asset("podigami.css")
    assert re.fullmatch(r"podigami\.css\?v=[0-9a-f]{8}", asset("podigami.css"))


def test_asset_unknown_file_falls_back_to_bare_name():
    assert asset("does-not-exist.css") == "does-not-exist.css"


def test_head_links_style_first_then_page_css():
    out = head("My Title", "podigami.css")
    assert out.startswith("<!DOCTYPE html>")
    assert "<title>My Title</title>" in out
    assert 'name="viewport"' in out
    assert 'content="width=device-width, initial-scale=1.0"' in out
    assert '<meta name="theme-color"' in out
    # no-flash theme script applies the stored/OS theme before paint
    assert 'setAttribute("data-theme"' in out
    assert "prefers-color-scheme: light" in out
    # CSS is linked with a cache-busting ?v= token, style.css before the page sheet
    assert 'href="style.css?v=' in out
    assert 'href="podigami.css?v=' in out
    assert out.index('href="style.css?v=') < out.index('href="podigami.css?v=')
    assert out.rstrip().endswith("</head>")


def test_head_without_extra_css_still_links_base():
    out = head("Bare")
    assert 'href="style.css?v=' in out


def test_nav_marks_only_the_active_link():
    out = nav("combos.html")
    assert '<a href="combos.html" class="active">Combinations</a>' in out
    # every other link is present and not active
    for href, _ in NAV_LINKS:
        if href != "combos.html":
            assert f'<a href="{href}">' in out
    # exactly one active link in the inline nav and one in the mobile drawer
    assert out.count('class="active"') == 2
    drawer = out[out.index('<aside class="nav-drawer"') : out.index("</aside>")]
    assert drawer.count('class="active"') == 1


def test_nav_has_mobile_drawer_machinery():
    out = nav("index.html")
    assert 'id="nav-drawer-toggle"' in out  # pure-CSS checkbox core
    assert 'class="nav-burger"' in out
    assert 'class="nav-scrim"' in out
    assert 'aria-controls="nav-drawer"' in out
    assert "Escape" in out  # a11y enhancement script ships with the nav


def test_nav_includes_theme_toggle():
    assert 'id="theme-toggle"' in nav("index.html")


def test_nav_has_brand_home_link():
    out = nav("index.html")
    assert 'class="brand"' in out
    assert 'href="index.html"' in out
    assert "brand-mark" in out  # podium logo svg
    assert "brand-name" in out


def test_nav_links_are_plain_labels_no_arrow():
    out = nav("overdue.html")
    assert "&rarr;" not in out
    assert '<a href="overdue.html" class="active">Overdue</a>' in out


def test_footer_is_shared_constant():
    assert "Jolpica F1 API" in FOOTER
    assert 'class="footer-nav"' in FOOTER


def test_organization_schema_shape():
    org = organization_schema()
    assert org["@context"] == "https://schema.org"
    assert org["@type"] == "Organization"
    assert org["name"] == "F1 Podigami"
    assert org["url"] == f"{SITE_URL}/"
    assert org["logo"] == f"{SITE_URL}/apple-touch-icon.png"


def test_breadcrumb_schema_subpage():
    bc = breadcrumb_schema("Podium Combinations", "combos.html")
    assert bc["@type"] == "BreadcrumbList"
    items = bc["itemListElement"]
    assert [i["position"] for i in items] == [1, 2]
    assert items[0]["name"] == "Home"
    assert items[0]["item"] == f"{SITE_URL}/"
    assert items[1]["name"] == "Podium Combinations"
    assert items[1]["item"] == f"{SITE_URL}/combos.html"


def test_breadcrumb_schema_homepage_is_single_item():
    bc = breadcrumb_schema("Home", "index.html")
    items = bc["itemListElement"]
    assert len(items) == 1
    assert items[0]["item"] == f"{SITE_URL}/"
