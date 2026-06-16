# F1 Podigami

A static-site generator that turns 76 years of Formula 1 race data into four browsable HTML pages — no server, no framework, just Python and a single `requests` dependency. The pages are fully responsive and tuned for mobile.

## Project layout

```
src/
  fetch/      API fetchers          -> data/*.json
  compute/    aggregation/analysis  -> data/*.json
  build/      page renderers        -> dist/*.html
  build_site.py   builds dist/ (renders pages + copies assets)
  update.py       refresh data, then build the site
assets/       source CSS + JS (copied into dist/ at build time)
data/         committed JSON datasets the site builds from
dist/         generated, deployable site (git-ignored)
tests/        pytest suite (run in CI)
```

---

## Pages

| File | What it shows |
|---|---|
| `index.html` | Every unique three-driver combination that has shared an F1 podium since 1950 — order doesn't matter, only the set |
| `soulmates.html` | A symmetric heatmap of the 40 most decorated drivers; how many podiums did each pair share? Sorted by era so partnerships cluster on the diagonal |
| `charts.html` | Career podium trajectories, a top-25 dot plot, and alignment charts — hover any point for race-level detail |
| `seasons.html` | For each completed season (1950–2025), how far did each race's finishing order match the year's final WDC standings? Top 3, top 5, top 10… |

---

## Data source

All race data is fetched from the [Jolpica F1 API](https://api.jolpi.ca) (an Ergast-compatible endpoint). No API key required.

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

---

## Usage

### After each race (fast)

Fetches new podium data incrementally (only the current season) and rebuilds the three podium-driven pages.

```bash
python src/update.py
```

The built site lands in `dist/` — open `dist/index.html` in your browser.

### Rebuild the site without fetching (offline)

Re-render all pages from the committed data and refresh `dist/`:

```bash
python src/build_site.py
```

### After the final race of a season (full rebuild)

Also re-fetches top-10 results and driver standings for all seasons, recomputes alignment data, and rebuilds `seasons.html`. This is slow — it pages through the full history.

```bash
python src/update.py --full
```

### First-ever run / full history rebuild

Wipe and re-fetch everything from 1950:

```bash
python src/fetch/fetch_podiums.py --full
python src/update.py --full
```

---

## Tests & CI

```bash
pytest
```

The suite (in `tests/`) covers data integrity, mobile-CSS regressions, and built-HTML
validation. It runs on every push and pull request via `.github/workflows/ci.yml`.

## Deployment

`.github/workflows/deploy.yml` builds `dist/` and publishes it to **GitHub Pages** on
every push to `main`. Enable it once under **Settings → Pages → Build and deployment →
Source: GitHub Actions**.

---

## Pipeline

```
                         ┌─ count_combos ────────────── build_html ───────────► dist/index.html
fetch_podiums ───────────┼─ compute_career_podiums ───── build_charts_page ───► dist/charts.html
                         └─ compute_soulmates ────────── build_soulmates_html ► dist/soulmates.html

fetch_standings ─┐
                 ├─ compute_alignments ── build_alignments_html ──────────────► dist/seasons.html
fetch_top10 ─────┘

└─── src/update.py (default) runs fetch+compute (top block), then build_site ───────────────┘
└─── src/update.py --full    also runs the seasonal block ──────────────────────────────────┘
```

---

## File map

| Script | Role |
|---|---|
| `src/fetch/fetch_podiums.py` | Fetch P1/P2/P3 for every race → `data/podiums.json` |
| `src/fetch/fetch_standings.py` | Fetch final WDC standings per season → `data/standings.json` |
| `src/fetch/fetch_top10.py` | Fetch top-10 finishers for every race → `data/top10.json` |
| `src/compute/count_combos.py` | Aggregate podiums into unique trios → `data/combos.json` |
| `src/compute/compute_career_podiums.py` | Cumulative podium trajectories per driver → `data/career_podiums.json` |
| `src/compute/compute_soulmates.py` | Shared-podium matrix for top-40 drivers → `data/soulmates.json` |
| `src/compute/compute_alignments.py` | Race-vs-championship order matching → `data/alignments.json` |
| `src/build/build_html.py` | Render `dist/index.html` |
| `src/build/build_soulmates_html.py` | Render `dist/soulmates.html` |
| `src/build/build_charts_page.py` | Render `dist/charts.html` |
| `src/build/build_alignments_html.py` | Render `dist/seasons.html` |
| `src/build/build_charts.py` | Shared ApexCharts rendering helpers |
| `src/build_site.py` | Build `dist/` (render all pages + copy assets) |
| `src/update.py` | Refresh data, then build the site |
