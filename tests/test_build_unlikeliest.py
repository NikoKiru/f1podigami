"""Unit tests for the unlikeliest page's pure render helpers (no IO)."""

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


def test_render_trio_escapes_and_separates():
    out = bu.render_trio(["A & B", "C", "D"])
    assert "A &amp; B" in out
    assert out.count('class="pdriver"') == 3
    assert 'class="sep"' in out


def test_render_hero_shows_race_link_and_framing():
    e = trio(["Ocon", "Perez", "Stroll"], ["o", "p", "s"], 152, 0.0065, 1, [0.02, 0.13, 0.02])
    html = bu.render_hero(e)
    # Wikipedia race report link for the race it happened
    assert "https://en.wikipedia.org/wiki/2020_Sakhir_Grand_Prix" in html
    assert "Sakhir Grand Prix" in html
    # the three drivers and their rates
    assert "Ocon" in html and "Perez" in html and "Stroll" in html
    assert "Raced together" in html and "152" in html
    # expected (score) vs actual (count) framing
    assert "0.0065" in html


def test_render_list_row_count_and_ranking_starts_at_two():
    entries = [
        trio(["A", "B", "C"], ["a", "b", "c"], 50, 0.10, 1, [0.5, 0.4, 0.3]),
        trio(["A", "B", "D"], ["a", "b", "d"], 30, 0.20, 2, [0.5, 0.4, 0.2]),
    ]
    html = bu.render_list(entries, start_rank=2)
    assert html.count('class="cand"') == 2
    assert ">2<" in html and ">3<" in html  # ranks continue from 2
    assert "0.1" in html  # score shown (compact, trailing zeros stripped)
    assert "raced" in html


def test_render_list_empty_shows_placeholder():
    assert "No trios." in bu.render_list([], start_rank=2)


def test_render_list_links_each_race_to_wikipedia():
    e = trio(["A", "B", "C"], ["a", "b", "c"], 50, 0.10, 1, [0.5, 0.4, 0.3], season="2017")
    html = bu.render_list([e], start_rank=2)
    assert "https://en.wikipedia.org/wiki/2017_Sakhir_Grand_Prix" in html
