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


def test_render_trio_escapes_and_separates():
    out = bo.render_trio(["A & B", "C Driver", "D Driver"])
    assert "A &amp; B" in out
    assert 'class="sep"' in out


# ── render_card ───────────────────────────────────────────────────────────────


def test_render_card_fields_present():
    e = entry(
        ["Lewis Hamilton", "Nico Rosberg", "Sebastian Vettel"],
        ["ham", "ros", "vet"],
        100,
        8.24,
        [0.6, 0.5, 0.4],
    )
    html = bo.render_card(1, e)
    assert 'class="od-rank"' in html
    assert "8.2×" in html
    assert 'class="dn-full"' in html
    assert "60%" in html
    assert "100" in html  # racesTogether


def test_render_card_hero_variant():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    assert "odcard-hero" in bo.render_card(1, e, hero=True)
    assert "odcard-hero" not in bo.render_card(2, e, hero=False)


def test_render_card_probability_stat_present():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    html = bo.render_card(1, e)
    # 1 - e^(-2) ≈ 86%
    assert "86%" in html


# ── render_cards ─────────────────────────────────────────────────────────────


def test_render_cards_structure():
    entries = [
        entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 50, 8.0, [0.5, 0.4, 0.3]),
        entry(["A Driver", "B Driver", "D Driver"], ["a", "b", "d"], 30, 4.0, [0.5, 0.4, 0.2]),
    ]
    html = bo.render_cards(entries)
    assert 'class="odcard-list"' in html
    assert "odcard-hero" in html
    assert html.count('<li class="odcard') == 2


def test_render_cards_empty():
    assert "No candidates." in bo.render_cards([])


# ── panel ─────────────────────────────────────────────────────────────────────


def test_panel_wraps_title_and_sub():
    out = bo.panel("My Title", "the subtitle", [])
    assert "<h2>My Title</h2>" in out
    assert "the subtitle" in out
    assert 'class="panel"' in out
