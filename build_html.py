"""Render data/combos.json into a static index.html."""

from __future__ import annotations

import html
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
COMBOS_PATH = ROOT / "data" / "combos.json"
PODIUMS_PATH = ROOT / "data" / "podiums.json"
OUT_PATH = ROOT / "index.html"


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

/* ---------- nav ---------- */
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

/* ---------- header ---------- */

header {
    background: linear-gradient(180deg, var(--surface) 0%, var(--bg-2) 100%);
    border-bottom: 1px solid var(--border);
    position: relative;
    padding: 48px 0 36px;
}
header::after {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: -1px;
    height: 2px;
    background: linear-gradient(90deg,
        transparent 0%,
        var(--accent) 20%,
        var(--accent-bright) 50%,
        var(--accent) 80%,
        transparent 100%);
    opacity: 0.85;
}
header h1 {
    margin: 0 0 6px;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.6px;
    line-height: 1.15;
}
header h1 .accent {
    color: var(--accent);
    font-weight: 800;
    margin-right: 10px;
}
header .tagline {
    margin: 0 0 24px;
    color: var(--muted);
    font-size: 15px;
    max-width: 720px;
}

.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    max-width: 720px;
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
    font-size: 24px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.1;
    letter-spacing: -0.3px;
}
.stat .label {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-top: 4px;
}

/* ---------- main ---------- */

main {
    flex: 1;
    padding: 32px 0 48px;
}

.controls { margin-bottom: 18px; }
.filters {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 10px;
}
.filters .search-wrap {
    position: relative;
    flex: 1 1 220px;
    min-width: 180px;
    max-width: 320px;
}
.filters .search-wrap::before {
    content: "";
    position: absolute;
    left: 12px; top: 50%;
    width: 13px; height: 13px;
    transform: translateY(-50%);
    background: var(--muted);
    -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='7'/><path d='m21 21-4.3-4.3'/></svg>") center/contain no-repeat;
            mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='7'/><path d='m21 21-4.3-4.3'/></svg>") center/contain no-repeat;
    pointer-events: none;
}
.filters input {
    width: 100%;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 9px 12px 9px 34px;
    border-radius: var(--radius-sm);
    font: inherit;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.filters input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(225, 6, 0, 0.15);
}
.filters input:not(:placeholder-shown) { border-color: var(--accent-dim); }
.filters input::placeholder { color: var(--muted-dim); }
.clear-btn {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
    padding: 9px 14px;
    border-radius: var(--radius-sm);
    font: inherit;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
    white-space: nowrap;
}
.clear-btn:hover:not(:disabled) {
    color: var(--text);
    border-color: var(--accent);
    background: rgba(225, 6, 0, 0.08);
}
.clear-btn:disabled { opacity: 0.45; cursor: default; }
.hint {
    color: var(--muted);
    font-size: 13px;
}
.hint strong { color: var(--text); font-weight: 600; }

/* ---------- table ---------- */

.table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    overflow-x: auto;
}
table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}
col.col-rank    { width: 68px; }
col.col-drivers { width: auto; }
col.col-count   { width: 92px; }
col.col-last    { width: 240px; }
col.col-expand  { width: 44px; }

thead th {
    text-align: left;
    padding: 13px 18px;
    background: var(--surface-2);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid var(--border);
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 1;
    white-space: nowrap;
}
thead th[data-sort] { cursor: pointer; transition: color 0.15s; }
thead th[data-sort]:hover { color: var(--text); }
thead th .sort-ind {
    display: inline-block;
    margin-left: 6px;
    width: 8px;
    color: var(--muted-dim);
    font-size: 10px;
    transition: transform 0.18s ease, color 0.15s;
    transform-origin: 50% 55%;
}
thead th.active            { color: var(--text); }
thead th.active .sort-ind  { color: var(--accent-bright); }
thead th.active.dir-asc .sort-ind { transform: rotate(180deg); }

tbody tr.combo {
    cursor: pointer;
    transition: background 0.12s;
}
tbody tr.combo > td {
    padding: 14px 18px;
    border-top: 1px solid var(--border);
    vertical-align: middle;
    overflow-wrap: break-word;
}
tbody tr.combo:first-child > td { border-top: none; }
tbody tr.combo:hover > td { background: var(--surface-2); }
tbody tr.combo:nth-of-type(2n) > td { background: rgba(255, 255, 255, 0.012); }
tbody tr.combo:nth-of-type(2n):hover > td { background: var(--surface-2); }
tbody tr.combo.expanded > td { background: var(--surface-2); }

td.rank {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 13px;
    white-space: nowrap;
}
td.drivers { font-weight: 500; color: var(--text); }
td.drivers .driver { white-space: nowrap; }
td.drivers .sep {
    color: var(--muted-dim);
    margin: 0 8px;
    font-weight: 400;
}
td.count {
    font-weight: 700;
    color: var(--accent-bright);
    font-variant-numeric: tabular-nums;
    font-size: 16px;
}
td.last {
    color: var(--muted);
    font-size: 14px;
    line-height: 1.35;
}
td.last .year {
    color: var(--text);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    margin-right: 8px;
}
td.last .race-name { color: var(--text-dim); }

td.expand {
    text-align: center;
    color: var(--muted-dim);
    width: 44px;
}
td.expand .chev {
    display: inline-block;
    width: 18px; height: 18px;
    line-height: 18px;
    text-align: center;
    border-radius: 50%;
    font-size: 10px;
    transition: transform 0.18s ease, color 0.15s, background 0.15s;
}
tr.combo:hover td.expand .chev { color: var(--text); }
tr.combo.expanded td.expand .chev {
    transform: rotate(180deg);
    color: var(--accent-bright);
    background: rgba(225, 6, 0, 0.12);
}

/* expanded detail row */
tr.detail { display: none; }
tr.detail.open { display: table-row; }
tr.detail > td {
    background: var(--bg-2);
    border-top: 1px solid var(--border);
    padding: 0;
}
.detail-inner {
    padding: 18px 24px 20px;
    border-left: 3px solid var(--accent);
}
.season-row {
    display: grid;
    grid-template-columns: 70px 1fr;
    gap: 14px;
    padding: 6px 0;
    border-top: 1px solid var(--border);
    align-items: baseline;
}
.season-row:first-child { border-top: none; padding-top: 0; }
.season-row .season-label {
    font-weight: 700;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    letter-spacing: -0.2px;
}
.season-row .season-label .ct {
    color: var(--muted-dim);
    font-weight: 500;
    font-size: 12px;
    margin-left: 4px;
}
.season-row .race-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.race-pill {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    font-size: 12.5px;
    color: var(--text-dim);
    line-height: 1.3;
    white-space: nowrap;
}
.race-pill .round {
    color: var(--muted-dim);
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 11px;
}

.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--muted);
    font-size: 14px;
}
.empty-state strong { color: var(--text); display: block; margin-bottom: 4px; }

/* ---------- footer ---------- */

footer {
    border-top: 1px solid var(--border);
    background: var(--bg-2);
    color: var(--muted);
    font-size: 13px;
    padding: 20px 0;
    text-align: center;
}
footer a {
    color: var(--text-dim);
    text-decoration: none;
    border-bottom: 1px dotted var(--border-strong);
}
footer a:hover { color: var(--accent-bright); border-color: var(--accent); }

/* ---------- responsive ---------- */

@media (max-width: 720px) {
    .container { padding: 0 12px; }
    header { padding: 32px 0 28px; }
    header h1 { font-size: 26px; }
    main { padding: 24px 0 32px; }
    col.col-last  { width: 150px; }
    col.col-rank  { width: 56px; }
    col.col-count { width: 70px; }
    thead th, tbody tr.combo > td { padding: 11px 10px; }
    thead th { font-size: 10px; }
    td.last .race-name { display: none; }
    .detail-inner { padding: 14px 14px 16px; }
    .season-row { grid-template-columns: 56px 1fr; }
}
"""

JS = """
const tbody = document.querySelector('tbody');
const comboRows = Array.from(tbody.querySelectorAll('tr.combo'));
const filterInputs = Array.from(document.querySelectorAll('.filters input[data-filter]'));
const clearBtn = document.getElementById('clear-filters');
const headers = document.querySelectorAll('th[data-sort]');
const visibleEl = document.getElementById('visible-count');
const totalEl = document.getElementById('total-count');
const emptyEl = document.getElementById('empty-state');
const totalRows = comboRows.length;
totalEl.textContent = totalRows;

let currentSort = { key: 'count', dir: 'desc' };

function applySort() {
    const { key, dir } = currentSort;
    const mult = dir === 'asc' ? 1 : -1;
    const sorted = comboRows.slice().sort((a, b) => {
        if (key === 'count') return (Number(a.dataset.count) - Number(b.dataset.count)) * mult;
        if (key === 'last')  return (Number(a.dataset.last)  - Number(b.dataset.last))  * mult;
        return a.dataset.drivers.localeCompare(b.dataset.drivers) * mult;
    });
    sorted.forEach((row, i) => {
        row.querySelector('.rank').textContent = i + 1;
        const detail = row.nextElementSibling;
        tbody.appendChild(row);
        if (detail && detail.classList.contains('detail')) tbody.appendChild(detail);
    });
    headers.forEach(h => {
        const isActive = h.dataset.sort === key;
        h.classList.toggle('active', isActive);
        h.classList.toggle('dir-asc', isActive && dir === 'asc');
        h.classList.toggle('dir-desc', isActive && dir === 'desc');
    });
}

headers.forEach(h => {
    h.addEventListener('click', () => {
        const key = h.dataset.sort;
        if (currentSort.key === key) {
            currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.key = key;
            currentSort.dir = (key === 'count' || key === 'last') ? 'desc' : 'asc';
        }
        applySort();
    });
});

comboRows.forEach(row => {
    row.addEventListener('click', () => {
        const detail = row.nextElementSibling;
        if (!detail || !detail.classList.contains('detail')) return;
        const open = detail.classList.toggle('open');
        row.classList.toggle('expanded', open);
    });
});

// Each non-empty filter must match a DISTINCT driver in the combo (substring, case-insensitive).
function matchesFilters(driverNames, filters) {
    if (filters.length === 0) return true;
    if (filters.length > driverNames.length) return false;
    function dfs(idx, usedMask) {
        if (idx >= filters.length) return true;
        for (let d = 0; d < driverNames.length; d++) {
            if (usedMask & (1 << d)) continue;
            if (driverNames[d].includes(filters[idx])) {
                if (dfs(idx + 1, usedMask | (1 << d))) return true;
            }
        }
        return false;
    }
    return dfs(0, 0);
}

function applyFilter() {
    const filters = filterInputs.map(i => i.value.trim().toLowerCase()).filter(v => v);
    let visible = 0;
    comboRows.forEach(row => {
        const drivers = row.dataset.drivers.split(' | ');
        const match = matchesFilters(drivers, filters);
        row.style.display = match ? '' : 'none';
        const detail = row.nextElementSibling;
        if (detail && detail.classList.contains('detail')) {
            if (!match) {
                detail.classList.remove('open');
                row.classList.remove('expanded');
                detail.style.display = 'none';
            } else {
                detail.style.display = '';
            }
        }
        if (match) visible++;
    });
    visibleEl.textContent = visible;
    emptyEl.style.display = visible === 0 ? '' : 'none';
    clearBtn.disabled = filters.length === 0;
}

filterInputs.forEach(i => i.addEventListener('input', applyFilter));
clearBtn.addEventListener('click', () => {
    filterInputs.forEach(i => { i.value = ''; });
    applyFilter();
    filterInputs[0].focus();
});

applySort();
applyFilter();
"""


def render_race_pills(races: list[dict]) -> str:
    """Group races by season; each season gets a row with year + race pills."""
    races_sorted = sorted(races, key=lambda r: (int(r["season"]), int(r["round"])))
    parts: list[str] = []
    for season, group in itertools.groupby(races_sorted, key=lambda r: r["season"]):
        group_list = list(group)
        pills = "".join(
            f'<span class="race-pill">'
            f'<span class="round">R{html.escape(r["round"])}</span>'
            f'{html.escape(short_race_name(r["raceName"]))}'
            f'</span>'
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
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html" class="active">Podium Combinations</a>
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
            </div>
            <div class="hint">
                Showing <strong id="visible-count">{unique_combos}</strong> of <span id="total-count">{unique_combos}</span>
                &middot; each field matches one distinct driver (AND)
                &middot; click a row to expand &middot; click a column header to sort
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
<script>{JS}</script>
</body>
</html>
"""

    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  rendered {unique_combos} combos covering {total_podiums} races ({season_min}-{season_max})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
