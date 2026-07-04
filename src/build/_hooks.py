"""Discovery hook cards: cross-page teasers with a live build-time stat.

A hook card is a whole-card link: kicker label, one stat line computed from
committed data, and an arrow CTA. Stat builders are pure functions over
already-loaded datalib models (callers do the I/O); every builder tolerates
``None`` or empty data by dropping the stat line, so a data gap can never
break the build.
"""

from __future__ import annotations

import html


def esc(s) -> str:
    return html.escape(str(s))


def _surname(name: str) -> str:
    parts = str(name).split()
    return parts[-1] if parts else str(name)


def _surnames(names) -> str:
    """Escaped "A / B / C" surname line for a trio."""
    return " / ".join(esc(_surname(n)) for n in names)


def hook_card(kicker: str, stat_html: str, href: str, cta: str) -> str:
    """One teaser card. ``stat_html`` is pre-escaped/trusted HTML; "" omits it."""
    stat = f'<span class="hook-stat">{stat_html}</span>' if stat_html else ""
    return (
        f'<a class="hook-card" href="{esc(href)}">'
        f'<span class="hook-kicker">{esc(kicker)}</span>'
        f"{stat}"
        f'<span class="hook-cta">{esc(cta)}'
        f' <span class="hook-arrow" aria-hidden="true">&rarr;</span></span>'
        f"</a>"
    )


def combos_hook(total_combos: int, since_year) -> str:
    stat = ""
    if total_combos:
        stat = (
            f"<b>{total_combos:,}</b> unique podium trios since {esc(since_year)}"
            f" &mdash; every single one, sortable"
        )
    return hook_card("All the combinations", stat, "combos.html", "Browse them all")


def soulmates_hook(soulmates) -> str:
    stat = ""
    if soulmates is not None and soulmates.topPairs:
        p = soulmates.topPairs[0]
        stat = (
            f"<b>{esc(p.a)} &amp; {esc(p.b)}</b> shared the podium"
            f" <b>{p.count}</b> times &mdash; F1&rsquo;s tightest duo"
        )
    return hook_card("Podium soulmates", stat, "soulmates.html", "See every partnership")


def overdue_hook(overdue) -> str:
    stat = ""
    if overdue is not None and overdue.allTime:
        t = overdue.allTime[0]
        stat = (
            f"<b>{_surnames(t.names)}</b>: {t.racesTogether} races together,"
            f" never all three on the podium"
        )
    return hook_card("Overdue trios", stat, "overdue.html", "Who's due next")


def unlikeliest_hook(unlikeliest) -> str:
    stat = ""
    if unlikeliest is not None and unlikeliest.trios:
        t = unlikeliest.trios[0]
        stat = (
            f"The most improbable podium ever: <b>{_surnames(t.names)}</b>,"
            f" {esc(t.happened.raceName)} {esc(t.happened.season)}"
        )
    return hook_card("Unlikeliest podiums", stat, "unlikeliest.html", "See the longest shots")


def explore_grid() -> str:
    """End-of-page hub: every other page, one line each (no stats — the in-flow
    hooks carry those; repeating them here would read as a glitch)."""
    cards = [
        hook_card(
            "Combinations",
            "Every unique podium trio in F1 history &mdash; sortable, searchable.",
            "combos.html",
            "Browse them all",
        ),
        hook_card(
            "Overdue",
            "Trios that keep almost happening &mdash; who&rsquo;s been waiting longest.",
            "overdue.html",
            "Who's due next",
        ),
        hook_card(
            "Unlikeliest",
            "The podiums that defied the odds the hardest.",
            "unlikeliest.html",
            "See the longest shots",
        ),
        hook_card(
            "Soulmates",
            "Which drivers keep meeting on the podium.",
            "soulmates.html",
            "See every partnership",
        ),
    ]
    return (
        '<section class="panel explore"><h2>Keep exploring</h2>'
        f'<div class="explore-grid">{"".join(cards)}</div></section>'
    )
