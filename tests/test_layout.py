"""Unit tests for the shared page-chrome helpers in build/_layout.py."""

from build._layout import FOOTER, NAV_LINKS, head, nav


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
    # style.css must come before the page-specific sheet
    assert out.index('href="style.css"') < out.index('href="podigami.css"')
    assert out.rstrip().endswith("</head>")


def test_head_without_extra_css_still_links_base():
    out = head("Bare")
    assert 'href="style.css"' in out


def test_nav_marks_only_the_active_link():
    out = nav("combos.html")
    assert '<a href="combos.html" class="active">Combinations</a>' in out
    # every other link is present and not active
    for href, _ in NAV_LINKS:
        if href != "combos.html":
            assert f'<a href="{href}">' in out
    assert out.count('class="active"') == 1


def test_nav_includes_theme_toggle():
    assert 'id="theme-toggle"' in nav("index.html")


def test_soulmates_arrow_only_when_not_active():
    # arrow present when Soulmates is not the current page
    assert "Soulmates &rarr;" in nav("index.html")
    # plain label (no arrow) on its own page
    sm = nav("soulmates.html")
    assert "Soulmates &rarr;" not in sm
    assert '<a href="soulmates.html" class="active">Soulmates</a>' in sm


def test_footer_is_shared_constant():
    assert "Jolpica F1 API" in FOOTER
    assert 'class="footer-nav"' in FOOTER
