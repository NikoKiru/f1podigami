# Unlikeliest Podiums — Design Spec

**Date:** 2026-06-29
**Status:** Approved, proceeding to implementation + deploy.

## Concept

A new fifth page, the **mirror of Overdue**. Where Overdue ranks trios that
*should* have happened but never did, **Unlikeliest** ranks trios that *did*
happen but — by the same heuristic — almost shouldn't have. Lowest score = the
biggest podium fluke in F1 history.

## Metric

Reuse the Overdue heuristic, applied to trios that actually occurred:

```
score = racesTogether × rateA × rateB × rateC
  racesTogether = number of races all three started together
  rate_d        = career podiums / career starts
```

- Lowest `score` = most unlikely.
- Score is always > 0 for a happened trio (each driver podiumed ≥ once), so no
  divide-by-zero and every happened trio gets a finite score.
- `score` reads naturally as an "expected co-podiums" heuristic; comparing it to
  the actual `count` ("expected ≈ 0.02, yet it happened") is the why-it-was-
  unlikely framing.

## Scope

Rank **all** trios that happened (every combo in `combos.json`) by `score`
ascending, keeping the top **N = 30**. `count` is shown so repeat trios
self-explain — they carry higher scores and naturally sink down the list.

## Architecture (follows Fetch → Compute → Render)

### 1. Compute — `src/compute/compute_unlikeliest.py` → `data/unlikeliest.json`

- Builds the same per-driver info as `compute_overdue.py` (podiums, starts,
  race-set, rate) from `podiums.json` + `driver_races.json`.
- Iterates every combo in `combos.json`; for each computes `racesTogether`
  (3-way race-set intersection), `score`, carries `count` and the **first**
  occurrence race (for the "happened at" line + wiki link).
- Sorts ascending by score, keeps top 30.
- **Edge case:** a driver missing from `driver_races.json` (data gaps for some
  early entrants) → skip that trio, log the skipped count. Page never renders a
  broken row.
- Deterministic: same inputs → byte-identical JSON (verbatim `save_*`).

Payload shape:

```json
{
  "params": {"topN": 30},
  "asOf": { "season": "...", "round": "...", "raceName": "..." },
  "trios": [
    {
      "driverIds": ["...", "...", "..."],
      "names": ["...", "...", "..."],
      "racesTogether": 14,
      "score": 0.0182,
      "count": 1,
      "happened": { "season": "...", "round": "...", "raceName": "..." },
      "perDriver": [
        {"name": "...", "podiums": 5, "starts": 82, "rate": 0.061}
      ]
    }
  ]
}
```

### 2. Datalib — `src/datalib/schemas.py` + `repository.py`

- New `UnlikeliestTrio`, `UnlikeliestParams`, `Unlikeliest` models (mirror
  `Overdue*`). `perDriver` reuses the shape of `OverduePerDriver`.
- `save_unlikeliest` / `load_unlikeliest` in `repository.py`, re-exported from
  the package root.
- Register `unlikeliest.json` in `datalib/validate.py` (CI gate).

### 3. Render — `src/build/build_unlikeliest.py` → `dist/unlikeliest.html`

Reuses `_layout` chrome and `podigami.css` (`panel` / `cand-list` styles, as
Overdue).

- **Hero (trio #1):** highlighted card — the three drivers, the race + year it
  happened (Wikipedia link), headline framing: "Raced together 14× · career
  podium rates 6% / 4% / 9% · expected ≈ 0.02 co-podiums, yet it happened."
- **Ranked list (#2–30):** `cand-list` rows: rank, trio, relative score bar,
  meta line with the rich breakdown — per-driver `rate (podiums/starts)`,
  `racesTogether`, expected (score) vs actual (count), and "happened: YYYY
  RaceName" wiki link.
- **Wiki links:** lift `wiki_url(season, raceName)` from `build_combos_html.py`
  into `_layout.py` so both pages share one copy; update the combos importer.

### 4. Wiring

- Add `("unlikeliest.html", "Unlikeliest")` to `NAV_LINKS` and the footer nav in
  `_layout.py` (appears on all pages).
- Register the page in `build_site.py`'s page→builder table.
- Add `compute_unlikeliest.py` to `update.py`'s compute step.

## Testing

- `test_compute_unlikeliest.py` — score math, ascending sort, skip-on-missing-
  driver, byte-identical determinism.
- `test_build_unlikeliest.py` — hero present, N rows, wiki links are Wikipedia
  URLs, nav has the new active link.
- `test_datalib.py` — schema round-trip for `unlikeliest.json`.
- `unlikeliest.json` added to validate registry.
- `RELEASE_NOTES.md` updated (required per project rules).

## Out of scope (YAGNI)

- No Plackett–Luce per-race probability (chosen heuristic instead).
- No current-grid split (this is an all-time, retrospective page).
- No new stylesheet unless the hero genuinely needs one beyond `podigami.css`.
