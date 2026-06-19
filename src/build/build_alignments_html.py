"""Render data/alignments.json into seasons.html."""

from __future__ import annotations

import html
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALIGNMENTS_PATH = ROOT / "data" / "alignments.json"
OUT_PATH = ROOT / "dist" / "seasons.html"


def driver_abbrev(name: str) -> str:
    """Last-name first-3 letters, uppercase ASCII. Schumachers disambiguated as MSC/RSC."""
    _ABBREV_OVERRIDES: dict[str, str] = {
        "Michael Schumacher": "MSC",
        "Ralf Schumacher": "RSC",
    }
    if name in _ABBREV_OVERRIDES:
        return _ABBREV_OVERRIDES[name]
    parts = name.split()
    last = parts[-1] if parts else name
    folded = "".join(c for c in unicodedata.normalize("NFKD", last) if not unicodedata.combining(c))
    return folded[:3].upper()


def render_champ_list(drivers: list[dict]) -> str:
    """Top 5 visible, rest hidden under toggle."""
    visible = drivers[:5]
    hidden = drivers[5:]
    items = "".join(
        f'<li><span class="driver-name">{html.escape(d["name"])}</span>'
        f'<span class="points">{html.escape(str(d["points"]))} pts</span></li>'
        for d in visible
    )
    extra = "".join(
        f'<li class="champ-list-extra"><span class="driver-name">{html.escape(d["name"])}</span>'
        f'<span class="points">{html.escape(str(d["points"]))} pts</span></li>'
        for d in hidden
    )
    toggle = ""
    if hidden:
        n = len(hidden)
        label = f"Show {n} more"
        toggle = f'<button class="champ-toggle" data-label="{html.escape(label, quote=True)}">{html.escape(label)}</button>'
    return (
        f'<ol class="champ-list">{items}{extra}</ol>{toggle}'
    )


def render_match_drivers(drivers: list[dict]) -> str:
    if not drivers:
        return '<span style="color:var(--muted-dim)">—</span>'
    return '<span class="sep">/</span>'.join(
        f'<span class="dr" title="{html.escape(d["name"])}">{html.escape(driver_abbrev(d["name"]))}</span>'
        for d in drivers
    )


def render_match_depth(L: int) -> str:
    return f'<span class="match-depth">Top {L}</span>'


def render_races(season_entry: dict) -> str:
    races_to_show = [r for r in season_entry["races"] if r["matchLength"] >= 3]
    races_to_show.sort(key=lambda r: (-r["matchLength"], int(r["round"])))
    if not races_to_show:
        return '<div class="empty">No races in this season had top-3 in championship order.</div>'
    rows = "".join(
        f'<tr>'
        f'<td class="col-r">R{html.escape(r["round"])}</td>'
        f'<td class="col-name">{html.escape(r["raceName"])}</td>'
        f'<td class="col-len">{render_match_depth(r["matchLength"])}</td>'
        f'<td class="col-drivers">{render_match_drivers(r["matchedDrivers"])}</td>'
        f'</tr>'
        for r in races_to_show
    )
    return (
        f'<div class="races-table-wrap">'
        f'<table class="races-table">'
        f'<thead><tr><th>Round</th><th>Race</th><th>Match</th><th>Matched drivers (in order)</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'</div>'
    )


def render_season_card(s: dict) -> str:
    season = s["season"]
    best = s["bestMatchLength"]
    p3 = s["perfectTop3Count"]
    indy = s["indy500Count"]

    n_races = len(s["races"])
    pct = round(100 * p3 / n_races) if n_races else 0
    rate_pct = (100 * p3 / n_races) if n_races else 0
    placeholder = '<span class="placeholder">&mdash;</span>'

    count_zone = (
        f'<div class="zone zone-count">'
        f'<span class="count">{p3}/{n_races}</span>'
        f'<span class="label">aligned</span>'
        f'</div>'
    )
    rate_zone = (
        f'<div class="zone zone-rate"><span class="rate">{pct}%</span></div>'
        if p3 > 0 else f'<div class="zone zone-rate">{placeholder}</div>'
    )
    best_zone = (
        f'<div class="zone zone-best"><span class="best">best <b>Top {best}</b></span></div>'
        if best >= 3 else f'<div class="zone zone-best">{placeholder}</div>'
    )
    zones = f'<div class="season-zones">{count_zone}{rate_zone}{best_zone}</div>'

    indy_note = (
        f'<div class="indy-note">{indy} Indy 500 round{"s" if indy != 1 else ""} excluded from comparison.</div>'
        if indy else ""
    )

    has_match = "has-match" if best >= 3 else ""
    return (
        f'<article class="season-card {has_match}" '
        f'data-season="{season}" data-best="{best}" data-perfect3="{p3}" '
        f'data-rate="{rate_pct:.4f}">'
        f'  <header class="season-head">'
        f'    <div class="season-year">{html.escape(season)}</div>'
        f'    {zones}'
        f'    <div class="season-chev">&#9662;</div>'
        f'  </header>'
        f'  <div class="season-body">'
        f'    <div class="grid">'
        f'      <div class="panel">'
        f'        <h3>Final WDC standings</h3>'
        f'        {render_champ_list(s["championship"])}'
        f'      </div>'
        f'      <div class="panel">'
        f'        <h3>Races matching championship order (top-3+)</h3>'
        f'        {render_races(s)}'
        f'        {indy_note}'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'</article>'
    )


def main() -> int:
    seasons = json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))

    total_seasons = len(seasons)
    total_perfect3 = sum(s["perfectTop3Count"] for s in seasons)

    longest = (0, None)
    for s in seasons:
        for r in s["races"]:
            if r["matchLength"] > longest[0]:
                longest = (r["matchLength"], (s["season"], r))

    if longest[1]:
        L, (season, race) = longest
        longest_str = f'Top {L} <small>{season} - {race["raceName"]}</small>'
    else:
        longest_str = "—"

    cards_html = "\n".join(render_season_card(s) for s in seasons)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<title>F1 Season Alignments - Race vs Championship Order</title>
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="seasons.css">
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html">Podigami</a>
        <a href="combos.html">Combinations</a>
        <a href="seasons.html" class="active">Season Alignments</a>
        <a href="charts.html">Charts</a>
        <a href="soulmates.html">Soulmates &rarr;</a>
    </div>
</nav>
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Season Alignments</h1>
        <p class="tagline">For each completed season (1950&ndash;2025), how often did a race finish in the exact same order as the year's final WDC standings? Top 3, top 4, top 5&hellip; how far does the alignment go?</p>
        <div class="stats">
            <div class="stat"><div class="num">{total_seasons}</div><div class="label">Completed seasons</div></div>
            <div class="stat"><div class="num">{total_perfect3:,}</div><div class="label">Races with top-3 alignment</div></div>
            <div class="stat"><div class="num">{longest_str}</div><div class="label">Longest-ever alignment</div></div>
        </div>
    </div>
</header>
<main>
    <div class="container">
        <div class="controls">
            <div class="filters">
                <div class="filter-group">
                    <label for="sort-by">Sort</label>
                    <select id="sort-by">
                        <option value="season-desc">Newest first</option>
                        <option value="season-asc">Oldest first</option>
                        <option value="best-desc">Best match length</option>
                        <option value="perfect-desc"># of top-3 alignments</option>
                        <option value="rate-desc">% alignment rate</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="min-len">Min match</label>
                    <input id="min-len" type="number" min="0" max="10" value="0" step="1">
                </div>
            </div>
            <span class="hint">Showing <strong id="visible-count">{total_seasons}</strong> of <span id="total-count">{total_seasons}</span> seasons &middot; click a card to expand</span>
        </div>
        <div class="season-grid" id="season-list">
{cards_html}
        </div>
        <div id="global-empty" class="global-empty" style="display:none">
            <strong>No seasons match the filter</strong>
            Lower the minimum match length.
        </div>
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; Indy 500 (1950&ndash;1960) excluded from comparison
        &middot; Sprint races excluded
    </div>
</footer>
<script src="seasons.js"></script>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  rendered {total_seasons} seasons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
