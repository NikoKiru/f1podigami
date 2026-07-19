"""Shared leaderboard-row renderer for the Overdue and Unlikeliest pages.

Every rank below the #1 hero card is one compact native <details> row: the
<summary> is the always-visible row face (rank, drivers, headline number,
optional race link) and the body holds the stat cells the old cards showed on
their face. Native disclosure means no JavaScript and free keyboard support.

Callers pass pre-escaped HTML fragments (driver spans, stat cells, race link);
this module only assembles structure.
"""

from __future__ import annotations


def render_row(rank: int, drivers_html: str, num: str, stats_html: str, race_html: str = "") -> str:
    """One expandable row. ``race_html`` (Unlikeliest only) sits on the row face
    on desktop; CSS moves it into the stats panel on phones."""
    race = f'<span class="rr-race">{race_html}</span>' if race_html else ""
    return (
        '<li class="rankrow">'
        "<details>"
        '<summary class="rr-face">'
        f'<span class="rr-rank">{rank}</span>'
        f'<span class="rr-drivers">{drivers_html}</span>'
        f"{race}"
        f'<span class="rr-num">{num}</span>'
        '<span class="rr-chev" aria-hidden="true">&#9662;</span>'
        "</summary>"
        f'<div class="rr-stats">{stats_html}</div>'
        "</details>"
        "</li>"
    )
