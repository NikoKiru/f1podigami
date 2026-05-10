"""Render data/alignments.json into seasons.html."""

from __future__ import annotations

import html
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
ALIGNMENTS_PATH = ROOT / "data" / "alignments.json"
OUT_PATH = ROOT / "seasons.html"

CSS = """
:root {
    --bg: #0b0d12;
    --bg-2: #0e1116;
    --surface: #161b22;
    --surface-2: #1f2630;
    --surface-3: #262d38;
    --text: #e6edf3;
    --text-dim: #c9d1d9;
    --muted: #8b949e;
    --muted-dim: #6e7681;
    --accent: #e10600;
    --accent-bright: #ff2d20;
    --accent-dim: #8a0500;
    --gold: #f4c430;
    --silver: #c0c0c0;
    --bronze: #cd7f32;
    --border: #2a313c;
    --border-strong: #3a4250;
    --radius: 10px;
    --radius-sm: 6px;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
    background: var(--bg);
    color: var(--text);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}
.container {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 32px;
}

/* nav */
.nav {
    background: var(--bg-2);
    border-bottom: 1px solid var(--border);
}
.nav-inner {
    display: flex;
    gap: 24px;
    padding: 12px 0;
    align-items: center;
}
.nav a {
    color: var(--muted);
    text-decoration: none;
    font-size: 13px;
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    transition: color 0.15s, background 0.15s;
}
.nav a:hover { color: var(--text); background: var(--surface-2); }
.nav a.active { color: var(--text); background: var(--surface-2); border-left: 2px solid var(--accent); padding-left: 10px; }

/* header */
header {
    background: linear-gradient(180deg, var(--surface) 0%, var(--bg-2) 100%);
    border-bottom: 1px solid var(--border);
    position: relative;
    padding: 40px 0 32px;
}
header::after {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: -1px;
    height: 2px;
    background: linear-gradient(90deg,
        transparent 0%, var(--accent) 20%, var(--accent-bright) 50%, var(--accent) 80%, transparent 100%);
    opacity: 0.85;
}
header h1 {
    margin: 0 0 6px;
    font-size: 30px;
    font-weight: 700;
    letter-spacing: -0.6px;
}
header h1 .accent { color: var(--accent); font-weight: 800; margin-right: 10px; }
header .tagline { margin: 0 0 22px; color: var(--muted); font-size: 15px; max-width: 760px; }

.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    max-width: 880px;
}
.stat {
    background: var(--surface-2);
    padding: 14px 18px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    position: relative;
    overflow: hidden;
}
.stat::before {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: var(--accent);
    opacity: 0.85;
}
.stat .num {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.15;
    letter-spacing: -0.3px;
}
.stat .num small { font-size: 13px; color: var(--muted); font-weight: 500; margin-left: 6px; }
.stat .label {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-top: 4px;
}

/* main + controls */
main { flex: 1; padding: 28px 0 48px; }
.controls {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 18px;
    flex-wrap: wrap;
}
.controls label {
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}
.controls select, .controls input[type=number] {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    font: inherit;
    font-size: 14px;
}
.controls select:focus, .controls input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(225, 6, 0, 0.15);
}
.hint { color: var(--muted); font-size: 13px; margin-left: auto; }
.hint strong { color: var(--text); font-weight: 600; }

/* season cards */
.season-grid {
    display: flex;
    flex-direction: column;
    gap: 14px;
}
.season-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.season-card.has-match { border-left: 3px solid var(--accent); }

.season-head {
    display: grid;
    grid-template-columns: 90px 1fr auto;
    gap: 18px;
    align-items: center;
    padding: 16px 22px;
    cursor: pointer;
    user-select: none;
    transition: background 0.12s;
}
.season-head:hover { background: var(--surface-2); }
.season-card.expanded .season-head { background: var(--surface-2); border-bottom: 1px solid var(--border); }
.season-year {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}
.season-zones {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    align-items: baseline;
    gap: 16px;
    min-width: 0;
}
.zone {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 8px;
    min-width: 0;
}
.zone .placeholder {
    color: var(--muted-dim);
    font-size: 14px;
}
.zone-count .count {
    font-size: 20px;
    font-weight: 700;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.3px;
    line-height: 1;
}
.zone-count .label {
    color: var(--text-dim);
    font-size: 13px;
}
.zone-rate .rate {
    color: var(--text);
    font-weight: 700;
    font-size: 18px;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.zone-best .best {
    color: var(--muted);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
}
.zone-best .best b {
    color: var(--accent-bright);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    margin-left: 4px;
}

.season-chev {
    color: var(--muted-dim);
    font-size: 14px;
    transition: transform 0.18s, color 0.15s;
}
.season-card.expanded .season-chev { transform: rotate(180deg); color: var(--accent-bright); }

/* expanded season body */
.season-body { display: none; padding: 18px 22px 22px; }
.season-card.expanded .season-body { display: block; }
.season-body .grid {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) 2fr;
    gap: 22px;
}
@media (max-width: 760px) {
    .season-body .grid { grid-template-columns: 1fr; }
    .season-head { grid-template-columns: 70px 1fr auto; gap: 14px; padding: 14px 16px; }
    .season-year { font-size: 24px; }
    .season-body { padding: 16px; }
    .container { padding: 0 18px; }
    .season-zones {
        display: flex;
        flex-wrap: wrap;
        column-gap: 14px;
        row-gap: 4px;
    }
    .zone { justify-content: flex-start; }
}

.panel {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
}
.panel h3 {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 700;
}

/* champ standings list */
.champ-list { list-style: none; padding: 0; margin: 0; counter-reset: champ; }
.champ-list li {
    counter-increment: champ;
    display: grid;
    grid-template-columns: 32px 1fr auto;
    gap: 8px;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
}
.champ-list li:last-child { border-bottom: none; }
.champ-list li::before {
    content: counter(champ);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--muted-dim);
    text-align: right;
    padding-right: 4px;
}
.champ-list li:nth-child(1)::before { color: var(--gold); }
.champ-list li:nth-child(2)::before { color: var(--silver); }
.champ-list li:nth-child(3)::before { color: var(--bronze); }
.champ-list li .driver-name { color: var(--text); font-weight: 500; }
.champ-list li .points { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.champ-list li.champ-list-extra { display: none; }
.champ-list.expanded li.champ-list-extra { display: grid; }
.champ-toggle {
    display: inline-block;
    margin-top: 10px;
    color: var(--muted);
    font-size: 12px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-decoration: underline dotted var(--border-strong);
}
.champ-toggle:hover { color: var(--text); }

/* races table */
.races-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.races-table th {
    text-align: left;
    padding: 8px 10px;
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
    border-bottom: 1px solid var(--border);
}
.races-table td {
    padding: 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
}
.races-table tr:last-child td { border-bottom: none; }
.races-table .col-r { width: 50px; color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; }
.races-table .col-name { color: var(--text); font-weight: 500; }
.races-table .col-len { width: 70px; }
.races-table .col-drivers { color: var(--text-dim); font-size: 13px; }
.races-table .col-drivers .dr {
    font-family: ui-monospace, SFMono-Regular, "Cascadia Mono", Menlo, Consolas, monospace;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--text);
    font-size: 13px;
}
.races-table .col-drivers .sep { color: var(--muted-dim); margin: 0 6px; }

/* match depth label */
.match-depth {
    font-weight: 700;
    color: var(--accent-bright);
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    letter-spacing: 0.2px;
}

.empty { color: var(--muted); font-size: 13px; padding: 12px 0; }
.indy-note { color: var(--muted-dim); font-size: 12px; margin-top: 10px; font-style: italic; }
.global-empty {
    text-align: center;
    color: var(--muted);
    padding: 60px 20px;
    font-size: 14px;
}
.global-empty strong { color: var(--text); display: block; margin-bottom: 4px; }

/* footer */
footer {
    border-top: 1px solid var(--border);
    background: var(--bg-2);
    color: var(--muted);
    font-size: 13px;
    padding: 18px 0;
    text-align: center;
}
footer a {
    color: var(--text-dim);
    text-decoration: none;
    border-bottom: 1px dotted var(--border-strong);
}
footer a:hover { color: var(--accent-bright); border-color: var(--accent); }
"""

JS = """
const cards = Array.from(document.querySelectorAll('.season-card'));
const sortSel = document.getElementById('sort-by');
const minLen = document.getElementById('min-len');
const visEl = document.getElementById('visible-count');
const totalEl = document.getElementById('total-count');
const list = document.getElementById('season-list');
const emptyEl = document.getElementById('global-empty');
const totalCards = cards.length;
totalEl.textContent = totalCards;

cards.forEach(card => {
    const head = card.querySelector('.season-head');
    head.addEventListener('click', () => card.classList.toggle('expanded'));
});

document.querySelectorAll('.champ-toggle').forEach(btn => {
    btn.addEventListener('click', e => {
        e.stopPropagation();
        const list = btn.previousElementSibling;
        const open = list.classList.toggle('expanded');
        btn.textContent = open ? 'Show less' : btn.dataset.label;
    });
});

function applySort() {
    const key = sortSel.value;
    const sorted = cards.slice().sort((a, b) => {
        const aS = Number(a.dataset.season);
        const bS = Number(b.dataset.season);
        const aB = Number(a.dataset.best);
        const bB = Number(b.dataset.best);
        const aP = Number(a.dataset.perfect3);
        const bP = Number(b.dataset.perfect3);
        const aR = Number(a.dataset.rate);
        const bR = Number(b.dataset.rate);
        if (key === 'season-desc') return bS - aS;
        if (key === 'season-asc')  return aS - bS;
        if (key === 'best-desc')   return (bB - aB) || (bS - aS);
        if (key === 'perfect-desc') return (bP - aP) || (bS - aS);
        if (key === 'rate-desc')   return (bR - aR) || (bS - aS);
        return 0;
    });
    sorted.forEach(c => list.appendChild(c));
}

function applyFilter() {
    const min = Number(minLen.value) || 0;
    let v = 0;
    cards.forEach(card => {
        const best = Number(card.dataset.best);
        const show = best >= min;
        card.style.display = show ? '' : 'none';
        if (show) v++;
    });
    visEl.textContent = v;
    emptyEl.style.display = v === 0 ? '' : 'none';
}

sortSel.addEventListener('change', applySort);
minLen.addEventListener('input', applyFilter);

applySort();
applyFilter();
"""


_ABBREV_OVERRIDES: dict[str, str] = {
    "Michael Schumacher": "MSC",
    "Ralf Schumacher": "RSC",
}


def driver_abbrev(name: str) -> str:
    """Last-name first-3 letters, uppercase ASCII. Schumachers disambiguated as MSC/RSC."""
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
        f'<table class="races-table">'
        f'<thead><tr><th>Round</th><th>Race</th><th>Match</th><th>Matched drivers (in order)</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
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
<title>F1 Season Alignments - Race vs Championship Order</title>
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html">&larr; Podium Combinations</a>
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
            <label for="sort-by">Sort</label>
            <select id="sort-by">
                <option value="season-desc">Newest first</option>
                <option value="season-asc">Oldest first</option>
                <option value="best-desc">Best match length</option>
                <option value="perfect-desc"># of top-3 alignments</option>
                <option value="rate-desc">% alignment rate</option>
            </select>
            <label for="min-len">Min match</label>
            <input id="min-len" type="number" min="0" max="10" value="0" step="1">
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
<script>{JS}</script>
</body>
</html>
"""
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  rendered {total_seasons} seasons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
