"""Mobile-CSS regression guards.

These lock in the responsive work so a future edit can't silently drop the
mobile layout. They read the source CSS in assets/ (not the build output).
"""

from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def css(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_shared_nav_is_scroll_strip_on_mobile():
    s = css("style.css")
    assert "@media (max-width: 720px)" in s
    assert "overflow-x: auto" in s  # nav becomes a horizontal scroll strip


def test_index_table_becomes_cards():
    s = css("index.css")
    assert "@media (max-width: 600px)" in s
    assert "display: block" in s          # table -> block/card layout
    assert 'content: "Podiums"' in s      # CSS-generated row labels
    assert 'content: "Last"' in s


def test_index_inputs_prevent_ios_zoom():
    # >=16px font-size on inputs stops iOS auto-zoom on focus
    assert "font-size: 16px" in css("index.css")


@pytest.mark.parametrize("name", ["soulmates.css", "podigami.css"])
def test_secondary_pages_have_phone_breakpoint(name):
    assert "@media (max-width: 600px)" in css(name)
