# Post-Qualifying Grid-Aware Prediction — Design

**Date:** 2026-07-15
**Status:** Approved

## Problem

The headline prediction (`chanceNextRaceNew`, the hero % and candidate trios) is computed
once, right after the previous race — deliberately *pre-qualifying*: model v2's snapshot
is taken before the upcoming race's quali is observed. But qualifying is the single most
informative pre-race event: it reveals current car/driver pace **and** fixes the starting
grid, whose track-position advantage has strong historical precedent (a Monaco pole is
worth far more than the pace it signals). Once the real quali happens, the site should
publish an updated, more accurate new-trio chance.

## Goals

- After the next race's qualifying session, automatically recompute and publish a
  **grid-aware** prediction: headline %, re-ranked candidate trios, updated driver form.
- Ground the grid effect in historical grid→finish data, intertwined with the existing
  model v2 rating engine — not a bolt-on.
- Know *when* qualifying is done (session timing in committed data; guard-driven trigger).
- Preserve every integrity property: walk-forward validation with an acceptance gate,
  deterministic byte-identical compute, no new silent-stall vectors in the update loop.

## Non-goals

- Sprint-race podiums/grids (the site tracks GP podiums only; the API's `Qualifying`
  session is the GP-grid-setting session even on sprint weekends).
- Penalty-adjusted official grids: the API does not publish them pre-race. The
  qualifying classification is the grid signal (see Limitations).
- Live/manual pole display beyond the prediction UI (can come later).

## Decisions (user-approved)

1. **Headline UX:** post-quali % becomes the hero number with an "⚡ Updated after
   qualifying" badge and a movement line ("↑ was 52% before the grid was set"). The
   pre-quali number remains visible as context.
2. **Update scope:** everything the prediction drives updates — hero pick, candidates
   panel (badged "grid-aware", with per-driver "starts P3" chips), driver form weights.
3. **Model approach:** ratings update from the quali order **plus** an explicit tuned,
   circuit-modulated grid-advantage term (Approach A), backtest-gated.

## Architecture

Three-stage pipeline extension; no new stages, no workflow changes.

```
fetch_schedule      +qualifyingDate/Time per race        → schedule.json
fetch_qualifying    (unchanged) picks up round N quali    → qualifying.json
compute_podigami    +postQuali block when next-race quali → podigami.json
check_update_due    +quali trigger (no-network guard)
build_podigami_html +hero badge/delta, grid chips, FAQ    → dist/index.html
backtest            +post-quali protocol, 2 rungs, gate   → model_eval.json
model_v2            +grid_offsets / predict_post_quali    (pure math, shared)
```

## Section 1 — Data & fetch layer

**schedule.json:** `fetch_schedule.py` copies the API's `Qualifying: {date, time}` into
each race as `qualifyingDate` / `qualifyingTime` (`str | None = None` in `ScheduleRace`;
canonical dumps emit `null` when absent, and the currently committed file — which lacks
the keys — still validates). Auto-updates refetch the schedule every run, so main gains
the fields on the first post-promotion update; the feature PR commits a locally
refetched `schedule.json` so develop exercises them immediately.

**qualifying.json:** zero fetch changes. The incremental fetcher already re-pulls the
current season's aggregate feed every run and merges by (season, round). Post-Saturday,
the feed holds round N's quali while `race_results.json` doesn't — that committed
asymmetric state is schema-legal, violates no data-integrity invariant, and *is* the
"between quali and race" signal.

**Entrant pool:** the post-quali prediction uses exactly the quali participants with the
constructor each qualified for (handles seat swaps and substitutes). Display names
resolve podium-history → `current_drivers.json` → title-cased driverId.

## Section 2 — Model math

Post-quali prediction = existing v2 filter state + two effects, in order:

1. **Information effect.** After filtering all history and applying between-race
   dynamics (what `_v2_next_race_model` does today), feed the fresh quali order through
   the same channel every historical quali gets:
   `engine.observe_order(entries, depth=depth_qual, weight=w_qual)`.
2. **Causal track-position effect.** At predict time each entry's mean becomes

   ```
   mu_d + w_grid * disp_ratio(circuit) ** (-grid_circuit_beta) * x(g_d)
   x(g) = -(ln g - mean(ln g over the field))    # centered power-law decay
   ```

   `disp_ratio` is the shrunk, clamped grid→finish displacement ratio `CircuitStats`
   already maintains, exposed via a small refactor (`temp()` becomes `ratio ** eta`).
   Negative exponent: processional circuits (low displacement, e.g. Monaco) amplify the
   grid term; chaotic ones dampen it. Variances, `p_finish`, and circuit temperature are
   untouched; `predict_race` is unchanged — offsets fold into the `mu` it already takes.

**New knobs (2):** `w_grid`, `grid_circuit_beta`, appended to `DEFAULT_PARAMS_V2`,
locked by a new `backtest.py --tune-v2-grid` coordinate descent on the existing
2010–2018 validation window with the other 18 knobs frozen.

**Placement:** pure helpers in `model_v2.py` — `grid_offsets(...)` plus a
`predict_post_quali(...)` orchestration — used identically by compute and backtest.

**Acceptance gate (same culture as v2):** the ladder gains two rungs scored under a
post-quali protocol (quali observed before the snapshot, offsets applied — legitimate
conditioning, since quali genuinely precedes the race):

- `v2 post-quali (ratings)` — information effect only (`w_grid=0`), the baseline.
- `v2 post-quali +grid` — full Approach A.

The grid term ships only if `+grid` beats ratings-only on test logLoss **and** brierNew;
otherwise `w_grid` locks to 0 and the feature degrades to the ratings-only update. Both
rungs land in `model_eval.json` for the FAQ to cite. Sanity assertion: post-quali
logLoss ≤ pre-quali on the test window.

## Section 3 — Compute & podigami.json contract

`compute_podigami.py`: everything computed today stays byte-for-byte the pre-quali
prediction. After it, resolve the next race from schedule + `asOf`; if `qualifying.json`
holds that exact (season, round) → emit `postQuali`; else `"postQuali": null`.

```jsonc
"postQuali": {
  "season": "2026", "round": "10", "raceName": "Belgian Grand Prix",
  "chanceNextRaceNew": 71.3,
  "candidates": [ /* same shape, re-ranked; perDriver entries gain "gridPosition" */ ],
  "driverForm": [ /* updated weights, same DriverStrength shape */ ]
}
```

- Top-level `chanceNextRaceNew` / `candidates` / `driverForm` keep their exact current
  (pre-quali) meaning; `asOf` semantics untouched.
- Schema: `Podigami.postQuali: PodigamiPostQuali | None = None`; `DriverStrength` gains
  optional `gridPosition: int | None`; `PodigamiParamsV2` gains `w_grid`,
  `grid_circuit_beta`, `usingPostQuali: bool`.
- Because params gains required keys, the feature PR recomputes and commits
  `podigami.json` offline (expect the usual standings-churn noise in the diff).
- Determinism: distinct derived fixed seed for the post-quali simulation; the file
  remains a byte-identical fixed point of its inputs (the #178 stall-class guardrail).

## Section 4 — Automation: trigger & guard

`check_update_due.py` gains a second, independent trigger (race trigger untouched):

> Find the first scheduled race after `asOf`. If it has `qualifyingDate/Time`, and
> `now >= quali start + QUALI_BUFFER (90 min)`, and `podigami.postQuali` doesn't already
> cover that (season, round) → due.

- Guard stays no-network, reading only `schedule.json` + `podigami.json`.
- Missing quali fields ⇒ trigger never fires (safe during rollout).
- Output stays a single `due` boolean; the update run is generic "sync everything," so a
  quali-triggered run fetches quali, computes `postQuali`, opens the same
  `auto/update-data` PR, auto-merges, deploys. **Zero `update.yml` changes.**
- Self-healing: API not published yet ⇒ no-op run, guard re-fires each 15-min tick;
  once `postQuali` covers the round the trigger goes quiet (one quali ⇒ one PR). After
  the race merges and `asOf` advances, the next compute clears `postQuali` to null in
  the same PR that adds the result, re-arming the trigger for the following round.
  Delayed quali lands late; a cancelled event drops out via the weekly `--full`
  schedule refetch.
- Timeline: quali ends ~15:00 UTC Saturday → trigger ~15:32–16:02 → PR + checks +
  deploy → updated headline live ~1.5–2h after quali, up ~24h until the race. Sprint
  weekends (Friday GP quali) get ~2 days of airtime.

## Section 5 — Rendering

`build_podigami_html.py` branches on `postQuali`:

- **Present:** hero renders the post-quali chance as the big number; pick + candidates
  panel come from `postQuali.candidates`; form tower uses `postQuali.driverForm`. New
  hero elements: "⚡ Updated after qualifying" badge + delta line
  "↑ was 52% before the grid was set" (old number from the top-level field). Candidate
  driver chips gain "starts P3" tags; candidates panel gets a "grid-aware" badge.
- **Null:** exactly today's page.
- Always: next-race box shows "Qualifying: Sat 14:00 UTC" when the schedule has it.
- CSS in `assets/podigami.css` via `_layout.asset()` cache-busting; 600px mobile
  breakpoint handled. FAQ gains an entry explaining the two-stage prediction and citing
  the post-quali rungs. README + RELEASE_NOTES.md updated in the same PR.

## Section 6 — Testing, validation & rollout

- **Unit:** guard quali-trigger matrix (before/after buffer, covered round, missing
  fields, next-season opener, garbage times); `grid_offsets` math (centering, decay
  shape, circuit modulation direction, `w_grid=0` ⇒ zero); post-quali determinism;
  entrant pool from quali rows incl. substitute-name fallback; compute emits
  `postQuali` vs null; schema round-trips both ways.
- **Render tests use fixtures, not live data** (#178 lesson): committed develop data
  normally has `postQuali: null` — dist-fixture tests assert the absence path; badge/
  delta/grid-chip markup is covered by direct render-helper tests with synthetic
  payloads. No test may depend on transient live-data state (new stall vector otherwise).
- **Model validation:** `--tune-v2-grid` locks the two knobs; full backtest run verifies
  the gate verdict; commit updated `model_eval.json` with the two rungs.
- **Manual:** build with a synthetic next-round quali entry, serve `dist/`, verify hero
  desktop + mobile in a real browser (Playwright) before the PR.
- **Rollout:** one feature PR → develop, promote develop → main **before Saturday
  2026-07-18** — Belgian GP qualifying is the first live firing. No PAT/workflow changes.

## Error handling (cross-cutting)

Every new path degrades to current behavior: missing quali schedule fields ⇒ no
trigger; unpublished quali data ⇒ no-op run + retry next tick; gate failure ⇒
`w_grid=0` ratings-only update; `postQuali: null` ⇒ today's page. Nothing new can wedge
the update loop.

## Limitations (accepted)

- The pre-race grid signal is the **qualifying classification**, not the official
  penalty-adjusted grid (not published pre-race by the API). Penalties occasionally
  shift the true grid after our update; the race result then supersedes it within hours.
- A driver who races but skipped quali is absent from the post-quali entrant pool
  (rare; the pre-quali prediction still covered them).
- `RESULTS_BUFFER`-style timing means the updated number lands ~1.5–2h after quali, not
  instantly (bounded by the 15-min cron + CI + Pages deploy).
