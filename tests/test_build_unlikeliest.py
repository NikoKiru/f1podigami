"""Unit tests for the unlikeliest page's pure render helpers (no IO)."""

import math

import pytest

from build import build_unlikeliest as bu
from datalib import UnlikeliestPerDriver, UnlikeliestTrio


def trio(names, ids, races_together, score, count, rates, season="2020", rnd="1"):
    return UnlikeliestTrio(
        driverIds=ids,
        names=names,
        racesTogether=races_together,
        score=score,
        count=count,
        happened={"season": season, "round": rnd, "raceName": "Sakhir Grand Prix"},
        perDriver=[
            UnlikeliestPerDriver(name=n, podiums=2, starts=100, rate=r)
            for n, r in zip(names, rates, strict=False)
        ],
    )


# --- probability / odds -------------------------------------------------------


def test_ever_prob_matches_poisson_formula():
    assert bu.ever_prob(0.0065) == pytest.approx(1 - math.exp(-0.0065))
    # monotonic: a bigger expected count -> bigger chance it ever happened
    assert bu.ever_prob(0.2) > bu.ever_prob(0.0065)


def test_format_odds_rounds_to_two_sig_figs():
    # 1 - e^-0.0065 = 0.006479 -> 1/p = 154.3 -> "1 in 150"
    assert bu.format_odds(0.0065) == "1 in 150"


def test_format_odds_small_n_is_integer():
    # score chosen so p ~ 1/6 -> "1 in 6", not "1 in 5.8"
    score = -math.log(1 - 1 / 6)
    assert bu.format_odds(score) == "1 in 6"


# --- responsive trio names ----------------------------------------------------


def test_render_trio_emits_full_and_abbreviated_names():
    out = bu.render_trio(["Esteban Ocon", "Sergio Pérez", "Lance Stroll"])
    assert out.count('class="dn-full"') == 3
    assert out.count('class="dn-abbr"') == 3
    assert "Esteban Ocon" in out  # full
    assert "E. Ocon" in out  # abbreviated for narrow screens


def test_render_trio_escapes_names():
    out = bu.render_trio(["A & B", "C D", "E F"])
    assert "A &amp; B" in out


# --- card -------------------------------------------------------------------


def test_render_card_has_every_field_in_place():
    e = trio(
        ["Esteban Ocon", "Sergio Pérez", "Lance Stroll"],
        ["o", "p", "s"],
        152,
        0.0065,
        1,
        [0.02, 0.13, 0.02],
    )
    html = bu.render_card(1, e)
    assert 'class="uncard' in html
    assert "1" in html  # rank
    assert "1 in 150" in html  # odds headline
    assert "2%" in html and "13%" in html  # per-driver rates
    assert "152" in html  # raced together
    assert "https://en.wikipedia.org/wiki/2020_Sakhir_Grand_Prix" in html  # race link
    # responsive names present
    assert "Esteban Ocon" in html and "E. Ocon" in html


def test_render_card_uses_official_f1_url_when_links_present():
    from datalib import RaceLink

    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    links = {"2020": {"1": RaceLink(id="1045", slug="austria")}}
    html = bu.render_card(1, e, links=links)
    assert "https://www.formula1.com/en/results/2020/races/1045/austria/race-result" in html


def test_render_card_hero_variant_is_flagged():
    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    assert "uncard-hero" in bu.render_card(1, e, hero=True)
    assert "uncard-hero" not in bu.render_card(2, e, hero=False)


def test_render_row_entry_shows_repeat_count():
    once = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    twice = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 2, [0.1, 0.1, 0.1])
    assert ">2<" in bu.render_row_entry(3, twice)  # count cell shows 2
    assert "Times it happened" in bu.render_row_entry(3, once)


def test_render_row_entry_race_on_face_and_in_stats():
    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 152, 0.0065, 1, [0.02, 0.13, 0.02])
    html = bu.render_row_entry(2, e)
    assert 'class="rankrow"' in html
    assert "1 in 150" in html  # headline odds on the row face
    # race link appears twice: on the desktop row face and in the stats panel
    assert html.count("https://en.wikipedia.org/wiki/2020_Sakhir_Grand_Prix") == 2
    assert 'class="rr-race"' in html
    assert 'class="un-stat rr-stat-race"' in html
    assert "152&times;" in html  # raced together stat


def test_render_cards_hero_then_rows():
    entries = [
        trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1]),
        trio(["G H", "I J", "K L"], ["g", "h", "i"], 20, 0.05, 1, [0.2, 0.2, 0.2]),
        trio(["M N", "O P", "Q R"], ["m", "n", "o"], 30, 0.08, 1, [0.2, 0.2, 0.2]),
    ]
    html = bu.render_cards(entries)
    assert html.count("uncard-hero") == 1  # only the first entry is a card
    assert html.count('class="rankrow"') == 2  # the rest are rows
    assert 'class="rank-list"' in html
    assert '<span class="rr-rank">2</span>' in html
    assert '<span class="rr-rank">3</span>' in html


def test_render_cards_empty_shows_placeholder():
    assert "No trios." in bu.render_cards([])
