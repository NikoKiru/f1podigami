"""Unit tests for the shared leaderboard-row renderer."""

from build._rows import render_row


def test_render_row_structure():
    out = render_row(2, "<span>A &middot; B &middot; C</span>", "1 in 440", "<div>stats</div>")
    assert out.startswith('<li class="rankrow">')
    assert out.endswith("</li>")
    assert "<details>" in out
    assert '<summary class="rr-face">' in out
    assert '<span class="rr-rank">2</span>' in out
    assert '<span class="rr-drivers"><span>A &middot; B &middot; C</span></span>' in out
    assert '<span class="rr-num">1 in 440</span>' in out
    assert '<span class="rr-chev" aria-hidden="true">&#9662;</span>' in out
    assert '<div class="rr-stats"><div>stats</div></div>' in out


def test_render_row_race_optional():
    assert 'class="rr-race"' not in render_row(2, "d", "n", "s")
    out = render_row(3, "d", "n", "s", race_html='<a href="x">1990 Japanese GP</a>')
    assert '<span class="rr-race"><a href="x">1990 Japanese GP</a></span>' in out
