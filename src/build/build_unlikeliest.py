"""Render data/unlikeliest.json into dist/unlikeliest.html.

The mirror of the Overdue page: podium trios that *did* happen, ranked by how
statistically unlikely they were. Every rank is a row in the shared ranked
table (``_rows.render_row``) that expands to show each driver's career podium
rate, how often they raced together, and how many times it hit. The #1 trio —
the single most improbable podium in F1 history — is the same closed row,
marked only by an accent rail.

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
    driver_name,
    head,
    nav,
    organization_schema,
    race_url,
)
from _rows import render_row, render_section, render_stat, render_table  # noqa: E402

from datalib import UnlikeliestTrio, load_race_links, load_unlikeliest  # noqa: E402

OUT_PATH = ROOT / "dist" / "unlikeliest.html"

# Grid tracks shared by the label strip and every row face: trio, odds,
# race, chevron.
COLS = "minmax(0,1fr) 110px 240px 26px"


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
    swap to 'E. Ocon' on narrow screens (matching the combos table). Each name
    carries the "/" after it, so inline a trio wraps only after a separator,
    and on a phone it stacks one name per line."""
    sep = '<span class="sep">/</span>'
    driver = (
        '<span class="undriver">'
        '<span class="dn-full">{full}</span>'
        '<span class="dn-abbr" aria-hidden="true">{abbr}</span>'
        "{sep}</span>"
    )
    names = [driver_name(n) for n in names]
    return "".join(
        driver.format(full=esc(n), abbr=esc(abbr_name(n)), sep=sep if i < len(names) - 1 else "")
        for i, n in enumerate(names)
    )


def _rates_cells(e: UnlikeliestTrio) -> str:
    return " &middot; ".join(f"{p.rate * 100:.0f}%" for p in e.perDriver)


def _race_link(e: UnlikeliestTrio, links: dict | None = None) -> str:
    """The race, split into year + name so it picks up the combinations table's
    "Last seen" treatment (bold year, dimmed name). The same fragment is reused
    in the expanded drawer on phones."""
    h = e.happened
    url = race_url(links or {}, h.season, h.round, h.raceName)
    label = f"{esc(h.season)} {esc(h.raceName)}"
    return (
        f'<a class="race-link" href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener" title="{label} &mdash; race report">'
        f'<span class="year">{esc(h.season)}</span>'
        f'<span class="race-name">{esc(h.raceName)}</span>'
        f"</a>"
    )


def _stats(e: UnlikeliestTrio, race: str) -> str:
    """Stat cells for the expanded drawer. The race repeats here because CSS
    moves it off the row face and into the drawer on phones."""
    return (
        render_stat("Podium rates", _rates_cells(e))
        + render_stat("Raced together", f"{e.racesTogether}&times;")
        + render_stat("Times it happened", str(e.count))
        + render_stat("Race", race, extra_class="rr-stat-race")
    )


def render_row_entry(e: UnlikeliestTrio, links: dict | None = None, hero: bool = False) -> str:
    """One leaderboard row. ``hero`` marks the top entry with an accent rail."""
    race = _race_link(e, links)
    return render_row(
        render_trio(e.names),
        format_odds(e.score),
        _stats(e, race),
        race_html=race,
        hero=hero,
    )


def render_cards(entries: list[UnlikeliestTrio], links: dict | None = None) -> str:
    if not entries:
        return '<p class="rank-sub">No trios.</p>'
    rows = "".join(render_row_entry(e, links, hero=(i == 1)) for i, e in enumerate(entries, 1))
    # "Odds" rather than "Chance it ever happened": the label strip truncates
    # anything wider than its track, and the combinations table sets the
    # precedent for short column labels.
    return render_table(
        rows,
        value_label="Odds",
        cols=COLS,
        race_label="Race",
    )


def main() -> int:
    data = load_unlikeliest()
    as_of = data.asOf
    body = render_section(
        "Against the odds",
        "Every trio ranked by how improbable their podium was &mdash; the odds they would "
        "<em>ever</em> share one, from each driver&rsquo;s career podium rate and how often "
        "the three raced together.",
        render_cards(data.trios, load_race_links()),
    )

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
