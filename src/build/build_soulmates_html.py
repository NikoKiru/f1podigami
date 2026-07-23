"""Render soulmates.html — the driver-partnership leaderboard.

Shares the site's ranked-list chrome (Overdue / Unlikeliest): the #1 duo is a
full hero card and every rank below it is a compact native ``<details>`` row
(``_rows.render_row``) that expands to show the partnership's stats. A second
panel surfaces the fun-fact stat cards computed from the full 40×40 matrix.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _layout import (  # noqa: E402  (needs the sys.path entry above)
    FOOTER,
    abbr_name,
    asset,
    breadcrumb_schema,
    head,
    nav,
    organization_schema,
)
from _rows import render_row  # noqa: E402

from datalib import SoulmatePair, Soulmates, load_soulmates  # noqa: E402

OUT_PATH = ROOT / "dist" / "soulmates.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def _seasons(p: SoulmatePair) -> int:
    """Seasons the pairing spanned, inclusive of both endpoints."""
    return p.lastYear - p.firstYear + 1


def render_pair(p: SoulmatePair) -> str:
    """The two drivers, each carrying a full and an abbreviated form so CSS can
    swap to 'L. Hamilton' on narrow screens (matching every other page)."""
    sep = '<span class="sep">/</span>'
    driver = (
        '<span class="smdriver">'
        '<span class="dn-full">{full}</span>'
        '<span class="dn-abbr" aria-hidden="true">{abbr}</span>'
        "</span>"
    )
    return sep.join(driver.format(full=esc(n), abbr=esc(abbr_name(n))) for n in (p.a, p.b))


def _stat(label: str, value: str) -> str:
    return (
        f'<div class="sm-stat">'
        f'<span class="sm-stat-label">{label}</span>'
        f'<span class="sm-stat-val">{value}</span>'
        f"</div>"
    )


def _pair_stats(p: SoulmatePair) -> str:
    seasons = _seasons(p)
    rate = p.count / seasons
    return (
        _stat("Years", f"{p.firstYear}&ndash;{p.lastYear}")
        + _stat("Seasons active", str(seasons))
        + _stat("Per season", f"{rate:.1f}")
    )


def render_hero(p: SoulmatePair) -> str:
    """The #1 pairing as the larger, accented hero card (mirrors Overdue)."""
    return (
        '<li class="smcard smcard-hero">'
        '<div class="sm-top"><span class="sm-rank">1</span></div>'
        f'<div class="sm-drivers">{render_pair(p)}</div>'
        f'<div class="sm-count">'
        f'<span class="sm-count-num">{p.count}</span>'
        f'<span class="sm-count-label">shared podiums</span>'
        f"</div>"
        f'<div class="sm-stats">{_pair_stats(p)}</div>'
        "</li>"
    )


def render_pairs(pairs: list[SoulmatePair]) -> str:
    if not pairs:
        return '<p class="panel-sub">No partnerships yet.</p>'
    hero = render_hero(pairs[0])
    rows = "".join(
        render_row(i, render_pair(p), str(p.count), _pair_stats(p))
        for i, p in enumerate(pairs[1:], 2)
    )
    return f'<ol class="rank-list">{hero}{rows}</ol>'


def _compute_facts(soulmates: Soulmates) -> list[dict]:
    drivers = soulmates.drivers
    matrix = soulmates.matrix
    top_pairs = soulmates.topPairs
    n = len(drivers)
    names = [d.name for d in drivers]
    median_by = {d.name: d.medianYear for d in drivers}

    facts = []

    # 1. Most connected driver (shares podiums with most other top-40 drivers)
    connections = [
        (sum(1 for j in range(n) if j != i and matrix[i][j] > 0), names[i]) for i in range(n)
    ]
    best_cnt, best_name = max(connections)
    facts.append(
        {
            "num": str(best_cnt),
            "unit": "connections",
            "label": "Most connected driver",
            "detail": f"<b>{esc(best_name)}</b> shared at least one podium with {best_cnt} different "
            f"drivers from the all-time top 40 — more than anyone else.",
        }
    )

    # 2. Longest active partnership
    if top_pairs:
        longest = max(top_pairs, key=lambda p: p.lastYear - p.firstYear)
        span = longest.lastYear - longest.firstYear
        facts.append(
            {
                "num": str(span),
                "unit": "seasons",
                "label": "Longest partnership",
                "detail": f"<b>{esc(longest.a)}</b> &amp; <b>{esc(longest.b)}</b> shared podiums "
                f"across {span} seasons ({longest.firstYear}&ndash;{longest.lastYear}), "
                f"the longest-running pairing in the top 30.",
            }
        )

    # 3. Most intense: highest shared podiums per active season
    if top_pairs:

        def intensity(p: SoulmatePair) -> float:
            return p.count / max(1, p.lastYear - p.firstYear + 1)

        hot = max(top_pairs, key=intensity)
        seasons = max(1, hot.lastYear - hot.firstYear + 1)
        rate = hot.count / seasons
        facts.append(
            {
                "num": f"{rate:.1f}",
                "unit": "per season",
                "label": "Most intense rivalry",
                "detail": f"<b>{esc(hot.a)}</b> &amp; <b>{esc(hot.b)}</b> averaged "
                f"{rate:.1f} shared podiums per season over their "
                f"{seasons}-season overlap — the densest podium partnership on record.",
            }
        )

    # 4. Biggest era gap: top-30 pair whose drivers' median career years differ most
    if top_pairs:

        def era_gap(p: SoulmatePair) -> float:
            return abs(median_by.get(p.a, 0) - median_by.get(p.b, 0))

        cross = max(top_pairs, key=era_gap)
        gap_years = int(round(era_gap(cross)))
        a_med = int(round(median_by.get(cross.a, 0)))
        b_med = int(round(median_by.get(cross.b, 0)))
        if a_med < b_med:
            older, older_med, younger, younger_med = cross.a, a_med, cross.b, b_med
        else:
            older, older_med, younger, younger_med = cross.b, b_med, cross.a, a_med
        facts.append(
            {
                "num": str(gap_years),
                "unit": "year era gap",
                "label": "Biggest cross-era connection",
                "detail": (
                    f"<b>{esc(older)}</b> (peak ~{older_med}) and <b>{esc(younger)}</b> "
                    f"(peak ~{younger_med}) still shared {cross.count} podiums "
                    f"despite their careers being {gap_years} years apart."
                ),
            }
        )

    # 5. Total unique shared podium moments across all 40×40 pairs
    total = sum(matrix[i][j] for i in range(n) for j in range(i + 1, n))
    facts.append(
        {
            "num": f"{total:,}",
            "unit": "",
            "label": "Total shared podium moments",
            "detail": f"Across all {n * (n - 1) // 2:,} possible pairings within the top {n}, "
            f"drivers shared a podium a combined <b>{total:,}</b> times.",
        }
    )

    # 6. Most isolated: top-40 driver with fewest connections to others in the group
    least_cnt, least_name = min(connections)
    least_total = next(d.total for d in drivers if d.name == least_name)
    facts.append(
        {
            "num": str(least_cnt),
            "unit": "connections",
            "label": "Solo legend",
            "detail": f"Despite {least_total} career podiums, <b>{esc(least_name)}</b> shared the box "
            f"with only {least_cnt} other driver{'s' if least_cnt != 1 else ''} "
            f"from the top 40 &mdash; a testament to era dominance.",
        }
    )

    return facts


def _render_facts(facts: list[dict]) -> str:
    cards = []
    for f in facts:
        unit_html = f' <span class="fc-unit">{f["unit"]}</span>' if f["unit"] else ""
        cards.append(
            f'<div class="fact-card">'
            f'  <div class="fc-label">{f["label"]}</div>'
            f'  <div class="fc-num">{f["num"]}{unit_html}</div>'
            f'  <div class="fc-detail">{f["detail"]}</div>'
            f"</div>"
        )
    return "\n".join(cards)


def main() -> int:
    soulmates = load_soulmates()

    top_pairs = soulmates.topPairs
    n_drivers = len(soulmates.drivers)

    pairs_html = render_pairs(top_pairs)
    facts_html = _render_facts(_compute_facts(soulmates))

    page = f"""{
        head(
            "F1 Podium Partnerships — Drivers Who Shared the Rostrum",
            "podigami.css",
            description="F1 podium history by partnership: which drivers spent the most race weekends together on the rostrum across 76 years of Formula 1.",
            page_path="soulmates.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Podium Partnerships", "soulmates.html"),
            ],
        )
    }
<body>
{nav("soulmates.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Podium Soulmates</h1>
        <p class="tagline">Which legends spent the most race weekends together on the box? 76 years of F1 history distilled into the partnerships that defined each era.</p>
    </div>
</header>
<main>
    <div class="container">
        <section class="panel">
            <h2>Closest partnerships</h2>
            <p class="panel-sub">Ranked by how many World Championship podiums each duo shared &mdash; {
        len(top_pairs)
    } partnerships drawn from the all-time top {n_drivers} drivers by career podiums.</p>
            {pairs_html}
        </section>

        <section class="panel">
            <h2>Did you know</h2>
            <p class="panel-sub">The quirks hiding inside the full {n_drivers}&times;{
        n_drivers
    } shared-podium matrix.</p>
            <div class="sm-facts">
                {facts_html}
            </div>
        </section>

        <p class="as-of">Shared podiums count every World Championship race where both drivers finished in the top three, across all F1 rounds since 1950. The field is the all-time top {
        n_drivers
    } drivers by career podiums.</p>
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
