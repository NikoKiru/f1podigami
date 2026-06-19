"""Render data/podigami.json into dist/index.html (the landing page).

Shows the current season's most likely *brand-new* podium trio ("podigami"),
a ranked list of contenders, the current-form grid, and a year-slider timeline
of every trio that debuted in each season.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PODIGAMI_PATH = ROOT / "data" / "podigami.json"
OUT_PATH = ROOT / "dist" / "index.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def render_trio_names(names: list[str], extra: str = "") -> str:
    parts = '<span class="sep">/</span>'.join(
        f'<span class="pdriver">{esc(n)}</span>' for n in names
    )
    cls = f"trio {extra}".strip()
    return f'<span class="{cls}">{parts}</span>'


def render_hero(top: dict, chance: float) -> str:
    pd = "".join(
        f'<div class="hero-driver">'
        f'<div class="hd-name">{esc(p["name"])}</div>'
        f'<div class="hd-stat">{p["seasonPodiums"]} podium{"s" if p["seasonPodiums"] != 1 else ""} this season</div>'
        f'</div>'
        for p in top["perDriver"]
    )
    return (
        f'<section class="hero">'
        f'  <div class="hero-head">'
        f'    <div class="hero-chance"><span class="hc-num">{chance:.0f}%</span>'
        f'      <span class="hc-label">chance the next race<br>delivers a brand-new trio</span></div>'
        f'  </div>'
        f'  <div class="hero-pick">'
        f'    <div class="hp-label">Most likely next <span class="accent">podigami</span></div>'
        f'    <div class="hero-drivers">{pd}</div>'
        f'    <div class="hp-prob">{top["prob"]:.1f}% of all possible podiums &mdash; the top never-before trio</div>'
        f'  </div>'
        f'</section>'
    )


def render_candidates(cands: list[dict]) -> str:
    if not cands:
        return ""
    top = cands[0]["prob"] or 1
    rows = []
    for i, c in enumerate(cands, 1):
        pct = round(100 * c["prob"] / top)
        rows.append(
            f'<li class="cand">'
            f'<span class="cand-rank">{i}</span>'
            f'<div class="cand-body">'
            f'  <div class="cand-names">{render_trio_names(c["names"], "trio-sm")}</div>'
            f'  <div class="cand-bar-wrap"><div class="cand-bar" style="width:{pct}%"></div></div>'
            f'</div>'
            f'<span class="cand-prob">{c["prob"]:.2f}%</span>'
            f'</li>'
        )
    return (
        f'<section class="panel">'
        f'  <h2>Most likely next combinations</h2>'
        f'  <p class="panel-sub">Trios that have never shared a podium, ranked by the model\'s probability they do it next.</p>'
        f'  <ol class="cand-list">{"".join(rows)}</ol>'
        f'</section>'
    )


def render_form(form: list[dict]) -> str:
    show = [d for d in form if d["weight"] > 0][:14]
    mx = max((d["weight"] for d in show), default=1)
    chips = []
    for d in show:
        pct = round(100 * d["weight"] / mx)
        chips.append(
            f'<div class="form-chip">'
            f'  <div class="fc-top"><span class="fc-name">{esc(d["name"])}</span>'
            f'    <span class="fc-w">{d["weight"]:.1f}</span></div>'
            f'  <div class="fc-bar-wrap"><div class="fc-bar" style="width:{pct}%"></div></div>'
            f'</div>'
        )
    return (
        f'<section class="panel">'
        f'  <h2>Current form</h2>'
        f'  <p class="panel-sub">Each driver\'s podium weight &mdash; recent podiums decay over ~8 races, with a boost for this season.</p>'
        f'  <div class="form-grid">{"".join(chips)}</div>'
        f'</section>'
    )


def render_timeline(data: dict) -> str:
    lo, hi = data["seasonRange"]
    current = int(data["currentSeason"])
    counts = data["seasonCounts"]
    mx = max(counts.values()) if counts else 1
    bars = []
    for y in range(lo, hi + 1):
        n = counts.get(str(y), 0)
        h = round(100 * n / mx) if mx else 0
        bars.append(
            f'<span class="tl-bar" data-season="{y}" title="{y}: {n} new trio(s)" '
            f'style="height:{max(h, 2)}%"></span>'
        )
    return (
        f'<section class="panel timeline">'
        f'  <h2>New podiums through the years</h2>'
        f'  <p class="panel-sub">Every trio that debuted on a podium that season. Drag the slider or click a bar.</p>'
        f'  <div class="tl-spark">{"".join(bars)}</div>'
        f'  <div class="tl-controls">'
        f'    <input type="range" id="tl-slider" min="{lo}" max="{hi}" value="{current}" step="1">'
        f'    <div class="tl-readout"><span id="tl-year">{current}</span>'
        f'      <span class="tl-count" id="tl-count"></span></div>'
        f'  </div>'
        f'  <ul class="tl-list" id="tl-list"></ul>'
        f'</section>'
    )


def main() -> int:
    data = json.loads(PODIGAMI_PATH.read_text(encoding="utf-8"))
    season = data["currentSeason"]
    chance = data["chanceNextRaceNew"]
    as_of = data["asOf"]
    cands = data["candidates"]
    lo, hi = data["seasonRange"]

    hero = render_hero(cands[0], chance) if cands else ""
    candidates = render_candidates(cands)
    form = render_form(data["driverForm"])
    timeline = render_timeline(data)

    # Embedded data for the slider (only what the client needs).
    embed = json.dumps(
        {"bySeason": data["bySeason"], "seasonCounts": data["seasonCounts"],
         "currentSeason": season},
        ensure_ascii=False,
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<title>F1 Podigami - Next Likely New Podium ({season})</title>
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="podigami.css">
</head>
<body>
<nav class="nav">
    <div class="container nav-inner">
        <a href="index.html" class="active">Podigami</a>
        <a href="combos.html">Combinations</a>
        <a href="soulmates.html">Soulmates &rarr;</a>
    </div>
</nav>
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Podigami</h1>
        <p class="tagline">Which never-before podium trio is most likely to happen next &mdash; a scorigami-style predictor for the {season} season, scored from {lo}&ndash;{hi} of podium history.</p>
    </div>
</header>
<main>
    <div class="container">
        {hero}
        <p class="as-of">Model up to date through the {esc(as_of["season"])} {esc(as_of["raceName"])} (round {esc(as_of["round"])}).</p>
        {candidates}
        {form}
        {timeline}
    </div>
</main>
<footer>
    <div class="container">
        Data from <a href="https://api.jolpi.ca/ergast/f1/" target="_blank" rel="noopener">Jolpica F1 API</a>
        &middot; Prediction is for fun, not betting &middot; <a href="combos.html">browse all combinations &rarr;</a>
    </div>
</footer>
<script type="application/json" id="podigami-data">{embed}</script>
<script src="podigami.js"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}: P(new)={chance}%, {len(cands)} candidates, seasons {lo}-{hi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
