# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

F1 Podigami is a Python static site generator that transforms Formula 1 race data (1950–present) into five interactive HTML pages (plus a 404 page). No backend server or framework — just Python, `requests`, and committed JSON datasets. The "podigami" concept is podium scorigami: spotting 3-driver podium trios that have never happened before, and predicting which brand-new trio is most likely next.

Deployed to GitHub Pages: https://nikokiru.github.io/f1podigami

## Environment notes

- **GitHub CLI is installed and authenticated** as `NikoKiru` (scopes: `repo`, `workflow`, `read:org`, `gist`). Prefer `gh` for all GitHub operations (PRs, merges, checks) over raw API calls.
  - `gh.exe` lives at `C:\Program Files\GitHub CLI\gh.exe`. A shell started before the install may not have it on PATH; refresh with:
    ```powershell
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    ```
- Primary shell is PowerShell 7+ on Windows; a Bash tool is also available.
- **Local MCP servers are available — reach for them when they bring more value than the CLI/scripts:**
  - **`playwright`** — drive a real browser to verify browser-only behaviour (JS-rendered timeline, asset cache-busting, mobile layout) against the live site or a locally-served `dist/`. Preferred over hand-rolled checks when a change is only observable in a rendered page.
  - **`github`** — structured GitHub access (PRs, issues, reviews, code search) when its typed results are clearer than parsing `gh` output. For routine git/PR/merge operations, `gh` remains the default (see above); use the MCP when it genuinely simplifies the task.

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
- `src/check_update_due.py` — cheap, no-network CI guard (`is_update_due`) for the automated refresh (polls every 15 min): decides from committed `schedule.json` + `podigami.json` `asOf` whether a finished race is newer than the data. See **Deployment → Automated data updates**.

### Five output pages

`src/build_site.py` is the source of truth for the page → builder mapping (it also builds `404.html` via `build/build_404_html.py`):

| Page | Builder | Description |
|------|---------|-------------|
| `index.html` | `build/build_podigami_html.py` | Landing page: next race, last race result (with podigami/repeat status + official F1 result link), prediction hero, current form, discovery hook cards, timeline, FAQ |
| `combos.html` | `build/build_combos_html.py` | Every unique 3-driver podium combination |
| `overdue.html` | `build/build_overdue_html.py` | Trios "overdue" to appear |
| `unlikeliest.html` | `build/build_unlikeliest.py` | Trios that happened despite the odds, ranked by improbability |
| `soulmates.html` | `build/build_soulmates_html.py` | Driver shared-podium relationships |

Shared build helpers: `build/_layout.py` (page chrome: `head()`, `nav()`, `FOOTER`), `build/_hooks.py` (cross-page discovery hook cards), `build/flags.py` (country flag SVGs), `build/team_colors.py` (`team_color()`, `text_on()`).

### Prediction model

The live predictor is **model v2** (`src/compute/model_v2.py`, params tag `dbpl-v2`): a dynamic Bayesian rating engine — Gaussian driver+constructor log-worth ratings filtered over `data/race_results.json` (full classifications 1950→) and `data/qualifying.json` (1994→) via closed-form truncated Plackett–Luce updates, with decayed DNF hazards (mechanical → car, incident → driver), circuit chaos character, and a deterministic Rao-Blackwellised podium simulation (fixed seed; same inputs → byte-identical JSON). `compute_podigami.py` uses it whenever `race_results.json` exists and falls back to the v1 recency Plackett–Luce model (`src/compute/model.py`) otherwise.

`src/compute/backtest.py` is the integrity core: a walk-forward ladder (v1 rungs + v2 ablation rungs) tuned on 2010–2018 and scored on a frozen 2019+ test window → `data/model_eval.json`, surfaced on the landing page as a badge and in the FAQ. An acceptance gate in `evaluate()` keeps v2 "chosen" only while it beats v1 on test logLoss AND brierNew. Tuning knobs are locked in `model_v2.DEFAULT_PARAMS_V2` (`--tune-v2` re-derives them; notable verdicts: qualifying weight 0.6, attrition channel 0).

`compute_podigami.py` still folds in `data/constructor_standings.json` (team labels + each driver's `constructorId`/`constructorStrength`), so a refresh that picks up updated standings can rewrite most numeric values in `podigami.json` even when `asOf` is unchanged — that churn is expected, not a bug. The two raw v2 datasets are stored **compact** (single-line JSON; `datalib.repository.COMPACT`) to keep the repo lean.

### Data flow

JSON files in `data/` are **committed to git** and serve as the intermediate format between stages. The build stage only reads from `data/` — it never touches the network, which is what makes build + tests safe to run in CI.

All access to `data/*.json` goes through **`src/datalib/`** (Pydantic v2 schemas in `schemas.py`, typed `load_*`/`save_*` in `repository.py`, re-exported from the package root). `load_*` returns validated model objects (builders use attribute access); `save_*` validates the computed payload and writes its **canonical schema serialization** (the validated model re-dumped — byte-identical to a `load_*`→dump round-trip, so regenerating never reformats committed data and a payload that omits optional fields still round-trips). Scripts reach the package by adding `src/` to `sys.path` and importing `datalib`. `python -m datalib.validate` (with `PYTHONPATH=src`) checks every dataset against its schema and gates CI.

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

## Branching workflow

The repo uses a two-stage **`develop` → `main`** flow. `develop` is the **default branch**; `main` is the release branch that deploys to GitHub Pages.

- **Feature work**: branch off `develop`, open a PR back into `develop` (`gh pr create` targets it by default). CI (`ci.yml`) and security (`security.yml`) run on every PR — 7 required checks gate the merge into `develop` (Lint & format, Test py3.11/3.12/3.13, Build & link-check, Dependency audit, Secret scan). CodeQL does **not** run here (it only triggers on `main`).
- **Verify before shipping**: there is no staging deploy — the live site only builds from `main`. "Confirmed working" = green CI + local preview (`python src/build_site.py`, then serve `dist/`).
- **Ship a release**: open a promotion PR `develop → main` (`gh pr create --base main --head develop`). Targeting `main` triggers the **full 9 required checks** (the 7 above + CodeQL's two `Analyze` checks). Merging it runs `deploy.yml` → Pages. Batch multiple features into one promotion PR, or promote one at a time.
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

Keeps the site fresh with no manual step, running the same pipeline as a local `python src/update.py` + push:

- A cheap **`check` job** runs `src/check_update_due.py` **every 15 min** (`cron: 2,17,32,47 * * * *`; offset off the hour to dodge GitHub's top-of-hour load, which often drops scheduled runs; no network, no secret) and proceeds only when a race that should have results by now is newer than `podigami.json`'s `asOf`. A weekly run (`0 7 * * 1`) forces an unconditional `--full` reconciliation; `workflow_dispatch` takes `mode` (auto/full) + `force`.
- When due, the **`update` job first waits for the results to exist** (see below), then runs `update.py`, opens/updates a single `auto/update-data` PR with **squash auto-merge**, and only then validates + tests (so a bad run surfaces as a visible red PR rather than a silently-skipped step). Once the full required checks pass it merges → `deploy.yml` ships it. One race ⇒ one PR (the guard stops once `asOf` advances on merge); re-running is idempotent (no churn).
- A **`watchdog` job** runs on every tick regardless of the guard, and is the only job *not* pinned to `main` (it reads no data, and its script must come from the same ref as the workflow file). It asks the API for the open `auto/update-data` PR and, if that PR has existed longer than `check_stalled_data_pr.STALL_AFTER` (**45 min**) without merging, reports why — failing required check, merge conflict, auto-merge not armed — into the same deduplicated `auto-update-failure` issue `notify-failure` uses. A *green* run whose PR sits `BLOCKED` was the last silent path (#229).
- A **`Detect podium revisions`** step (`src/check_revisions.py`) compares every podium already on `main` with the refreshed data. A change — Jolpica editing a settled race — retitles the data PR (`Update race data … · Podium revised: 2026 R6 Monaco Grand Prix — Hadjar → Gasly`) and opens one issue per revision, or a single summary issue when more than `MAX_ISSUES` (5) revise at once (a mid-season renumbering or a `--full` run). Dedup is against **open** `podium-revised` issues only — closing one re-arms detection, so a repeat flip-flop after that still notifies. It never blocks the auto-merge: the retitle (via `DATA_PUSH_TOKEN`, the REST API rather than `gh pr edit` — that command also queries projects/labels/milestones a fine-grained PAT may not be allowed to read) happens only *after* `gh pr merge --auto` has already armed, and the PR label (via `GITHUB_TOKEN`, also REST rather than `gh pr edit`) is applied only after the issues are created. Both the retitle and the label are non-fatal (`|| echo "::warning::..."`); issue creation stays loud, since a revision alert failing to notify is the one failure mode that must surface. Issues/labels use `GITHUB_TOKEN` because `DATA_PUSH_TOKEN` has no Issues permission.

#### The cron is ~1/hour, not every 15 min — don't design around the schedule

GitHub honours only a fraction of the requested slots. Measured on race Sunday 2026-07-19: **13 scheduled runs against 76 expected (~17%)**, landing at arbitrary minutes (not `:02/:17/:32/:47`), with multi-hour overnight gaps, and one slot additionally queued **41 min** before executing. This is normal Actions throttling for scheduled workflows; **making the cron denser does not help** — the extra slots are dropped too.

The consequence that actually hurts: the Jolpica API often has not published a just-finished race when the run fetches. Previously that meant the run produced a PR with no new race (`asOf` unchanged), and the retry had to wait for the *next surviving slot* — **a full hour**. At the 2026 Belgian GP that put the result on the site ~100 min after the flag (fetched 15:32Z with nothing upstream → PR #204 carried no race → only #205 at 16:23Z did).

**Fix (#206): wait in-run rather than retry across runs.** `src/wait_for_results.py` polls `/{season}/last/results.json` every 3 min for up to 2h until the round appears, then the pipeline runs once. Cron now only has to land **one** slot in a wide window, which it reliably does. Notes:
- It polls an **aggregate** feed on purpose — the round-indexed endpoint lags for hours (see #178 below).
- A timeout is **not** a failure: the pipeline runs anyway (idempotent) and the guard re-fires.
- It runs on **scheduled events only** (`github.event_name == 'schedule'`) and not for `mode=full`, so a human dispatch stays snappy instead of blocking up to 2h.
- `RESULTS_BUFFER` is **1h40** — the end of a real ~100-min race, *not* "results are published". Publish lag belongs to the watcher; padding the buffer instead just burns wall-clock every race weekend.
- The `update` job carries `timeout-minutes: 180` to cover the poll budget plus the pipeline.
- Trigger on demand: `gh workflow run update.yml -f mode=auto -f force=true` (or `-f mode=full`).

#### ⚠️ When a finished race doesn't appear (silent-stall failure mode)

Past the normal post-race lag (API publish delay + dropped cron slots), a missing result is usually **not** more lag but a **silently stalled update**: `asOf` never advances, so the guard re-fires `due=true` every tick without anything ever merging — a self-perpetuating stall one race behind. Nobody watches the Actions tab, so every known path into it now raises **one deduplicated `auto-update-failure` issue**: `notify-failure` covers a red run, and the `watchdog` job covers a green run whose PR won't merge. Treat that issue (not the Actions tab) as the signal.

- **Diagnose:** open the latest `update.yml` run. `check` green + `update` red is a pipeline failure (read the failed step). `check` green + `update` green + the site still stale means the **PR** is the problem — `gh pr view auto/update-data` and look at its required checks. Upstream tell: `api.jolpi.ca/ergast/f1/<season>/<round>/results.json` can sit **empty for hours** after a race while the aggregate feeds (`/<season>/results/1.json`, `/<season>/results.json`, `/<season>/last/results.json`) already carry the round — so a fetcher that keys off the latest round alone gets nothing.
- **#175** — under the develop/main flow the guard read `develop`'s stale `asOf` and looped; fixed by pinning both jobs to `main`.
- **#178** — the round-indexed endpoint lag above emptied `fetch_constructor_standings`' driver→constructor map → `compute` switched the constructor overlay off and omitted optional `constructor`/`constructorStrength` keys → the byte-identical round-trip test failed → PR skipped. Fixed by (a) `fetch_driver_constructors(season, rounds)` walking back to the last round with results, and (b) `_save` writing the canonical schema form so an omitted-optional payload still round-trips.
- **#183** — the `pytest` gate used to run *before* the "open PR" step, so any test failure skipped PR creation entirely. The PR is now opened first (a bad run is a visible red PR, not a missing one) and a failed run opens the alert issue.
- **#229** — a required check failing on the PR *itself* (unpinned ruff resolving to 0.16.0, whose formatter output changed) left it `BLOCKED` for ~2h with every job green and nothing to alert on. The `watchdog` job now watches the PR, not just the run.
- **#239 — the API's response cache is keyed on request headers.** Jolpica answers with `Vary: Accept, origin, accept-encoding` and caches each variant independently with a long TTL, so **the same URL returns different data to different clients**. Every fetcher sends `Accept: application/json`, a cold variant: on 2026-07-26 it served a **57-minute-old** `/2026/results.json` (220 rows, no round 11) while the header-less variant of that URL was 13 min old and had it. Two consequences, both seen the same afternoon: (a) fetchers running seconds apart disagreed about whether a race existed, so `podiums.json` advanced to round 11 while `race_results.json` stayed at 10; (b) `wait_for_results` re-read one stale `last/results` body every 3 min and burned an hour on a race that was already published. `Cache-Control: no-cache` is **ignored** by the origin — a unique query parameter is the only bypass that works (`fetch/api_cache.fresh()`). Apply it to current-season reads and the watcher only; busting the cache across a `--full` 1950→ rebuild is hundreds of pointless origin misses.
- **#245 — a mid-season calendar change renumbers rounds, and a merge-only refresh can't unlearn.** Upstream inserted "Bahrain Grand Prix in Malaysia" as 2026 R16 (Sepang), shifting Singapore→R17 etc. `fetch_race_links.update_map` merged the freshly-matched season *over* the committed rounds — able to add or overwrite rows but never remove one — so the pre-shift `R16→singapore` row survived next to the new `R17→singapore`, and the race-identity guardrail (correctly) failed all three Test checks. The PR sat `BLOCKED` for 15 days. The alert fired as designed but landed as comment #400-something on a month-old open issue — no new notification ever reached a human. Fixed by (a) pruning any carried-over row whose slug no longer identity-matches its round's race name (the file passes the guardrail by construction), (b) teaching `ACCEPTABLE_SLUGS` the relocated race name (F1 keeps the `bahrain` slug for it), and (c) making alerts humane: `notify-failure` stays quiet while the failure is unchanged, and a `notify-recovery` job closes the issue once no data PR is open, so the next incident opens a fresh, notifying issue. Lesson: any dataset key that other data is indexed by (round numbers) can be reassigned upstream mid-season — refreshes must be able to *remove* stale rows, not just add.
- **Silent upstream revisions (#<PR>).** Jolpica rewrote Monaco 2026's P3 twice (Hadjar Jun 8 → Gasly Jun 16 → Hadjar Sep 6); both edits merged in routine data PRs and the site showed a trio that never officially happened for 82 days. Now flagged by the revision alert. The fix for a *wrong* revision is upstream — the fetchers re-read the whole season every run, so a local revert is overwritten.
- **Develop's workflow, main's scripts.** A scheduled run takes `update.yml` from the default branch (`develop`) but the `update` job checks out `main`, so between merging a PR to `develop` and promoting it, the workflow can call a script or flag `main` doesn't have yet. Every data update then fails. Guard any new step that calls a new script (`if [ -f src/<script>.py ]; then …; fi`, with the skip path writing safe step outputs), and after merging to `develop` run a forced update to prove it: `gh workflow run update.yml -f mode=auto -f force=true`.
- **Datasets that must agree are fetched independently — never assume they're in step.** `asOf` comes from `podiums.json`, the v2 filter from `race_results.json`. When #239 skewed them, compute happily produced a *post-qualifying* grid prediction for a race that had already finished. Any code deriving "which race is next" must reconcile across datasets (take whichever is further ahead), and the renderer should refuse to display a post-quali block whose race is no longer upcoming.
- **A driver→seat map built from one round is a snapshot, not a roster.** `driverConstructor` names only the latest round's starters, so a driver who misses a race (injury, substitution) drops out of it and — before #254 — was predicted in an unknown, i.e. brand-new, car: at the 2026 Dutch GP swap that would have cut Hadjar's rating ~36,000× and shown him teamless. Seats now fall back to the last car each driver started in `race_results.json` (latest round wins, so a real team change still overwrites). The mirror case — a *substitute* keeping the borrowed seat for the following race — is corrected only when that race's qualifying lands and `_post_quali_block` rebuilds the entry list from it.
- **Guardrail for new work:** any change that makes a compute script emit different keys/types, or any new test that can fail on live data, can re-trigger this class of stall. Keep compute output a byte-identical fixed point of its schema, and make fetchers tolerate partial/lagging upstream data. Anything that can make a *required check* fail for non-data reasons (an unpinned tool, a new required check) stalls the PR the same way — pin tool versions, and let ruff upgrades arrive as a deliberate reformatting PR.

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
