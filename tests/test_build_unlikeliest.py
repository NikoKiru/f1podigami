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


def test_render_card_hero_variant_is_flagged():
    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    assert "uncard-hero" in bu.render_card(1, e, hero=True)
    assert "uncard-hero" not in bu.render_card(2, e, hero=False)


def test_render_card_shows_repeat_count_when_more_than_one():
    once = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    twice = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 2, [0.1, 0.1, 0.1])
    assert ">2<" in bu.render_card(3, twice)  # count cell shows 2
    # the once card shows 1 somewhere in its count cell
    assert "Times it happened" in bu.render_card(3, once)


def test_render_cards_lists_all_with_hero_first():
    entries = [
        trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1]),
        trio(["G H", "I J", "K L"], ["g", "h", "i"], 20, 0.05, 1, [0.2, 0.2, 0.2]),
    ]
    html = bu.render_cards(entries)
    assert html.count('<li class="uncard') == 2
    assert html.count("uncard-hero") == 1  # only the first
    assert ">1<" in html and ">2<" in html  # ranks


def test_render_cards_empty_shows_placeholder():
    assert "No trios." in bu.render_cards([])
