"""Render data/combos.json into dist/combos.html (the full combinations table).

This is the former landing page; index.html is now the podigami predictor
(build_podigami_html.py). Content is unchanged — only the nav and output path.
"""

from __future__ import annotations

import itertools
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMBOS_PATH = ROOT / "data" / "combos.json"
PODIUMS_PATH = ROOT / "data" / "podiums.json"
OUT_PATH = ROOT / "dist" / "combos.html"


def wiki_url(season: str, race_name: str) -> str:
    """Wikipedia race-report URL — the same source the Ergast/Jolpica API cites."""
    title = f"{season} {race_name}".replace(" ", "_")
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title)


def render_race_pills(races: list[dict]) -> str:
    """Group races by season; each season gets a row with year + race pills."""
    import html
    races_sorted = sorted(races, key=lambda r: (int(r["season"]), int(r["round"])))
    parts: list[str] = []
    for season, group in itertools.groupby(races_sorted, key=lambda r: r["season"]):
        group_list = list(group)
        pills = "".join(
            f'<a class="race-pill" href="{html.escape(wiki_url(r["season"], r["raceName"]), quote=True)}"'
            f' target="_blank" rel="noopener"'
            f' title="{html.escape(r["season"] + " " + r["raceName"], quote=True)} &mdash; race report">'
            f'<span class="round">R{html.escape(r["round"])}</span>'
            f'{html.escape(short_race_name(r["raceName"]))}'
            f'</a>'
            for r in group_list
        )
        ct = len(group_list)
        ct_html = f'<span class="ct">x{ct}</span>' if ct > 1 else ""
        parts.append(
            f'<div class="season-row">'
            f'<div class="season-label">{html.escape(season)}{ct_html}</div>'
            f'<div class="race-list">{pills}</div>'
            f'</div>'
        )
    return "".join(parts)


def short_race_name(name: str) -> str:
    """Trim "Grand Prix" -> "GP" for compact pill display."""
    if name.endswith(" Grand Prix"):
        return name[: -len(" Grand Prix")] + " GP"
    return name


def render_combo(rank: int, combo: dict) -> str:
    import html
    drivers_html = '<span class="sep">/</span>'.join(
        f'<span class="driver">{html.escape(d)}</span>' for d in combo["drivers"]
    )
    drivers_data = " | ".join(combo["drivers"]).lower()
    last = combo["lastRace"]
    last_html = (
        f'<span class="year">{html.escape(last["season"])}</span>'
        f'<span class="race-name">{html.escape(last["raceName"])}</span>'
    )
    n = combo["count"]

    combo_row = (
        f'<tr class="combo" data-count="{n}"'
        f' data-last="{combo["lastRaceKey"]}"'
        f' data-drivers="{html.escape(drivers_data, quote=True)}">'
        f'<td class="rank">{rank}</td>'
        f'<td class="drivers">{drivers_html}</td>'
        f'<td class="count">{n}</td>'
        f'<td class="last">{last_html}</td>'
        f'<td class="expand"><span class="chev">&#9662;</span></td>'
        f'</tr>'
    )
    detail_row = (
        f'<tr class="detail">'
        f'<td colspan="5">'
        f'<div class="detail-inner">{render_race_pills(combo["races"])}</div>'
        f'</td></tr>'
    )
    return combo_row + detail_row


def main() -> int:
    combos = json.loads(COMBOS_PATH.read_text(encoding="utf-8"))
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))

    seasons = sorted({int(p["season"]) for p in podiums})
    total_podiums = len(podiums)
    unique_combos = len(combos)
    season_min, season_max = seasons[0], seasons[-1]

    rows_html = "\n".join(render_combo(i, c) for i, c in enumerate(combos, 1))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<title>F1 Podium Combinations - {season_min}-{season_max}</title>
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="index.css">
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html">Podigami</a>
        <a href="combos.html" class="active">Combinations</a>
        <a href="seasons.html">Season Alignments</a>
        <a href="charts.html">Charts</a>
        <a href="soulmates.html">Soulmates &rarr;</a>
    </div>
</nav>
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Podium Combinations</h1>
        <p class="tagline">Every unique trio that has shared an F1 World Championship podium since 1950 &mdash; order doesn't matter, only the set.</p>
        <div class="stats">
            <div class="stat"><div class="num">{total_podiums:,}</div><div class="label">Races</div></div>
            <div class="stat"><div class="num">{unique_combos:,}</div><div class="label">Unique Combos</div></div>
            <div class="stat"><div class="num">{season_min}&ndash;{season_max}</div><div class="label">Seasons</div></div>
        </div>
    </div>
</header>
<main>
    <div class="container">
        <div class="controls">
            <div class="filters">
                <div class="search-wrap">
                    <input data-filter type="search" placeholder="Driver 1..." aria-label="Driver 1 filter">
                </div>
                <div class="search-wrap">
                    <input data-filter type="search" placeholder="Driver 2..." aria-label="Driver 2 filter">
                </div>
                <div class="search-wrap">
                    <input data-filter type="search" placeholder="Driver 3..." aria-label="Driver 3 filter">
                </div>
                <button id="clear-filters" type="button" class="clear-btn" disabled>Clear</button>
                <div class="filter-group mobile-sort">
                    <label for="mobile-sort">Sort</label>
                    <select id="mobile-sort">
                        <option value="count-desc">Count (high &rarr; low)</option>
                        <option value="count-asc">Count (low &rarr; high)</option>
                        <option value="last-desc">Last seen (newest)</option>
                        <option value="last-asc">Last seen (oldest)</option>
                        <option value="drivers-asc">Drivers (A &rarr; Z)</option>
                        <option value="drivers-desc">Drivers (Z &rarr; A)</option>
                    </select>
                </div>
            </div>
            <div class="hint">
                Showing <strong id="visible-count">{unique_combos}</strong> of <span id="total-count">{unique_combos}</span>
                &middot; each field matches one distinct driver (AND)
                &middot; click a row to expand
            </div>
        </div>
        <div class="table-wrap">
            <table>
                <colgroup>
                    <col class="col-rank">
                    <col class="col-drivers">
                    <col class="col-count">
                    <col class="col-last">
                    <col class="col-expand">
                </colgroup>
                <thead>
                    <tr>
                        <th>#</th>
                        <th data-sort="drivers">Drivers <span class="sort-ind">&#9662;</span></th>
                        <th data-sort="count">Count <span class="sort-ind">&#9662;</span></th>
                        <th data-sort="last">Last seen <span class="sort-ind">&#9662;</span></th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
            <div id="empty-state" class="empty-state" style="display:none">
                <strong>No matches</strong>
                Try a different driver name.
            </div>
        </div>
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; Includes Indy 500 (1950&ndash;1960) &middot; Excludes Sprint races
    </div>
</footer>
<script src="index.js"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  rendered {unique_combos} combos covering {total_podiums} races ({season_min}-{season_max})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
