"""Unit tests for the overdue page's pure render helpers (no IO)."""

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


def test_render_trio_escapes_and_separates():
    out = bo.render_trio(["A & B", "C", "D"])
    assert "A &amp; B" in out  # HTML-escaped
    assert out.count('class="pdriver"') == 3
    assert 'class="sep"' in out


def test_render_list_marks_top_bar_full_width():
    entries = [
        entry(["A", "B", "C"], ["a", "b", "c"], 50, 8.0, [0.5, 0.4, 0.3]),
        entry(["A", "B", "D"], ["a", "b", "d"], 30, 4.0, [0.5, 0.4, 0.2]),
    ]
    html = bo.render_list(entries)
    assert html.count('class="cand"') == 2
    assert "width:100%" in html  # top entry bar is full
    assert "width:50%" in html  # second is score/top = 4/8
    assert "raced <b>50</b> times together" in html  # meta line
    assert "8.00" in html and "4.00" in html  # score formatting
    assert "50% / 40% / 30% podium rates" in html  # rates formatting


def test_render_list_empty_shows_placeholder():
    assert "No candidates." in bo.render_list([])


def test_panel_wraps_title_and_sub():
    out = bo.panel("My Title", "the subtitle", [])
    assert "<h2>My Title</h2>" in out
    assert "the subtitle" in out
    assert 'class="panel"' in out
