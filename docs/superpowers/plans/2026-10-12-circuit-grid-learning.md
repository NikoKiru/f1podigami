# Per-circuit learned grid effect — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Learn, for each of the six circuits left on the 2026 calendar, a correction to how much starting position matters in the post-qualifying prediction, and ship it only if it beats today's grid term on the frozen test window.

**Architecture:** A new `CircuitGridLearner` in `src/compute/model_v2.py` holds a Gaussian correction `d_c` per listed circuit, updated inside `HistoryFilter.step` (after the snapshot, before the race order moves the ratings) by one closed-form truncated-Plackett–Luce gradient/Hessian step. `grid_offsets` gains a `scale_adj` argument; `compute_podigami` and `backtest` pass the learned mean. `backtest.py` gains a circuit filter, a `--tune-v2-cgrid` tuner and a strict two-score gate on the run-in-circuit subset.

**Tech Stack:** Python 3.11+, pytest, ruff, Pydantic v2 (`src/datalib`).

**Spec:** `docs/superpowers/specs/2026-10-12-circuit-grid-learning-design.md`

## Global Constraints

- Listed circuits, exactly: `americas`, `rodriguez`, `interlagos`, `vegas`, `losail`, `yas_marina` (constant `model_v2.CGRID_CIRCUITS`).
- `cgrid_sigma0 <= 0` must switch the feature off **exactly**: no learner state, `grid_adj == 0.0`, predictions byte-identical to today's.
- The learner never modifies driver or constructor states.
- Post-quali prediction only; pre-quali prediction, `temp`, DNF delta unchanged.
- Strict gate: ship only if the candidate is **strictly lower** on both test `logLoss` and `brierNew` than the baseline, on races at listed circuits in the 2019+ window.
- New knobs are appended **after `con_adapt_hl`** in both `DEFAULT_PARAMS_V2` and the two Pydantic schemas (key order must match for the byte-identical round-trip).
- Run commands from the repo root. Tests: `python -m pytest -q`. Lint: `python -m ruff check .` and `python -m ruff format --check .`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work on branch `feat/circuit-grid-learning` (already created off `develop`; the spec is committed there).

---

### Task 1: Grid-term helpers and `scale_adj` on `grid_offsets`

**Files:**
- Modify: `src/compute/model_v2.py` (`__all__` ~line 31; `grid_offsets` lines 217–231)
- Test: `tests/test_model_v2.py` (grid_offsets section ~line 448)

**Interfaces:**
- Produces:
  - `centred_log_grid(grid: dict[str, int]) -> dict[str, float]` — `x(g) = mean ln g − ln g`
  - `base_grid_scale(disp_ratio: float, params: dict) -> float` — `w_grid * max(disp_ratio, 1e-6) ** (-grid_circuit_beta)`
  - `grid_offsets(quali_pos, disp_ratio, params, scale_adj: float = 0.0) -> dict[str, float]`

- [ ] **Step 1: Write the failing tests** — append to the `# --- grid_offsets ---` section of `tests/test_model_v2.py`:

```python
def test_grid_offsets_scale_adj_zero_is_todays_term():
    qpos = {"a": 1, "b": 2, "c": 5}
    p = _gparams(w=0.4, beta=1.0)
    assert model_v2.grid_offsets(qpos, 0.8, p, 0.0) == model_v2.grid_offsets(qpos, 0.8, p)
    base = model_v2.base_grid_scale(0.8, p)
    assert base == pytest.approx(0.4 / 0.8)
    x = model_v2.centred_log_grid(qpos)
    assert model_v2.grid_offsets(qpos, 0.8, p) == {d: base * v for d, v in x.items()}


def test_centred_log_grid_is_zero_sum_and_pole_highest():
    x = model_v2.centred_log_grid({"a": 1, "b": 2, "c": 3})
    assert sum(x.values()) == pytest.approx(0.0, abs=1e-12)
    assert x["a"] > x["b"] > x["c"]
    assert model_v2.centred_log_grid({}) == {}


def test_grid_offsets_scale_adj_shifts_and_floors_at_zero():
    qpos = {"a": 1, "b": 2, "c": 3}
    p = _gparams(w=0.4, beta=0.0)  # base scale is exactly 0.4
    x = model_v2.centred_log_grid(qpos)
    up = model_v2.grid_offsets(qpos, 1.0, p, 0.2)
    down = model_v2.grid_offsets(qpos, 1.0, p, -0.2)
    assert up["a"] == pytest.approx(0.6 * x["a"])
    assert down["a"] == pytest.approx(0.2 * x["a"])
    # a correction can switch the grid term off, never invert it
    assert model_v2.grid_offsets(qpos, 1.0, p, -1.0) == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_grid_offsets_zero_weight_ignores_scale_adj():
    qpos = {"a": 1, "b": 2, "c": 3}
    zeros = {"a": 0.0, "b": 0.0, "c": 0.0}
    assert model_v2.grid_offsets(qpos, 1.0, _gparams(w=0.0), 0.5) == zeros
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_model_v2.py -q -k "scale_adj or centred_log_grid"`
Expected: FAIL — `AttributeError: module 'compute.model_v2' has no attribute 'base_grid_scale'` / `centred_log_grid`, and `TypeError` on the 4-argument `grid_offsets`.

- [ ] **Step 3: Implement** — in `src/compute/model_v2.py`, replace the whole `grid_offsets` function with:

```python
def centred_log_grid(grid: dict[str, int]) -> dict[str, float]:
    """``x(g) = mean ln g - ln g``: the centred power-law grid term (pole highest)."""
    if not grid:
        return {}
    logs = {d: math.log(g) for d, g in grid.items()}
    mean_log = sum(logs.values()) / len(logs)
    return {d: mean_log - lg for d, lg in logs.items()}


def base_grid_scale(disp_ratio: float, params: dict) -> float:
    """The circuit-modulated grid weight ``w_grid * disp_ratio ** (-grid_circuit_beta)``."""
    return params["w_grid"] * (max(disp_ratio, 1e-6) ** (-params["grid_circuit_beta"]))


def grid_offsets(
    quali_pos: dict[str, int], disp_ratio: float, params: dict, scale_adj: float = 0.0
) -> dict[str, float]:
    """Causal track-position term: additive log-worth offsets from grid slots.

    ``x(g) = -(ln g - mean ln g)`` -- a centered power-law decay in grid
    position -- scaled by ``w_grid`` and amplified at processional circuits
    (low displacement ratio) via ``disp_ratio ** (-grid_circuit_beta)``.
    ``scale_adj`` is the learned per-circuit correction (CircuitGridLearner);
    the total scale is floored at 0, so a correction can switch the term off
    but never invert it. Zero-sum across the field, so it shifts relative
    order, not overall level.
    """
    if params["w_grid"] <= 0.0 or not quali_pos:
        return dict.fromkeys(quali_pos, 0.0)
    scale = max(0.0, base_grid_scale(disp_ratio, params) + scale_adj)
    return {d: scale * x for d, x in centred_log_grid(quali_pos).items()}
```

Add to `__all__`: `"base_grid_scale"` immediately before `"classify_status"`, and `"centred_log_grid"` immediately after it.

- [ ] **Step 4: Run the whole model file** (the existing grid_offsets tests prove `scale_adj=0` is unchanged)

Run: `python -m pytest tests/test_model_v2.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/compute/model_v2.py tests/test_model_v2.py
git commit -m "Model v2: split the grid term into helpers and add a scale correction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `CircuitGridLearner` (pure math)

**Files:**
- Modify: `src/compute/model_v2.py` (new constant + class right after `class CircuitStats`, before `class HistoryFilter`; `__all__`)
- Test: `tests/test_model_v2.py` (new section after the CircuitStats tests, before `# --- grid_offsets ---`)

**Interfaces:**
- Consumes: `centred_log_grid` (Task 1); existing `Gauss`, `_clamp_var`, `RatingEngine._nudge(st, g, h, weight) -> float`.
- Produces:
  - `CGRID_CIRCUITS: tuple[str, ...]`
  - `CircuitGridLearner(sigma0: float, tau: float, circuits=CGRID_CIRCUITS)` with attributes `sigma0`, `tau`, `circuits: frozenset[str]`, and methods
    - `adj(circuit_id: str) -> float`
    - `observe(circuit_id: str, finishers: list[tuple[str, float, int]], base_scale: float, depth: int) -> None` — `finishers` = `(driverId, rating mean, grid slot >= 1)` in finishing order.

- [ ] **Step 1: Write the failing tests**

```python
# --- CircuitGridLearner -----------------------------------------------------------


def _fin(order_grid, mu=None):
    """(driverId, rating mean, grid slot) in finishing order; equal ratings by default."""
    return [(d, 0.0 if mu is None else mu[d], g) for d, g in order_grid]


_BACK_WINS = [("a", 10), ("b", 9), ("c", 8)] + [(f"x{g}", g) for g in range(1, 8)]
_GRID_HOLDS = [(f"x{g}", g) for g in range(1, 11)]


def test_cgrid_circuits_are_the_2026_run_in():
    assert model_v2.CGRID_CIRCUITS == (
        "americas",
        "rodriguez",
        "interlagos",
        "vegas",
        "losail",
        "yas_marina",
    )


def test_cgrid_disabled_when_sigma0_zero():
    lr = model_v2.CircuitGridLearner(0.0, 0.05)
    lr.observe("americas", _fin(_BACK_WINS), 0.4, 3)
    assert lr.adj("americas") == 0.0
    assert lr._d == {}


def test_cgrid_ignores_unlisted_circuits():
    lr = model_v2.CircuitGridLearner(0.3, 0.05)
    lr.observe("monaco", _fin(_BACK_WINS), 0.4, 3)
    assert lr.adj("monaco") == 0.0
    assert lr._d == {}


def test_cgrid_skips_fields_under_three():
    lr = model_v2.CircuitGridLearner(0.3, 0.05)
    lr.observe("americas", _fin([("a", 2), ("b", 1)]), 0.4, 3)
    assert lr._d == {}


def test_cgrid_podium_from_the_back_moves_negative():
    lr = model_v2.CircuitGridLearner(0.3, 0.0)
    lr.observe("americas", _fin(_BACK_WINS), 0.4, 3)
    assert lr.adj("americas") < 0.0


def test_cgrid_grid_holding_against_expectation_moves_positive():
    lr = model_v2.CircuitGridLearner(0.3, 0.0)
    # base scale 0: the model expected no grid effect, yet finish == grid
    lr.observe("americas", _fin(_GRID_HOLDS), 0.0, 3)
    assert lr.adj("americas") > 0.0


def test_cgrid_ratings_explain_a_fast_cars_recovery():
    order = [("fast", 10)] + [(f"x{g}", g) for g in range(1, 10)]
    neutral = model_v2.CircuitGridLearner(0.3, 0.0)
    neutral.observe("americas", _fin(order), 0.4, 3)
    rated = model_v2.CircuitGridLearner(0.3, 0.0)
    mu = {d: 0.0 for d, _ in order} | {"fast": 4.0}
    rated.observe("americas", _fin(order, mu), 0.4, 3)
    # a win from P10 by a car the ratings already expected to win says less
    # about overtaking than the same win by an equal-rated car
    assert neutral.adj("americas") < rated.adj("americas")


def test_cgrid_drift_lets_a_late_visit_move_further():
    def last_move(tau):
        lr = model_v2.CircuitGridLearner(0.3, tau)
        for _ in range(5):
            lr.observe("americas", _fin(_GRID_HOLDS), 0.4, 3)
        before = lr.adj("americas")
        lr.observe("americas", _fin(_BACK_WINS), 0.4, 3)
        return before - lr.adj("americas")

    assert last_move(0.2) > last_move(0.0) > 0.0


def test_cgrid_is_deterministic():
    a, b = (model_v2.CircuitGridLearner(0.3, 0.05) for _ in range(2))
    for lr in (a, b):
        lr.observe("americas", _fin(_BACK_WINS), 0.4, 3)
        lr.observe("americas", _fin(_GRID_HOLDS), 0.4, 3)
    assert a.adj("americas") == b.adj("americas")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_model_v2.py -q -k cgrid`
Expected: FAIL — `AttributeError: ... no attribute 'CGRID_CIRCUITS'` / `'CircuitGridLearner'`.

- [ ] **Step 3: Implement** — insert after `class CircuitStats` (and its methods), before `class HistoryFilter`:

```python
# The circuits still to race in 2026 when the learned grid correction was added
# (2026-10-12). Every other circuit keeps the plain disp_ratio grid term.
CGRID_CIRCUITS: tuple[str, ...] = (
    "americas",
    "rodriguez",
    "interlagos",
    "vegas",
    "losail",
    "yas_marina",
)


class CircuitGridLearner:
    """Learned per-circuit correction to the post-quali grid scale.

    Each listed circuit carries ``d_c ~ N(mean, var)``, born at
    ``N(0, sigma0**2)``, which is added to the circuit-modulated base scale
    (``base_grid_scale``). A race there is read as a truncated PL order over
    race-day strengths ``mu_i + (base + d_c) * x_i`` (``x`` = centred log
    grid), and one closed-form gradient/Hessian step moves ``d_c``. The
    ratings already carry pace, so only grid-vs-finish movement they did not
    expect counts as evidence about the track. Each visit first adds
    ``tau**2`` drift so old eras fade. ``sigma0 <= 0`` disables it entirely.
    """

    def __init__(self, sigma0: float, tau: float, circuits: tuple[str, ...] = CGRID_CIRCUITS):
        self.sigma0 = sigma0
        self.tau = tau
        self.circuits = frozenset(circuits)
        self._d: dict[str, Gauss] = {}

    def adj(self, circuit_id: str) -> float:
        """Current mean correction (0.0 for an unlisted or unvisited circuit)."""
        st = self._d.get(circuit_id)
        return st.mu if st is not None else 0.0

    def observe(
        self,
        circuit_id: str,
        finishers: list[tuple[str, float, int]],
        base_scale: float,
        depth: int,
    ) -> None:
        """One update from a race. ``finishers`` lists (driverId, rating mean,
        grid slot >= 1) in finishing order; ``depth`` truncates the order to the
        first N picks, exactly as the pace channel does."""
        if self.sigma0 <= 0.0 or circuit_id not in self.circuits or len(finishers) < 3:
            return
        st = self._d.setdefault(circuit_id, Gauss(0.0, self.sigma0**2))
        st.var = _clamp_var(st.var + self.tau**2)

        xmap = centred_log_grid({d: g for d, _, g in finishers})
        x = [xmap[d] for d, _, _ in finishers]
        k = base_scale + st.mu
        w = [
            math.exp(max(-30.0, min(30.0, mu + k * xi)))
            for (_, mu, _), xi in zip(finishers, x, strict=True)
        ]
        m = len(finishers)
        r = max(1, min(depth, m - 1))
        g = h = 0.0
        for j in range(r):
            z = sum(w[j:])
            ex = sum(wi * xi for wi, xi in zip(w[j:], x[j:], strict=True)) / z
            ex2 = sum(wi * xi * xi for wi, xi in zip(w[j:], x[j:], strict=True)) / z
            g += x[j] - ex
            h += max(ex2 - ex * ex, 0.0)
        RatingEngine._nudge(st, g, h, 1.0)
```

Add `"CGRID_CIRCUITS"` and `"CircuitGridLearner"` to `__all__` (next to `"CircuitStats"`).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_model_v2.py -q`
Expected: all PASS. If `test_cgrid_drift_lets_a_late_visit_move_further` or `test_cgrid_ratings_explain_a_fast_cars_recovery` fails, re-derive the gradient by hand before touching the test — they encode the spec's intended behaviour.

- [ ] **Step 5: Commit**

```bash
git add src/compute/model_v2.py tests/test_model_v2.py
git commit -m "Model v2: add the per-circuit grid correction learner

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Knobs, schemas, and `HistoryFilter` integration

**Files:**
- Modify: `src/compute/model_v2.py` (`DEFAULT_PARAMS_V2` end; `HistoryFilter.__init__`, new `grid_scale_adj`, `step`)
- Modify: `src/datalib/schemas.py` (`PodigamiParamsV2` after `con_adapt_hl` ~line 277; `ModelParamsV2` after `con_adapt_hl` ~line 421)
- Modify: `data/podigami.json`, `data/model_eval.json` (regenerated)
- Test: `tests/test_model_v2.py`

**Interfaces:**
- Consumes: `CircuitGridLearner`, `base_grid_scale` (Tasks 1–2).
- Produces:
  - `DEFAULT_PARAMS_V2["cgrid_sigma0"] = 0.0`, `DEFAULT_PARAMS_V2["cgrid_tau"] = 0.0`
  - `HistoryFilter.cgrid: CircuitGridLearner`
  - `HistoryFilter.grid_scale_adj(circuit_id: str) -> float`
  - snapshot dict key `"grid_adj": float` (the correction from **before** that race's update)

- [ ] **Step 1: Write the failing tests**

In `test_default_params_have_exactly_the_locked_knobs`, add `"cgrid_sigma0"` and `"cgrid_tau"` to the expected set. Then append to the `# --- HistoryFilter ---` section:

```python
def _grid_field_race(season, rnd, circuit, finish_grid):
    """Drivers d<g>/cars t<g>; ``finish_grid`` lists grid slots in finishing order."""
    rows = [_rrow(f"d{g}", f"t{g}", g, i + 1, 50, "Finished") for i, g in enumerate(finish_grid)]
    return _rrace(season, rnd, circuit, rows)


_BACK_PODIUM = [8, 9, 10, 1, 2, 3, 4, 5, 6, 7]


def _cgrid_filter(sigma0=0.3, tau=0.05):
    return model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2, cgrid_sigma0=sigma0, cgrid_tau=tau))


def test_cgrid_never_touches_ratings_and_off_means_zero():
    off, on = _cgrid_filter(sigma0=0.0), _cgrid_filter()
    for rnd in range(1, 6):
        race = _grid_field_race(2020, rnd, "americas", _BACK_PODIUM)
        s_off, s_on = off.step(race, None), on.step(race, None)
        assert s_off["drivers"] == s_on["drivers"]
        assert s_off["grid_adj"] == 0.0
    assert off.grid_scale_adj("americas") == 0.0
    assert on.grid_scale_adj("americas") < 0.0


def test_cgrid_unlisted_circuit_has_no_correction():
    hf = _cgrid_filter()
    for rnd in range(1, 4):
        snap = hf.step(_grid_field_race(2020, rnd, "monaco", _BACK_PODIUM), None)
        assert snap["grid_adj"] == 0.0
    assert hf.grid_scale_adj("monaco") == 0.0


def test_cgrid_snapshot_carries_the_pre_race_correction():
    hf = _cgrid_filter()
    first = hf.step(_grid_field_race(2020, 1, "americas", _BACK_PODIUM), None)
    assert first["grid_adj"] == 0.0
    after_first = hf.grid_scale_adj("americas")
    assert after_first != 0.0
    second = hf.step(_grid_field_race(2020, 2, "americas", list(range(1, 11))), None)
    assert second["grid_adj"] == after_first
    assert hf.grid_scale_adj("americas") != after_first


def test_cgrid_pit_lane_starter_counts_as_last():
    def race(winner_grid):
        rows = [_rrow("d0", "t0", winner_grid, 1, 50, "Finished")]
        rows += [_rrow(f"d{g}", f"t{g}", g, g + 1, 50, "Finished") for g in range(1, 11)]
        return _rrace(2020, 1, "americas", rows)

    pit, back = _cgrid_filter(), _cgrid_filter()
    pit.step(race(0), None)  # pit-lane start
    back.step(race(11), None)  # the slot after the last numbered one
    assert pit.grid_scale_adj("americas") == back.grid_scale_adj("americas")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_model_v2.py -q -k "cgrid or locked_knobs"`
Expected: FAIL — `KeyError: 'cgrid_sigma0'` / `KeyError: 'grid_adj'` / `AttributeError: ... 'grid_scale_adj'`, and the knob-set assertion.

- [ ] **Step 3: Implement**

3a. Append to `DEFAULT_PARAMS_V2` (after `"con_adapt_hl": 1.0,`):

```python
    # Learned per-circuit grid correction (CircuitGridLearner, CGRID_CIRCUITS),
    # added 2026-10-12. sigma0 0 == off: the post-quali grid term is exactly
    # w_grid * disp_ratio ** -beta. Candidate values live in backtest.CIRCUIT_GRID
    # and move here only if the run-in-circuit gate accepts them.
    "cgrid_sigma0": 0.0,  # prior std of a circuit's grid-scale correction
    "cgrid_tau": 0.0,  # per-visit drift std of that correction
```

3b. `HistoryFilter.__init__` — add after `self.circuits = CircuitStats()`:

```python
        self.cgrid = CircuitGridLearner(params["cgrid_sigma0"], params["cgrid_tau"])
```

and add this method right after `__init__`:

```python
    def grid_scale_adj(self, circuit_id: str) -> float:
        """Learned correction to the post-quali grid scale here (0.0 if none)."""
        return self.cgrid.adj(circuit_id)
```

3c. In `step`, add `"grid_adj": self.cgrid.adj(circuit),` to the `snapshot` dict (after `"disp_ratio"`). Then, in the `# ---- channel 2: race pace ----` block, between `classified = sorted(...)` and `self.engine.observe_order(...)`, insert:

```python
        # ---- circuit grid correction (listed circuits only): after the snapshot,
        # before the race order moves the ratings it is measured against ----
        if self.cgrid.sigma0 > 0.0 and circuit in self.cgrid.circuits:
            back = max((r["grid"] for r in rows), default=0) + 1  # pit lane -> last
            finishers = [
                (
                    r["driverId"],
                    self.engine.combined(r["driverId"], r["constructorId"])[0],
                    r["grid"] if r["grid"] > 0 else back,
                )
                for r in classified
            ]
            self.cgrid.observe(
                circuit,
                finishers,
                base_grid_scale(snapshot["disp_ratio"], p),
                int(p["depth_race"]),
            )
```

3d. `src/datalib/schemas.py` — in **both** `PodigamiParamsV2` and `ModelParamsV2`, directly after `con_adapt_hl: float = ...`:

```python
    # Learned per-circuit grid correction (added 2026-10-12); optional with
    # defaults for the same reason as the adaptive knobs above.
    cgrid_sigma0: float = 0.0
    cgrid_tau: float = 0.0
```

- [ ] **Step 4: Run model + datalib tests**

Run: `python -m pytest tests/test_model_v2.py tests/test_datalib.py -q`
Expected: model tests PASS. `test_dataset_roundtrips_byte_identical[podigami.json]` and `[model_eval.json]` FAIL (the committed files lack the two new keys) — fixed in Step 5.

- [ ] **Step 5: Regenerate the two data files and check the diff is only the new keys**

```bash
python src/compute/compute_podigami.py
PYTHONPATH=src python src/compute/backtest.py
git diff --stat data/
git diff data/ | grep '^[+-] ' 
```

Expected: only `data/podigami.json` and `data/model_eval.json` change, and the only `+`/`-` lines are the added `"cgrid_sigma0": 0.0,` / `"cgrid_tau": 0.0` (plus a trailing-comma change on the preceding `con_adapt_hl` line where JSON needs it). Any other numeric change means the off switch is not exact — stop and debug (superpowers:systematic-debugging). Also check the files are still compact/indented as before (memory: an external formatter can re-indent `data/*.json`).

- [ ] **Step 6: Full suite + validate + lint**

```bash
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/compute/model_v2.py src/datalib/schemas.py tests/test_model_v2.py data/podigami.json data/model_eval.json
git commit -m "Model v2: learn the circuit grid correction in the history filter (off by default)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Use the correction in the live post-quali prediction

**Files:**
- Modify: `src/compute/compute_podigami.py:409` (the `grid_offsets` call in `_post_quali_block`)
- Test: `tests/test_compute_podigami.py` (after `test_post_quali_pole_shock_lifts_underdog`, ~line 818)

**Interfaces:**
- Consumes: `HistoryFilter.grid_scale_adj(circuit_id) -> float` (Task 3), `grid_offsets(..., scale_adj)` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
def test_post_quali_applies_the_learned_circuit_grid_correction(scenario_post_quali, monkeypatch):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    kw = dict(constructor_data=con, race_results=rres, qualifying=quali, schedule=SCHED_R6)
    base = cp.compute(podiums, combos, grid, **kw)["postQuali"]

    asked = []

    def no_grid(self, circuit_id):
        asked.append(circuit_id)
        return -10.0  # floors the grid scale at zero: no grid term at all

    monkeypatch.setattr(cp.model_v2.HistoryFilter, "grid_scale_adj", no_grid)
    flat = cp.compute(podiums, combos, grid, **kw)["postQuali"]

    assert asked == ["monaco"]
    w_base = {d["driverId"]: d["weight"] for d in base["driverForm"]}
    w_flat = {d["driverId"]: d["weight"] for d in flat["driverForm"]}
    assert w_flat["eli"] < w_base["eli"]  # the pole-sitter loses the grid boost
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_compute_podigami.py -q -k learned_circuit_grid`
Expected: FAIL — `assert [] == ['monaco']`.

- [ ] **Step 3: Implement** — replace the line

```python
    offsets = model_v2.grid_offsets(gpos, disp, params)
```

with

```python
    adj = hf.grid_scale_adj(circuit) if circuit else 0.0
    offsets = model_v2.grid_offsets(gpos, disp, params, adj)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_compute_podigami.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/compute/compute_podigami.py tests/test_compute_podigami.py
git commit -m "Post-quali prediction: apply the learned circuit grid correction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Backtest — circuit filter, tuner, run-in gate, CLI

**Files:**
- Modify: `src/compute/backtest.py` (constants after `V2_GRID_TUNE_GRID` ~line 256; `score_window_v2` ~line 282; `tune_v2_grid` ~line 407; `evaluate` post-quali block ~line 485; `main` ~line 530)
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `HistoryFilter` snapshot `"grid_adj"` (Task 3), `grid_offsets(..., scale_adj)` (Task 1), `model_v2.CGRID_CIRCUITS`.
- Produces:
  - `CIRCUIT_GRID: dict` (initial `{"cgrid_sigma0": 0.2, "cgrid_tau": 0.05}`; Task 6 replaces it with the tuned values)
  - `V2_CGRID_TUNE_GRID: dict[str, list]`
  - `RUNGS_V2_CGRID: list[tuple[str, dict]]`
  - `score_window_v2(..., circuits: frozenset[str] | None = None)`
  - `tune_v2_cgrid(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict`
  - `evaluate(...)["postQuali"]["circuitGridAccepted"]: bool`
  - CLI flag `--tune-v2-cgrid`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_backtest.py`:

```python
# --- run-in circuit grid correction ---------------------------------------------

_RUNIN = "americas"


def _runin_history():
    """Finish == grid with a rotating grid, so long-run ratings equalise and the
    grid is the only stable signal. Odd rounds run at a run-in circuit, even
    rounds at an unlisted one."""
    drivers = [("a", "t1"), ("b", "t1"), ("c", "t2"), ("d", "t2")]
    rresults, quali_map, trio_keys = [], {}, {}
    for season in (2010, 2011):
        for rnd in range(1, 16):
            order = drivers[rnd % 4 :] + drivers[: rnd % 4]
            rows = [_rrow_v2(d, c, i + 1, i + 1) for i, (d, c) in enumerate(order)]
            rresults.append(
                {
                    "season": str(season),
                    "round": str(rnd),
                    "raceName": "GP",
                    "date": "",
                    "circuitId": _RUNIN if rnd % 2 else "ring",
                    "results": rows,
                }
            )
            quali_map[(str(season), str(rnd))] = _q_for(season, rnd, order)
            trio_keys[(str(season), str(rnd))] = tuple(sorted(d for d, _ in order[:3]))
    return rresults, quali_map, trio_keys


def test_score_window_v2_circuit_filter_scores_only_listed_races():
    rresults, quali_map, trio_keys = _runin_history()
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2)
    every = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), params, post_quali=True
    )
    sub = backtest.score_window_v2(
        rresults,
        quali_map,
        trio_keys,
        (2011, 2011),
        params,
        post_quali=True,
        circuits=frozenset({_RUNIN}),
    )
    assert len(every) == 15
    assert len(sub) == 8  # the odd rounds


def test_circuit_grid_learning_sharpens_on_grid_holding_history():
    rresults, quali_map, trio_keys = _runin_history()
    off = dict(backtest.model_v2.DEFAULT_PARAMS_V2, cgrid_sigma0=0.0)
    on = dict(backtest.model_v2.DEFAULT_PARAMS_V2, cgrid_sigma0=0.4, cgrid_tau=0.0)
    kw = dict(post_quali=True, circuits=frozenset({_RUNIN}))
    r_off = backtest.score_window_v2(rresults, quali_map, trio_keys, (2011, 2011), off, **kw)
    r_on = backtest.score_window_v2(rresults, quali_map, trio_keys, (2011, 2011), on, **kw)
    assert sum(r["p_true"] for r in r_on) > sum(r["p_true"] for r in r_off)


def test_rungs_v2_cgrid_shape():
    names = [name for name, _ in backtest.RUNGS_V2_CGRID]
    assert names == [
        "v2 post-quali +grid [run-in circuits]",
        "v2 post-quali +circuit grid [run-in circuits]",
    ]
    assert backtest.RUNGS_V2_CGRID[0][1] == {"cgrid_sigma0": 0.0}
    assert backtest.RUNGS_V2_CGRID[1][1] is backtest.CIRCUIT_GRID
    assert backtest.CIRCUIT_GRID["cgrid_sigma0"] > 0.0


def test_evaluate_appends_cgrid_rows_and_gate():
    rresults, quali_map, trio_keys = _runin_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    res = backtest.evaluate(races, active, (2011, 2011), v2_data=(rresults, quali_map))
    names = [name for name, _ in res["ladder"]]
    assert names[-2:] == [name for name, _ in backtest.RUNGS_V2_CGRID]
    assert all(m["n"] == 8 for _, m in res["ladder"][-2:])
    assert isinstance(res["postQuali"]["circuitGridAccepted"], bool)


def test_tune_v2_cgrid_touches_only_the_cgrid_knobs():
    rresults, quali_map, trio_keys = _runin_history()
    winner = backtest.tune_v2_cgrid(
        rresults, quali_map, trio_keys, (2010, 2010), sweeps=1, verbose=False
    )
    for knob in ("cgrid_sigma0", "cgrid_tau"):
        assert winner[knob] in backtest.V2_CGRID_TUNE_GRID[knob]
    for k, v in backtest.model_v2.DEFAULT_PARAMS_V2.items():
        if k not in ("cgrid_sigma0", "cgrid_tau"):
            assert winner[k] == v


def test_main_tune_v2_cgrid_flag_prints_winner(monkeypatch, capsys):
    rresults, quali_map, trio_keys = _runin_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: (rresults, quali_map))
    rc = backtest.main(["--tune-v2-cgrid"])
    assert rc == 0
    assert "Best circuit-grid knobs" in capsys.readouterr().out
```

Also extend the existing `test_evaluate_appends_post_quali_rungs_and_gate` (its history runs only at `"ring"`, so no run-in rows are added) with:

```python
    assert res["postQuali"]["circuitGridAccepted"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_backtest.py -q`
Expected: the new tests FAIL (`TypeError: ... unexpected keyword argument 'circuits'`, `AttributeError: ... 'RUNGS_V2_CGRID'`, `KeyError: 'circuitGridAccepted'`).

- [ ] **Step 3: Implement**

3a. After `V2_GRID_TUNE_GRID`, add:

```python
# Learned per-circuit grid correction (model_v2.CircuitGridLearner). Tuned by
# --tune-v2-cgrid on the validation window; copied into DEFAULT_PARAMS_V2 only
# if the run-in-circuit gate in evaluate() accepts it.
CIRCUIT_GRID = {"cgrid_sigma0": 0.2, "cgrid_tau": 0.05}

# Per-knob grids for --tune-v2-cgrid (every other knob stays frozen).
V2_CGRID_TUNE_GRID: dict[str, list] = {
    "cgrid_sigma0": [0.0, 0.1, 0.2, 0.4],
    "cgrid_tau": [0.0, 0.02, 0.05, 0.1],
}

# Both rows score ONLY races at model_v2.CGRID_CIRCUITS (post-quali protocol):
# the correction changes nothing anywhere else, so the full window would only
# dilute the comparison. The first row is the gate's baseline.
RUNGS_V2_CGRID = [
    ("v2 post-quali +grid [run-in circuits]", {"cgrid_sigma0": 0.0}),
    ("v2 post-quali +circuit grid [run-in circuits]", CIRCUIT_GRID),
]
```

3b. `score_window_v2`: add keyword parameter `circuits: frozenset[str] | None = None` after `post_quali=False`; add to the docstring: "``circuits`` restricts *scoring* to races at those circuitIds (the filter still sees every race)." Extend the scoring condition:

```python
        if (
            key is not None
            and window[0] <= int(race["season"]) <= window[1]
            and len(snap["drivers"]) >= 3
            and (circuits is None or race.get("circuitId") in circuits)
        ):
```

and change the offsets line to:

```python
                    offs = model_v2.grid_offsets(
                        qpos, snap["disp_ratio"], params, snap["grid_adj"]
                    )
```

3c. Replace `tune_v2_grid` with a shared helper plus two thin wrappers:

```python
def _tune_post_quali(
    rresults, quali_map, trio_keys, val, knob_grid, *, circuits=None, sweeps=2, verbose=True
) -> dict:
    """Coordinate descent over ``knob_grid`` only (post-quali protocol), every
    other DEFAULT_PARAMS_V2 knob frozen; ``circuits`` restricts the scored races."""

    def j_of(params: dict) -> float:
        recs = score_window_v2(
            rresults, quali_map, trio_keys, val, params, post_quali=True, circuits=circuits
        )
        return v2_objective(recs)

    best = dict(model_v2.DEFAULT_PARAMS_V2)
    best_j = j_of(best)
    if verbose:
        print(f"start J={best_j:.4f}")
    for sweep in range(sweeps):
        for knob, grid in knob_grid.items():
            for value in grid:
                if value == best[knob]:
                    continue
                trial = dict(best, **{knob: value})
                j = j_of(trial)
                if j < best_j:
                    best_j, best = j, trial
            if verbose:
                print(f"  sweep {sweep + 1} {knob} -> {best[knob]}  (J={best_j:.4f})")
    return best


def tune_v2_grid(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict:
    """Coordinate descent over ONLY the two grid knobs (post-quali protocol),
    with the locked v2 knobs frozen."""
    return _tune_post_quali(
        rresults, quali_map, trio_keys, val, V2_GRID_TUNE_GRID, sweeps=sweeps, verbose=verbose
    )


def tune_v2_cgrid(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict:
    """Coordinate descent over ONLY the two circuit-grid knobs (post-quali
    protocol), scored on races at model_v2.CGRID_CIRCUITS — the only races the
    correction can change."""
    return _tune_post_quali(
        rresults,
        quali_map,
        trio_keys,
        val,
        V2_CGRID_TUNE_GRID,
        circuits=frozenset(model_v2.CGRID_CIRCUITS),
        sweeps=sweeps,
        verbose=verbose,
    )
```

3d. In `evaluate`, directly after the `post_quali_info = {"gridAccepted": ...}` assignment, add:

```python
        # Run-in circuit gate: the learned per-circuit grid correction ships only
        # if it beats the plain grid term on BOTH headline scores, on the races
        # at model_v2.CGRID_CIRCUITS (the only races it can change).
        runin = frozenset(model_v2.CGRID_CIRCUITS)
        cgrid_rows: dict[str, dict] = {}
        for name, overrides in RUNGS_V2_CGRID:
            params = dict(model_v2.DEFAULT_PARAMS_V2, **overrides)
            recs = score_window_v2(
                rresults,
                quali_map,
                keys,
                test,
                params,
                with_rank=True,
                post_quali=True,
                circuits=runin,
            )
            if recs:
                ladder.append((name, summarize(recs)))
                cgrid_rows[name] = ladder[-1][1]
        base_c = cgrid_rows.get(RUNGS_V2_CGRID[0][0])
        cand_c = cgrid_rows.get(RUNGS_V2_CGRID[1][0])
        post_quali_info["circuitGridAccepted"] = bool(
            base_c is not None
            and cand_c is not None
            and cand_c["logLoss"] < base_c["logLoss"]
            and cand_c["brierNew"] < base_c["brierNew"]
        )
```

3e. In `main`: add the flag after `--tune-v2-grid`:

```python
    ap.add_argument(
        "--tune-v2-cgrid",
        action="store_true",
        help="coordinate-descent the two circuit-grid knobs on the run-in circuits (validation window)",
    )
```

add the branch after the `if args.tune_v2_grid:` block:

```python
    if args.tune_v2_cgrid:
        if v2_data is None:
            print("race_results.json missing - run src/fetch/fetch_race_results.py first")
            return 1
        winner = tune_v2_cgrid(v2_data[0], v2_data[1], trio_keys_from(races), val)
        print("Best circuit-grid knobs (candidate for backtest.CIRCUIT_GRID):")
        print({k: winner[k] for k in ("cgrid_sigma0", "cgrid_tau")})
        return 0
```

and at the end of the `if res.get("postQuali") is not None:` block (after the existing post-quali print, `by` is in scope):

```python
        b_name, c_name = (name for name, _ in RUNGS_V2_CGRID)
        if b_name in by and c_name in by:
            b, c = by[b_name], by[c_name]
            print(
                f"run-in circuit gate: circuitGridAccepted="
                f"{res['postQuali']['circuitGridAccepted']} ({c['n']} races)"
                f" | logLoss {c['logLoss']:.4f} vs {b['logLoss']:.4f}"
                f" | brierNew {c['brierNew']:.4f} vs {b['brierNew']:.4f}"
            )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_backtest.py -q`
Expected: all PASS. If `test_circuit_grid_learning_sharpens_on_grid_holding_history` fails, debug the learner wiring (Task 3c) — do not weaken the test.

- [ ] **Step 5: Full suite + lint**

```bash
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
```
Expected: green. (`data/model_eval.json` is regenerated in Task 6, so don't commit a backtest run here.)

- [ ] **Step 6: Commit**

```bash
git add src/compute/backtest.py tests/test_backtest.py
git commit -m "Backtest: tune and gate the circuit grid correction on the run-in circuits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Tune, run the gate, decide (checkpoint with the user)

**Files:**
- Modify: `src/compute/backtest.py` (`CIRCUIT_GRID`, maybe `V2_CGRID_TUNE_GRID`)
- Modify (only if accepted): `src/compute/model_v2.py` (`DEFAULT_PARAMS_V2` cgrid knobs + comment)
- Modify: `data/model_eval.json`, and if accepted `data/podigami.json`

- [ ] **Step 1: Tune on 2010–2018** (~1 min)

Run: `PYTHONPATH=src python src/compute/backtest.py --tune-v2-cgrid`
Record the start J, the final J and the winner.

- If the winner has `cgrid_sigma0 == 0.0`: the validation window itself rejects the feature. Skip to Step 4 (rejected), reporting the J values.
- If a winner sits on the top edge (`cgrid_sigma0 == 0.4` or `cgrid_tau == 0.1`): widen that knob's list once in `V2_CGRID_TUNE_GRID` (append `0.8` for sigma0, `0.2` for tau), re-run, and note the widening in the commit message.

- [ ] **Step 2: Lock the candidate** — set `CIRCUIT_GRID` in `backtest.py` to the winner, e.g. `CIRCUIT_GRID = {"cgrid_sigma0": <winner>, "cgrid_tau": <winner>}` with a comment line `# --tune-v2-cgrid 2026-10-12: J <start> -> <final> on the run-in circuits, 2010-2018.`

- [ ] **Step 3: Run the gate on the frozen 2019+ window** (~1 min)

Run: `PYTHONPATH=src python src/compute/backtest.py`
Read the `run-in circuit gate:` line.

- [ ] **Step 4a: If `circuitGridAccepted=True`**

Copy the winner into `DEFAULT_PARAMS_V2` and replace the knobs' comment with the evidence:

```python
    # Learned per-circuit grid correction (CircuitGridLearner, CGRID_CIRCUITS),
    # added 2026-10-12. Tuned by backtest.py --tune-v2-cgrid on the run-in
    # circuits, 2010-2018 (J <start> -> <final>); accepted by the run-in gate on
    # the frozen 2019+ window (<n> races: logLoss <cand> vs <base>, brierNew
    # <cand> vs <base>). sigma0 0 switches it off exactly.
    "cgrid_sigma0": <winner>,
    "cgrid_tau": <winner>,
```

Then regenerate and verify:

```bash
PYTHONPATH=src python src/compute/backtest.py
python src/compute/compute_podigami.py
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python src/build_site.py
```

Spot-check the live effect: print `hf.grid_scale_adj(c)` for the six circuits from a filter over the committed data (a scratch script in the session scratchpad, modelled on `compute_podigami._v2_predict`'s loop) and record the values for the PR description.

Commit:

```bash
git add src/compute/backtest.py src/compute/model_v2.py data/model_eval.json data/podigami.json
git commit -m "Ship the learned circuit grid correction (run-in gate accepted)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4b: If rejected**

Keep `DEFAULT_PARAMS_V2` at 0.0/0.0 and replace the knobs' comment with the rejection evidence (same format as the `con_adapt_gain` comment: tuned values, J, test logLoss/brierNew candidate vs baseline, "shipped dormant"). Commit `src/compute/backtest.py`, `src/compute/model_v2.py`, `data/model_eval.json`.

**STOP and report the numbers to the user.** Ask (AskUserQuestion) whether to keep it as a dormant rung (continue to Task 7 with a "dormant" release note) or drop the branch.

---

### Task 7: Docs, PR, merge, promote

**Files:**
- Modify: `RELEASE_NOTES.md`, `README.md` (model section, ~lines 76 and 98), `CLAUDE.md` (Prediction model paragraph)

- [ ] **Step 1: Release notes** — add under a `## 2026-10-12` heading at the top of `RELEASE_NOTES.md`:
  - Accepted → `### Improvements` — one line in plain words, e.g. "**The post-qualifying prediction now learns how much the grid matters at each remaining 2026 circuit** (COTA, Mexico City, Interlagos, Las Vegas, Losail, Yas Marina) from how past races there departed from the ratings' expectations, replacing an era-skewed measure; it beat the previous grid term on both headline scores at those circuits since 2019 (#PR)".
  - Dormant → `### Improvements` — "Tested a learned per-circuit grid effect for the remaining 2026 circuits; it did not beat the current grid term on the 2019+ hold-out, so it ships switched off (#PR)".

- [ ] **Step 2: README** — accepted only: in the **Grid** bullet (~line 76) add one sentence: "At the circuits still to come in 2026, how strongly the grid holds is learned per circuit from past races there, measured against what the ratings expected." Update the ablation sentence (~line 98) to mention the run-in gate. Dormant: add it to the ablation sentence as shipping dormant, like the adaptive car.

- [ ] **Step 3: CLAUDE.md** — in **Prediction model**, add one sentence naming `CircuitGridLearner` / `CGRID_CIRCUITS`, `--tune-v2-cgrid`, the run-in gate, and its verdict.

- [ ] **Step 4: Verify before claiming done** (superpowers:verification-before-completion)

```bash
python -m ruff check . && python -m ruff format --check .
python -m pytest -q
PYTHONPATH=src python -m datalib.validate
python src/build_site.py
```

- [ ] **Step 5: Commit, push, PR into `develop`** (template: Summary / Changes / Testing / Checklist; body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`), include the tuning + gate numbers and the six learned values.

```bash
git add RELEASE_NOTES.md README.md CLAUDE.md
git commit -m "Docs: per-circuit learned grid effect

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin feat/circuit-grid-learning
gh pr create --base develop --title "Learn the grid effect per circuit for the 2026 run-in" --body-file <scratchpad>/pr_body.md
gh pr checks --watch
```

- [ ] **Step 6: Merge, then promote** — `gh pr merge --squash --delete-branch`; then `gh pr create --base main --head develop`. The promotion **will conflict on `data/podigami.json`** (and possibly `data/model_eval.json`): resolve by taking `main`'s inputs and regenerating (`python src/compute/compute_podigami.py`, `PYTHONPATH=src python src/compute/backtest.py`), then `datalib.validate` + `pytest -q` — never pick a side. Merge once the 9 checks pass, confirm `deploy.yml` succeeds, and delete the local branch. Target: live before the United States GP qualifying (2026-10-24).
