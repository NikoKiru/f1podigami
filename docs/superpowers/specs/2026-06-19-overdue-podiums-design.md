# Overdue Podiums — Design

## Context

`f1_podigami` predicts the *next* brand-new podium trio for the current season. This feature adds
the historical mirror image: which never-happened podium trios were the **most overdue** — drivers
who raced together often and each podiumed frequently, yet somehow never all three shared a podium.

It lives on a new **Overdue** page and shows two ranked lists:
- **All-time near-misses** — across all of F1 history (driver pool = top podium-getters).
- **Current grid, still possible** — trios on this season's grid that could still happen.

## The metric

For a trio (A, B, C) that has **never** shared a podium:

```
score(A,B,C) = races_together × rate_A × rate_B × rate_C

  races_together = number of races where all three started the same event  (|A ∩ B ∩ C|)
  rate_d         = career podiums / career starts          (a driver's podium rate)
```

`score` ≈ the expected number of shared podiums if podiums were independent — so a high score with
**zero** actual shared podiums means "this should statistically have happened, but never did".

It is a **ranking heuristic**, not a true probability: it ignores the 3-slot podium constraint
(only three drivers can podium per race, so the three marginals are not independent). The UI
therefore presents the concrete, defensible numbers — `races_together` and the three podium rates —
as the real stats, and uses `score` only to order and size the bars.

Trios with `races_together == 0` (careers never overlapped) are excluded.

## Data pipeline

### 1. `src/fetch/fetch_driver_races.py` → `data/driver_races.json`

Provides the two things podiums.json cannot: per-driver **race-entry sets** (for intersections) and
**career starts** (the rate denominator).

- **Driver pool** = top `POOL_N` (=60) drivers by career podium count (from `podiums.json`)
  ∪ the current grid (`current_drivers.json`).
- For each driver, page through Ergast `GET /drivers/{id}/results.json?limit=100&offset=…`
  (same backoff/User-Agent pattern as the other fetchers), collecting:
  - `races`: sorted list of integer race keys `season*1000 + round`
  - `starts`: `MRData.total`
- **Incremental**: load existing `driver_races.json`; a driver already present **and not on the
  current grid** is historical/immutable → skip. Refetch only current-grid drivers and any pool
  members not yet cached. (~60–80 calls on first run, a handful thereafter.)
- Output:
  ```json
  { "drivers": { "max_verstappen": { "name": "Max Verstappen", "starts": 230, "races": [2015001, …] }, … } }
  ```

### 2. `src/compute/compute_overdue.py` → `data/overdue.json`

Inputs: `podiums.json`, `combos.json`, `current_drivers.json`, `driver_races.json`. Pure `compute()`
core (testable, no IO) plus a thin `main()` for file IO — mirrors `compute_podigami.py`.

- Per driver: `podiums` (count in podiums.json), `starts` (driver_races), `rate = podiums/starts`
  (0 if `starts == 0`), `raceSet = set(races)`.
- Existing trios = `{ tuple(sorted(c["driverIds"])) for c in combos.json }`.
- For each pool (`allTime` = top-60 by podiums; `currentGrid` = grid driverIds, intersected with
  drivers we have race data for):
  - enumerate `C(pool, 3)` trios not in existing trios,
  - `races_together = len(rA & rB & rC)`; skip if 0,
  - `score = races_together * rate_A * rate_B * rate_C`,
  - rank by score desc, keep top `TOP_N` (=15).
- Output:
  ```json
  {
    "params": { "poolN": 60, "topN": 15 },
    "asOf": { "season": "2026", "round": "7", "raceName": "…" },
    "allTime":    [ { "driverIds", "names", "racesTogether", "score",
                      "perDriver": [ { "name", "podiums", "starts", "rate" } × 3 ] }, … ],
    "currentGrid": [ … same shape … ]
  }
  ```

### 3. `src/build/build_overdue_html.py` → `dist/overdue.html`

- Loads `style.css` + `podigami.css` (reuses `.panel`, `.cand-list`, `.cand`, `.trio` styling).
- Two `.panel` sections ("All-time near-misses", "Current grid — still possible"), each a ranked
  `.cand-list`: rank · trio names (`.trio`) · score bar (`.cand-bar`, width ∝ score/top) ·
  a new `.cand-meta` line: `raced N times together · 25% / 20% / 12% podium rates`.
- Header + footer like the other pages; `asOf` note.
- One small CSS addition to `podigami.css`: `.cand-meta { font-size:12px; color:var(--muted) }`.

### 4. Wiring

- `src/build_site.py`: add `build_overdue_html.py` to `PAGE_BUILDERS`.
- `src/update.py`: add `fetch/fetch_driver_races.py` and `compute/compute_overdue.py` to `STEPS`
  (after `fetch_current_drivers` / `compute_podigami`). `--full` also forces a full driver-races
  refetch.
- **Nav** gains an "Overdue" link on every page: `build_podigami_html.py`, `build_combos_html.py`,
  `build_soulmates_html.py`, and the new `build_overdue_html.py`
  → `Podigami · Combinations · Overdue · Soulmates`.

## Tests

- **`tests/test_compute_overdue.py`** (pure `compute()` on a synthetic fixture):
  - score = races_together × product of rates (exact arithmetic check),
  - a trio that already shared a podium is excluded,
  - a trio whose careers never overlapped (`races_together == 0`) is excluded,
  - results ranked by score descending; `currentGrid` list only uses grid drivers,
  - a frequently-overlapping high-rate trio outranks a rarely-overlapping one.
- **`tests/test_pipeline_integrity.py`** (committed data): every `overdue.json` candidate is absent
  from `combos.json`, has `racesTogether > 0`, scores are descending, and all candidate drivers
  appear in `driver_races.json`.
- **`tests/test_data_integrity.py`**: add `driver_races.json`, `overdue.json` to `DATASETS`.
- **`tests/test_build_output.py` / `test_build_links.py`**: add `overdue.html` to `PAGES`; assert
  it has both panels and that every page's nav links to `overdue.html`.

## Verification

1. `python src/fetch/fetch_driver_races.py` → inspect `data/driver_races.json` (grid + top podium
   drivers present, plausible `starts`).
2. `python src/compute/compute_overdue.py` → `overdue.json`: both lists non-empty, top all-time
   entry is a well-known high-overlap great trio, grid list uses only 2026 drivers.
3. `pytest -q` → all green (new + existing).
4. `python src/build_site.py` → open `dist/overdue.html`; both ranked lists render, bars/meta look
   right, nav links resolve on every page.
5. `python src/update.py` runs fetch→compute→build end to end without errors.

## Tunables / deferred

- `POOL_N = 60`, `TOP_N = 15` are constants in `compute_overdue.py` / the fetcher.
- The independence heuristic could later be replaced by a 3-slot-aware probability; out of scope now.
