"""Unit tests for the overdue page's pure render helpers (no IO)."""

import math

from build import build_overdue_html as bo
from datalib import OverduePerDriver, OverdueTrio


def entry(names, ids, races_together, score, rates):
    return OverdueTrio(
        driverIds=ids,
        names=names,
        racesTogether=races_together,
        score=score,
        perDriver=[
            OverduePerDriver(name=n, podiums=1, starts=10, rate=r)
            for n, r in zip(names, rates, strict=False)
        ],
    )


# ── format_score ─────────────────────────────────────────────────────────────


def test_format_score_one_decimal():
    assert bo.format_score(8.24) == "8.2×"


def test_format_score_whole_number():
    assert bo.format_score(8.0) == "8.0×"


def test_format_score_under_one():
    assert bo.format_score(0.65) == "0.7×"


# ── format_probability ────────────────────────────────────────────────────────


def test_format_probability_medium():
    # 1 - e^(-0.5) ≈ 0.3935 → "39%"
    p = (1.0 - math.exp(-0.5)) * 100
    assert bo.format_probability(0.5) == f"{p:.0f}%"


def test_format_probability_high():
    # score=8 → ~99.97% → rounds to "100%"
    assert bo.format_probability(8.0) == "100%"


# ── render_trio ───────────────────────────────────────────────────────────────


def test_render_trio_responsive_names():
    out = bo.render_trio(["Esteban Ocon", "Sergio Pérez", "Lance Stroll"])
    assert 'class="dn-full"' in out
    assert 'class="dn-abbr"' in out
    assert "E. Ocon" in out


def test_render_trio_bills_antonelli_as_kimi():
    out = bo.render_trio(["Andrea Kimi Antonelli", "Lando Norris", "George Russell"])
    assert '<span class="dn-full">Kimi Antonelli</span>' in out
    assert ">K. Antonelli<" in out
    assert "Andrea" not in out


def test_render_trio_escapes_and_separates():
    out = bo.render_trio(["A & B", "C Driver", "D Driver"])
    assert "A &amp; B" in out
    assert 'class="sep"' in out


def test_render_trio_separator_rides_with_the_name_before_it():
    """The "/" lives inside the name before it, so an inline trio wraps only
    after a separator and a stacked one simply hides it. The last carries none."""
    out = bo.render_trio(["Esteban Ocon", "Sergio Pérez", "Lance Stroll"])
    assert out.count('<span class="sep">/</span>') == 2
    assert '</span><span class="sep">/</span></span><span class="oddriver">' in out
    assert out.endswith("L. Stroll</span></span>")


# ── render_row_entry ─────────────────────────────────────────────────────────


def test_render_row_entry_carries_score_and_stats():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    html = bo.render_row_entry(e)
    assert 'class="rankrow"' in html
    assert "2.0×" in html  # headline number on the row face
    assert "Chance by now" in html and "86%" in html  # stats in the details body
    assert "10&times;" in html  # raced together
    assert 'class="dn-abbr"' in html  # responsive names still emitted


def test_render_row_entry_hero_is_open():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    assert "rankrow-hero" in bo.render_row_entry(e, hero=True)
    assert "rankrow-hero" not in bo.render_row_entry(e)


# ── render_cards ─────────────────────────────────────────────────────────────


def test_render_cards_table_with_hero_first_row():
    entries = [
        entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 50, 8.0, [0.5, 0.4, 0.3]),
        entry(["A Driver", "B Driver", "D Driver"], ["a", "b", "d"], 30, 4.0, [0.5, 0.4, 0.2]),
        entry(["A Driver", "C Driver", "D Driver"], ["a", "c", "d"], 20, 3.0, [0.5, 0.3, 0.2]),
    ]
    html = bo.render_cards(entries)
    # one combos-style container with a column-label strip
    assert 'class="rank-wrap"' in html
    assert '<span class="rh-num">Expected co-podiums</span>' in html
    assert 'class="rank-list"' in html
    # every rank is a row; #1 carries the accent rail but is closed like the rest
    assert html.count('class="rankrow') == 3
    assert html.count("rankrow-hero") == 1
    assert "<details open>" not in html
    assert 'class="rr-rank"' not in html  # ordered <ol>; no ordinal column


def test_render_cards_empty():
    assert "No candidates." in bo.render_cards([])


# ── section ───────────────────────────────────────────────────────────────────


def test_section_wraps_title_and_sub_without_a_box():
    """Heading and description sit naked above the table — the table is the only
    framed element, so there is no panel box and no collapsible header."""
    out = bo.section("My Title", "the subtitle", [])
    assert "<h2>My Title</h2>" in out
    assert "the subtitle" in out
    assert out.startswith('<section class="rank-section">')
    assert "od-panel" not in out
    assert "panel-chev" not in out
    assert "<details" not in out
