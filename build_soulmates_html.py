"""Render soulmates.html — ranked pairs list + fun-fact stat cards."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from build_alignments_html import CSS as BASE_CSS

ROOT = Path(__file__).parent
SOULMATES_PATH = ROOT / "data" / "soulmates.json"
OUT_PATH = ROOT / "soulmates.html"


SOULMATES_CSS = """
/* ── page grid ───────────────────────────────────────── */
.sm-page {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 380px;
    gap: 32px;
    align-items: start;
}
@media (max-width: 960px) {
    .sm-page { grid-template-columns: 1fr; }
}

/* ── section heading ─────────────────────────────────── */
.sm-section-title {
    margin: 0 0 12px;
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.3px;
}

/* ── ranked pairs list ───────────────────────────────── */
.pl-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.pl-row {
    display: grid;
    grid-template-columns: 24px 1fr auto;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    background: var(--surface);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    transition: border-color 0.12s, background 0.12s;
}
.pl-row:hover {
    background: var(--surface-2);
    border-color: var(--border);
}
.pl-rank {
    font-size: 11px;
    color: var(--muted-dim);
    font-weight: 700;
    text-align: right;
    font-variant-numeric: tabular-nums;
}
.pl-body { min-width: 0; }
.pl-names {
    font-size: 13px;
    color: var(--text);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 5px;
}
.pl-names b { color: var(--text); font-weight: 700; }
.pl-bar-wrap {
    height: 3px;
    background: var(--surface-3);
    border-radius: 2px;
    overflow: hidden;
}
.pl-bar {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    opacity: 0.7;
    transition: opacity 0.12s;
}
.pl-row:hover .pl-bar { opacity: 1; }
.pl-meta { text-align: right; flex-shrink: 0; }
.pl-count {
    display: block;
    font-size: 17px;
    font-weight: 700;
    color: var(--accent-bright);
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
}
.pl-years {
    display: block;
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
}

/* ── fact cards ──────────────────────────────────────── */
.fact-stack {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.fact-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 14px 16px;
    transition: border-color 0.12s, background 0.12s;
}
.fact-card:hover {
    background: var(--surface-2);
    border-color: var(--border-strong);
    border-left-color: var(--accent-bright);
}
.fc-num {
    font-size: 24px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.4px;
    line-height: 1.1;
    margin-bottom: 2px;
}
.fc-num .fc-unit {
    font-size: 13px;
    font-weight: 500;
    color: var(--muted);
    margin-left: 4px;
    letter-spacing: 0;
}
.fc-label {
    font-size: 10px;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.3px;
    margin-bottom: 6px;
}
.fc-detail {
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.5;
}
.fc-detail b { color: var(--text); font-weight: 600; }
"""


def _last(name: str) -> str:
    parts = name.split()
    return parts[-1] if parts else name


def _render_pairs(pairs: list[dict]) -> str:
    if not pairs:
        return ""
    max_c = pairs[0]["count"]
    rows = []
    for i, p in enumerate(pairs, 1):
        pct = round(100 * p["count"] / max_c)
        rows.append(
            f'<li class="pl-row">'
            f'<span class="pl-rank">{i}</span>'
            f'<div class="pl-body">'
            f'  <div class="pl-names"><b>{p["a"]}</b> &amp; <b>{p["b"]}</b></div>'
            f'  <div class="pl-bar-wrap"><div class="pl-bar" style="width:{pct}%"></div></div>'
            f'</div>'
            f'<div class="pl-meta">'
            f'  <span class="pl-count">{p["count"]}</span>'
            f'  <span class="pl-years">{p["firstYear"]}&ndash;{p["lastYear"]}</span>'
            f'</div>'
            f'</li>'
        )
    return "\n".join(rows)


def _compute_facts(soulmates: dict) -> list[dict]:
    drivers   = soulmates["drivers"]
    matrix    = soulmates["matrix"]
    top_pairs = soulmates.get("topPairs", [])
    n         = len(drivers)
    names     = [d["name"] for d in drivers]
    median_by = {d["name"]: d["medianYear"] for d in drivers}

    facts = []

    # 1. Most connected driver (shares podiums with most other top-40 drivers)
    connections = [
        (sum(1 for j in range(n) if j != i and matrix[i][j] > 0), names[i])
        for i in range(n)
    ]
    best_cnt, best_name = max(connections)
    facts.append({
        "num": str(best_cnt),
        "unit": "connections",
        "label": "Most connected driver",
        "detail": f"<b>{best_name}</b> shared at least one podium with {best_cnt} different "
                  f"drivers from the all-time top 40 — more than anyone else.",
    })

    # 2. Longest active partnership
    if top_pairs:
        longest = max(top_pairs, key=lambda p: p["lastYear"] - p["firstYear"])
        span    = longest["lastYear"] - longest["firstYear"]
        facts.append({
            "num": str(span),
            "unit": "seasons",
            "label": "Longest partnership",
            "detail": f"<b>{longest['a']}</b> &amp; <b>{longest['b']}</b> shared podiums "
                      f"across {span} seasons ({longest['firstYear']}&ndash;{longest['lastYear']}), "
                      f"the longest-running pairing in the top 30.",
        })

    # 3. Most intense: highest shared podiums per active season
    if top_pairs:
        def intensity(p: dict) -> float:
            return p["count"] / max(1, p["lastYear"] - p["firstYear"] + 1)
        hot = max(top_pairs, key=intensity)
        seasons = max(1, hot["lastYear"] - hot["firstYear"] + 1)
        rate    = hot["count"] / seasons
        facts.append({
            "num": f"{rate:.1f}",
            "unit": "per season",
            "label": "Most intense rivalry",
            "detail": f"<b>{hot['a']}</b> &amp; <b>{hot['b']}</b> averaged "
                      f"{rate:.1f} shared podiums per season over their "
                      f"{seasons}-season overlap — the densest podium partnership on record.",
        })

    # 4. Biggest era gap: top-30 pair whose drivers' median career years differ most
    if top_pairs:
        def era_gap(p: dict) -> float:
            return abs(median_by.get(p["a"], 0) - median_by.get(p["b"], 0))
        cross      = max(top_pairs, key=era_gap)
        gap_years  = int(round(era_gap(cross)))
        a_med      = int(round(median_by.get(cross["a"], 0)))
        b_med      = int(round(median_by.get(cross["b"], 0)))
        if a_med < b_med:
            older, older_med, younger, younger_med = cross["a"], a_med, cross["b"], b_med
        else:
            older, older_med, younger, younger_med = cross["b"], b_med, cross["a"], a_med
        facts.append({
            "num": str(gap_years),
            "unit": "year era gap",
            "label": "Biggest cross-era connection",
            "detail": (
                f"<b>{older}</b> (peak ~{older_med}) and <b>{younger}</b> "
                f"(peak ~{younger_med}) still shared {cross['count']} podiums "
                f"despite their careers being {gap_years} years apart."
            ),
        })

    # 5. Total unique shared podium moments across all 40×40 pairs
    total = sum(matrix[i][j] for i in range(n) for j in range(i + 1, n))
    facts.append({
        "num": f"{total:,}",
        "unit": "",
        "label": "Total shared podium moments",
        "detail": f"Across all {n * (n - 1) // 2:,} possible pairings within the top {n}, "
                  f"drivers shared a podium a combined <b>{total:,}</b> times.",
    })

    # 6. Most isolated: top-40 driver with fewest connections to others in the group
    least_cnt, least_name = min(connections)
    least_total = next(d["total"] for d in drivers if d["name"] == least_name)
    facts.append({
        "num": str(least_cnt),
        "unit": "connections",
        "label": "Solo legend",
        "detail": f"Despite {least_total} career podiums, <b>{least_name}</b> shared the box "
                  f"with only {least_cnt} other driver{'s' if least_cnt != 1 else ''} "
                  f"from the top 40 &mdash; a testament to era dominance.",
    })

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
            f'</div>'
        )
    return "\n".join(cards)


def main() -> int:
    soulmates = json.loads(SOULMATES_PATH.read_text(encoding="utf-8"))

    top_pairs = soulmates.get("topPairs", [])
    top       = top_pairs[0] if top_pairs else None
    n_drivers = len(soulmates["drivers"])

    stats_html = ""
    if top:
        stats_html = f"""
        <div class="stats">
            <div class="stat">
                <div class="num">{n_drivers}</div>
                <div class="label">Drivers charted</div>
            </div>
            <div class="stat">
                <div class="num">{top["count"]} <small>shared podiums</small></div>
                <div class="label">{_last(top["a"])} &amp; {_last(top["b"])} &mdash; #1 pair</div>
            </div>
            <div class="stat">
                <div class="num">{len(top_pairs)}</div>
                <div class="label">Pairs ranked</div>
            </div>
        </div>"""

    pairs_html = _render_pairs(top_pairs)
    facts      = _compute_facts(soulmates)
    facts_html = _render_facts(facts)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<title>F1 Soulmates &middot; Podigami</title>
<style>{BASE_CSS}{SOULMATES_CSS}</style>
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html">&larr; Podium Combinations</a>
        <a href="seasons.html">Season Alignments</a>
        <a href="charts.html">Charts</a>
        <a href="soulmates.html" class="active">Soulmates</a>
    </div>
</nav>
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Podium Soulmates</h1>
        <p class="tagline">Which legends spent the most race weekends together on the box? 76 years of F1 history distilled into the partnerships that defined each era.</p>
        {stats_html}
    </div>
</header>
<main>
    <div class="container">
        <div class="sm-page">

            <section>
                <p class="sm-section-title">Ranked pairs</p>
                <ol class="pl-list">
                    {pairs_html}
                </ol>
            </section>

            <section>
                <p class="sm-section-title">Did you know</p>
                <div class="fact-stack">
                    {facts_html}
                </div>
            </section>

        </div>
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; 1950&ndash;2025
    </div>
</footer>
</body>
</html>
"""
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
