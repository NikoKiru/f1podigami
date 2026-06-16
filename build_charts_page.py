"""Render charts.html — dashboard page with embedded ApexCharts visualizations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build_charts
from build_alignments_html import CSS as BASE_CSS

ROOT = Path(__file__).parent
ALIGNMENTS_PATH = ROOT / "data" / "alignments.json"
CAREER_PATH = ROOT / "data" / "career_podiums.json"
OUT_PATH = ROOT / "charts.html"


def main() -> int:
    seasons = json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))
    career = json.loads(CAREER_PATH.read_text(encoding="utf-8"))
    heatmap = build_charts.render_alignment_heatmap(seasons)
    depth_area = build_charts.render_alignment_depth_area(seasons)
    line_race = build_charts.render_career_line_race(career)
    dotplot = build_charts.render_top25_dotplot(career["breakdown"])

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<title>F1 Charts &middot; Podigami</title>
<style>{BASE_CSS}{build_charts.CHART_CSS}</style>
{build_charts.APEX_CDN_TAG}
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html">&larr; Podium Combinations</a>
        <a href="seasons.html">Season Alignments</a>
        <a href="charts.html" class="active">Charts</a>
        <a href="soulmates.html">Soulmates &rarr;</a>
    </div>
</nav>
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Charts</h1>
        <p class="tagline">Visual overviews of 76 years of F1 podium history. Hover any chart for race-level detail.</p>
    </div>
</header>
<main>
    <div class="container">
        {line_race["html"]}
        {dotplot["html"]}
        {depth_area["html"]}
        {heatmap["html"]}
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; 1950&ndash;2025
    </div>
</footer>
<script>{line_race["js_init"]}</script>
<script>{dotplot["js_init"]}</script>
<script>{depth_area["js_init"]}</script>
<script>{heatmap["js_init"]}</script>
</body>
</html>
"""
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
