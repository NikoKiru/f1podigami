"""Render data/unlikeliest.json into dist/unlikeliest.html.

The mirror of the Overdue page: podium trios that *did* happen, ranked by how
statistically unlikely they were. The #1 trio (the single most improbable
podium in F1 history) is a full hero card; every other rank is a compact
leaderboard row (shared ``_rows.render_row``) that expands to show each
driver's career podium rate, how often they raced together, and how many
times it hit.

The headline "1 in N" is the odds the trio would *ever* share a podium, derived
from the expected co-podium count s = racesTogether x rates via the Poisson
tail P(at least once) = 1 - e^-s. More shared races push the odds up (more
chances), so a trio that did it in few shared races is the bigger fluke.
"""

from __future__ import annotations

import html
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _layout import (  # noqa: E402
    FOOTER,
    abbr_name,
    asset,
    breadcrumb_schema,
    head,
    nav,
    organization_schema,
    race_url,
)
from _rows import render_row  # noqa: E402

from datalib import UnlikeliestTrio, load_race_links, load_unlikeliest  # noqa: E402

OUT_PATH = ROOT / "dist" / "unlikeliest.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def ever_prob(score: float) -> float:
    """Probability the trio would share a podium at least once, from the expected
    co-podium count ``score`` (Poisson tail): P(>=1) = 1 - e^-score."""
    return 1.0 - math.exp(-score)


def _round_sig2(n: float) -> int:
    """Round to 2 significant figures (e.g. 154 -> 150, 1234 -> 1200); integers
    below 10 are returned as-is so we never print '1 in 5.8'."""
    if n < 10:
        return round(n)
    factor = 10 ** (math.floor(math.log10(n)) - 1)
    return int(round(n / factor) * factor)


def format_odds(score: float) -> str:
    """'1 in N' odds the trio would ever share a podium."""
    p = ever_prob(score)
    n = _round_sig2(1.0 / p) if p > 0 else 0
    return f"1 in {n:,}"


def render_trio(names: list[str]) -> str:
    """The three drivers, each carrying a full and an abbreviated form so CSS can
    swap to 'E. Ocon' on narrow screens (matching the combos table)."""
    sep = '<span class="sep">&middot;</span>'
    driver = (
        '<span class="undriver">'
        '<span class="dn-full">{full}</span>'
        '<span class="dn-abbr" aria-hidden="true">{abbr}</span>'
        "</span>"
    )
    return sep.join(driver.format(full=esc(n), abbr=esc(abbr_name(n))) for n in names)


def _rates_cells(e: UnlikeliestTrio) -> str:
    return " &middot; ".join(f"{p.rate * 100:.0f}%" for p in e.perDriver)


def _race_link(e: UnlikeliestTrio, links: dict | None = None) -> str:
    h = e.happened
    url = race_url(links or {}, h.season, h.round, h.raceName)
    label = f"{esc(h.season)} {esc(h.raceName)}"
    return (
        f'<a class="race-link" href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener" title="{label} &mdash; race report">{label}</a>'
    )


def _stat(label: str, value: str) -> str:
    return (
        f'<div class="un-stat">'
        f'<span class="un-stat-label">{label}</span>'
        f'<span class="un-stat-val">{value}</span>'
        f"</div>"
    )


def render_card(
    rank: int, e: UnlikeliestTrio, hero: bool = False, links: dict | None = None
) -> str:
    """One uniform card. ``hero`` makes it the larger, accented #1 variant."""
    cls = "uncard uncard-hero" if hero else "uncard"
    drivers = f'<div class="un-drivers">{render_trio(e.names)}</div>'
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Times it happened", str(e.count))
    )
    return (
        f'<li class="{cls}">'
        f'<div class="un-top">'
        f'<span class="un-rank">{rank}</span>'
        f'<span class="un-race">{_race_link(e, links)}</span>'
        f"</div>"
        f"{drivers}"
        f'<div class="un-odds">'
        f'<span class="un-odds-num">{format_odds(e.score)}</span>'
        f'<span class="un-odds-label">chance it ever happened</span>'
        f"</div>"
        f'<div class="un-stats">{stats}</div>'
        f"</li>"
    )


def render_row_entry(rank: int, e: UnlikeliestTrio, links: dict | None = None) -> str:
    """One compact leaderboard row for ranks below the hero. The race link sits
    on the row face on desktop and repeats in the stats panel, where CSS shows
    it on phones instead."""
    race = _race_link(e, links)
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Times it happened", str(e.count))
        + f'<div class="un-stat rr-stat-race">'
        f'<span class="un-stat-label">Race</span>'
        f'<span class="un-stat-val">{race}</span>'
        f"</div>"
    )
    return render_row(rank, render_trio(e.names), format_odds(e.score), stats, race_html=race)


def render_cards(entries: list[UnlikeliestTrio], links: dict | None = None) -> str:
    if not entries:
        return '<p class="panel-sub">No trios.</p>'
    hero = render_card(1, entries[0], hero=True, links=links)
    rows = "".join(render_row_entry(i, e, links) for i, e in enumerate(entries[1:], 2))
    return f'<ol class="rank-list">{hero}{rows}</ol>'


def main() -> int:
    data = load_unlikeliest()
    as_of = data.asOf
    body = render_cards(data.trios, load_race_links())

    page = f"""{
        head(
            "F1 Unlikeliest Podiums — Most Improbable Trios Ever",
            "podigami.css",
            description="The most statistically improbable podiums in F1 history: trios of drivers who rarely podiumed, yet once all three shared the rostrum against the odds.",
            page_path="unlikeliest.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Unlikeliest Podiums", "unlikeliest.html"),
            ],
        )
    }
<body>
{nav("unlikeliest.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Unlikeliest Podiums</h1>
        <p class="tagline">The podiums that <em>almost shouldn't have happened</em> &mdash; trios who barely podiumed, or barely raced together, yet once all three lined up on the rostrum against the odds.</p>
    </div>
</header>
<main>
    <div class="container">
        {body}
        <p class="as-of">The odds are the chance a trio would <em>ever</em> share a podium, from each driver's career podium rate and how often the three raced together (more shared races &rarr; better odds). A long-shot that happened anyway is the surprise. Up to date through the {
        esc(as_of.season)
    } {esc(as_of.raceName)} (round {esc(as_of.round)}).</p>
    </div>
</main>
{FOOTER}
<script src="{asset("theme.js")}"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  trios: {len(data.trios)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
