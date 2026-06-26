# Design: Calendar-Year Season Detection (Issue #84)

## Problem

Every fetch script derives the "current season" from `max(season in data/podiums.json)`. Because `podiums.json` only contains **completed** races, in the off-season gap (roughly December–March) `max(season)` still returns the previous year. This causes:

- `fetch_schedule.py` to pull last year's schedule → every race is in the past → next-race box shows "Season complete — see you next year"
- `fetch_current_drivers.py` to pull last year's grid → predictions use stale drivers
- `fetch_constructor_standings.py` to pull last year's standings → same staleness
- `render_last_race` to return `""` when the schedule's most-recent past race hasn't landed in `podiums.json` yet (API lag)

## Approach

Use `datetime.date.today().year` as the canonical current season in all three fetch scripts. No new files, no new abstractions — four targeted edits.

## Changes

### 1. `src/fetch/fetch_schedule.py`

Delete `current_season()` (lines 59–61). In `main()`, replace the call with:

```python
import datetime
season = datetime.date.today().year
```

### 2. `src/fetch/fetch_current_drivers.py`

Replace `season_and_recent_rounds()` (lines 56–60) with a version that:
1. Uses `datetime.date.today().year` as the season.
2. Filters rounds from `podiums.json` for that year (same logic as before).
3. Returns `(year, [])` if no rounds exist yet for the current year.

`main()` will then write `{"season": year, "drivers": []}` — the build layer already handles an empty drivers list gracefully (no prediction section rendered).

### 3. `src/fetch/fetch_constructor_standings.py`

Replace `season_and_rounds()` (lines 59–63) with the same calendar-year pattern:
1. Use `datetime.date.today().year` as the season.
2. Filter rounds for that year from `podiums.json`.
3. Return `(year, [])` if none exist.

`main()` already has a `MIN_ROUNDS` guard (line 90) that writes an empty payload when rounds are too few — so off-season is already handled once the season source is corrected.

### 4. `src/build/build_podigami_html.py` — `render_last_race` fallback

Currently at line 182, if no podium record matches the schedule's last race, the function returns `""`.

Fix: instead of returning empty, find the most recent podium in the dataset:

```python
if not pod:
    pod = max(podiums, key=lambda p: (int(p["season"]), int(p["round"])), default=None)
    if not pod:
        return ""
```

Render that fallback podium using the existing render path. This handles the window between a race finishing and its API record appearing in `podiums.json`.

## Data Flow

```
datetime.date.today().year
  └─→ fetch_schedule.py      → data/schedule.json  (current year's calendar)
  └─→ fetch_current_drivers  → data/current_drivers.json  (empty list off-season)
  └─→ fetch_constructor_standings → data/constructor_standings.json (empty off-season)

podiums.json (most recent entry)
  └─→ render_last_race fallback  (when scheduled round not yet in dataset)
```

## Error Handling

- Off-season `fetch_current_drivers`: empty drivers list → compute/build skip prediction section (existing behaviour when grid is empty).
- Off-season `fetch_constructor_standings`: `MIN_ROUNDS` guard already writes empty payload.
- `render_last_race` with no podiums at all: `max(..., default=None)` → returns `""` (same as today).

## Testing

- Unit tests for the three updated helper functions: assert they return `today().year` when called, and return `(year, [])` when no rounds exist for the current year.
- Update `test_build_podigami.py`: add a case for `render_last_race` where the scheduled round has no podium — assert it renders the most recent available podium instead of returning empty.
- Existing `pytest -q` suite must still pass.
- Lint: `ruff check . && ruff format --check .`
