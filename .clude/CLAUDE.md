# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

F1 Podigami is a Python static site generator that transforms Formula 1 race data (1950–present) into four interactive HTML pages. No backend server or framework — just Python, `requests`, and committed JSON datasets.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Full pipeline: fetch latest data from API + rebuild site
python src/update.py

# Full pipeline including seasonal data (standings, top10, alignments)
python src/update.py --full

# Rebuild HTML from committed JSON (no network needed)
python src/build_site.py

# Run tests
pytest -q

# Run a single test file
pytest tests/test_data_integrity.py -q

# Run a single test
pytest tests/test_build_output.py::test_index_has_table -q
```

## Architecture

Three-stage pipeline: **Fetch → Compute → Render**

```
src/fetch/       → API calls to Jolpica F1 API → data/*.json
src/compute/     → Aggregation over fetched data → data/*.json
src/build/       → HTML generation from JSON    → dist/*.html
```

Orchestrators:
- `src/update.py` — runs fetch + compute + build via `subprocess` calls to individual scripts
- `src/build_site.py` — runs only the build stage, copies `assets/` into `dist/`

### Four output pages

| Page | Builder | Description |
|------|---------|-------------|
| `index.html` | `build/build_html.py` | Every unique 3-driver podium combination |
| `soulmates.html` | `build/build_soulmates_html.py` | Top-40 driver shared-podium heatmap |
| `charts.html` | `build/build_charts_page.py` | Career trajectories, partnership charts |
| `seasons.html` | `build/build_alignments_html.py` | Per-race vs championship alignment per season |

### Data flow

JSON files in `data/` are **committed to git** and serve as the intermediate format between stages. Each fetch/compute script reads/writes specific JSON files. The build stage only reads from `data/` — it never touches the network.

## Key Conventions

- **Path resolution**: Scripts use `Path(__file__).resolve().parents[N]` for all path references — no hardcoded absolute paths.
- **HTML generation**: String-based (no template engine). Uses `html.escape()` for user-facing data.
- **API rate limiting**: 1-second sleep between requests; exponential backoff retry on 429/5xx (up to 6 retries).
- **Each script is standalone**: Can be run individually (e.g., `python src/fetch/fetch_podiums.py`).
- **Charts**: ApexCharts loaded from CDN; chart config generated in `build/build_charts.py` (889 lines, largest module).
- **CSS breakpoint**: Primary mobile breakpoint at `max-width: 600px`.

## Testing

Three test categories in `tests/`:
- **test_data_integrity.py** — validates JSON dataset shapes and constraints
- **test_build_output.py** — checks generated HTML structure, assets, DOM elements
- **test_mobile_css.py** — mobile CSS regression tests

The `conftest.py` fixture builds `dist/` once per test session.

## Deployment

GitHub Actions deploys to GitHub Pages on push to `main`. CI runs `pytest` + build verification on every push/PR.
