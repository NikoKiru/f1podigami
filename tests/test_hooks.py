"""Unit tests for the discovery hook cards (src/build/_hooks.py)."""

import re
from types import SimpleNamespace as NS

from build import _hooks


def test_hook_card_structure_and_escaping():
    out = _hooks.hook_card("Kick & er", "<b>stat</b>", "combos.html?a=1&b=2", "Go <now>")
    assert out.startswith('<a class="hook-card" href="combos.html?a=1&amp;b=2">')
    assert '<span class="hook-kicker plate plate-secondary">Kick &amp; er</span>' in out
    assert '<span class="hook-stat"><b>stat</b></span>' in out  # stat_html is trusted HTML
    assert "Go &lt;now&gt;" in out  # CTA text is escaped
    assert "hook-arrow" in out


def test_hook_card_without_stat_omits_stat_line():
    out = _hooks.hook_card("Overdue trios", "", "overdue.html", "Who is due")
    assert "hook-stat" not in out
    assert 'href="overdue.html"' in out


def test_combos_hook_formats_total():
    out = _hooks.combos_hook(1234, 1950)
    assert "1,234" in out
    assert "1950" in out
    assert 'href="combos.html"' in out


def test_combos_hook_zero_total_falls_back_statless():
    assert "hook-stat" not in _hooks.combos_hook(0, 1950)


def test_soulmates_hook_top_pair_and_escaping():
    sm = NS(topPairs=[NS(a="Lewis & Hamilton", b="Sebastian Vettel", count=61)])
    out = _hooks.soulmates_hook(sm)
    assert "Lewis &amp; Hamilton" in out
    assert "61" in out
    assert 'href="soulmates.html"' in out


def test_soulmates_hook_bills_antonelli_as_kimi():
    sm = NS(topPairs=[NS(a="Andrea Kimi Antonelli", b="George Russell", count=9)])
    out = _hooks.soulmates_hook(sm)
    assert "Kimi Antonelli &amp; George Russell" in out
    assert "Andrea" not in out


def test_soulmates_hook_missing_data():
    assert "hook-stat" not in _hooks.soulmates_hook(None)
    assert "hook-stat" not in _hooks.soulmates_hook(NS(topPairs=[]))
    assert 'href="soulmates.html"' in _hooks.soulmates_hook(None)


def test_overdue_hook_surnames_and_races():
    od = NS(
        allTime=[
            NS(
                names=["Lewis Hamilton", "Max Verstappen", "Oscar Piastri"],
                racesTogether=78,
            )
        ]
    )
    out = _hooks.overdue_hook(od)
    assert "Hamilton / Verstappen / Piastri" in out
    assert "78" in out
    assert 'href="overdue.html"' in out


def test_overdue_hook_missing_data():
    assert "hook-stat" not in _hooks.overdue_hook(None)
    assert "hook-stat" not in _hooks.overdue_hook(NS(allTime=[]))


def test_unlikeliest_hook_race_and_season():
    ul = NS(
        trios=[
            NS(
                names=["Esteban Ocon", "Sergio Pérez", "Lance Stroll"],
                happened=NS(season="2020", round="16", raceName="Sakhir Grand Prix"),
            )
        ]
    )
    out = _hooks.unlikeliest_hook(ul)
    assert "Ocon / Pérez / Stroll" in out
    assert "Sakhir Grand Prix" in out
    assert "2020" in out
    assert 'href="unlikeliest.html"' in out


def test_unlikeliest_hook_missing_data():
    assert "hook-stat" not in _hooks.unlikeliest_hook(None)
    assert "hook-stat" not in _hooks.unlikeliest_hook(NS(trios=[]))


def test_explore_grid_leaves_out_the_page_it_sits_on():
    out = _hooks.explore_grid("overdue.html")
    assert 'href="overdue.html"' not in out
    assert 'href="unlikeliest.html"' in out


def test_explore_grid_links_every_other_page():
    out = _hooks.explore_grid()
    for href in (
        "combos.html",
        "overdue.html",
        "unlikeliest.html",
        "soulmates.html",
        "scorecard.html",
    ):
        assert f'href="{href}"' in out
    assert "Keep exploring" in out
    assert out.count("hook-card") >= 4


def test_overdue_hook_keeps_surname_particles():
    od = NS(
        allTime=[
            NS(
                names=["Wolfgang von Trips", "Phil Hill", "Jim Clark"],
                racesTogether=3,
            )
        ]
    )
    assert "von Trips / Hill / Clark" in _hooks.overdue_hook(od)


# ---- explore_list: the phone's one-line-per-page hub --------------------------

_EXPLORE_HREFS = [
    "combos.html",
    "overdue.html",
    "unlikeliest.html",
    "soulmates.html",
    "scorecard.html",
]


def _explore_fixtures():
    sm = NS(topPairs=[NS(a="Lewis Hamilton", b="Sebastian Vettel", count=61)])
    od = NS(
        allTime=[
            NS(names=["Wolfgang von Trips", "Phil Hill", "Jim Clark"], racesTogether=3),
        ]
    )
    un = NS(
        trios=[
            NS(
                names=["Lewis Hamilton", "Max Verstappen", "Oscar Piastri"],
                happened=NS(season="2021", raceName="Some GP"),
            )
        ]
    )
    return sm, od, un


def test_explore_list_has_five_rows_in_order_and_formats_total():
    sm, od, un = _explore_fixtures()
    out = _hooks.explore_list(755, 1950, sm, od, un)
    assert out.startswith('<section class="panel explore-list"><h2>Explore</h2>')
    hrefs = re.findall(r'<a class="ex-row" href="([^"]+)"', out)
    assert hrefs == _EXPLORE_HREFS
    assert "<b>755</b> trios since 1950" in out
    assert '<span class="ex-chev" aria-hidden="true">&rsaquo;</span>' in out
    assert '<span class="plate plate-secondary">Combinations</span>' in out
    assert "<b>Hamilton &amp; Vettel</b> &middot; 61 together" in out
    assert "<b>Hamilton / Verstappen / Piastri</b> &middot; 2021" in out
    assert "Every prediction, graded" in out


def test_explore_list_overdue_stat_uses_surnames():
    sm, od, un = _explore_fixtures()
    out = _hooks.explore_list(755, 1950, sm, od, un)
    assert "<b>von Trips / Hill / Clark</b> &middot; 3 races" in out


def test_explore_list_keeps_every_row_without_data():
    out = _hooks.explore_list(0, 1950, None, None, None)
    assert re.findall(r'<a class="ex-row" href="([^"]+)"', out) == _EXPLORE_HREFS
    assert out.count('class="ex-stat"') == 5
