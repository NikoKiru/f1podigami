"""Mobile-CSS regression guards.

These lock in the responsive work so a future edit can't silently drop the
mobile layout. They read the source CSS in assets/ (not the build output).
"""

from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def css(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_index_table_becomes_cards():
    s = css("index.css")
    assert "@media (max-width: 600px)" in s
    assert "display: block" in s  # table -> block/card layout
    assert 'content: "Podiums"' in s  # CSS-generated row labels
    assert 'content: "Last"' in s


def test_index_inputs_prevent_ios_zoom():
    # >=16px font-size on inputs stops iOS auto-zoom on focus
    assert "font-size: 16px" in css("index.css")


@pytest.mark.parametrize("name", ["soulmates.css", "podigami.css"])
def test_secondary_pages_have_phone_breakpoint(name):
    assert "@media (max-width: 600px)" in css(name)


def test_hero_team_name_truncates_on_mobile():
    """.hd-team must stay single-line on mobile so long team names ("Cadillac F1
    Team") don't wrap and grow one hero card taller than its siblings (#149).
    """
    import re

    s = css("podigami.css")
    assert re.search(
        r"@media \(max-width: 600px\).*?\.hd-team\s*\{[^}]*white-space:\s*nowrap",
        s,
        re.DOTALL,
    ), "Hero .hd-team must be forced to a single line inside the mobile breakpoint (fixes #149)"


def test_hook_grids_collapse_on_mobile():
    """The 2-up hook row and 2x2 explore grid must stack to one column on phones."""
    import re

    s = css("podigami.css")
    assert ".hook-card" in s and ".explore-grid" in s
    assert re.search(
        r"@media \(max-width: 600px\).*?\.hook-row[\s\S]*?grid-template-columns:\s*1fr",
        s,
        re.DOTALL,
    ), "hook-row/explore-grid must collapse to 1 column inside the 600px breakpoint"


def test_podigami_hero_collapses_at_720px():
    """Hero switches to single-column at 720px to fix the 601-720px dead zone.

    Without this, the container already has 14px padding from the 720px nav rule
    (style.css) but the hero grid stays in 2-column desktop mode until 600px,
    leaving the right column too narrow for 3 driver cards side by side.
    """
    import re

    s = css("podigami.css")
    assert re.search(
        r"@media \(max-width: 720px\).*?grid-template-columns:\s*1fr",
        s,
        re.DOTALL,
    ), "Hero must switch to single-column grid inside a max-width:720px block (fixes #116)"


def test_shared_nav_collapses_to_drawer_on_mobile():
    """At <=720px the inline nav links hide behind a burger that opens a left
    slide-out drawer (CSS checkbox core, so it works without JS)."""
    import re

    s = css("style.css")
    m = re.search(r"@media \(max-width: 720px\)[\s\S]*", s)
    assert m, "style.css must keep the 720px breakpoint"
    mobile = m.group(0)
    assert re.search(r"\.nav-links\s*\{[^}]*display:\s*none", mobile), (
        "inline nav links must hide on mobile"
    )
    assert re.search(r"\.nav-burger\s*\{[^}]*display:\s*(inline-)?flex", mobile), (
        "burger must appear on mobile"
    )
    # drawer starts off-canvas left and slides in when the checkbox is checked
    assert re.search(r"\.nav-drawer\s*\{[^}]*translateX\(-", s)
    assert ".nav-drawer-toggle:checked" in s


def test_rank_rows_swap_race_into_panel_on_mobile():
    """Leaderboard rows: on phones the race name leaves the row face and shows
    as a stat cell inside the expanded panel instead; driver names abbreviate."""
    import re

    s = css("podigami.css")
    assert "od-toggle" not in s, "the old JS Details-toggle CSS must be gone"
    block = re.search(r"@media \(max-width: 600px\)[\s\S]*", s).group(0)
    assert re.search(r"\.rr-race\s*\{[^}]*display:\s*none", block), (
        "mobile must hide the race name on the row face"
    )
    assert re.search(r"\.rr-stat-race\s*\{[^}]*display:\s*flex", block), (
        "mobile must show the race stat cell in the expanded panel"
    )
    assert ".rr-drivers .dn-full" in block and ".rr-drivers .dn-abbr" in block, (
        "row driver names must swap to abbreviated form on mobile"
    )
