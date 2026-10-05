# Official Starting Grid — Design

**Date:** 2026-10-05
**Status:** Approved (design)
**Builds on:** `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md`, which listed
"Replacing the manual `grid_penalties.json` with OpenF1 `starting_grid`" as a follow-up.

## Problem

The post-qualifying prediction (`podigami.json` → `postQuali`) needs the grid the race
will actually start from. Today that grid is rebuilt from the qualifying order plus
penalties a human types into `data/grid_penalties.json`. Nothing alerts when an entry
is missing or out of date, and the rebuild cannot represent drivers who set no time.

Evidence (research of 2026-10-05, all 16 rounds of 2026):

| Finding | Detail |
|---|---|
| F1 publishes the exact grid | formula1.com's "Starting grid" page matched the grid each race actually started from (Jolpica `race_results.json` `grid`) for every car in **16 of 16** rounds, pit-lane starters included. |
| OpenF1 mirrors it | OpenF1 `starting_grid` (keyed by the qualifying session) matched the F1.com page in **16 of 16** rounds. Its docs say the data appears "a few minutes after the official results are published on the official Formula 1 website". |
| The manual rebuild was often wrong | Of the 7 rounds with a live post-quali block (R10–R16), the rebuilt grid matched the official one in only 3. R14 had no entry at all (Sainz +3 and Stroll to the back were on F1.com by Saturday 21:55Z). R15 missed Sainz's 5-place and Perez's 3-place qualifying penalties. In R10 and R13 the grid changed on Sunday. |
| Drivers who set no lap time vanish | `qualifying.json` leaves out drivers with no lap time (R1: Verstappen, Sainz, Stroll; R14: Stroll, Bearman). `_post_quali_block` builds its field from qualifying only, so those starters are never simulated. |
| Publish timing | F1.com shows the grid a few hours after qualifying. Hungary was still empty 1 h 10 m after qualifying ended and populated 5 h 14 m after. Australia, Malaysia and Spain were populated 5–8 h after qualifying. |
| Race-morning changes | **4 of 16** rounds changed on Sunday before the start: China Albon (pit lane), Belgium Sainz (+10), Italy Alonso and Lawson (pit lane), Spain Bearman (pit lane). |
| No-time drivers are mappable | OpenF1's qualifying `drivers` list includes every car on the grid, even ones with no lap time (checked R1, R14, R16: 22 of 22). |

## Goals

- The post-quali prediction uses F1's official starting grid automatically, within minutes
  of OpenF1 publishing it, both on Saturday evening and when it is revised on race morning.
- Drivers with no qualifying time are part of the simulated field; a qualifier who will not
  start is not.
- No manual step on a normal weekend. `grid_penalties.json` keeps working as the fallback
  until the official grid exists.
- Keep every existing property: fail closed, deterministic compute, byte-identical
  re-runs, no network in build/tests, and no new silent-stall path.

## Non-goals

- Scraping formula1.com. F1's Guidelines say results data "may not be reproduced or used
  commercially through scraping". OpenF1 already mirrors the page as JSON.
- Any new page element or label. The hero and chips already show the grid slot
  (`starts 8th`, `P8`).
- Changes after lights out (formation-lap DNS, a car starting from the pit lane late). The
  grid is treated as frozen at the scheduled start.
- Sprint grids. The site tracks Grand Prix podiums only.

## Decisions (user-approved)

1. **Scope: Saturday and Sunday.** The official grid is picked up after qualifying, and the
   race-day watch also re-checks it until the start.
2. **Source: OpenF1 `starting_grid`.** Not F1.com.
3. **The official grid wins.** For its round it replaces `grid_penalties.json`. The manual
   file stays as the fallback before the grid is published (e.g. power-unit penalties
   known before qualifying).
4. **Approach: extend the existing watcher.** No new workflow, no extra cron.

## Architecture

```
Saturday  quali watch → pipeline (postQuali from qualifying + grid_penalties.json)
          guard: postQuali covers the round, no official grid yet → "grid" watch
          grid watch polls OpenF1 starting_grid → published=grid → pipeline
                                                    → hand-over if anything is pending
Sunday    race watch (armed 3 h before the start) polls results as today and, until
          the start, also re-checks the grid: OpenF1 grid != committed → published=grid
          → pipeline → hand-over → the successor resumes the race watch
```

New: `src/fetch/fetch_starting_grid.py`, `data/starting_grids.json`
(`StartingGridRace` schema). Changed: `compute_podigami.py`, `check_update_due.py`,
`wait_for_results.py`, `update.py`, `.github/workflows/update.yml`, datalib.

## Section 1 — Fetcher and dataset

`data/starting_grids.json`, a list with one entry per round, kept as history:

```json
[{"season": "2026", "round": "17",
  "grid": [{"driverId": "max_verstappen", "constructorId": "red_bull", "position": 1}, ...]}]
```

Schema `StartingGridRace {season, round, grid: list[StartingGridRow]}`, where
`StartingGridRow` is `{driverId, constructorId, position: int}`. A validator requires
positions to be exactly 1..N and driver IDs to be unique. It is registered in
`datalib.REGISTRY` (so `datalib.validate` covers it) with `load_starting_grids` /
`save_starting_grids`. It is committed initially as `[]`.

`src/fetch/fetch_starting_grid.py`:

- **`target_race(schedule, podiums, now)`** is the newest scheduled race whose qualifying
  has started (`fetch_openf1.newest_started`). It returns `None` if that race is already
  in `podiums.json` or `now` is past its scheduled start.
- **`build_grid(race, season, current, client)`** matches the qualifying session with
  `fetch_openf1.match_session`, then reads `client.starting_grid(key)`. It maps car
  numbers through `fetch_openf1.map_drivers(client.drivers(key), current)`, which checks
  number, surname and team. It returns `{season, round, grid}` sorted by position, or
  `None` (nothing written) when:
  - OpenF1 fails, has no grid yet, or has no single matching session;
  - any car doesn't map, or a position isn't an int;
  - the positions aren't exactly 1..N;
  - the grid's car numbers aren't exactly the qualifying session's entrants.
- **`fresh_grid(race, season, current, grids, client)`** returns the built entry only
  when it differs from the committed entry for that round, or there is none. This is the
  **single comparison** used by both the fetcher and the watcher, so they can never
  disagree about whether something changed.
- **`main()`** honours `JOLPICA_ONLY` (skips, like the fast lane) and `--now`
  (rehearsals). It replaces or appends the round's entry, validates the payload, saves
  it, and prints which drivers start somewhere other than their qualifying position.
  Any exception is printed and leaves the file untouched (exit 0).
- **`update.py`** runs it after "Fetching constructor standings" (so `current_drivers.json`
  and `schedule.json` are fresh) and before "Computing podigami".

## Section 2 — Compute

`compute()` / `_post_quali_block()` take `starting_grids`. `main()` loads it when the
file exists. When an entry exists for the predicted (season, round):

- Grid slots (`gpos`) come from the official grid. `grid_penalties.json` is not
  consulted for that round.
- The simulated field is the official grid's drivers minus `retirements.json`. A driver
  on the grid but not in qualifying takes his `constructorId` from the grid row.
- The qualifying order still feeds the rating channel (`observe_order` over qualifying
  rows only). A driver with no lap time adds no qualifying information.

Without an entry, the behaviour is byte-for-byte today's. The `gridPosition` schema
comment is updated to name both sources.

## Section 3 — Guard, watcher and workflow

**Guard (`check_update_due.py`).**
- `next_grid_target(schedule, asof, post_quali, grids, now)` returns the next race's
  (season, round) when `postQuali` already covers it, `starting_grids.json` has no entry
  for it, and `now < race start − ARM_BEFORE`. It is fail-safe in the same way as
  `next_quali_target`.
- `read_grids()` loads the file and returns `[]` if it is missing or unreadable.
- `main()` ORs a `grid` trigger into `due`.
- `pending_session_starts()` adds the qualifying start of a pending grid, so a timed-out
  grid watch hands over until qualifying start + `SUCCESSOR_WINDOW`.

**Watcher (`wait_for_results.py`).**
- `wait_target(..., grids, jolpica_only)` checks targets in the order race → qualifying →
  grid (skipped when `jolpica_only`) → confirmations.
- `choose_source(...)` gains `grid_ready` and `before_start`:
  - A `grid` watch ends only on `grid_ready()`.
  - A `race` watch keeps Jolpica → OpenF1 precedence, then, while `before_start`, also
    ends on `grid_ready()`.
  - `jolpica_only` disables both grid paths.
- `grid_ready` wraps `fetch_starting_grid.fresh_grid`. It is imported lazily and any
  exception reads as "not ready" (the same pattern as `_openf1_ready`).
- A grid watch's budget is `min(POLL_TIMEOUT_S, race start − ARM_BEFORE − now)`, so it
  can never hold the runner into the race window.
- Outcome `grid` reports `published=grid` and logs
  `OpenF1 has a new official starting grid for round N at <UTC>`. That line is the
  timing measurement.

**Workflow (`update.yml`).**
- `published=grid` already passes the pipeline gate (`!= 'none'`).
- After the tests, two new steps mirror the fast lane's confirmation hand-over: `id:
  regrid` runs `check_update_due.py --successor` when `published == 'grid'`, and
  "Hand over after a grid update" dispatches `update.yml -f mode=auto -f wait=true`.
- On race day the successor's in-flight wait sees the grid PR merge (median 1.3 min), and
  its race watch then finds no change.

**Loop and stall analysis.**
- The fetcher and the watcher share `fresh_grid`, so the watcher only fires on something
  the pipeline will write.
- A transient OpenF1 failure inside the pipeline costs one extra iteration, at most until
  the start.
- `JOLPICA_ONLY` (an earlier data PR still open) disables every grid check and write.
- A failed pipeline ends red and alerts, like the fast lane, so it doesn't hand over.
- **Develop-window safety:** main's current watcher never reports `grid`, so the new
  steps are inert until the scripts are promoted.

## Error handling

Fail closed everywhere: any doubt about OpenF1's grid writes nothing, and the prediction
keeps today's qualifying + `grid_penalties.json` behaviour. Watcher grid checks swallow
exceptions as "not ready", with a log line. The guard's grid trigger is bounded by the
race window, so a grid that never appears can't keep runs firing.

## Testing

- **`tests/test_fetch_starting_grid.py`.** Replays `tests/fixtures/openf1/openf1_2026.json.gz`
  (2026 R1–R13 quali sessions, drivers and grids). Mapped grids must equal Jolpica's
  `race_results` `grid` (`jolpica_2026.json.gz`) for every round. R1 must include its
  three drivers with no lap time. Fail-closed cases:
  - no session, or an OpenF1 error;
  - an empty grid;
  - an unmapped car or a duplicate position;
  - a gap in positions;
  - a missing qualifier.

  It also covers target selection (before qualifying, after the start, race already
  classified), and write/replace/no-change handling (byte-identical).
- **`test_compute_podigami.py`.** The official grid overrides penalties; a driver with no
  lap time joins the field; a non-starter leaves it; another round's entry is ignored;
  retirements still apply; the output is deterministic and schema-valid.
- **`test_check_update_due.py` / `test_wait_for_results.py`.** Cover:
  - when the grid trigger is due and not due, and where it is bounded;
  - successor windows;
  - target order and `jolpica_only`;
  - `choose_source` for grid and race watches before and after the start;
  - grid-watch budget capping.
- **`test_datalib.py`.** Round-trip and validator tests for `starting_grids.json`.
- **Rehearsal against live OpenF1.** In a scratch worktree, overlay `data/` from main just
  before the R16 race (and before R14), then run `fetch_starting_grid.py --now …` and
  `compute_podigami.py`. `postQuali.driverForm` `gridPosition` must equal F1.com's grid.
  For R14, Stroll and Bearman must be in the field.

## Rollout

1. PR `feat/official-starting-grid` → `develop` (7 checks). Then run a forced update to
   prove the develop window: `gh workflow run update.yml -f mode=auto -f force=true`.
2. Promotion PR `develop → main` (9 checks) → deploy, then another forced run.
3. First live use: Singapore R17. Qualifying is Sat 2026-10-10 13:00Z; the race is Sun
   12:00Z. Read the watcher's `OpenF1 has a new official starting grid` lines for timing.
4. CLAUDE.md (automation section and data flow), README, and RELEASE_NOTES updated in the
   feature PR.

## Limitations (accepted)

- If OpenF1 only publishes the grid late, or never, before a race, the prediction falls
  back to today's behaviour. The logs show it, and the manual file still works.
- A Sunday change costs one pipeline run (~20 min) and a hand-over inside the race watch.
  That is well before results arrive (OpenF1 needs at least 30 min after the flag).
- If OpenF1 ever served a pre-penalty grid, it would win over manual penalties. This is
  unlikely: F1.com shows "No results available" until the FIA grid exists, and OpenF1
  mirrors F1.com.
