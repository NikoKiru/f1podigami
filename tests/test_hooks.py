"""Unit tests for the discovery hook cards (src/build/_hooks.py)."""

from types import SimpleNamespace as NS

from build import _hooks


def test_hook_card_structure_and_escaping():
    out = _hooks.hook_card("Kick & er", "<b>stat</b>", "combos.html?a=1&b=2", "Go <now>")
    assert out.startswith('<a class="hook-card" href="combos.html?a=1&amp;b=2">')
    assert '<span class="hook-kicker">Kick &amp; er</span>' in out
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


def test_explore_grid_links_all_four_pages():
    out = _hooks.explore_grid()
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in out
    assert "Keep exploring" in out
    assert out.count("hook-card") >= 4
