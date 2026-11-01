# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

F1 Podigami is a Python static site generator that transforms Formula 1 race data (1950–present) into six interactive HTML pages (plus a 404 page). No backend server or framework — just Python, `requests`, and committed JSON datasets. The "podigami" concept is podium scorigami: spotting 3-driver podium trios that have never happened before, and predicting which brand-new trio is most likely next. The name is podium + origami, the way scorigami is score + origami.

Deployed to GitHub Pages: https://nikokiru.github.io/f1podigami

## Environment notes

- **GitHub CLI is installed and authenticated** as `NikoKiru` (scopes: `repo`, `workflow`, `read:org`, `gist`). Prefer `gh` for all GitHub operations (PRs, merges, checks) over raw API calls.
  - `gh.exe` lives at `C:\Program Files\GitHub CLI\gh.exe`. A shell started before the install may not have it on PATH; refresh with:
    ```powershell
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    ```
- Primary shell is PowerShell 7+ on Windows; a Bash tool is also available.
- **Playwright is a Python package here, not an MCP server.** It's in `.venv` with Chromium and Firefox, and isn't in `requirements-dev.txt`: CI's `E2E (browser)` job (not a required check) installs it itself to run `tests/test_e2e.py` and `tests/test_slider_alignment.py`, which skip without it. Drive a real browser to verify browser-only behaviour (JS-rendered timeline, asset cache-busting, mobile layout) against the live site or a built `dist/`. Preferred over hand-rolled checks when a change is only observable in a rendered page. Headless browsers hide scrollbars: pass `ignore_default_args=["--hide-scrollbars"]`, or launch headed (`channel="msedge", headless=False`).
- **The `github` MCP server is available** — structured GitHub access (PRs, issues, reviews, code search) when its typed results are clearer than parsing `gh` output. For routine git/PR/merge operations, `gh` remains the default (see above); use the MCP when it genuinely simplifies the task.

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
src/fetch/    → API calls to the Jolpica F1 API (api.jolpi.ca/ergast/f1), plus OpenF1 for the newest round only → data/*.json
src/compute/  → Aggregation / modelling over fetched data               → data/*.json
src/build/    → HTML generation from JSON                               → dist/*.html

src/datalib/  → Pydantic schemas + typed load/save: the validated data contract
               for every data/*.json (compute writes via save_*, build reads via load_*)
```

Orchestrators:
- `src/update.py` — runs fetch + compute + build via `subprocess` calls to individual scripts.
- `src/build_site.py` — runs only the build stage, copies `assets/` into `dist/`, and writes `robots.txt` + `sitemap.xml`.
- `src/check_update_due.py` — cheap, no-network CI guard (`is_update_due`) for the automated refresh (polls every 15 min): decides from committed `schedule.json` + `podigami.json` `asOf` whether a finished race is newer than the data. See **Deployment → Automated data updates**.

### Six output pages

`src/build_site.py` is the source of truth for the page → builder mapping (it also builds `404.html` via `build/build_404_html.py`):

| Page | Builder | Description |
|------|---------|-------------|
| `index.html` | `build/build_podigami_html.py` | Landing page: next race, last race result (with podigami/repeat status + official F1 result link), prediction hero, current form, discovery hook cards, timeline, FAQ |
| `combos.html` | `build/build_combos_html.py` | Every unique 3-driver podium combination |
| `overdue.html` | `build/build_overdue_html.py` | Trios "overdue" to appear |
| `unlikeliest.html` | `build/build_unlikeliest.py` | Trios that happened despite the odds, ranked by improbability |
| `soulmates.html` | `build/build_soulmates_html.py` | Driver shared-podium relationships |
| `scorecard.html` | `build/build_scorecard_html.py` | Each race's published prediction against its real podium, with the totals |

Shared build helpers: `build/_layout.py` (page chrome: `head()`, `nav()`, `FOOTER`, `WELCOME`), `build/_hooks.py` (cross-page discovery hook cards), `build/flags.py` (country flag SVGs), `build/team_colors.py` (`team_color()`, `text_on()`).

### Prediction model

The live predictor is **model v2** (`src/compute/model_v2.py`, params tag `dbpl-v2`): a dynamic Bayesian rating engine — Gaussian driver+constructor log-worth ratings filtered over `data/race_results.json` (full classifications 1950→) and `data/qualifying.json` (1994→) via closed-form truncated Plackett–Luce updates, with decayed DNF hazards (mechanical → car, incident → driver), circuit chaos character, and a deterministic Rao-Blackwellised podium simulation (fixed seed; same inputs → byte-identical JSON). `compute_podigami.py` uses it whenever `race_results.json` exists and falls back to the v1 recency Plackett–Luce model (`src/compute/model.py`) otherwise.

`src/compute/backtest.py` is the integrity core: a walk-forward ladder (v1 rungs + v2 ablation rungs) tuned on 2010–2018 and scored on a frozen 2019+ test window → `data/model_eval.json`, surfaced on the landing page as a badge and in the FAQ. An acceptance gate in `evaluate()` keeps v2 "chosen" only while it beats v1 on test logLoss AND brierNew. Tuning knobs are locked in `model_v2.DEFAULT_PARAMS_V2` (`--tune-v2` re-derives them; notable verdicts: qualifying weight 0.6, attrition channel 0).

`compute_podigami.py` still folds in `data/constructor_standings.json` (team labels + each driver's `constructorId`/`constructorStrength`), so a refresh that picks up updated standings can rewrite most numeric values in `podigami.json` even when `asOf` is unchanged — that churn is expected, not a bug. The two raw v2 datasets are stored **compact** (single-line JSON; `datalib.repository.COMPACT`) to keep the repo lean.

### Prediction log

`data/prediction_log.json` is the one dataset that **can't be regenerated**: every data update rewrites `podigami.json`, so it's the only record of what the site said before a race. `src/compute/compute_scorecard.py` (the last compute step) keeps the upcoming race's record up to date and stops at lights out (`update_log`), so a mid-race update that drops retired cars can't rewrite what was published. Never hand-edit a finished race's record, and don't regenerate the file. It was seeded from the git history of `podigami.json` on `main`, back to the 2026 Austrian GP. Records match races by name, not round, because upstream renumbers rounds mid-season. `data/scorecard.json` is derived from it and the podiums, so a revised podium rescores itself.

### Data flow

JSON files in `data/` are **committed to git** and serve as the intermediate format between stages. The build stage only reads from `data/` — it never touches the network, which is what makes build + tests safe to run in CI.

All access to `data/*.json` goes through **`src/datalib/`** (Pydantic v2 schemas in `schemas.py`, typed `load_*`/`save_*` in `repository.py`, re-exported from the package root). `load_*` returns validated model objects (builders use attribute access); `save_*` validates the computed payload and writes its **canonical schema serialization** (the validated model re-dumped — byte-identical to a `load_*`→dump round-trip, so regenerating never reformats committed data and a payload that omits optional fields still round-trips). Scripts reach the package by adding `src/` to `sys.path` and importing `datalib`. `python -m datalib.validate` (with `PYTHONPATH=src`) checks every dataset against its schema and gates CI.

## Key Conventions

- **Path resolution**: scripts use `Path(__file__).resolve().parents[N]` — no hardcoded absolute paths.
- **HTML generation**: string-based (no template engine); use `html.escape()` (the `esc()` helper) for any data interpolated into HTML.
- **Each script is standalone**: can be run individually (e.g. `python src/fetch/fetch_podiums.py`).
- **API rate limiting**: 1-second sleep between requests; exponential backoff on 429/5xx.
- **Lint/format**: `ruff` (config in `pyproject.toml`). CI fails on `ruff check` or `ruff format --check` violations. In Claude Code, a `PreToolUse` hook (`.claude/hooks/ruff_gate.py`) runs both on every `git commit` and blocks a failure. It uses `.venv`'s Python, so it only runs where that path exists; anywhere else the commit goes ahead, so run both yourself.
- **CSS**: global tokens in `assets/style.css`; page-specific styles in `assets/podigami.css` etc. Primary mobile breakpoint at `max-width: 600px`. Spacing density lives in three `:root` tokens (`--gap-section`, `--pad-panel`, `--pad-row`), so tighten or loosen the site there rather than per component; the combinations and ranked tables share `--pad-row` to stay cell-for-cell. Local Chromium renders Segoe UI, which is narrower than CI's Liberation Sans and most visitors' fonts, so a row that only just fits here can overflow elsewhere: check layout changes with `WIDER_FONT` from `tests/test_e2e.py`.

## Testing

Tests live in `tests/` (pytest). Notable files: `test_build_output.py` (generated HTML structure), `test_build_podigami.py` (landing-page render helpers), `test_compute_podigami.py` / `test_model.py` / `test_backtest.py` (modelling), `test_datalib.py` (schema fidelity + byte-identical load/save round-trips), `test_data_integrity.py` (semantic dataset invariants), `test_mobile_css.py` (mobile CSS regressions).

The `conftest.py` `dist` fixture builds `dist/` once per session via `build_site.py`; tests then assert against the real generated output. When you change rendered HTML, update the corresponding assertions.

Browser tests open as returning visitors: the autouse `returning_visitor` fixture marks the first-visit card (`assets/welcome.js`) as seen, so it can't sit on top of what a test clicks. Tests of the card itself use `@pytest.mark.new_visitor`. Local e2e runs load `dist/` over `file://`, whose load timing can hide races that a real HTTP load shows: the short FAQ jump on phones only reproduced over HTTP, so test the cause rather than the timing.

`deploy.yml` runs `pytest -q` with `requirements.txt` only, while CI and `update.yml` also install `requirements-dev.txt`. A test that needs a dev tool such as ruff must skip without it (`pytest.importorskip`), or it passes every check on the PR and then blocks the deploy after the merge. To check, run `pytest -q` in a fresh venv with only `requirements.txt`.

## Branching workflow

The repo uses a two-stage **`develop` → `main`** flow. `develop` is the **default branch**; `main` is the release branch that deploys to GitHub Pages.

- **Feature work**: branch off `develop`, open a PR back into `develop` (`gh pr create` targets it by default). CI (`ci.yml`) and security (`security.yml`) run on every PR — 7 required checks gate the merge into `develop` (Lint & format, Test py3.11/3.12/3.13, Build & link-check, Dependency audit, Secret scan). CodeQL does **not** run here (it only triggers on `main`).
- **Verify before shipping**: there is no staging deploy — the live site only builds from `main`. "Confirmed working" = green CI + local preview (`python src/build_site.py`, then serve `dist/`).
- **Ship a release**: open a promotion PR `develop → main` (`gh pr create --base main --head develop`). Targeting `main` triggers the **full 9 required checks** (the 7 above + CodeQL's two `Analyze` checks). Merging it runs `deploy.yml` → Pages. Batch multiple features into one promotion PR, or promote one at a time.
- **Finished work always ships.** Once a change is verified and `RELEASE_NOTES.md` is updated (plus `README.md` and this file where affected), take it from idea to deploy without asking: branch, PR into `develop` with auto-merge armed (`gh pr merge --auto --squash`), promotion PR to `main` with auto-merge armed (`gh pr merge --auto --merge`, a merge commit), then confirm the `deploy.yml` run and the live site. An uncommitted change or an open PR is unfinished work. Auto-merge waits only for required checks and `E2E (browser)` isn't one, so read its result too; `gh pr checks --watch` can also exit green while CI jobs are still queued. `bash .claude/scripts/wait_for_pr.sh <pr>` covers both: it waits for the merge and every check, then the deploy on a PR into `main`, and exits 1 if anything failed. The `CodeQL` result check (not the two required `Analyze` jobs) reports new alerts, runs only on PRs into `main` and isn't required, so auto-merge can land a new alert. If the script stops on it, read the alert and fix it forward even when the PR has merged.
- **Merged branches delete themselves** (`delete_branch_on_merge` is on). `develop` and `main` are protected, so it can't touch them, and `update.yml` recreates `auto/update-data` on each run. Don't pass `--delete-branch` on a promotion.
- **Data-update automation is unaffected**: `update.yml` operates entirely on `main` — both jobs check out `ref: main` (the guard must read `main`'s `asOf`, which is the only one data PRs advance, and the data branch must be cut from `main`) and the PR pins `--base main` — so `auto/update-data` PRs go straight to `main` and auto-merge/deploy without waiting in `develop`. Committed `data/` on `develop` therefore drifts behind `main` between promotions; that's expected (tests are data-agnostic, and a promotion's three-way merge keeps `main`'s newer data).
- **RELEASE_NOTES.md**: each feature PR into `develop` carries its own entry (per the Release Notes rules below); the promotion PR just bundles them — no separate entry needed for the promotion itself.

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

GitHub Actions (`.github/workflows/`) runs CI (lint, format, tests across py3.11–3.13, build + link-check, CodeQL, security scans) on every push/PR, and deploys to GitHub Pages on push to `main` (`deploy.yml`). `dist/` is gitignored — it is built in CI from committed `data/`, not committed.

### Automated data updates (`update.yml`)

`update.yml` keeps the site fresh with no manual step. It polls for a pending session, waits in-run for the results, opens one `auto/update-data` PR with auto-merge, and `deploy.yml` ships it. The detail lives in path-scoped rules that load when Claude touches a matching file, so it costs nothing on other work:

| Rule file | Covers |
|-----------|--------|
| `.claude/rules/data-updates.md` | The guard, the watcher and hand-over chain, the watchdog, podium revision alerts, and why the cron can't be trusted |
| `.claude/rules/openf1-and-grid.md` | The OpenF1 fast lane and the official starting grid |
| `.claude/rules/update-failures.md` | Every known way a data update has stalled, and the guardrails against them |
| `.claude/rules/season-rollover.md` | What happens between seasons, and what needs a person before a new one |

Rules only load for files you open, so read the matching one yourself when the task starts from a symptom rather than a file.

#### When a finished race does not appear

A missing result past the normal lag is usually a silently stalled update, not more lag. Read `.claude/rules/update-failures.md` first. It also applies to an `auto-update-failure` issue or a stuck `auto/update-data` PR. To trigger a run on a race weekend, always add `-f wait=true`: see `.claude/rules/data-updates.md`.

### ⚠️ CI cannot push to `main` with the built-in token

`main` is a **protected branch** (9 required status checks, `enforce_admins=false`, no required reviews). For any Actions automation:

1. A push with the built-in `GITHUB_TOKEN` is **rejected** (`GH006: protected branch update failed`).
2. Even a successful `GITHUB_TOKEN` push/merge **does not trigger** downstream workflows like `deploy.yml`.

So `update.yml` lands changes via the **PR + auto-merge** flow above, authenticated with repo secret **`DATA_PUSH_TOKEN`** — a fine-grained PAT (this repo; **Contents + Pull requests: read/write**; owned by an admin, so its merge bypasses required checks and, being a real-user action, triggers the deploy). **The PAT expires (≤1 yr); if it lapses, automated updates silently stop** — keep its expiry beyond the season and rotate as needed. Any future automation that must commit to `main` from Actions has to use this same PR-based path (not a direct `GITHUB_TOKEN` push).

## Keeping README.md current

`README.md` is user-facing documentation, not generated — it drifts silently. Whenever a change affects something the README describes (page list/nav, feature bullets, architecture diagram, file map, test count, workflow behavior, badges), update the relevant README section as part of that same PR. Treat it like `RELEASE_NOTES.md`: a checklist item on every PR that touches pipeline stages, pages, or CI, not a periodic cleanup task.

## Release Notes

`RELEASE_NOTES.md` in the repo root is the project changelog, linked from every page's footer. **Every PR must include an update to this file.** When creating a PR:

1. Add a new entry under the current date heading (create one if it doesn't exist yet, format: `## YYYY-MM-DD`).
2. Categorise the change under `### Features`, `### Improvements`, or `### Fixes` as appropriate.
3. Keep entries concise — one line per change, referencing the PR/issue number (e.g. `(#123)`).
4. Automated data-update PRs (`auto/update-data`) are excluded — they don't need release note entries.
