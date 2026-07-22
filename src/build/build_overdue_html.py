"""Render data/overdue.json into dist/overdue.html.

Two ranked sections — all-time near-misses and current-grid candidates. In
each, the #1 trio is a full hero card and every other rank is a compact
leaderboard row (shared ``_rows.render_row``) that expands to show its stats.
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
from _layout import FOOTER, abbr_name, asset, head, nav  # noqa: E402
from _rows import render_row  # noqa: E402

from datalib import OverdueTrio, load_overdue  # noqa: E402

OUT_PATH = ROOT / "dist" / "overdue.html"


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
    sep = '<span class="sep">&middot;</span>'
    driver = (
        '<span class="oddriver">'
        '<span class="dn-full">{full}</span>'
        '<span class="dn-abbr" aria-hidden="true">{abbr}</span>'
        "</span>"
    )
    return sep.join(driver.format(full=esc(n), abbr=esc(abbr_name(n))) for n in names)


def _rates_cells(e: OverdueTrio) -> str:
    return " &middot; ".join(f"{p.rate * 100:.0f}%" for p in e.perDriver)


def _stat(label: str, value: str) -> str:
    return (
        f'<div class="od-stat">'
        f'<span class="od-stat-label">{label}</span>'
        f'<span class="od-stat-val">{value}</span>'
        f"</div>"
    )


def render_card(rank: int, e: OverdueTrio, hero: bool = False) -> str:
    """One full card. ``hero`` makes it the larger, accented #1 variant."""
    cls = "odcard odcard-hero" if hero else "odcard"
    drivers = f'<div class="od-drivers">{render_trio(e.names)}</div>'
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Chance by now", format_probability(e.score))
    )
    return (
        f'<li class="{cls}">'
        f'<div class="od-top">'
        f'<span class="od-rank">{rank}</span>'
        f"</div>"
        f"{drivers}"
        f'<div class="od-score">'
        f'<span class="od-score-num">{format_score(e.score)}</span>'
        f'<span class="od-score-label">expected co-podiums</span>'
        f"</div>"
        f'<div class="od-stats">{stats}</div>'
        f"</li>"
    )


def render_row_entry(rank: int, e: OverdueTrio) -> str:
    """One compact leaderboard row for ranks below the hero."""
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Chance by now", format_probability(e.score))
    )
    return render_row(rank, render_trio(e.names), format_score(e.score), stats)


def render_cards(entries: list[OverdueTrio]) -> str:
    if not entries:
        return '<p class="panel-sub">No candidates.</p>'
    hero = render_card(1, entries[0], hero=True)
    rows = "".join(render_row_entry(i, e) for i, e in enumerate(entries[1:], 2))
    return f'<ol class="rank-list">{hero}{rows}</ol>'


def panel(title: str, sub: str, entries: list[OverdueTrio]) -> str:
    """One collapsible ranked section.

    A native ``<details open>`` so the header toggles the whole section with no
    JS.
    """
    return (
        f'<details class="panel od-panel" open>'
        f'<summary class="panel-head">'
        f"<h2>{title}</h2>"
        f'<span class="panel-chev" aria-hidden="true">&#9662;</span>'
        f"</summary>"
        f'<p class="panel-sub">{sub}</p>'
        f"{render_cards(entries)}"
        f"</details>"
    )


def main() -> int:
    data = load_overdue()
    as_of = data.asOf

    all_time = panel(
        "All-time near-misses",
        "Trios from across F1 history that raced together often and each podiumed often "
        "&mdash; yet never all three on the same podium. Expected co-podiums = races together "
        "&times; each driver&rsquo;s career podium rate.",
        data.allTime,
    )
    grid = panel(
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
