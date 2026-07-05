# Podigami predictor v2 — dynamic Bayesian rating engine

**Date:** 2026-07-04 · **Status:** approved (approach B chosen by user)

## Goal

Replace the podium-count Plackett–Luce predictor with a model that extracts
essentially all public result signal and demonstrably improves the two numbers
the site leads with:

1. `chanceNextRaceNew` — P(the next podium is a brand-new trio). Today this is
   barely better than the base rate (Brier 0.2396 vs 0.2412 on the 2019+ test
   window).
2. The ranked list of most-likely *new* trios (`candidates`).

"Better" is decided by the frozen walk-forward test window (2019 → latest),
scored with the existing proper scoring rules (trio log-loss, Brier, top-k,
ECE). Every added layer must earn its place via an ablation rung in the
backtest ladder. If v2 does not beat v1 on the test window, v1 stays live and
the ladder ships as evidence.

## Non-goals

- No weather/tyre/telemetry data (no free, stable source; revisit later).
- No use of the *upcoming* race's qualifying (data updates run post-race; the
  prediction is made before the next weekend).
- No new runtime dependencies (pure Python + stdlib; `requests` for fetch).
- No backend/DB — everything stays committed JSON → static HTML.
- Sprint results are out of scope for v2 (small n; can be a later channel).

## Research grounding

- Henderson & Kirrane 2018 (*Bayesian Analysis* 13(2), doi:10.1214/17-BA1048):
  attrition (reverse Plackett–Luce) beats forward PL for F1
  winner/podium/top-10 forecasting; truncating forward PL (~top-6) helps;
  geometric time-decay of past results improves forecasts; PL has a
  Gumbel/Thurstone latent representation (Yellott 1977) that justifies
  simulation.
- van Kesteren & Bergkamp 2023 (*JQAS* 19(4), arXiv:2203.08489): Bayesian
  rank-ordered logit with driver + constructor terms; ~88% of finishing-order
  variance is the constructor → the car must be a first-class, per-race-updated
  state, not an overlay.
- Weng & Lin 2011 (*JMLR* 12, 267–300): closed-form Gaussian approximate
  Bayesian updates for PL-type rank likelihoods → no MCMC needed; we use the
  equivalent assumed-density-filtering form (one Newton/Laplace step per race).

## New datasets

### `data/race_results.json` (new, committed, compact JSON)

Full World Championship classifications 1950 → present. One entry per race:

```json
{"season":"2026","round":"8","raceName":"Austrian Grand Prix",
 "date":"2026-06-28","circuitId":"red_bull_ring",
 "results":[
   {"driverId":"russell","constructorId":"mercedes","grid":1,
    "position":1,"laps":71,"status":"Finished"},
   {"driverId":"albon","constructorId":"williams","grid":9,
    "position":null,"laps":52,"status":"Gearbox"}]}
```

- `position`: integer classified position, `null` when unclassified (DNF, DSQ,
  DNS, …). `status` is the verbatim API string; interpretation happens in
  compute, not fetch. `grid`: int, 0 = pit lane/unknown. `laps`: int (orders
  retirements for the attrition channel).
- Fetched from Jolpica `/{season}/results.json` (limit 100, offset paging).
- Written compact (no indent) via a per-file format override in
  `datalib.repository._save`; ~2.5–3 MB. All other datasets keep `indent=2`.

### `data/qualifying.json` (new, committed, compact JSON)

Grid-setting qualifying classifications, 1994 → present (Ergast/Jolpica
coverage starts 1994; missing races/seasons are simply absent — the model
treats qualifying as an optional extra observation channel).

```json
{"season":"2026","round":"8",
 "results":[{"driverId":"russell","constructorId":"mercedes","position":1}]}
```

### Fetch scripts

`src/fetch/fetch_race_results.py` and `src/fetch/fetch_qualifying.py`, both
mirroring `fetch_podiums.py` conventions: incremental by default (re-fetch the
latest season on disk + probe the next), `--full` backfill, 1.1 s sleeps,
exponential backoff, `datalib.save_*`. Budget check: full backfill ≈ 300 + 150
requests, under Jolpica's 500/h sustained limit; the routine incremental update
adds ~4 requests. `update.py` gains two steps right after "Fetching podiums"
(with `--full` propagation).

## Model (new module `src/compute/model_v2.py`, pure, no IO)

### States

- Driver skill `θ_d ~ N(μ_d, σ²_d)`, prior `N(rookie_mean, σ0²_d)`.
- Constructor strength `β_c ~ N(μ_c, σ²_c)`, prior `N(newteam_mean, σ0²_c)`.
- A driver's log-worth in a session: `s = θ_d + β_c(d)` (single pace latent;
  race and qualifying are two observation channels of it).

### Observation update (per session, closed form)

Forward PL log-likelihood of an observed order truncated at depth `r`
(worths `w = exp(s)`), with prefix sums `Z_j = Σ_{m ≥ j} w_m`:

```
grad_i = [rank(i) ≤ r] − Σ_{j ≤ min(rank(i), r)} w_i / Z_j
hess_i = Σ_{j ≤ min(rank(i), r)} (w_i/Z_j)(1 − w_i/Z_j)
```

Each state gets a scalar Kalman/Laplace step with channel weight `κ`
(a power likelihood, i.e. Henderson's power-prior device):

```
denom = 1 + σ² κ h        μ ← μ + σ² κ g / denom        σ² ← σ² / denom
```

`g,h` for a driver state are `grad,hess` of its `s`; a constructor state
receives the summed `grad/hess` of its drivers in that session.

Channels per race weekend, each with its own orientation/truncation/weight:

1. **Race pace** (forward PL on classified finishers, truncated at `r_race`,
   weight 1.0) — DNFs excluded from this channel.
2. **Attrition** (reverse PL: the full race order *including* DNFs, reversed;
   DNFs ranked by laps completed; forward-PL update applied to the reversed
   order with negated states, weight `κ_attr`). This is the Henderson/Graves
   attrition model as a second channel rather than a replacement.
3. **Qualifying** (forward PL on quali classification, truncated at `r_qual`,
   weight `κ_qual`) — when data exists for that weekend.

Rows with status DNS/withdrawn are dropped from all channels; DSQ rows are
dropped from rank channels but count as finishes for reliability.

### Dynamics (between sessions)

- Per race gap: `σ² += τ²` (τ_drv, τ_con).
- Season boundary: `σ² += κ_season` (driver and constructor variants).
- Regulation resets (curated constant `REG_RESET_SEASONS` = {1961, 1966,
  1989, 2009, 2014, 2022, 2026} — the major engine/aero formula changes):
  extra constructor inflation `κ_reg`.
- Constructor continuity across rebrands via a curated alias map
  (`CONSTRUCTOR_LINEAGE`: toro_rosso→alphatauri→rb, force_india→racing_point→
  aston_martin, sauber→alfa→sauber→audi, benetton→renault→lotus_f1→renault→
  alpine, brawn→mercedes chain, …, complete for 1990+, best-effort earlier).
  States carry over; the reg/season inflation still applies.

### Reliability (DNF hazard)

Status strings classified once in compute into `{finished, mech_dnf,
driver_dnf, excluded}` (curated mapping constant; `+N Laps` = finished;
Accident/Collision/Spun off = driver_dnf; DSQ = excluded-from-ranks but a
finish for hazard; DNS/DNQ/Withdrew = excluded entirely).

- Constructor mechanical rate and driver incident rate: exponentially decayed
  event counts (half-life `hl_rel` races) with Beta shrinkage toward the
  era rate (itself an exponentially decayed global rate, so the 1950s ≠ 2020s).
- `p_finish(d) = (1 − p_mech(c(d))) · (1 − p_inc(d))`, then circuit attrition
  adjustment on log-odds: `logit(p_dnf) += γ · circuit_dnf_logodds_delta`,
  clamped to [0.02, 0.995].

### Circuit chaos

Per `circuitId`, recency-weighted and shrunk toward 1.0 by race count:

- **Attrition delta**: circuit DNF log-odds minus era log-odds (feeds hazard).
- **Shuffle temperature** `T_circ`: mean |grid − finish| displacement among
  classified finishers (races with usable grid data only), relative to the
  era mean, raised to a fitted exponent `η`. Applied as worth exponent
  `1/T` in the prediction layer only (training uses raw orders).
- Unknown/new circuits get the neutral 1.0 / era values.
- A global **wild-race mixture**: with fitted probability `p_wild` the race
  uses `T · T_wild` (rain/safety-car chaos the calendar can't tell us about).

### Prediction layer (the podigami numbers)

For the next race (entrants = `current_drivers.json`, teams =
`constructor_standings.driverConstructor`, circuit = next schedule entry after
`asOf`, else neutral):

1. Deterministic Monte Carlo, `random.Random(20260704)`, N = 512 draws of:
   per-driver skill noise `s_i = μ_i + z·σ_i`, survivor set via `p_finish`
   Bernoullis, wild flag via `p_wild`.
2. Per draw, **exact** conditional PL top-3-set probabilities (6-permutation
   closed form, worths `exp(s/T)`) over the survivors — Rao-Blackwellised, so
   512 draws give tight estimates.
3. `P(new) = 1 − Σ_{seen trios possible on this grid} P(trio)` — the
   complement over seen trios is exact (no truncation error).
4. Candidate list: screen unseen trios by the closed-form no-noise
   probability, keep the top 250, compute exact averaged probabilities for
   those, rank, emit top 12. Seen-trio count on a 22-driver grid is small
   (≤ ~80), so steps 2–4 stay well under a minute in pure Python.

Same layer runs inside the backtest with N = 64 (only the realised trio and
the seen-set complement are needed there).

## Hyperparameters & tuning

18 knobs: `σ0_drv, σ0_con, rookie_mean, newteam_mean, τ_drv, τ_con,
κ_season_drv, κ_season_con, κ_reg, r_race, κ_attr, r_qual, κ_qual, hl_rel,
γ, η, p_wild, T_wild` (r_* are small-integer choices). Tuned by coordinate
descent (2–3 sweeps over coarse grids) minimising walk-forward trio log-loss
on 2010–2018 (filter warm-starts from 1950), tie-break `brierNew`. Winners are
locked into `model_v2.DEFAULT_PARAMS` (same convention as v1); `backtest.py
--tune-v2` reproduces the search. The 2019+ window is never touched by tuning.

## Evaluation (extend `src/compute/backtest.py`)

- Ladder keeps the v1 rungs and adds: `v2 pace` (channels 1+3 off, attrition
  off — race channel only), `v2 +attrition`, `v2 +reliability+chaos`,
  `v2 full (+quali)`. Metrics unchanged (top1/3/5, logLoss, brierSet,
  brierNew, ECE + calibration bins) so rows are directly comparable.
- `chosen` = best v2 rung by test log-loss (expected: full). Comparison vs v1
  and vs base rates reported as today.
- Pools: entrants per race from `race_results.json` (exact), replacing the
  `driver_races.json` approximation inside the backtest (that dataset stays —
  other pages use it).
- Runtime budget: full ladder ≤ ~90 s pure Python in CI (single filter pass
  per rung is O(races · field²)).

## Integration

- `compute_podigami.py`: if both new datasets exist → v2 engine produces
  `lam`-equivalent posterior means for `driverForm` display, exact
  `candidates` + `chanceNextRaceNew` from the prediction layer; else fall back
  to v1 unchanged (keeps CI green until the backfill lands, and is the
  rollback path).
- `podigami.json` schema: `params` becomes a tagged union — `model:
  "plackett-luce"` keeps today's required fields; `model: "dbpl-v2"` carries
  the v2 params block (typed, no extras). `DriverStrength` gains optional
  `finishProb` and `uncertainty` floats (only emitted by v2). Builders keep
  rendering `weight`; landing FAQ copy is rewritten to describe v2 accurately
  (pace + survival + chaos layers, closed-form Bayesian updates, calibration
  numbers from `model_eval.json` as today).
- `model_eval.json` schema: `modelParams` becomes optional-v1 + optional-v2
  block; ladder row names are free-form already.
- All committed floats rounded (probabilities 3 dp, rates 4 dp) — cross-
  platform byte-identical output, same churn characteristics as today.
- README (architecture, feature bullets), RELEASE_NOTES entry, this spec
  committed under `docs/superpowers/specs/`.

## Testing

TDD throughout; key cases:

- **Update math**: hand-computed 2–3 driver gradients; posterior mean moves
  toward winner, variance shrinks; reverse-channel sign flip; truncation stops
  gradient flow below depth `r`; constructor state accumulates both drivers'
  terms; power weight `κ` scales the step.
- **Dynamics**: gap/season/reg inflation; lineage map carries state across a
  rebrand; rookie/new-team priors.
- **Reliability/chaos**: status classification table; shrinkage arithmetic on
  synthetic sequences; circuit deltas from synthetic grids; clamping.
- **Prediction layer**: with zero variance, p_finish = 1, T = 1 it must equal
  v1's `pl_set_prob` exactly (bridge test); Σ over all trios ≈ 1; complement
  identity; byte-determinism across two runs.
- **Fetch**: fixture-driven parsing (existing `test_fetch_season.py` pattern),
  incremental merge, DNS/DSQ rows preserved, compact write format.
- **Data integrity**: for overlapping races, `race_results` top-3 ==
  `podiums.json` trio (with a small documented skip-list for historical data
  quirks, e.g. shared drives).
- **Schemas**: round-trip fidelity in `test_datalib.py` for both new files and
  both params unions.
- **E2E**: `dist` fixture builds with a v2 `podigami.json`.

## Risks & mitigations

- **API data quirks** (shared drives pre-1960s, Indianapolis 500 1950–60,
  missing grids): defensive parsing, integrity-test skip-list, chaos stats
  ignore races without grid data.
- **Rate limits**: throttled + resumable backfill; incremental steady state.
- **2026 cold start** (new regs, Cadillac): reg-reset inflation + new-team
  prior are designed exactly for this; sanity-check driverForm vs 2026
  standings before shipping.
- **CI cadence**: every layer budgeted; if the ladder exceeds budget, ablation
  rungs move behind a `--full-ladder` flag while the chosen rung always runs.
- **v2 loses on the frozen test**: v1 stays live; ladder ships as evidence;
  iterate in a follow-up.

## Rollout order

1. Fetchers + schemas + backfill (data lands as its own reviewable commit).
2. `model_v2.py` core (update math, dynamics, reliability, chaos) under TDD.
3. Prediction layer + bridge test.
4. Backtest ladder + tuning run → lock `DEFAULT_PARAMS`.
5. Wire `compute_podigami.py` + schema/builder/FAQ/README/RELEASE_NOTES.
6. Full verification (ruff, pytest, validate, build, local preview), PR into
   `develop`, merge, then promotion PR `develop → main` to deploy.
