"""Render soulmates.html — ranked pairs list + compact CSS grid heatmap."""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

from build_alignments_html import CSS as BASE_CSS

ROOT = Path(__file__).parent
SOULMATES_PATH = ROOT / "data" / "soulmates.json"
OUT_PATH = ROOT / "soulmates.html"


SOULMATES_CSS = """
/* ── page grid ───────────────────────────────────────── */
.sm-page {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 620px);
    gap: 32px;
    align-items: start;
}
@media (max-width: 1050px) {
    .sm-page { grid-template-columns: 1fr; }
}

/* ── section headings ────────────────────────────────── */
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

/* ── CSS heatmap ─────────────────────────────────────── */
.hm-wrap { overflow-x: auto; }
.hm-hint {
    font-size: 12px;
    color: var(--muted-dim);
    margin: 0 0 10px;
}

/* x-axis (rotated abbreviated labels above the grid) */
.hm-xaxis {
    display: flex;
    margin-left: 74px;   /* y-label width (70px) + gap (4px) */
    height: 56px;
    align-items: flex-end;
    gap: 1px;
}
.hm-xlabel {
    width: 12px;
    flex-shrink: 0;
    font-size: 8px;
    color: var(--muted);
    white-space: nowrap;
    transform: rotate(-45deg);
    transform-origin: right bottom;
    text-align: right;
    line-height: 1;
    cursor: default;
    user-select: none;
}

/* y-labels + grid row */
.hm-body {
    display: flex;
    gap: 4px;
}
.hm-ylabels {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex-shrink: 0;
    width: 70px;
}
.hm-ylabel {
    height: 12px;
    font-size: 8px;
    color: var(--muted);
    line-height: 12px;
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: default;
    user-select: none;
}

/* the grid itself */
.hm-grid {
    display: grid;
    grid-template-columns: repeat(40, 12px);
    grid-auto-rows: 12px;
    gap: 1px;
    flex-shrink: 0;
}
.hm-cell {
    width: 12px;
    height: 12px;
    border-radius: 1px;
    cursor: crosshair;
    transition: filter 0.08s;
}
.hm-cell:hover { filter: brightness(1.4); }

/* legend */
.hm-legend {
    display: flex;
    gap: 14px;
    margin-top: 10px;
    flex-wrap: wrap;
}
.hm-leg-item {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: var(--muted);
}
.hm-leg-swatch {
    width: 10px;
    height: 10px;
    border-radius: 1px;
    flex-shrink: 0;
}

/* floating tooltip */
.hm-tooltip {
    position: fixed;
    pointer-events: none;
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.55;
    z-index: 9999;
    display: none;
    max-width: 240px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}
.hm-tooltip .tt-head {
    color: var(--accent-bright);
    font-weight: 700;
    margin-bottom: 3px;
}
.hm-tooltip .tt-body { color: var(--text); }
"""


TOOLTIP_JS = """
(function () {
    const tt = document.getElementById('hm-tt');
    document.querySelectorAll('.hm-cell').forEach(function (cell) {
        cell.addEventListener('mouseenter', function (e) {
            const a = cell.dataset.a;
            const b = cell.dataset.b;
            const v = parseInt(cell.dataset.v, 10);
            if (!a || !b || a === b) return;
            tt.innerHTML =
                '<div class="tt-head">' + a + ' &amp; ' + b + '</div>' +
                '<div class="tt-body">' +
                (v > 0 ? v + ' shared podium' + (v === 1 ? '' : 's') : 'No shared podiums') +
                '</div>';
            tt.style.display = 'block';
            move(e);
        });
        cell.addEventListener('mousemove', move);
        cell.addEventListener('mouseleave', function () { tt.style.display = 'none'; });
    });
    function move(e) {
        const m = 16, w = 250, h = 60;
        let x = e.clientX + m;
        let y = e.clientY + m;
        if (x + w > window.innerWidth)  x = e.clientX - w - m;
        if (y + h > window.innerHeight) y = e.clientY - h - m;
        tt.style.left = x + 'px';
        tt.style.top  = y + 'px';
    }
})();
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def _ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _abbrev(name: str) -> str:
    OVERRIDES = {"Michael Schumacher": "MSC", "Ralf Schumacher": "RSC"}
    if name in OVERRIDES:
        return OVERRIDES[name]
    parts = name.split()
    return _ascii_fold(parts[-1])[:3].upper() if parts else name[:3].upper()


def _make_abbrevs(names: list[str]) -> list[str]:
    from collections import Counter
    raw = [_abbrev(n) for n in names]
    dups = {a for a, c in Counter(raw).items() if c > 1}
    result = []
    for name, abbr in zip(names, raw):
        if abbr in dups:
            fi = _ascii_fold(name.split()[0])[0].upper()
            result.append(f"{fi}.{abbr}")
        else:
            result.append(abbr)
    return result


def _last(name: str) -> str:
    parts = name.split()
    return parts[-1] if parts else name


def _cell_color(v: int, max_val: int) -> str:
    if not v:
        return "#1a1f2a"
    p = v / max_val
    if p < 0.10: return "#3d1a17"
    if p < 0.25: return "#6a1410"
    if p < 0.45: return "#a50300"
    if p < 0.70: return "#d80500"
    return "#ff2d20"


# ── renderers ─────────────────────────────────────────────────────────────────

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


def _render_matrix(soulmates: dict) -> str:
    drivers = soulmates["drivers"]
    matrix  = soulmates["matrix"]
    max_val = soulmates.get("max", 1) or 1

    names   = [d["name"] for d in drivers]
    abbrevs = _make_abbrevs(names)
    n       = len(names)

    y_labels = "\n".join(
        f'<div class="hm-ylabel" title="{names[i]}">{_last(names[i])}</div>'
        for i in range(n)
    )
    x_labels = "\n".join(
        f'<span class="hm-xlabel" title="{names[j]}">{abbrevs[j]}</span>'
        for j in range(n)
    )

    cells = []
    for i in range(n):
        for j in range(n):
            v = matrix[i][j] if i != j else 0
            c = _cell_color(v, max_val)
            cells.append(
                f'<div class="hm-cell" style="background:{c}"'
                f' data-a="{names[i]}" data-b="{names[j]}" data-v="{v}"></div>'
            )

    return f"""
<div class="hm-xaxis">{x_labels}</div>
<div class="hm-body">
    <div class="hm-ylabels">{y_labels}</div>
    <div class="hm-grid">{"".join(cells)}</div>
</div>
<div class="hm-legend">
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#1a1f2a"></span>none</span>
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#3d1a17"></span>1&ndash;6</span>
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#6a1410"></span>7&ndash;15</span>
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#a50300"></span>16&ndash;27</span>
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#d80500"></span>28&ndash;43</span>
    <span class="hm-leg-item"><span class="hm-leg-swatch" style="background:#ff2d20"></span>44+</span>
</div>
<div id="hm-tt" class="hm-tooltip"></div>
"""


# ── main ──────────────────────────────────────────────────────────────────────

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

    pairs_html  = _render_pairs(top_pairs)
    matrix_html = _render_matrix(soulmates)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
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
        <p class="tagline">Which legends spent the most race weekends together on the box? Era-mates form bright clusters along the diagonal &mdash; Senna &amp; Prost, Schumacher &amp; Barrichello, Hamilton &amp; Verstappen.</p>
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
                <p class="sm-section-title">Shared podium matrix</p>
                <p class="hm-hint">Hover any cell &mdash; diagonal clusters show era-mates</p>
                <div class="hm-wrap">
                    {matrix_html}
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
<script>{TOOLTIP_JS}</script>
</body>
</html>
"""
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
