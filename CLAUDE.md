# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

F1 Podigami is a Python static site generator that transforms Formula 1 race data (1950–present) into four interactive HTML pages. No backend server or framework — just Python, `requests`, and committed JSON datasets. The "podigami" concept is podium scorigami: spotting 3-driver podium trios that have never happened before, and predicting which brand-new trio is most likely next.

Deployed to GitHub Pages: https://nikokiru.github.io/f1podigami

## Environment notes

- **GitHub CLI is installed and authenticated** as `NikoKiru` (scopes: `repo`, `workflow`, `read:org`, `gist`). Prefer `gh` for all GitHub operations (PRs, merges, checks) over raw API calls.
  - `gh.exe` lives at `C:\Program Files\GitHub CLI\gh.exe`. A shell started before the install may not have it on PATH; refresh with:
    ```powershell
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    ```
- Primary shell is PowerShell 7+ on Windows; a Bash tool is also available.

## Commands

```bash
# Install dependencies (runtime + dev/test)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Full pipeline: fetch latest data from API + recompute + rebuild site
python src/update.py
python src/update.py --full      # include seasonal/standings data

# Rebuild HTML from committed JSON (no network needed)
python src/build_site.py

# Validate every committed dataset against its schema (also a CI gate)
PYTHONPATH=src python -m datalib.validate

# Lint, format, test (mirrors CI)
python -m ruff check .
python -m ruff format --check .   # add --check to verify; omit to apply
python -m pytest -q

# Rebuild just the landing page during iteration
python src/build/build_podigami_html.py
```

## Architecture

Three-stage pipeline: **Fetch → Compute → Render**

```
src/fetch/    → API calls to the Jolpica F1 API (api.jolpi.ca/ergast/f1) → data/*.json
src/compute/  → Aggregation / modelling over fetched data               → data/*.json
src/build/    → HTML generation from JSON                               → dist/*.html

src/datalib/  → Pydantic schemas + typed load/save: the validated data contract
               for every data/*.json (compute writes via save_*, build reads via load_*)
```

Orchestrators:
- `src/update.py` — runs fetch + compute + build via `subprocess` calls to individual scripts.
- `src/build_site.py` — runs only the build stage, copies `assets/` into `dist/`, and writes `robots.txt` + `sitemap.xml`.

### Four output pages

`src/build_site.py` is the source of truth for the page → builder mapping:

| Page | Builder | Description |
|------|---------|-------------|
| `index.html` | `build/build_podigami_html.py` | Landing page: next race, last race result (with podigami/repeat status + wiki link), prediction hero, current form, timeline, FAQ |
| `combos.html` | `build/build_combos_html.py` | Every unique 3-driver podium combination |
| `overdue.html` | `build/build_overdue_html.py` | Trios "overdue" to appear |
| `soulmates.html` | `build/build_soulmates_html.py` | Driver shared-podium relationships |

Shared build helpers: `build/_layout.py` (page chrome: `head()`, `nav()`, `FOOTER`), `build/flags.py` (country flag SVGs), `build/team_colors.py` (`team_color()`, `text_on()`).

### Prediction model

`src/compute/model.py` + `compute_podigami.py` implement a **Plackett–Luce** model over recency-weighted driver strengths. `src/compute/backtest.py` produces `data/model_eval.json` (backtested top-k accuracy + calibration), surfaced on the landing page as a badge and in the FAQ.

### Data flow

JSON files in `data/` are **committed to git** and serve as the intermediate format between stages. The build stage only reads from `data/` — it never touches the network, which is what makes build + tests safe to run in CI.

All access to `data/*.json` goes through **`src/datalib/`** (Pydantic v2 schemas in `schemas.py`, typed `load_*`/`save_*` in `repository.py`, re-exported from the package root). `load_*` returns validated model objects (builders use attribute access); `save_*` validates the computed payload then writes it **verbatim** (byte-identical, so regenerating a dataset never reformats it). Scripts reach the package by adding `src/` to `sys.path` and importing `datalib`. `python -m datalib.validate` (with `PYTHONPATH=src`) checks every dataset against its schema and gates CI.

## Key Conventions

- **Path resolution**: scripts use `Path(__file__).resolve().parents[N]` — no hardcoded absolute paths.
- **HTML generation**: string-based (no template engine); use `html.escape()` (the `esc()` helper) for any data interpolated into HTML.
- **Each script is standalone**: can be run individually (e.g. `python src/fetch/fetch_podiums.py`).
- **API rate limiting**: 1-second sleep between requests; exponential backoff on 429/5xx.
- **Lint/format**: `ruff` (config in `pyproject.toml`). CI fails on `ruff check` or `ruff format --check` violations — run both before pushing.
- **CSS**: global tokens in `assets/style.css`; page-specific styles in `assets/podigami.css` etc. Primary mobile breakpoint at `max-width: 600px`.

## Testing

Tests live in `tests/` (pytest). Notable files: `test_build_output.py` (generated HTML structure), `test_build_podigami.py` (landing-page render helpers), `test_compute_podigami.py` / `test_model.py` / `test_backtest.py` (modelling), `test_datalib.py` (schema fidelity + byte-identical load/save round-trips), `test_data_integrity.py` (semantic dataset invariants), `test_mobile_css.py` (mobile CSS regressions).

The `conftest.py` `dist` fixture builds `dist/` once per session via `build_site.py`; tests then assert against the real generated output. When you change rendered HTML, update the corresponding assertions.

## Pull Requests

A PR template lives at `.github/pull_request_template.md`. When creating PRs via `gh pr create`, always follow this template structure in the body:
- **Summary**: what changed and why.
- **Changes**: bullet list of specific changes.
- **Testing**: how the change was verified (e.g. `pytest -q`, `ruff check .`, manual).
- **Checklist**: confirm lint, format, tests pass, and no security issues introduced.

## GitHub Issues

Issue templates live in `.github/ISSUE_TEMPLATE/`. When creating issues via `gh issue create`, use the appropriate template:
- **Bug Report** (`bug_report.yml`): for broken behavior — include description, repro steps, and expected behavior.
- **Feature Request** (`feature_request.yml`): for new features or improvements — include description and motivation.

Always prefer these templates over blank issues so reports stay structured and actionable.

## Deployment

GitHub Actions (`.github/workflows/`) runs CI (lint, format, tests across py3.11–3.13, build + link-check, CodeQL, security scans) on every push/PR, and deploys to GitHub Pages on push to `main`. `dist/` is gitignored — it is built in CI, not committed.
