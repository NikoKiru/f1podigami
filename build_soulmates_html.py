"""Render soulmates.html — driver-pair heatmap + ranked pairs sidebar."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build_charts
from build_alignments_html import CSS as BASE_CSS

ROOT = Path(__file__).parent
SOULMATES_PATH = ROOT / "data" / "soulmates.json"
OUT_PATH = ROOT / "soulmates.html"


def main() -> int:
    soulmates = json.loads(SOULMATES_PATH.read_text(encoding="utf-8"))
    matrix = build_charts.render_soulmate_matrix(soulmates)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F1 Soulmates &middot; Podigami</title>
<style>{BASE_CSS}{build_charts.CHART_CSS}</style>
{build_charts.APEX_CDN_TAG}
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
        <p class="tagline">Which legends spent the most race weekends together on the box? A symmetric heatmap of the 40 most decorated drivers, sorted by era so partnerships glow as bright clusters.</p>
    </div>
</header>
<main>
    <div class="container">
        {matrix["html"]}
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; 1950&ndash;2025
    </div>
</footer>
<script>{matrix["js_init"]}</script>
</body>
</html>
"""
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
