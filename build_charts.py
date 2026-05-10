"""Chart rendering helpers for F1 podigami.

Each render_* function returns a dict {html, js_init} that the page-build
scripts compose into final HTML pages. Pages that embed any chart should also
include APEX_CDN_TAG in <head> and CHART_CSS in their <style> block.
"""

from __future__ import annotations

import json
import unicodedata

APEX_CDN_TAG = '<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>'

CHART_CSS = """
.chart-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 22px;
    margin-bottom: 18px;
}
.chart-card .chart-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 6px;
    flex-wrap: wrap;
}
.chart-card h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.2px;
}
.chart-card .chart-sub {
    color: var(--muted);
    font-size: 13px;
    margin: 0 0 12px;
    line-height: 1.5;
}
.chart-card .chart-host {
    width: 100%;
    overflow-x: auto;
}
/* tooltip overrides */
.apexcharts-tooltip.apexcharts-theme-dark {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text) !important;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.5) !important;
    border-radius: var(--radius-sm) !important;
}
.apex-tt {
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.55;
    font-family: ui-monospace, SFMono-Regular, "Cascadia Mono", Menlo, Consolas, monospace;
}
.apex-tt .tt-head {
    color: var(--accent-bright);
    font-weight: 700;
    margin-bottom: 4px;
    letter-spacing: 0.3px;
}
.apex-tt .tt-row { color: var(--text); }
.apex-tt .tt-dim { color: var(--muted); margin-top: 2px; }
.apex-tt .tt-drivers { color: var(--text-dim); margin-top: 4px; }
/* axis tweaks */
.apexcharts-xaxis text, .apexcharts-yaxis text { fill: var(--muted) !important; }
.apexcharts-gridline { stroke: var(--border) !important; }

/* soulmate matrix layout */
.soulmate-grid {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
    gap: 22px;
    align-items: start;
}
@media (max-width: 1000px) {
    .soulmate-grid { grid-template-columns: 1fr; }
}
.pair-list h3 {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 700;
}
.pair-rows {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.pair-row {
    display: grid;
    grid-template-columns: 28px 1fr auto auto;
    align-items: baseline;
    column-gap: 10px;
    padding: 7px 10px;
    border-radius: var(--radius-sm);
    background: var(--bg-2);
    border: 1px solid transparent;
    font-size: 13px;
    transition: background 0.12s, border-color 0.12s;
}
.pair-row:hover {
    background: var(--surface-2);
    border-color: var(--border);
}
.pair-rank {
    font-variant-numeric: tabular-nums;
    color: var(--muted-dim);
    font-size: 11px;
    text-align: right;
    font-weight: 700;
}
.pair-names {
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.pair-names b {
    color: var(--text);
    font-weight: 600;
}
.pair-count {
    color: var(--accent-bright);
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    font-size: 14px;
    min-width: 28px;
    text-align: right;
}
.pair-years {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    min-width: 76px;
    text-align: right;
}
"""


_ABBREV_OVERRIDES = {
    "Michael Schumacher": "MSC",
    "Ralf Schumacher": "RSC",
}


def _ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def driver_abbrev(name: str) -> str:
    if name in _ABBREV_OVERRIDES:
        return _ABBREV_OVERRIDES[name]
    parts = name.split()
    last = parts[-1] if parts else name
    return _ascii_fold(last)[:3].upper()


def render_alignment_heatmap(seasons: list[dict]) -> dict[str, str]:
    """Year × round heatmap, color encodes matchLength.

    seasons is the alignments.json list (each item: season, races[], ...).
    Newest season at the top of the chart.
    """
    sorted_seasons = sorted(seasons, key=lambda s: int(s["season"]), reverse=True)
    max_round = max(
        (int(r["round"]) for s in sorted_seasons for r in s["races"]),
        default=24,
    )

    series = []
    for s in sorted_seasons:
        by_round = {int(r["round"]): r for r in s["races"]}
        points = []
        for rnd in range(1, max_round + 1):
            r = by_round.get(rnd)
            if r is None:
                points.append({"x": str(rnd), "y": None})
                continue
            drivers_str = " · ".join(
                driver_abbrev(d["name"]) for d in r.get("matchedDrivers", [])
            )
            points.append({
                "x": str(rnd),
                "y": r["matchLength"],
                "raceName": r["raceName"],
                "drivers": drivers_str,
            })
        series.append({"name": s["season"], "data": points})

    series_json = json.dumps(series, ensure_ascii=False)

    html = """
<section class="chart-card" id="chart-alignment-heatmap">
    <div class="chart-head">
        <h2>Alignment Heatmap</h2>
        <span class="chart-sub" style="margin: 0;">Hover a cell for race detail</span>
    </div>
    <p class="chart-sub">Every race since 1950 (rows = season, columns = round number). Hot cells are races whose finishing order matched the year's final WDC top-N — the deeper the match, the brighter the cell.</p>
    <div class="chart-host"><div id="alignment-heatmap"></div></div>
</section>
"""

    js = f"""
(function() {{
    const series = {series_json};
    const options = {{
        chart: {{
            type: 'heatmap',
            height: Math.max(680, series.length * 11),
            background: 'transparent',
            foreColor: '#c9d1d9',
            toolbar: {{ show: false }},
            animations: {{ enabled: false }},
            fontFamily: 'inherit',
        }},
        series: series,
        plotOptions: {{
            heatmap: {{
                radius: 1,
                enableShades: false,
                useFillColorAsStroke: false,
                colorScale: {{
                    ranges: [
                        {{ from: 0, to: 0, color: '#262d38', name: 'no match' }},
                        {{ from: 1, to: 1, color: '#3d1a17', name: 'top 1' }},
                        {{ from: 2, to: 2, color: '#6a1410', name: 'top 2' }},
                        {{ from: 3, to: 3, color: '#a50300', name: 'top 3' }},
                        {{ from: 4, to: 4, color: '#d80500', name: 'top 4' }},
                        {{ from: 5, to: 10, color: '#ff2d20', name: 'top 5+' }},
                    ]
                }}
            }}
        }},
        stroke: {{ width: 1, colors: ['#0b0d12'] }},
        dataLabels: {{ enabled: false }},
        xaxis: {{
            type: 'category',
            title: {{ text: 'Round', style: {{ color: '#8b949e', fontSize: '11px', fontWeight: 600 }}, offsetY: -2 }},
            labels: {{ style: {{ colors: '#8b949e', fontSize: '11px' }} }},
            axisBorder: {{ color: '#2a313c' }},
            axisTicks: {{ color: '#2a313c' }},
            position: 'top',
        }},
        yaxis: {{
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '10px' }},
                formatter: function(v) {{
                    if (typeof v !== 'string') v = String(v);
                    const n = parseInt(v, 10);
                    return (!isNaN(n) && n % 5 === 0) ? v : '';
                }},
            }},
        }},
        grid: {{ show: false, padding: {{ top: 0, right: 8, bottom: 0, left: 8 }} }},
        legend: {{
            show: true,
            position: 'top',
            horizontalAlign: 'left',
            offsetY: -4,
            labels: {{ colors: '#8b949e' }},
            markers: {{ size: 6, shape: 'square', strokeWidth: 0, offsetX: -2 }},
            itemMargin: {{ horizontal: 8, vertical: 2 }},
            fontSize: '11px',
            fontWeight: 600,
        }},
        tooltip: {{
            theme: 'dark',
            custom: function({{seriesIndex, dataPointIndex, w}}) {{
                const point = w.config.series[seriesIndex].data[dataPointIndex];
                if (!point || point.y === null || point.y === undefined) return '';
                const season = w.config.series[seriesIndex].name;
                const drivers = point.drivers
                    ? '<div class="tt-drivers">' + point.drivers + '</div>'
                    : '';
                return '<div class="apex-tt">'
                    + '<div class="tt-head">' + season + ' &middot; R' + point.x + '</div>'
                    + '<div class="tt-row">' + (point.raceName || '') + '</div>'
                    + '<div class="tt-dim">top ' + point.y + ' aligned</div>'
                    + drivers
                    + '</div>';
            }},
        }},
    }};
    new ApexCharts(document.getElementById('alignment-heatmap'), options).render();
}})();
"""

    return {"html": html, "js_init": js}


# 20-color palette tuned for dark backgrounds
LINE_PALETTE = [
    "#ff2d20", "#f4c430", "#3da9fc", "#80ed99", "#a78bfa",
    "#ff8c42", "#06d6a0", "#f72585", "#fbb13c", "#9d4edd",
    "#ff5c8a", "#5cdb95", "#ffd166", "#118ab2", "#ef476f",
    "#73d2de", "#ffaa5c", "#bdb2ff", "#fb8500", "#a0c4ff",
]


def render_career_line_race(career: dict) -> dict[str, str]:
    """Multi-series line chart: cumulative podium count vs race index for top-N drivers."""
    drivers = career["drivers"]
    year_markers = career["yearMarkers"]  # {race_idx_str: year}
    total_races = career["totalRaces"]

    series = [{"name": d["name"], "data": d["data"]} for d in drivers]
    colors = LINE_PALETTE[: len(drivers)]

    series_json = json.dumps(series, ensure_ascii=False)
    year_markers_json = json.dumps(year_markers)
    colors_json = json.dumps(colors)

    html = """
<section class="chart-card" id="chart-career-line-race">
    <div class="chart-head">
        <h2>Career Podiums &mdash; Race to the Top</h2>
        <span class="chart-sub" style="margin: 0;">Top 20 drivers, all-time</span>
    </div>
    <p class="chart-sub">Cumulative podium count over chronological races (1950&nbsp;&rarr;&nbsp;2025). Steeper slope = denser podium era. Hover any line to see the driver and their count at that race.</p>
    <div class="chart-host"><div id="career-line-race"></div></div>
</section>
"""

    js = f"""
(function() {{
    const series = {series_json};
    const colors = {colors_json};
    const yearMarkers = {year_markers_json};
    const totalRaces = {total_races};

    // Pre-compute (sorted) array of [race_idx, year] for tick formatter + tooltip
    const markerEntries = Object.entries(yearMarkers)
        .map(([k, v]) => [parseInt(k, 10), v])
        .sort((a, b) => a[0] - b[0]);
    const tickYears = [1955, 1965, 1975, 1985, 1995, 2005, 2015, 2025];
    const tickPositions = tickYears.map(y => {{
        const m = markerEntries.find(([_, yr]) => yr === y);
        return m ? m[0] : null;
    }}).filter(p => p !== null);

    function yearForIdx(idx) {{
        let y = markerEntries[0][1];
        for (const [i, yr] of markerEntries) {{
            if (i > idx) break;
            y = yr;
        }}
        return y;
    }}

    const options = {{
        chart: {{
            type: 'line',
            height: 540,
            background: 'transparent',
            foreColor: '#c9d1d9',
            toolbar: {{ show: false }},
            zoom: {{ enabled: true, type: 'x' }},
            animations: {{ enabled: false }},
            fontFamily: 'inherit',
        }},
        series: series,
        colors: colors,
        stroke: {{ width: 2, curve: 'straight', lineCap: 'round' }},
        markers: {{ size: 0, hover: {{ size: 4 }} }},
        dataLabels: {{ enabled: false }},
        xaxis: {{
            type: 'numeric',
            min: 0,
            max: totalRaces,
            tickAmount: tickPositions.length,
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '11px' }},
                formatter: function(v) {{
                    const n = Math.round(Number(v));
                    if (n <= 0) return '1950';
                    return String(yearForIdx(n));
                }},
            }},
            axisBorder: {{ color: '#2a313c' }},
            axisTicks: {{ color: '#2a313c' }},
            tooltip: {{ enabled: false }},
            title: {{ text: '', style: {{ color: '#8b949e' }} }},
        }},
        yaxis: {{
            min: 0,
            labels: {{ style: {{ colors: '#8b949e', fontSize: '11px' }} }},
            title: {{ text: 'Cumulative podiums', style: {{ color: '#8b949e', fontSize: '11px', fontWeight: 600 }} }},
        }},
        grid: {{
            borderColor: '#2a313c',
            strokeDashArray: 3,
        }},
        legend: {{
            show: true,
            position: 'right',
            horizontalAlign: 'left',
            offsetY: 4,
            labels: {{ colors: '#c9d1d9' }},
            markers: {{ size: 6, shape: 'square', strokeWidth: 0, offsetX: -2 }},
            itemMargin: {{ horizontal: 6, vertical: 3 }},
            fontSize: '12px',
            fontWeight: 500,
            onItemHover: {{ highlightDataSeries: true }},
        }},
        tooltip: {{
            theme: 'dark',
            shared: false,
            intersect: false,
            x: {{ show: false }},
            custom: function({{seriesIndex, dataPointIndex, w}}) {{
                const point = w.config.series[seriesIndex].data[dataPointIndex];
                if (!point) return '';
                const name = w.config.series[seriesIndex].name;
                const color = w.globals.colors[seriesIndex];
                const year = point.year || yearForIdx(point.x);
                const race = point.raceName ? '<div class="tt-dim">' + year + ' R' + (point.round || '?') + ' &middot; ' + point.raceName + '</div>' : '<div class="tt-dim">' + year + '</div>';
                return '<div class="apex-tt">'
                    + '<div class="tt-head" style="color:' + color + '">' + name + '</div>'
                    + '<div class="tt-row">' + point.y + ' career podiums</div>'
                    + race
                    + '</div>';
            }},
        }},
        responsive: [{{
            breakpoint: 760,
            options: {{
                chart: {{ height: 460 }},
                legend: {{ position: 'bottom', offsetY: 0 }},
            }},
        }}],
    }};
    new ApexCharts(document.getElementById('career-line-race'), options).render();
}})();
"""

    return {"html": html, "js_init": js}


def render_top25_dotplot(breakdown: list[dict]) -> dict[str, str]:
    """Horizontal stacked bar of top-25 podium-getters, segmented by P1/P2/P3."""
    rows = breakdown[:25]
    # Reverse so #1 lands at top of the chart (ApexCharts plots first category at bottom)
    rows = list(reversed(rows))

    names = [r["name"] for r in rows]
    p1 = [r["p1"] for r in rows]
    p2 = [r["p2"] for r in rows]
    p3 = [r["p3"] for r in rows]
    meta = [
        {"total": r["total"], "firstYear": r["firstYear"], "lastYear": r["lastYear"]}
        for r in rows
    ]

    series = [
        {"name": "P1 wins", "data": p1, "color": "#f4c430"},
        {"name": "P2",      "data": p2, "color": "#c0c0c0"},
        {"name": "P3",      "data": p3, "color": "#cd7f32"},
    ]

    series_json = json.dumps(series, ensure_ascii=False)
    names_json = json.dumps(names, ensure_ascii=False)
    meta_json = json.dumps(meta, ensure_ascii=False)

    html = """
<section class="chart-card" id="chart-top25-dotplot">
    <div class="chart-head">
        <h2>All-Time Podiums &mdash; Top 25</h2>
        <span class="chart-sub" style="margin: 0;">Gold = P1, silver = P2, bronze = P3</span>
    </div>
    <p class="chart-sub">Career podium counts for the 25 most decorated F1 drivers, segmented by finishing position. Hover for breakdown and active years.</p>
    <div class="chart-host"><div id="top25-dotplot"></div></div>
</section>
"""

    js = f"""
(function() {{
    const series = {series_json};
    const names = {names_json};
    const meta = {meta_json};
    const options = {{
        chart: {{
            type: 'bar',
            height: 620,
            stacked: true,
            background: 'transparent',
            foreColor: '#c9d1d9',
            toolbar: {{ show: false }},
            animations: {{ enabled: false }},
            fontFamily: 'inherit',
        }},
        series: series,
        plotOptions: {{
            bar: {{
                horizontal: true,
                barHeight: '62%',
                borderRadius: 2,
                borderRadiusApplication: 'end',
            }},
        }},
        dataLabels: {{
            enabled: true,
            formatter: function(val, opts) {{
                if (opts.seriesIndex !== 0) return '';
                const m = meta[opts.dataPointIndex];
                return m ? m.total : '';
            }},
            textAnchor: 'start',
            offsetX: 6,
            style: {{
                colors: ['#e6edf3'],
                fontSize: '12px',
                fontWeight: 700,
                fontFamily: 'ui-monospace, SFMono-Regular, "Cascadia Mono", Menlo, Consolas, monospace',
            }},
            background: {{ enabled: false }},
        }},
        xaxis: {{
            categories: names,
            labels: {{ style: {{ colors: '#8b949e', fontSize: '11px' }} }},
            axisBorder: {{ color: '#2a313c' }},
            axisTicks: {{ color: '#2a313c' }},
        }},
        yaxis: {{
            labels: {{
                style: {{ colors: '#c9d1d9', fontSize: '12px', fontWeight: 500 }},
                maxWidth: 180,
            }},
        }},
        grid: {{
            borderColor: '#2a313c',
            strokeDashArray: 3,
            yaxis: {{ lines: {{ show: false }} }},
        }},
        legend: {{
            show: true,
            position: 'top',
            horizontalAlign: 'left',
            offsetY: -4,
            labels: {{ colors: '#8b949e' }},
            markers: {{ size: 6, shape: 'square', strokeWidth: 0, offsetX: -2 }},
            itemMargin: {{ horizontal: 8, vertical: 2 }},
            fontSize: '11px',
            fontWeight: 600,
        }},
        tooltip: {{
            theme: 'dark',
            shared: true,
            intersect: false,
            custom: function({{series, dataPointIndex, w}}) {{
                const name = w.globals.labels[dataPointIndex];
                const m = meta[dataPointIndex];
                const p1v = series[0][dataPointIndex];
                const p2v = series[1][dataPointIndex];
                const p3v = series[2][dataPointIndex];
                return '<div class="apex-tt">'
                    + '<div class="tt-head">' + name + '</div>'
                    + '<div class="tt-row">' + m.total + ' career podiums</div>'
                    + '<div class="tt-row">'
                    +   '<span style="color:#f4c430">' + p1v + ' P1</span> &middot; '
                    +   '<span style="color:#c0c0c0">' + p2v + ' P2</span> &middot; '
                    +   '<span style="color:#cd7f32">' + p3v + ' P3</span>'
                    + '</div>'
                    + '<div class="tt-dim">' + m.firstYear + '&ndash;' + m.lastYear + '</div>'
                    + '</div>';
            }},
        }},
        responsive: [{{
            breakpoint: 760,
            options: {{
                chart: {{ height: 720 }},
                yaxis: {{ labels: {{ style: {{ fontSize: '11px' }}, maxWidth: 110 }} }},
            }},
        }}],
    }};
    new ApexCharts(document.getElementById('top25-dotplot'), options).render();
}})();
"""

    return {"html": html, "js_init": js}


def render_soulmate_matrix(soulmates: dict) -> dict[str, str]:
    """40x40 driver-pair heatmap. Color = # shared podiums. Drivers sorted by era."""
    drivers = soulmates["drivers"]
    matrix = soulmates["matrix"]
    max_val = soulmates.get("max", 1) or 1

    names = [d["name"] for d in drivers]
    n = len(names)

    # ApexCharts plots first series at the bottom; reverse so oldest era ends up at the bottom too.
    # We want the era to read top-to-bottom = newest to oldest, matching how the year scale flows.
    series = []
    # Newest era at top of chart -> last in sorted_names is newest -> first in series
    for i in range(n - 1, -1, -1):
        row_name = names[i]
        data = []
        for j in range(n):
            v = matrix[i][j] if i != j else None
            data.append({"x": names[j], "y": v})
        series.append({"name": row_name, "data": data})

    series_json = json.dumps(series, ensure_ascii=False)

    # Color ranges scaled by max_val (relative steps)
    def step(p: float) -> int:
        return max(1, int(round(max_val * p)))
    ranges = [
        {"from": 1, "to": step(0.10), "color": "#3d1a17"},
        {"from": step(0.10) + 1, "to": step(0.25), "color": "#6a1410"},
        {"from": step(0.25) + 1, "to": step(0.45), "color": "#a50300"},
        {"from": step(0.45) + 1, "to": step(0.70), "color": "#d80500"},
        {"from": step(0.70) + 1, "to": max_val, "color": "#ff2d20"},
    ]
    # Dedupe overlapping ranges (e.g. when max_val is small)
    seen_to = -1
    dedup_ranges = [{"from": 0, "to": 0, "color": "#262d38", "name": "no shared"}]
    for r in ranges:
        if r["to"] > seen_to and r["from"] <= r["to"]:
            r["from"] = max(r["from"], seen_to + 1)
            dedup_ranges.append(r)
            seen_to = r["to"]
    ranges_json = json.dumps(dedup_ranges)

    pairs = soulmates.get("topPairs", [])[:20]
    pairs_html = "\n".join(
        f'<li class="pair-row">'
        f'<span class="pair-rank">{i+1}</span>'
        f'<span class="pair-names"><b>{p["a"]}</b> &amp; <b>{p["b"]}</b></span>'
        f'<span class="pair-count">{p["count"]}</span>'
        f'<span class="pair-years">{p["firstYear"]}&ndash;{p["lastYear"]}</span>'
        f'</li>'
        for i, p in enumerate(pairs)
    )

    html = f"""
<section class="chart-card" id="chart-soulmate-matrix">
    <div class="chart-head">
        <h2>Podium Soulmates</h2>
        <span class="chart-sub" style="margin: 0;">Top 40 drivers, sorted by era</span>
    </div>
    <p class="chart-sub">For each pair of legendary drivers, how many races did they share a podium together? Era-mates form bright squares along the diagonal &mdash; Senna &amp; Prost, Schumacher &amp; Barrichello, Hamilton &amp; Verstappen.</p>
    <div class="soulmate-grid">
        <div class="chart-host"><div id="soulmate-matrix"></div></div>
        <aside class="pair-list">
            <h3>Top pairs</h3>
            <ol class="pair-rows">
                {pairs_html}
            </ol>
        </aside>
    </div>
</section>
"""

    js = f"""
(function() {{
    const series = {series_json};
    const ranges = {ranges_json};
    const options = {{
        chart: {{
            type: 'heatmap',
            height: 760,
            background: 'transparent',
            foreColor: '#c9d1d9',
            toolbar: {{ show: false }},
            animations: {{ enabled: false }},
            fontFamily: 'inherit',
        }},
        series: series,
        plotOptions: {{
            heatmap: {{
                radius: 1,
                enableShades: false,
                useFillColorAsStroke: false,
                colorScale: {{ ranges: ranges }},
            }},
        }},
        stroke: {{ width: 1, colors: ['#0b0d12'] }},
        dataLabels: {{ enabled: false }},
        xaxis: {{
            type: 'category',
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '9px' }},
                rotate: -55,
                rotateAlways: true,
                trim: false,
                hideOverlappingLabels: false,
            }},
            axisBorder: {{ color: '#2a313c' }},
            axisTicks: {{ color: '#2a313c' }},
            position: 'top',
        }},
        yaxis: {{
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '10px' }},
                maxWidth: 160,
            }},
        }},
        grid: {{ show: false, padding: {{ top: 0, right: 8, bottom: 0, left: 0 }} }},
        legend: {{
            show: true,
            position: 'bottom',
            horizontalAlign: 'left',
            labels: {{ colors: '#8b949e' }},
            markers: {{ size: 6, shape: 'square', strokeWidth: 0, offsetX: -2 }},
            itemMargin: {{ horizontal: 8, vertical: 2 }},
            fontSize: '11px',
            fontWeight: 600,
        }},
        tooltip: {{
            theme: 'dark',
            custom: function({{seriesIndex, dataPointIndex, w}}) {{
                const point = w.config.series[seriesIndex].data[dataPointIndex];
                if (!point || point.y === null || point.y === undefined || point.y === 0) return '';
                const a = w.config.series[seriesIndex].name;
                const b = point.x;
                return '<div class="apex-tt">'
                    + '<div class="tt-head">' + a + ' &amp; ' + b + '</div>'
                    + '<div class="tt-row">' + point.y + ' shared podium' + (point.y === 1 ? '' : 's') + '</div>'
                    + '</div>';
            }},
        }},
    }};
    new ApexCharts(document.getElementById('soulmate-matrix'), options).render();
}})();
"""

    return {"html": html, "js_init": js}


def render_alignment_depth_area(seasons: list[dict]) -> dict[str, str]:
    """100% stacked area: per-year share of races by matchLength bucket {0, 1, 2, 3+}."""
    by_year = sorted(seasons, key=lambda s: int(s["season"]))

    years: list[str] = []
    bucket_pct: dict[str, list[float]] = {"0": [], "1": [], "2": [], "3+": []}

    for s in by_year:
        races = s["races"]
        total = len(races)
        if not total:
            continue
        years.append(s["season"])
        counts = {"0": 0, "1": 0, "2": 0, "3+": 0}
        for r in races:
            L = r["matchLength"]
            key = "3+" if L >= 3 else str(L)
            counts[key] += 1
        for k in bucket_pct:
            bucket_pct[k].append(round(100 * counts[k] / total, 2))

    series = [
        {"name": "no match", "data": bucket_pct["0"], "color": "#262d38"},
        {"name": "top 1",    "data": bucket_pct["1"], "color": "#5b6470"},
        {"name": "top 2",    "data": bucket_pct["2"], "color": "#8a0500"},
        {"name": "top 3+",   "data": bucket_pct["3+"], "color": "#ff2d20"},
    ]

    series_json = json.dumps(series, ensure_ascii=False)
    years_json = json.dumps(years)

    html = """
<section class="chart-card" id="chart-alignment-depth">
    <div class="chart-head">
        <h2>Alignment Depth Share Over Time</h2>
        <span class="chart-sub" style="margin: 0;">Hover for year breakdown</span>
    </div>
    <p class="chart-sub">For each season, what fraction of its races finished aligned with the final WDC standings, broken down by depth. Bright red is the headline story: years where multiple races mirrored the championship's top-3+ in order.</p>
    <div class="chart-host"><div id="alignment-depth-area"></div></div>
</section>
"""

    js = f"""
(function() {{
    const series = {series_json};
    const years = {years_json};
    const options = {{
        chart: {{
            type: 'area',
            height: 380,
            stacked: true,
            stackType: '100%',
            background: 'transparent',
            foreColor: '#c9d1d9',
            toolbar: {{ show: false }},
            zoom: {{ enabled: false }},
            animations: {{ enabled: false }},
            fontFamily: 'inherit',
        }},
        series: series,
        dataLabels: {{ enabled: false }},
        stroke: {{ width: 0 }},
        fill: {{
            type: 'solid',
            opacity: 1,
        }},
        xaxis: {{
            type: 'category',
            categories: years,
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '11px' }},
                rotate: 0,
                hideOverlappingLabels: true,
                formatter: function(v) {{
                    const n = parseInt(v, 10);
                    return (!isNaN(n) && n % 5 === 0) ? v : '';
                }},
            }},
            axisBorder: {{ color: '#2a313c' }},
            axisTicks: {{ color: '#2a313c' }},
            tooltip: {{ enabled: false }},
        }},
        yaxis: {{
            min: 0,
            max: 100,
            tickAmount: 4,
            labels: {{
                style: {{ colors: '#8b949e', fontSize: '11px' }},
                formatter: function(v) {{ return Math.round(v) + '%'; }},
            }},
        }},
        grid: {{
            borderColor: '#2a313c',
            strokeDashArray: 3,
            xaxis: {{ lines: {{ show: false }} }},
        }},
        legend: {{
            show: true,
            position: 'top',
            horizontalAlign: 'left',
            offsetY: -4,
            labels: {{ colors: '#8b949e' }},
            markers: {{ size: 6, shape: 'square', strokeWidth: 0, offsetX: -2 }},
            itemMargin: {{ horizontal: 8, vertical: 2 }},
            fontSize: '11px',
            fontWeight: 600,
        }},
        tooltip: {{
            theme: 'dark',
            shared: true,
            intersect: false,
            custom: function({{series, seriesIndex, dataPointIndex, w}}) {{
                const year = w.globals.labels[dataPointIndex];
                let html = '<div class="apex-tt"><div class="tt-head">' + year + '</div>';
                for (let i = 0; i < series.length; i++) {{
                    const name = w.globals.seriesNames[i];
                    const v = series[i][dataPointIndex];
                    if (v === undefined || v === null) continue;
                    const color = w.globals.colors[i];
                    html += '<div class="tt-row">'
                        + '<span style="display:inline-block;width:9px;height:9px;background:' + color
                        + ';margin-right:6px;border-radius:1px;"></span>'
                        + name + ': ' + v.toFixed(0) + '%'
                        + '</div>';
                }}
                html += '</div>';
                return html;
            }},
        }},
    }};
    new ApexCharts(document.getElementById('alignment-depth-area'), options).render();
}})();
"""

    return {"html": html, "js_init": js}
