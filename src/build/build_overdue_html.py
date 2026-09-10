"""Render data/overdue.json into dist/overdue.html.

Two ranked sections — all-time near-misses and current-grid candidates. Each
renders through the shared ranked table (``_rows``): a heading and one-line
description sitting above one bordered table, with a row per rank that expands
to show its stats. Rank #1 is the same closed row, marked only by an accent
rail.

Every entry leads with the expected number of shared podiums (racesTogether ×
rates) shown as "X.Y×", which makes the overdue-ness concrete: a score of 8
means statistics expected this to happen roughly eight times already. A
"chance by now" stat converts the same number to a probability (Poisson tail:
1 − e^−score) so readers can see just how likely it should have been.
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
)
from _rows import render_row, render_section, render_stat, render_table  # noqa: E402

from datalib import OverdueTrio, load_overdue  # noqa: E402

OUT_PATH = ROOT / "dist" / "overdue.html"

# Grid tracks shared by the label strip and every row face: trio, value,
# chevron.
COLS = "minmax(0,1fr) 200px 26px"


def esc(s: str) -> str:
    return html.escape(str(s))


def format_score(score: float) -> str:
    """Expected co-podium count formatted as '8.2×'."""
    return f"{score:.1f}×"


def format_probability(score: float) -> str:
    """Probability trio would have shared a podium by now, as integer %.

    Uses the Poisson tail: P(≥1) = 1 − e^−score.
    """
    p = 1.0 - math.exp(-score)
    return f"{p * 100:.0f}%"


def render_trio(names: list[str]) -> str:
    """Three drivers with full and abbreviated forms for CSS to swap on narrow screens."""
    sep = '<span class="sep">/</span>'
    driver = (
        '<span class="oddriver">'
        '<span class="dn-full">{full}</span>'
        '<span class="dn-abbr" aria-hidden="true">{abbr}</span>'
        "</span>"
    )
    return sep.join(
        driver.format(full=esc(n), abbr=esc(abbr_name(n))) for n in map(driver_name, names)
    )


def _rates_cells(e: OverdueTrio) -> str:
    return " &middot; ".join(f"{p.rate * 100:.0f}%" for p in e.perDriver)


def _stats(e: OverdueTrio) -> str:
    return (
        render_stat("Podium rates", _rates_cells(e))
        + render_stat("Raced together", f"{e.racesTogether}&times;")
        + render_stat("Chance by now", format_probability(e.score))
    )


def render_row_entry(e: OverdueTrio, hero: bool = False) -> str:
    """One leaderboard row. ``hero`` marks the top entry with an accent rail."""
    return render_row(render_trio(e.names), format_score(e.score), _stats(e), hero=hero)


def render_cards(entries: list[OverdueTrio]) -> str:
    if not entries:
        return '<p class="rank-sub">No candidates.</p>'
    rows = "".join(render_row_entry(e, hero=(i == 1)) for i, e in enumerate(entries, 1))
    return render_table(rows, value_label="Expected co-podiums", cols=COLS)


def section(title: str, sub: str, entries: list[OverdueTrio]) -> str:
    """One ranked section: heading, one-line description, table. No box —
    the table is the only framed element, matching the combinations page."""
    return render_section(title, sub, render_cards(entries))


def main() -> int:
    data = load_overdue()
    as_of = data.asOf

    all_time = section(
        "All-time near-misses",
        "Trios from across F1 history that raced together often and each podiumed often "
        "&mdash; yet never all three on the same podium. Expected co-podiums = races together "
        "&times; each driver&rsquo;s career podium rate.",
        data.allTime,
    )
    grid = section(
        "Current grid &mdash; still possible",
        "The most overdue trios among this season&rsquo;s drivers. These could still happen.",
        data.currentGrid,
    )

    page = f"""{
        head(
            "F1 Overdue Podiums — Trios That Should Have Happened",
            "podigami.css",
            description="F1 podium history's missing trios: drivers who raced together dozens of times, each a regular podium finisher, yet never all three on the rostrum at once.",
            page_path="overdue.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Overdue Podiums", "overdue.html"),
            ],
        )
    }
<body>
{nav("overdue.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Overdue Podiums</h1>
        <p class="tagline">The podium that <em>should</em> have happened but never did &mdash; trios who raced together time and again, each a regular podium finisher, yet never once all three on the rostrum together.</p>
    </div>
</header>
<main>
    <div class="container">
        {all_time}
        {grid}
        <p class="as-of">Expected co-podiums = races together &times; each driver&rsquo;s career podium rate; chance by now is the Poisson tail P(&ge;1) = 1&minus;e<sup>&minus;score</sup>. Up to date through the {
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
    print(f"  all-time: {len(data.allTime)}, current-grid: {len(data.currentGrid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
