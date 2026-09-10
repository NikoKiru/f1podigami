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


def test_index_combo_row_collapses_to_one_line():
    """On phones a combination is one line — trio, podium count, chevron — with
    the last-race cell revealed only on expand, so 754 rows stay scannable.
    """
    import re

    s = css("index.css")
    block = s[s.index("@media (max-width: 600px)") :]
    assert re.search(
        r"tbody tr\.combo td\.last\s*\{[^}]*display:\s*none",
        block,
    ), "collapsed combo rows must hide the last-race cell on phones"
    assert re.search(
        r"tbody tr\.combo\.expanded td\.last\s*\{[^}]*display:\s*block",
        block,
    ), "expanding a combo row must reveal the last-race cell"
    assert 'content: "Last"' in block  # CSS-generated label on the revealed cell


def test_index_combo_rows_stay_one_table_on_mobile():
    """Rows divide with a hairline inside the table frame instead of floating as
    separate rounded cards — 754 of them must read as a list, not a stack."""
    import re

    s = css("index.css")
    block = s[s.index("@media (max-width: 600px)") :]
    row = re.search(r"tbody tr\.combo \{([^}]*)\}", block)
    assert row, "no mobile rule for tbody tr.combo"
    body = row.group(1)
    assert "border-top:" in body, "mobile combo rows need a hairline divider"
    assert "border-radius" not in body, "mobile combo rows must not be rounded cards"
    assert "margin-bottom" not in body, "mobile combo rows must not be gapped apart"


def test_index_inputs_prevent_ios_zoom():
    # >=16px font-size on inputs stops iOS auto-zoom on focus
    assert "font-size: 16px" in css("index.css")


@pytest.mark.parametrize("name", ["index.css", "podigami.css"])
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


def test_podigami_hero_trio_stacks_on_mobile():
    """The hero's three driver columns must stack on a phone.

    Replaces the old 720px check: the hero is no longer a two-column grid, so
    the 601-720px dead zone it guarded (#116) cannot recur. The surviving risk
    is the 3-up trio row, which at 600px would leave ~158px a column — no room
    to spare for a post-qualifying "Aston Martin · starts 12th" line.
    """
    import re

    s = css("podigami.css")
    mobile = re.search(r"@media \(max-width: 600px\)[\s\S]*", s)
    assert mobile, "podigami.css must keep the 600px breakpoint"
    assert re.search(
        r"\.hero-drivers\s*\{[^}]*grid-template-columns:\s*1fr",
        mobile.group(0),
    ), ".hero-drivers must collapse to one column inside the 600px breakpoint"


def test_next_race_plate_becomes_a_band_on_mobile():
    """The circuit plate must lay out as a row on phones.

    Stacked, the outline renders as a small off-centre doodle costing ~90px of
    scroll before the prediction hero. As a row it is a 54px outline beside its
    caption — one band, roughly half the height, and it reads as a caption.
    """
    import re

    s = css("podigami.css")
    mobile = re.search(r"@media \(max-width: 600px\)[\s\S]*", s)
    assert mobile, "podigami.css must keep the 600px breakpoint"
    assert re.search(
        r"\.nr-art\s*\{[^}]*flex-direction:\s*row",
        mobile.group(0),
    ), ".nr-art must lay out as a row inside the 600px breakpoint"
    assert re.search(
        r"\.nr-track\s*\{[^}]*width:\s*\d+px",
        mobile.group(0),
    ), ".nr-track must take a fixed width on phones so the band stays short"


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


def test_season_slider_swaps_for_selects_on_mobile():
    """The dual-handle slider is a pointer control: below the 720px breakpoint
    it gives way to the From/To selects, the way .mobile-sort mirrors the
    sortable table headers.
    """
    import re

    s = css("index.css")
    assert ".filter-group.mobile-seasons {\n    display: none;\n}" in s

    block = re.search(r"@media \(max-width: 720px\) \{.*?\n\}\n", s, re.S)
    assert block, "expected a 720px breakpoint block"
    mobile = block.group(0)
    assert re.search(r"\.season-range \{\s*display: none;", mobile)
    assert re.search(r"\.filter-group\.mobile-seasons \{\s*display: flex;", mobile)


def test_filters_become_a_slide_out_panel_on_mobile():
    """The filter block is the tallest thing on the combinations page; below
    720px it must leave the flow for a drawer behind the "Filters" trigger so
    the table, not the controls, owns the top of a phone screen.
    """
    import re

    s = css("index.css")
    # Inert on widescreen: the trigger and the panel chrome are hidden.
    assert re.search(r"\.filter-toggle \{\s*display: none;", s)
    assert re.search(r"\.fp-head,\n\.fp-foot \{\s*display: none;", s)

    block = re.search(r"@media \(max-width: 720px\) \{.*?\n\}\n", s, re.S)
    assert block, "expected a 720px breakpoint block"
    mobile = block.group(0)
    assert re.search(r"\.filter-toggle \{\s*display: inline-flex;", mobile)
    assert re.search(r"\.filter-panel \{[^}]*position: fixed", mobile), (
        "the panel must be a fixed drawer inside the 720px breakpoint"
    )
    assert re.search(r"\.filter-panel \{[^}]*transform: translateX\(105%\)", mobile), (
        "the panel must start off-canvas"
    )
    assert re.search(r"\.fp-toggle:checked ~ \.filter-panel \{[^}]*translateX\(0\)", mobile), (
        "the checkbox core must slide the panel in with no JS"
    )


def test_season_slider_thumbs_stay_grabbable():
    """The two range inputs overlap, so the input surfaces must be
    click-through with pointer events restored on the thumbs alone.
    """
    s = css("index.css")
    assert ".sr-input {" in s
    assert "pointer-events: none;" in s
    assert s.count("pointer-events: auto;") >= 2  # webkit + moz thumb


def test_trio_board_window_shrinks_on_mobile():
    """A 12-row window is desktop-sized; on a phone it outgrows the viewport and
    the panel swallows the page, so the breakpoint must shorten it."""
    import re

    s = css("podigami.css")
    assert "--board-rows: 12" in s  # desktop default
    mobile = s[s.index("@media (max-width: 600px)") :]
    block = re.search(r"\.cand-scroll\s*\{([^}]*)\}", mobile)
    assert block, ".cand-scroll has no mobile override"
    rows = re.search(r"--board-rows:\s*(\d+)", block.group(1))
    assert rows and int(rows.group(1)) < 12


def test_trio_board_chains_scroll_to_the_page():
    """The board is a panel mid-page, not a modal: reaching the end of the list
    must hand the gesture back to the page instead of trapping the reader."""
    import re

    s = css("podigami.css")
    block = re.search(r"\.cand-scroll \{([^}]*)\}", s)
    assert block, ".cand-scroll rule missing"
    assert not re.search(r"overscroll-behavior:\s*contain", block.group(1)), (
        ".cand-scroll must not contain overscroll — it strands the reader in the board"
    )


def test_trio_board_bubble_fits_phone_width():
    """Capped well inside the viewport, not merely to it: allowed to fill the
    screen the bubble stopped reading as a tooltip and became a band across the
    list."""
    s = css("podigami.css")
    mobile = s[s.index("@media (max-width: 600px)") :]
    assert "max-width: min(300px, calc(100vw - 32px))" in mobile


def test_trio_board_fade_is_an_overlay_not_a_mask():
    """A mask on the scroll container makes it a containing block for
    position:fixed descendants and clips them, which truncated the history
    bubbles to a sliver. The fade must stay an overlay on the wrapper."""
    s = css("podigami.css")
    assert "mask-image" not in s, "a mask on the board would clip the fixed bubbles"
    assert ".cand-board.has-more::after" in s
