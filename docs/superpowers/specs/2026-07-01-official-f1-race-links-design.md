# Official F1 Race Links — Design

- **Date:** 2026-07-01
- **Status:** Approved for planning
- **Author:** Nikolaj (with Claude)

## Goal

Replace every **race-report link** on the site — currently pointing at Wikipedia
— with the equivalent **official Formula 1 result page** on `formula1.com`, while
never producing a dead link (Wikipedia remains a per-race fallback).

## Non-goals

- The **"scorigami"** concept link (`build_podigami_html.py:576`) stays on
  Wikipedia — there is no official F1 page for the concept.
- No change to what data the site displays; this is purely about where the
  existing race links point.
- No new UI/visual design — links keep their existing markup, `target`, and
  `rel` attributes.

## Background — current state

Every race link is built from Wikipedia:

| Location | What it links | Source |
|---|---|---|
| `_layout.py` `wiki_url(season, raceName)` | combos + unlikeliest race pills | constructed wiki title |
| `build_podigami_html.py:215` | landing **last-race** name | `schedule.url` (API=wiki) → constructed wiki |
| `build_podigami_html.py:254` | landing "last time this trio happened" repeat link | constructed wiki |
| `build_podigami_html.py:132` | landing **next-race** name | `schedule.url` (API=wiki) |
| `data/schedule.json` `url` | feeds next/last-race | Jolpica/Ergast API (returns wiki) |
| `build_podigami_html.py:576` | **"scorigami"** concept | hard-coded wiki (KEEP) |
| `build_overdue_html.py` | — | *no race links* |

Every race reference across the codebase carries **season + round + raceName**
(`RaceRef`, `ScheduleRace`, the landing `pod`/`second_last` dicts). So a single
join key — **`(season, round)`** — works at every call site.

## Legality assessment

- **Linking** (deep-linking to F1's public result pages) is permitted and sends
  users to F1's own site.
- **Obtaining** the identifiers requires reading F1's public results-archive
  index pages and extracting URL identifiers (F1 publishes no API). This touches
  F1's anti-scraping terms but is low-risk: a few dozen small pages fetched
  **once** then cached in git; only URL identifiers (facts) are stored, not
  copyrighted content; used purely to link back to F1.
- **Verified:** `robots.txt` (`User-Agent: *`) allows `/en/results/` (only
  `/en/latest/tags/*` is disallowed). We honor robots.txt, reuse the existing
  1s rate-limit + exponential backoff + descriptive `User-Agent`, and never
  re-fetch historic (immutable) years.

## Official URL structure

```
https://www.formula1.com/en/results/{YEAR}/races/{RACE_ID}/{location-slug}/race-result
```

- `{RACE_ID}` — F1's internal sequential ID. **Not** the round number and **not**
  derivable (2026 jumps 1281→1284; 1950 starts at 94). Must be fetched + stored.
- `{location-slug}` — country/city slug (`austria`, `great-britain`,
  `barcelona-catalunya`). Not derivable from our race names. Must be stored.
- F1 publishes a per-year index at `…/results/{YEAR}/races` listing every race,
  **back to 1950**, retrievable with plain `requests` (server-rendered, HTTP 200).

### Verified parsing nuance

The raw index HTML lists each race **multiple times and not in strict round
order** (a "latest race" selector repeats/reorders entries). But numeric IDs are
**monotonic with round within a year** (1950: 94→100; 2026: 1279→1302). Therefore
the fetcher must:

1. Regex-extract all `/en/results/{year}/races/(\d+)/([a-z0-9-]+)/race-result`.
2. **Dedupe** by ID.
3. **Sort ascending by numeric ID** → this recovers round order.
4. Map sorted position *i* (0-based) → **round `i+1`**.
5. **Cross-validate** each entry's slug against our own data (see below).

## Architecture (Approach A — standalone committed links map)

Mirrors the existing **Fetch → data → Build** pipeline. Compute stays offline;
the build reads only committed JSON.

### 1. New committed dataset — `data/f1_race_links.json`

Shape: `season → round → {id, slug}`.

```json
{
  "1950": { "1": {"id": "94", "slug": "great-britain"}, "2": {"id": "95", "slug": "monaco"} },
  "2026": { "1": {"id": "1279", "slug": "australia"},   "8": {"id": "1288", "slug": "austria"} }
}
```

- Only races that **pass cross-validation** are present; a missing `(season,
  round)` simply falls back to Wikipedia at render time.
- Deterministic output: seasons ascending, rounds ascending numerically, so
  regeneration is byte-stable (matches the repo's byte-identical save contract).

### 2. datalib integration (`src/datalib/`)

- `schemas.py`: `class RaceLink(_Base): id: str; slug: str`.
- `repository.py` REGISTRY:
  `"f1_race_links.json": TypeAdapter(dict[str, dict[str, RaceLink]])`.
- Add `load_race_links()` / `save_race_links()`; re-export from package root.
- `python -m datalib.validate` picks it up via REGISTRY (CI gate).

### 3. Fetcher — `src/fetch/fetch_race_links.py`

Standalone script (runnable alone, like the other fetchers).

- **Modes:**
  - *default (incremental):* load existing map; (re)fetch **only the current
    season**'s index (IDs can appear/shift as a season is set up); leave historic
    years untouched.
  - *`--backfill`:* fetch **every** season from 1950 → current. Run once to seed
    the committed file; also usable to rebuild from scratch.
- **Per season:** GET `…/results/{year}/races` → regex-extract → dedupe → sort by
  numeric ID → assign rounds (see parsing nuance).
- **Cross-validation (per-race, max coverage).** Note the data available differs
  by era: `schedule.json` (current season) has `country`/`locality`/`raceName`,
  but `podiums.json` (historic) has only `season`/`round`/`raceName` — no
  country/locality. So:
  - **Strong per-season guard:** unique F1 ID count for the season must equal our
    race count (rounds in `schedule`/`podiums`). When counts match, the
    sort-by-ID → round positional mapping is high-confidence for the whole season.
  - **Per-race soft check:** compare the F1 slug against a normalized token form
    of `raceName` (plus `country`/`locality` when available, i.e. current season).
    **Omit** a single race (→ wiki fallback) only on a clear conflict — e.g. its
    slug shares no tokens with its own race yet matches a neighbor's, indicating a
    positional slip. A merely "fuzzy" non-match (e.g. slug `great-britain` vs
    `British Grand Prix`) is **not** grounds to omit; the count guard governs.
  - If the season **count guard fails**, treat the whole season conservatively:
    keep only races whose slug positively matches, wiki-fallback the rest.
  - Log every omission + a per-season coverage count (`mapped X / Y`).
- **Networking:** reuse the shared pattern — `User-Agent`, `Accept`, 1s sleep
  between requests, exponential backoff on 429/5xx.
- Writes via `save_race_links()`.

### 4. Render helper — `race_url()` in `_layout.py`

```python
@cache
def _race_links() -> dict:
    from datalib import load_race_links  # lazy: avoids import-order coupling
    return load_race_links()

def race_url(season: str, round: str, race_name: str) -> str:
    link = _race_links().get(season, {}).get(str(round))
    if link:
        return (f"https://www.formula1.com/en/results/{season}/races/"
                f"{link.id}/{link.slug}/race-result")
    return wiki_url(season, race_name)   # per-race Wikipedia fallback
```

- `wiki_url()` is **kept** (fallback + still the mechanism the constructed-title
  logic relied on).
- Call-site changes (all have round available):
  - `build_combos_html.py:39` → `race_url(r.season, r.round, r.raceName)`
  - `build_unlikeliest.py:78` → `race_url(h.season, h.round, h.raceName)`
  - `build_podigami_html.py` last-race (`:215`), repeat link (`:254`), and
    next-race (`:132`) → `race_url(...)` using each record's season/round/name,
    replacing the current `schedule.url`/constructed-wiki logic.
- `data/schedule.json`'s `url` field is left as-is (faithful API mirror); it is
  simply no longer the link source.

### 5. Pipeline wiring

- `src/update.py`: add a `fetch_race_links.py` (incremental) step alongside the
  other fetchers so new-season/new-race IDs are picked up automatically. The
  automated `update.yml` inherits this (≈1 F1 index page per run, current season
  only).
- One-time: run `--backfill`, commit `data/f1_race_links.json`.

## Testing strategy ("make sure it works")

- **`tests/test_race_links.py`** (new):
  - schema load/save byte-identical round-trip;
  - `race_url()` builds the exact expected F1 URL for a mapped race, and returns
    the wiki fallback for an unmapped `(season, round)`;
  - **no dead links:** every race referenced by `combos.json`, `unlikeliest.json`,
    and `schedule.json` resolves to either a valid F1 URL or a wiki fallback;
  - URL-format assertion (regex) for all mapped entries.
- **`tests/test_build_links.py`**: update `test_race_report_links_are_wikipedia`
  → assert links are F1 result URLs (tolerating wiki fallback), rename
  accordingly.
- **`tests/test_units.py`**: keep `wiki_url` unit tests (still used as fallback);
  add `race_url` lookup/fallback unit tests.
- **`tests/test_next_race.py`** / **`test_build_unlikeliest.py`**: update the
  hard-coded wiki assertions to the F1 URLs (or fallback) for their fixtures.
- **Live spot-check (manual, during implementation):** confirm a sample of
  generated F1 URLs (oldest, newest, a few mid-history) return HTTP 200 and are
  not soft-404 redirects — via `requests` and/or Playwright against the live site.
- Standard gates: `ruff check`/`format`, `pytest -q`, `python -m datalib.validate`.

## Rollout

1. Add schema + repository + `datalib.validate` coverage.
2. Add `fetch_race_links.py`; run `--backfill`; commit `data/f1_race_links.json`.
3. Add `race_url()`; switch all call sites; keep scorigami on wiki.
4. Wire into `update.py`.
5. Update/extend tests; run full gate + live spot-check.
6. `RELEASE_NOTES.md` entry under `### Improvements` (or `### Features`),
   referencing the PR.
7. PR into `develop` (per branching workflow), then promote to `main`.

## Risks & mitigations

- **F1 list ↔ Ergast round misalignment** (cancelled/renamed/merged historic
  races). → per-race cross-validation + Wikipedia fallback; backfill logs
  coverage per season for review.
- **F1 changes its URL scheme / archive HTML.** → fallback keeps links alive;
  fetcher failure is visible in CI logs; historic map already committed so a
  scheme change only affects newly-fetched current-season entries.
- **F1 blocks automated access.** → low request rate + robots-compliant; if it
  ever fails, the committed historic map + wiki fallback keep the site working.
- **`id`/`slug` drift for the current season** before races run. → incremental
  re-fetch each pipeline run refreshes the current season.
