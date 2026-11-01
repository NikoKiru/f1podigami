"""Shared ranked-table renderer for the Overdue, Unlikeliest and Soulmates pages.

The three pages present the same shape of content — a ranked list of driver
groupings, each with one headline number and a handful of supporting stats — so
they render through one component that mirrors the Combinations table
cell-for-cell: a single hairline frame with no outer panel, an uppercase
column-label strip, flat rows at the page type size, and an expanded drawer on
``--bg-2`` behind an accent rail.

Every entry is one native ``<details>`` row: the ``<summary>`` is the row face
(drivers, headline number, optional race) and the body holds the stat cells.
Closed shows the headline stat only; open reveals the detail — including for
#1, which is a normal closed row carrying nothing but an accent rail to mark it
as the leader. The list carries no ordinal column: it is an ordered ``<ol>``
and position says the same thing.

Column geometry lives in one custom property (``--rank-cols``, a CSS grid track
list set per page), shared by the label strip and every row face, so labels sit
directly above their values with no layout engine.

Callers pass pre-escaped HTML fragments (driver spans, stat cells, race link);
this module only assembles structure.
"""

from __future__ import annotations

import html


def render_row(
    drivers_html: str,
    num: str,
    stats_html: str,
    race_html: str = "",
    hero: bool = False,
) -> str:
    """One expandable row. Column order mirrors the combinations table: group,
    headline value, context, chevron. ``race_html`` (Unlikeliest only) sits on
    the row face on desktop; CSS moves it into the stats drawer on phones.
    ``hero`` marks the top entry, which differs only by an accent rail — same
    type size, and closed by default like every other row."""
    race = f'<span class="rr-race">{race_html}</span>' if race_html else ""
    cls = "rankrow rankrow-hero" if hero else "rankrow"
    return (
        f'<li class="{cls}">'
        "<details>"
        '<summary class="rr-face">'
        f'<span class="rr-drivers">{drivers_html}</span>'
        f'<span class="rr-num">{num}</span>'
        f"{race}"
        '<span class="rr-chev" aria-hidden="true"><span class="chev">&#9662;</span></span>'
        "</summary>"
        f'<div class="rr-stats">{stats_html}</div>'
        "</details>"
        "</li>"
    )


def render_race_link(url: str, season: str, race_name: str) -> str:
    """A race the way the combinations table's "Last seen" shows it (bold year,
    dimmed name), linking to its report. The same fragment goes on the row face
    and in the drawer, where CSS moves it on phones."""
    year, name = html.escape(season), html.escape(race_name)
    return (
        f'<a class="race-link" href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener" title="{year} {name} &mdash; race report">'
        f'<span class="year">{year}</span>'
        f'<span class="race-name">{name}</span>'
        f"</a>"
    )


def render_stat(label: str, value: str, extra_class: str = "") -> str:
    """One labelled stat cell for a row's expanded drawer. All three pages use
    the same cell so the styling lives in one place."""
    cls = f"rr-stat {extra_class}".strip()
    return (
        f'<div class="{cls}">'
        f'<span class="rr-stat-label">{label}</span>'
        f'<span class="rr-stat-val">{value}</span>'
        f"</div>"
    )


def render_link(href: str, label: str) -> str:
    """The way on from a row, closing its drawer. ``href`` is a plain URL, escaped
    here because a filtered Combinations link carries an ``&``."""
    return (
        f'<a class="rr-link" href="{html.escape(href, quote=True)}">{label}'
        ' <span aria-hidden="true">&rarr;</span></a>'
    )


def render_table(
    rows_html: str,
    *,
    value_label: str,
    cols: str,
    group_label: str = "Trio",
    race_label: str = "",
) -> str:
    """Wrap rendered rows in the frame + column-label strip.

    ``cols`` is the CSS grid track list (group, value, [race], chevron) handed
    to CSS as ``--rank-cols`` so the strip and every row face share the same
    geometry. The strip is hidden on phones, where rows stack instead. Keep
    ``value_label`` short — like the combinations table's "Count" and "Last
    seen" — since a label wider than its track is truncated, not wrapped.
    """
    race_head = f'<span class="rh-race">{race_label}</span>' if race_label else ""
    return (
        f'<div class="rank-wrap" style="--rank-cols:{cols}">'
        '<div class="rank-head">'
        f'<span class="rh-drivers">{group_label}</span>'
        f'<span class="rh-num">{value_label}</span>'
        f"{race_head}"
        '<span class="rh-chev"></span>'
        "</div>"
        f'<ol class="rank-list">{rows_html}</ol>'
        "</div>"
    )


def render_section(title: str, sub: str, body_html: str) -> str:
    """A heading and one-line description sitting directly above the table, with
    no surrounding panel box — the combinations page's heading/hint/table
    rhythm, so the table itself is the only framed element on the page."""
    return (
        f'<section class="rank-section">'
        f"<h2>{title}</h2>"
        f'<p class="rank-sub">{sub}</p>'
        f"{body_html}"
        f"</section>"
    )
