---
paths:
  - "src/fetch/fetch_openf1.py"
  - "src/fetch/openf1.py"
  - "src/fetch/stewards_gate.py"
  - "src/fetch/unconfirmed.py"
  - "src/fetch/fetch_starting_grid.py"
  - "src/wait_for_results.py"
  - "src/check_update_due.py"
  - "tests/test_fetch_openf1.py"
  - "tests/test_openf1.py"
  - "tests/test_fetch_starting_grid.py"
  - "tests/test_stewards_gate.py"
  - "tests/test_unconfirmed.py"
  - "tests/fixtures/openf1/**"
  - "data/unconfirmed.json"
  - "data/starting_grids.json"
  - "data/grid_penalties.json"
---

## OpenF1 fast lane (#327)

`src/fetch/fetch_openf1.py` runs right after the Jolpica fetchers. For the newest race and qualifying session Jolpica does not have yet, it writes OpenF1's classification (api.openf1.org, available from ~30 min after the session ends) into `podiums.json` / `race_results.json` / `qualifying.json` in Jolpica's exact row shape. One race has been measured live so far, and from a **local** fetcher run polling every 3 min rather than the production pipeline: at the 2026 Spanish GP (R14, started 13:00 UTC) OpenF1's `session_result` was still a 404 at 15:40 UTC, the fast lane first filled the round at 16:01 UTC with the stewards' check clear — about three hours after the start — and Jolpica published at about 19:45 UTC, nearly four hours later, with rows identical to OpenF1's (the podium, the race header and all 22 result rows, grid positions included). The Monza rehearsal replayed data days later with `--now`, so it proves the mapping, not the timing. Replaying 2026 R1–R13 from frozen fixtures (`tests/test_fetch_openf1.py`), every race the stewards' check lets through produces podium and race-result rows identical to Jolpica's. Qualifying is compared **by position**: Jolpica's stored row order differs in R5 and R10, and OpenF1 omits a car that set no time (R4), so a qualifying confirmation can reorder rows or add a car — a harmless diff.
- **Fail closed.** No write on any OpenF1 error, an unmatched/cancelled session (matched by UTC date + 6 h window), an unknown car number, a surname mismatch, an unknown team name (`TEAM_TO_CONSTRUCTOR` — a rebrand needs a new alias), or a held **stewards' check** (`src/fetch/stewards_gate.py`: open incident, unserved drive-through or time penalties that would change the podium *trio*, OpenF1's positions 1–3 disagreeing with its own race times, or a top-three row with no driver number). Holds ~22% of races (backtest: 65/83 published); those keep the Jolpica timing.
- **Rate limit.** OpenF1's free tier caps a client at 30 requests/minute (HTTP 429 + `Retry-After: 60`). `fetch/openf1.py` spaces request starts ≥ 2.1 s apart and retries a 429 after its Retry-After, clamped to 0–65 s, at most twice per request and 130 s in total per process, then fails closed. Go through that client; never add a second one or extra sleeps. The fixture recorder (`tests/fixtures/openf1/record_fixtures.py`) lifts the total cap, aborts on any failed request instead of writing an empty entry, and writes deterministic gzip.
- **Jolpica always wins.** A race is only filled when both `podiums.json` and `race_results.json` lack it. Each written round is listed in `data/unconfirmed.json` (per dataset); each Jolpica fetcher confirms the rounds its API returned (`fetch/unconfirmed.py`). The guard stays armed while anything is unconfirmed. A fast-lane run (`published=fast`) runs the pipeline, then hands over to a confirmation run (`Check whether Jolpica still has to confirm` → `Hand over to a confirmation run`) that waits on Jolpica only. **No double publish:** if the fast PR hasn't merged by the next run's in-flight wait, that step writes `still_open=true` and the run is Jolpica-only (`JOLPICA_ONLY`: the watcher ignores OpenF1 and `fetch_openf1.py` doesn't fill), so a result is never pushed twice and the chain can't loop.
- **The confirmation hand-over needs a real fill.** `fetch_openf1.py` writes `filled=race|qualifying` to `GITHUB_OUTPUT`, and the pipeline step (`id: pipeline`) carries it. `Check whether Jolpica still has to confirm` runs only on `published == 'fast' && steps.pipeline.outputs.filled != ''`. A fast run whose fill failed closed doesn't hand over, so a same-round retry waits for the next scheduled run instead of repeating a pipeline minutes later.
- **The Jolpica watcher can't be taken down by the fast lane.** `wait_for_results.py` imports `fetch_openf1` lazily inside `_openf1_ready`, so an import error or exception there is logged and read as "not ready".
- **Discrepancies are loud.** Jolpica's confirmation overwrites OpenF1's rows; a changed podium triggers the podium revision alert. A round unconfirmed > 48 h after its session fails the run (`--fail-on-stale`) → `auto-update-failure` issue.
- **Accepted trade-off (confirmation hold).** While a round stays unconfirmed past its 12 h successor window, every due scheduled run holds the concurrency group for a 5 h confirmation watch until Jolpica confirms. The watchdog's cadence degrades for that stretch, and a session that arms meanwhile waits for the next run. `--fail-on-stale` still surfaces a round unconfirmed > 48 h after its session, at most one watch late.
- **Accepted trade-off (fast-lane retries).** While OpenF1 fills keep failing, a scheduled run that reaches a still-pending race ends right after its fast pipeline instead of holding for Jolpica, so Jolpica's result then waits for the next scheduled run.
- **Can't be foreseen:** post-race scrutineering disqualifications (Austin 2023, Spa 2024, Las Vegas 2025). The site shows the crossed-the-line trio for a few hours, then corrects itself with a revision alert.
- **Where to read the timings.** Each watch prints a UTC stamp when it ends, accurate to the 3-min poll: `OpenF1 has round … at …` in the fast run, then `Jolpica has round … at …` in the confirmation run. Use those two to measure the gain per race.
- Rehearse with `python src/fetch/fetch_openf1.py --now <ISO>` in a scratch worktree (see the plan's Task 7).

## Official starting grid

`src/fetch/fetch_starting_grid.py` records F1's official starting grid for the next race in `data/starting_grids.json`, one entry per round, kept as history. `compute_podigami` uses it instead of `data/grid_penalties.json` for that round's post-quali prediction:
- grid slots come straight from F1;
- drivers with no qualifying time are included;
- the qualifying order still feeds the ratings.

F1 keeps a car that won't start on its grid, so `data/retirements.json` is still how to take one out. A substitute who wasn't in qualifying has a car number the qualifying entrants don't list, so the grid fails closed and the prediction keeps qualifying plus penalties.

- **Source.** OpenF1 `starting_grid`, keyed by the qualifying session, which mirrors formula1.com's "Starting grid" page. Research on 2026-10-05: in all 16 rounds of 2026 the F1.com page matched the grid each race started from (Jolpica's `grid`, pit-lane starters included), and OpenF1 matched the page. We don't scrape F1.com, because its Guidelines forbid reproducing results data "through scraping". Cars map through OpenF1's qualifying `drivers` list, which includes cars with no lap time, using the fast lane's `map_drivers`.
- **Timing.** F1 publishes the grid a few hours after qualifying. At Hungary 2026 it was still empty 1 h 10 m after the session and there 5 h 14 m after. It changed on race morning in 4 of 16 rounds, for pit-lane starts and power-unit elements fitted overnight.
- **Saturday.** The guard's `next_grid_target` is due once `postQuali` covers the next race and `starting_grids.json` lacks it, until `ARM_BEFORE` the race. The watcher's `grid` target polls OpenF1 until the grid appears. It is checked after qualifying and *before* confirmations, so the run handed over after a fast-lane qualifying result becomes a grid watch, and Jolpica's qualifying confirmation then lands with that run's pipeline or the next one. `watch_budget` caps a grid watch at the race window, so it never delays the results watch. `window_wait` makes a capped watch wait into the window, because `wait_until` stops up to one poll early, and only then is the race armed for the hand-over to start the race watch.
- **Sunday.** While a race watch holds the runner (from `ARM_BEFORE` the start, when a run is in place), it also re-checks the grid at every poll until the scheduled start. A change ends the watch with `published=grid` and the pipeline republishes. Then `regrid` runs `check_update_due.py --successor`, and "Hand over after a grid update" dispatches a successor that resumes the race watch. The grid PR has normally merged by the successor's in-flight wait. If it hasn't, that successor runs `JOLPICA_ONLY`, so its whole results watch goes without the OpenF1 fast lane. That's rare, since data PRs merge in ~1–2 min. Both steps run under `!cancelled()` (never after a failed pipeline): this watch gave up the results watch, so a later red step, such as a failed test or `--fail-on-stale` during a Jolpica outage, must not drop the hand-over. `tests/test_update_workflow.py` pins this.
- **One comparison.** `fetch_starting_grid.fresh_grid` decides "is there a new grid" for both the fetcher and the watcher, so a watch never ends on a grid the pipeline won't write.
- **Fail closed.** Nothing is written when OpenF1 errors or returns 404, no single qualifying session matches, a car won't map, the positions aren't exactly 1..N, or the grid isn't exactly the qualifying entrants. `JOLPICA_ONLY` skips every grid check and write. The schema rejects gaps and repeated positions or drivers.
- **`grid_penalties.json` is now the fallback,** used only until the official grid exists. It is still worth filling in for penalties known before qualifying (e.g. power-unit changes), because the official grid comes hours later.
- **Measure it.** The watcher prints `OpenF1 has a new official starting grid for round N at <UTC>`, and the fetcher prints who starts behind where they qualified: the penalties, pit-lane starts and drivers with no lap time.
- **Rehearse** with `python src/fetch/fetch_starting_grid.py --now <ISO>` and `python src/check_update_due.py --now <ISO>` on a copy of `data/` from before a race.
