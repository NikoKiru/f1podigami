"""Render soulmates.html — the driver-partnership leaderboard.

Shares the site's ranked table (Overdue / Unlikeliest, via ``_rows``): one
bordered table with a column-label strip and a native ``<details>`` row per
rank that expands to show the partnership's stats, the #1 duo marked only by an
accent rail. A second section surfaces the fun-fact stat cards computed from
the full 40×40 matrix. Neither section sits in a panel box — the table is the
only framed element, matching the combinations page.
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
    driver_name,
    head,
    nav,
    organization_schema,
)
from _rows import render_row, render_section, render_stat, render_table  # noqa: E402

from datalib import SoulmatePair, Soulmates, load_soulmates  # noqa: E402

OUT_PATH = ROOT / "dist" / "soulmates.html"

# Grid tracks shared by the label strip and every row face: duo, value,
# chevron.
COLS = "minmax(0,1fr) 200px 26px"


def esc(s: str) -> str:
    return html.escape(str(s))


def _who(name: str) -> str:
    """A driver named in a fact card, escaped. The facts match drivers to pairs
    on their data names, so the display name is swapped in only here."""
    return esc(driver_name(name))


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
    return sep.join(
        driver.format(full=esc(n), abbr=esc(abbr_name(n))) for n in map(driver_name, (p.a, p.b))
    )


def _pair_stats(p: SoulmatePair) -> str:
    seasons = _seasons(p)
    rate = p.count / seasons
    return (
        render_stat("Years", f"{p.firstYear}&ndash;{p.lastYear}")
        + render_stat("Seasons active", str(seasons))
        + render_stat("Per season", f"{rate:.1f}")
    )


def render_pairs(pairs: list[SoulmatePair]) -> str:
    if not pairs:
        return '<p class="rank-sub">No partnerships yet.</p>'
    rows = "".join(
        render_row(render_pair(p), str(p.count), _pair_stats(p), hero=(i == 1))
        for i, p in enumerate(pairs, 1)
    )
    return render_table(rows, value_label="Shared podiums", cols=COLS, group_label="Duo")


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
            "detail": f"<b>{_who(best_name)}</b> shared at least one podium with {best_cnt} different "
            f"drivers from the all-time top 40 — more than anyone else.",
        }
    )

    # 2. Longest active partnership. The span counts both endpoint seasons, the
    # same way the row's own "Seasons active" stat does (_seasons) — 2007-2023 is
    # 17 seasons, not 16 — so the card and the row it describes agree.
    if top_pairs:
        longest = max(top_pairs, key=_seasons)
        span = _seasons(longest)
        unit = "season" if span == 1 else "seasons"
        facts.append(
            {
                "num": str(span),
                "unit": unit,
                "label": "Longest partnership",
                "detail": f"<b>{_who(longest.a)}</b> &amp; <b>{_who(longest.b)}</b> shared podiums "
                f"across {span} {unit} ({longest.firstYear}&ndash;{longest.lastYear}), "
                f"the longest-running pairing in the top {len(top_pairs)}.",
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
                "detail": f"<b>{_who(hot.a)}</b> &amp; <b>{_who(hot.b)}</b> averaged "
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
                    f"<b>{_who(older)}</b> (peak ~{older_med}) and <b>{_who(younger)}</b> "
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
            "detail": f"Despite {least_total} career podiums, <b>{_who(least_name)}</b> shared the box "
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

    pairs_section = render_section(
        "Closest partnerships",
        "Ranked by how many World Championship podiums each duo shared &mdash; "
        f"{len(top_pairs)} partnerships drawn from the all-time top {n_drivers} drivers "
        "by career podiums.",
        render_pairs(top_pairs),
    )
    facts_section = render_section(
        "Did you know",
        f"The quirks hiding inside the full {n_drivers}&times;{n_drivers} shared-podium matrix.",
        f'<div class="sm-facts">{_render_facts(_compute_facts(soulmates))}</div>',
    )

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
        {pairs_section}

        {facts_section}

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
