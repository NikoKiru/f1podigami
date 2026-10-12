# Per-circuit learned grid effect (2026 run-in circuits) — design

Date: 2026-10-12 · Status: approved in brainstorming, pending spec review

## Problem

The post-qualifying prediction weights grid position by circuit:
`grid_offsets` scales the centred log-grid term by `w_grid · disp_ratio^-β`,
where `CircuitStats.disp_ratio` is a circuit's mean |grid − finish| relative to
the global mean, summed over **every visit since 1950** against an **all-era**
baseline, with no decay.

That measure is confounded by era. Measured on the committed data
(2026-10-12):

| Circuit | disp_ratio | grid scale | podium slots from P4+ since 2014 |
|---|---|---|---|
| Monaco | 1.02 (≈ neutral) | 0.98× | 19% |
| Yas Marina | 0.73 | 1.38× | 17% |
| Bahrain | 0.77 (processional) | 1.29× | 36% |
| Monza | 1.09 | 0.91× | 33% |

Monaco reads as an average track because its high-attrition 1950s–70s visits
inflate its displacement; Bahrain reads as processional because it has only
been raced in the reliable era. The measure also cannot separate "a fast car
recovered from P10" (expected by the ratings) from "this track lets you
overtake". The last grid tuning pinned both knobs to the edge of their range,
consistent with a noisy circuit signal.

## Scope

- **Model only.** No UI change; users see better post-quali predictions.
- **Only the circuits still to race in 2026:** `americas`, `rodriguez`,
  `interlagos`, `vegas`, `losail`, `yas_marina`. Every other circuit keeps the
  current behaviour exactly.
- **Only the post-qualifying prediction.** The pre-quali prediction, circuit
  temperature (`temp`) and DNF log-odds shift are unchanged.
- Ships only through the **strict gate** (below).

## Design

### The learned quantity

Each listed circuit `c` carries a correction `d_c ~ N(mean, var)`, created at
`N(0, cgrid_sigma0²)` on its first visit. The post-quali grid scale there is

```
scale_c = w_grid · disp_ratio_c^-β  +  mean(d_c)
          (today's term)               (learned correction)
```

With no data the correction is 0, so the prediction equals today's. Negative ⇒
grid matters less (out-of-position fast cars recover); positive ⇒ more
processional than `disp_ratio` says. Unlisted circuits never get a correction.

### Learning (in `HistoryFilter.step`)

For a race at a listed circuit, **after the snapshot** (leakage-free) and
**immediately before the race-order observation**:

1. Drift: `var += cgrid_tau²` (one step per visit — old eras fade, layout
   changes surface within a few visits).
2. Over the **classified finishers** (the same set and order the pace channel
   observes; DNFs are left to the reliability channel), build each one's
   race-day strength
   `s_i = μ_i + scale_c · x_i`, where `μ_i` is the engine's combined
   driver+constructor mean at that point (qualifying already observed in both
   snapshot modes) and `x_i = mean_j ln g_j − ln g_i` is the same centred
   log-grid term `grid_offsets` uses (centring is irrelevant to PL
   probabilities, so centring over finishers rather than the full grid is
   harmless).
3. Grid slots come from `race_results.json` `grid` (actual start, penalties
   included — matching the live official-grid input). `grid == 0`
   (pit-lane start) is treated as the slot after the highest numbered grid
   slot in that race.
4. Over the observed finishing order truncated to `depth_race` picks (the same
   truncation the pace channel uses), with stage-`j` PL probabilities
   `p_i^(j)` over the not-yet-picked entrants:
   - gradient `g = Σ_j [ x_{pick j} − Σ_i p_i^(j) x_i ]`
   - Hessian  `h = Σ_j Var_{p^(j)}(x)`
5. Update `d_c` with the engine's existing `RatingEngine._nudge` (weight 1.0).

Races with fewer than 3 classified finishers are skipped (no update). The update never touches driver/constructor states.

### Settings

- `DEFAULT_PARAMS_V2` gains `cgrid_sigma0` (prior std; **0 switches the feature
  off exactly** — no state is created and offsets are unchanged) and
  `cgrid_tau` (per-visit drift std). Defaults ship as `0.0` / `0.0` unless the
  gate accepts the tuned values.
- `model_v2.CGRID_CIRCUITS`: a module-level tuple of the six circuit ids.
- `datalib.schemas.ModelParamsV2` gains both knobs as optional floats
  (default 0.0) so a previously written `model_eval.json` still validates.

### Interfaces

- `HistoryFilter` exposes `grid_scale_adj(circuit_id) -> float` (the
  correction's mean, 0.0 for unlisted/unseen circuits). The snapshot dict
  carries `"grid_adj"` for the race being snapshotted.
- `grid_offsets(quali_pos, disp_ratio, params, scale_adj=0.0)`: the scale
  becomes `max(0, w · disp_ratio^-β + scale_adj)` — a correction can switch
  the grid term off but never invert it (pole never becomes a handicap). With `w_grid <= 0` it still returns
  zeros (the "ratings" baseline rung stays a pure ratings model).
- `compute_podigami._post_quali_block` passes
  `hf.grid_scale_adj(circuit)`; `backtest.score_window_v2` passes
  `snap["grid_adj"]`. Only the mean is used; the correction's variance is not
  propagated into `predict_race`.

## Validation

### Tuning (validation window 2010–2018)

`backtest.py --tune-v2-cgrid`: coordinate descent (2 sweeps) over only
`cgrid_sigma0 ∈ {0, 0.1, 0.2, 0.4}` and `cgrid_tau ∈ {0, 0.02, 0.05, 0.1}`,
post-quali protocol, every other knob frozen, objective = the existing
trio logLoss + novelty logLoss `J`, **scored on races at the listed circuits
only** (~29 races; nothing else changes). If a winner sits on a range edge,
widen that knob's range once and record it.

### Strict gate (frozen 2019+ test window)

Following the adaptive-car pattern, `backtest.CIRCUIT_GRID` holds the tuned
values. Two ladder rows are added, both scored on the **subset** of test races
at the listed circuits (~32 races):

- `v2 post-quali +grid [run-in circuits]` — `DEFAULT_PARAMS_V2` with
  `cgrid_sigma0 = 0` (baseline)
- `v2 post-quali +circuit grid [run-in circuits]` — `DEFAULT_PARAMS_V2` +
  `CIRCUIT_GRID` (candidate)

`circuitGridAccepted` is true only if the candidate wins on **both** logLoss
and brierNew. It is printed alongside the existing post-quali gate. The
existing full-window `v2 post-quali +grid` row keeps using
`DEFAULT_PARAMS_V2`, so after acceptance it reflects the shipped model and the
landing-page row lookup (exact model name) is unaffected.

Caveat accepted up front: ~32 races make brierNew noisy; the strict gate will
likely reject anything short of a clear effect.

### Outcomes

- **Accepted:** copy `CIRCUIT_GRID` into `DEFAULT_PARAMS_V2` with a comment
  recording the validation/test numbers; regenerate `model_eval.json` and
  `podigami.json`; one README sentence in the model "Grid" bullet.
- **Rejected:** nothing user-facing changes. Report the numbers; the user
  decides between keeping it as a dormant rung (defaults 0.0, like
  `con_adapt_gain`) or dropping the branch.

## Tests (TDD)

`tests/test_model_v2.py`:
- `cgrid_sigma0 = 0` ⇒ `HistoryFilter` snapshots and `predict_race` output are
  identical to the current model (regression guard).
- Direction: a synthetic race at a listed circuit won from the back of the grid
  moves the correction negative; one where the grid order holds against the
  ratings' expectation moves it positive.
- Unlisted circuits never get a correction (`grid_scale_adj == 0.0`).
- Leakage-free: a race's snapshot `grid_adj` is the value from before that
  race's update.
- Pit-lane starters (`grid == 0`) are placed last; too-small fields skip.
- `grid_offsets(..., scale_adj=0.0)` equals the old result; `w_grid = 0`
  returns zeros regardless of `scale_adj`.

`tests/test_backtest.py`:
- The two subset rows appear in the ladder and score only listed-circuit races.
- The `circuitGridAccepted` flag follows the both-scores rule.

`tests/test_datalib.py` / `test_compute_podigami.py`: `model_eval.json` and
`podigami.json` still round-trip byte-identically with the new optional knobs
(silent-stall guardrail).

## Delivery

Feature branch `feat/circuit-grid-learning` off `develop` → PR into
`develop` (with a `RELEASE_NOTES.md` entry) → promotion to `main` before the
United States GP qualifying (2026-10-24).
