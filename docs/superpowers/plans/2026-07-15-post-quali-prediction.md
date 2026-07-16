# Post-Qualifying Grid-Aware Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved spec `docs/superpowers/specs/2026-07-15-post-quali-prediction-design.md`: after the next race's qualifying session, automatically recompute and publish a grid-aware prediction (headline %, re-ranked candidates, updated driver form) grounded in a tuned, circuit-modulated grid-advantage term plus the v2 rating engine's qualifying channel — backtest-gated, deterministic, with no new silent-stall vectors.

**Architecture:** No new pipeline stages. `fetch_schedule` adds quali session times to `schedule.json`; `model_v2` gains two pure helpers (`disp_ratio`, `grid_offsets`) and a `snapshot_after_quali` step mode; `compute_podigami` emits a `postQuali` block when `qualifying.json` covers the next race; `check_update_due` gains a second no-network trigger; `backtest` gains a post-quali protocol, two ladder rungs, an acceptance gate and a `--tune-v2-grid` tuner; `build_podigami_html` branches the hero/candidates/form on `postQuali`. **Zero `update.yml` changes.**

**Tech stack:** Pure Python 3.11+ stdlib, pydantic v2 (datalib), pytest, ruff. `gh` CLI for shipping.

**Hard constraints (from CLAUDE.md + memory — every task must respect these):**

1. **Every commit green**: `python -m ruff check .`, `python -m ruff format --check .`, `python -m pytest -q`, `PYTHONPATH=src python -m datalib.validate` all pass at every commit boundary.
2. **Byte-identical fixed point**: adding schema fields (canonical dump emits `null` for absent optionals) and regenerating the affected `data/*.json` must land in the **same commit**, or the round-trip test in `tests/test_datalib.py` breaks (the #178 stall class).
3. **No test may depend on transient live-data state** — dist-level assertions about `postQuali` must be conditional on the committed data (the update job runs pytest on live `main` data where `postQuali` toggles between null and a block).
4. Backtest sanity checks are **prints, never asserts**.
5. Deadline: promoted to `main` before **Saturday 2026-07-18** (Belgian GP quali is the first live firing).

**Interface contracts locked here** (all tasks must match):

```python
# model_v2.py — additions
DEFAULT_PARAMS_V2 += {"w_grid": <tuned>, "grid_circuit_beta": <tuned>}  # provisional 0.1 / 0.5 until Task 9

class CircuitStats:
    def disp_ratio(self, circuit_id: str) -> float   # shrunk, clamped [0.5, 2.2]; 1.0 neutral
    def temp(self, circuit_id: str, eta: float) -> float  # == disp_ratio(circuit_id) ** eta

def grid_offsets(quali_pos: dict[str, int], disp_ratio: float, params: dict) -> dict[str, float]
    # additive log-worth offsets: w_grid * disp_ratio**(-grid_circuit_beta) * (mean ln g - ln g)

class HistoryFilter:
    def step(self, race, quali=None, *, snapshot_after_quali: bool = False) -> dict
        # snapshot dict gains "disp_ratio": float; quali observed BEFORE the snapshot
        # when the flag is True (and never observed twice)

# compute_podigami.py
def _next_race(schedule, as_of_season, as_of_round) -> dict | None    # replaces _next_circuit
def _title_from_id(driver_id: str) -> str                             # "zed_zephyr" -> "Zed Zephyr"
def _post_quali_block(v2, qualifying, seen, nm, season_pod, recent_pod,
                      cid_name, con_strength, using_constructors) -> dict | None
# _v2_next_race_model return dict gains: "hf", "next_race", "next_season"
# payload gains: "postQuali": <block dict> | None
# post-quali seed = SEED + int(season) * 100 + int(round)   (backtest convention)

# check_update_due.py
QUALI_BUFFER = timedelta(minutes=90)
def _next_race_entry(schedule: dict, have: tuple[int, int]) -> dict | None
def is_post_quali_update_due(schedule, asof, post_quali, now) -> bool
# main(): due = race_due or quali_due (single output, unchanged workflow contract)

# backtest.py
RUNGS_V2_POSTQUALI = [("v2 post-quali (ratings)", {"w_grid": 0.0}), ("v2 post-quali +grid", {})]
V2_GRID_TUNE_GRID = {"w_grid": [0.0, 0.05, 0.1, 0.2, 0.4], "grid_circuit_beta": [0.0, 0.5, 1.0]}
def score_window_v2(..., post_quali: bool = False)
def tune_v2_grid(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict
# evaluate() returns res["postQuali"] = {"gridAccepted": bool} | None  (in-memory only —
# NOT persisted to model_eval.json; the two rungs land in the ladder and the FAQ derives from them)

# datalib schemas
ScheduleRace  += qualifyingDate: str | None = None; qualifyingTime: str | None = None
DriverStrength += gridPosition: int | None = None
class PodigamiPostQuali(_Base): season, round, raceName: str; chanceNextRaceNew: float;
                                candidates: list[PodigamiCandidate]; driverForm: list[DriverStrength]
Podigami += postQuali: PodigamiPostQuali | None = None      # after driverForm
PodigamiParamsV2 += w_grid: float; grid_circuit_beta: float  # REQUIRED, after t_wild  (Task 2)
ModelParamsV2    += w_grid: float; grid_circuit_beta: float  # REQUIRED, after t_wild  (Task 9 ONLY)

# build_podigami_html.py
def render_hero(top, chance, meta, acc_badge="", pre_chance: float | None = None) -> str
def render_candidates(cands, meta, form_html="", grid_aware: bool = False) -> str
# render_next_race gains a .nr-quali line; render_faq gains a post-quali item (v2 only)
```

**postQuali JSON contract** (spec §3):

```jsonc
"postQuali": {
  "season": "2026", "round": "10", "raceName": "Belgian Grand Prix",
  "chanceNextRaceNew": 71.3,
  "candidates": [ /* PodigamiCandidate shape; perDriver entries carry "gridPosition" */ ],
  "driverForm": [ /* DriverStrength shape, post-quali weights, gridPosition set */ ]
}
```

---

## Task 1: Qualifying session times in the schedule

The guard and the next-race box need to know when qualifying starts. Optional schema fields + fetcher passthrough + a refetched `schedule.json` — all in ONE commit (constraint 2: the canonical dump of the new optionals emits `null`, so the committed file must be regenerated in the same commit the schema changes).

**Files:**
- Modify: `src/datalib/schemas.py` (ScheduleRace)
- Modify: `src/fetch/fetch_schedule.py` (build_race)
- Create: `tests/test_fetch_schedule.py`
- Regenerate: `data/schedule.json` (network fetch)

**Step 1.1: Write the failing tests** — create `tests/test_fetch_schedule.py`:

```python
"""Tests for the schedule fetcher's pure race transform (no network)."""

from fetch import fetch_schedule as fs

RACE_API = {
    "round": "10",
    "raceName": "Belgian Grand Prix",
    "date": "2026-07-19",
    "time": "13:00:00Z",
    "url": "https://en.wikipedia.org/wiki/2026_Belgian_Grand_Prix",
    "Circuit": {
        "circuitId": "spa",
        "circuitName": "Circuit de Spa-Francorchamps",
        "Location": {"lat": "50.4372", "long": "5.97139", "locality": "Spa", "country": "Belgium"},
    },
    "Qualifying": {"date": "2026-07-18", "time": "14:00:00Z"},
}


def test_build_race_carries_qualifying_session():
    entry = fs.build_race(RACE_API, [])
    assert entry["qualifyingDate"] == "2026-07-18"
    assert entry["qualifyingTime"] == "14:00:00Z"


def test_build_race_without_qualifying_yields_none():
    race = {k: v for k, v in RACE_API.items() if k != "Qualifying"}
    entry = fs.build_race(race, [])
    assert entry["qualifyingDate"] is None
    assert entry["qualifyingTime"] is None


def test_build_race_qualifying_date_without_time():
    race = dict(RACE_API, Qualifying={"date": "2026-07-18"})
    entry = fs.build_race(race, [])
    assert entry["qualifyingDate"] == "2026-07-18"
    assert entry["qualifyingTime"] is None


def test_schedule_race_schema_accepts_both_shapes():
    from datalib import ScheduleRace

    legacy = {
        "round": "1",
        "raceName": "GP",
        "date": "2026-03-08",
        "time": "04:00:00Z",
        "circuitId": "x",
        "circuitName": "X",
        "locality": "L",
        "country": "C",
        "lat": "0",
        "long": "0",
        "url": "",
    }
    assert ScheduleRace.model_validate(legacy).qualifyingDate is None
    withq = dict(legacy, qualifyingDate="2026-03-07", qualifyingTime="07:00:00Z")
    assert ScheduleRace.model_validate(withq).qualifyingTime == "07:00:00Z"
```

**Step 1.2: Verify they fail** — `python -m pytest tests/test_fetch_schedule.py -q` → 3 failures (KeyError `qualifyingDate`), 1 pass or fail depending on schema. Expected: FAIL.

**Step 1.3: Implement.** In `src/datalib/schemas.py`, `ScheduleRace`, insert after `time: str`:

```python
    # Qualifying session start (from the API's Qualifying block); None for seasons
    # fetched before this field existed and for races the API hasn't scheduled yet.
    qualifyingDate: str | None = None
    qualifyingTime: str | None = None
```

In `src/fetch/fetch_schedule.py` `build_race`, insert after `"time": race.get("time", ""),`:

```python
        "qualifyingDate": (race.get("Qualifying") or {}).get("date"),
        "qualifyingTime": (race.get("Qualifying") or {}).get("time"),
```

Also update the module docstring's schedule.json shape line to include the two fields.

**Step 1.4: Refetch the schedule** (network): `python src/fetch/fetch_schedule.py`. Inspect `git diff data/schedule.json`: every race gains `qualifyingDate`/`qualifyingTime` (2026 races should all have them — the API publishes session times); confirm the file was written by `save_schedule` (canonical form, no whole-file reformat per the external-formatter memory). Note the Belgian GP (round 10) quali time — it drives the Saturday rollout check in Task 16.

**Step 1.5: Full verify** — `python -m pytest -q` (round-trip + integrity green because schema + data changed together), `python -m ruff check .`, `python -m ruff format --check .`, `PYTHONPATH=src python -m datalib.validate`.

**Step 1.6: Commit**

```
git add src/datalib/schemas.py src/fetch/fetch_schedule.py tests/test_fetch_schedule.py data/schedule.json
git commit -m "feat: qualifying session times in schedule.json"
```

---

## Task 2: Grid knobs + podigami-side schemas (+ podigami.json regen, same commit)

Add the two provisional knobs to `DEFAULT_PARAMS_V2` and everything `podigami.json` needs schema-side. Because `compute_podigami` spreads all v2 params into `params`, `PodigamiParamsV2` must gain the two keys as REQUIRED — and the committed `podigami.json` must be regenerated in the same commit. **Do NOT touch `ModelParamsV2` here** (model_eval.json is only rewritten by `backtest.main()`, deferred to Task 9).

**Files:**
- Modify: `src/compute/model_v2.py` (DEFAULT_PARAMS_V2)
- Modify: `src/datalib/schemas.py` (PodigamiParamsV2, DriverStrength, PodigamiPostQuali, Podigami)
- Modify: `src/datalib/__init__.py` (export PodigamiPostQuali)
- Modify: `tests/test_model_v2.py` (locked-knobs test)
- Modify: `tests/test_datalib.py` (_GRID_KNOBS, union test, postQuali test)
- Regenerate: `data/podigami.json` (offline)

**Step 2.1: Failing tests.** In `tests/test_model_v2.py`, add `"w_grid"` and `"grid_circuit_beta"` to the set in `test_default_params_have_exactly_the_locked_knobs`.

In `tests/test_datalib.py`, directly under the `_V2_KNOBS` dict (which stays 18 keys — it is reused by the ModelParamsV2 test that must NOT change until Task 9), add:

```python
# The two grid knobs added by the post-quali feature. Kept separate from
# _V2_KNOBS: PodigamiParamsV2 requires them from Task 2, ModelParamsV2 only
# from the tuning task (model_eval.json is regenerated there).
_GRID_KNOBS = {"w_grid": 0.1, "grid_circuit_beta": 0.5}
```

In `test_podigami_params_union_accepts_v1_and_v2`, change the v2 dict to include `**_GRID_KNOBS` (after `**_V2_KNOBS`).

Add new tests at the end of the v2-params section:

```python
def test_podigami_post_quali_block_and_null():
    from datalib import DriverStrength, PodigamiPostQuali

    ds = {
        "driverId": "verstappen",
        "name": "Max Verstappen",
        "weight": 2.5,
        "seasonPodiums": 5,
        "recentPodiums": 4,
        "constructorId": "red_bull",
        "finishProb": 0.96,
        "uncertainty": 0.2,
        "gridPosition": 3,
    }
    assert DriverStrength.model_validate(ds).gridPosition == 3
    block = {
        "season": "2026",
        "round": "10",
        "raceName": "Belgian Grand Prix",
        "chanceNextRaceNew": 71.3,
        "candidates": [
            {"driverIds": ["a", "b", "c"], "names": ["A", "B", "C"], "prob": 3.2,
             "perDriver": [dict(ds, driverId=d, gridPosition=i + 1) for i, d in enumerate("abc")]}
        ],
        "driverForm": [ds],
    }
    assert isinstance(PodigamiPostQuali.model_validate(block), PodigamiPostQuali)
    # committed file must expose the key (null or block) after this task's regen
    pj = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    assert "postQuali" in pj
```

**Step 2.2: Verify fail** — `python -m pytest tests/test_model_v2.py::test_default_params_have_exactly_the_locked_knobs tests/test_datalib.py -q` → FAIL (missing knobs / import error).

**Step 2.3: Implement.** `src/compute/model_v2.py` — append to `DEFAULT_PARAMS_V2` (after `"t_wild"`):

```python
    # Post-quali grid term (grid_offsets): PROVISIONAL until backtest.py
    # --tune-v2-grid locks them on 2010-2018 (see the tuning task).
    "w_grid": 0.1,  # weight of the causal grid-position term
    "grid_circuit_beta": 0.5,  # circuit modulation: disp_ratio ** (-beta)
```

`src/datalib/schemas.py`:
- `PodigamiParamsV2`: after `t_wild: float` add `w_grid: float` and `grid_circuit_beta: float`.
- `DriverStrength`: after `uncertainty: float | None = None` add:

```python
    # Post-quali only: the driver's qualifying classification position.
    gridPosition: int | None = None
```

- After `SeasonDebut`, add:

```python
class PodigamiPostQuali(_Base):
    """Grid-aware prediction recomputed after the next race's qualifying.

    Present only between a qualifying session and its race; ``null`` otherwise.
    ``candidates``/``driverForm`` reuse the pre-quali shapes; ``perDriver``
    entries additionally carry ``gridPosition``.
    """

    season: str
    round: str
    raceName: str
    chanceNextRaceNew: float
    candidates: list[PodigamiCandidate]
    driverForm: list[DriverStrength]
```

- `Podigami`: after `driverForm: list[DriverStrength]` add `postQuali: PodigamiPostQuali | None = None`.

`src/datalib/__init__.py`: add `PodigamiPostQuali,` to the `.schemas` import block (after `PodigamiParamsV2`) and to `__all__` (after `"PodigamiCandidate"`).

**Step 2.4: Regenerate** — `python src/compute/compute_podigami.py`. Diff check: `params` gains the two knobs, every DriverStrength gains `"gridPosition": null`, payload gains `"postQuali": null`; expect the usual standings-churn noise. Verify compactness conventions unchanged (podigami.json is NOT a compact dataset; just confirm the diff is key-additions, not a reformat).

**Step 2.5: Full verify** — all four gates (pytest includes the byte-identical round-trip on the regenerated file).

**Step 2.6: Commit**

```
git add src/compute/model_v2.py src/datalib/schemas.py src/datalib/__init__.py tests/test_model_v2.py tests/test_datalib.py data/podigami.json
git commit -m "feat: grid knobs + postQuali schema contract (provisional values)"
```

---

## Task 3: `CircuitStats.disp_ratio()` refactor

Expose the shrunk displacement ratio directly; `temp` becomes `disp_ratio ** eta`. Pure refactor — existing temp behavior byte-identical.

**Files:**
- Modify: `src/compute/model_v2.py`
- Modify: `tests/test_model_v2.py`

**Step 3.1: Failing tests** (add to the CircuitStats section of `tests/test_model_v2.py`; reuse its existing helpers/imports):

```python
def test_disp_ratio_neutral_for_unknown_circuit():
    cs = model_v2.CircuitStats()
    assert cs.disp_ratio("nowhere") == 1.0


def test_temp_equals_disp_ratio_to_eta():
    cs = model_v2.CircuitStats()
    # calm circuit: half the displacement of the global average
    for _ in range(10):
        cs.observe_race("calm", starters=20, dnfs=2, mean_disp=1.0)
        cs.observe_race("wild", starters=20, dnfs=2, mean_disp=3.0)
    r = cs.disp_ratio("calm")
    assert 0.5 <= r < 1.0  # below the global mean, inside the clamp
    assert cs.temp("calm", 0.7) == pytest.approx(r**0.7)
    assert cs.temp("calm", 0.0) == pytest.approx(1.0)
    assert cs.disp_ratio("wild") > 1.0
```

**Step 3.2: Verify fail** — `python -m pytest tests/test_model_v2.py -q -k disp_ratio` → AttributeError.

**Step 3.3: Implement.** In `CircuitStats`, replace `temp` with:

```python
    def disp_ratio(self, circuit_id: str) -> float:
        """Shrunk grid->finish displacement ratio vs the global mean.

        1.0 = neutral/unknown; clamped to [0.5, 2.2]. Low = processional
        (finish follows the grid), high = high-churn.
        """
        rec = self._c.get(circuit_id)
        if not rec or rec[4] <= 0.0 or self._g[4] <= 0.0:
            return 1.0
        g_disp = self._g[3] / self._g[4]
        if g_disp <= 0.0:
            return 1.0
        w = rec[4] / (rec[4] + _CIRCUIT_SHRINK_N)
        ratio = 1.0 + w * (rec[3] / rec[4] / g_disp - 1.0)
        return min(2.2, max(0.5, ratio))

    def temp(self, circuit_id: str, eta: float) -> float:
        """Softmax temperature multiplier: >1 at high-churn circuits."""
        return self.disp_ratio(circuit_id) ** eta
```

**Step 3.4: Verify** — `python -m pytest tests/test_model_v2.py tests/test_backtest.py tests/test_compute_podigami.py -q` (all pre-existing temp-dependent numbers unchanged), then the four gates.

**Step 3.5: Commit** — `git commit -am "refactor: expose CircuitStats.disp_ratio (temp = ratio**eta)"`

---

## Task 4: `grid_offsets()` pure helper

**Files:**
- Modify: `src/compute/model_v2.py`
- Modify: `tests/test_model_v2.py`

**Step 4.1: Failing tests:**

```python
# --- grid_offsets ---------------------------------------------------------------


def _gparams(w=0.2, beta=0.5):
    return dict(DEFAULT_PARAMS_V2, w_grid=w, grid_circuit_beta=beta)


def test_grid_offsets_centered_and_monotone():
    qpos = {f"d{g}": g for g in range(1, 11)}
    offs = model_v2.grid_offsets(qpos, 1.0, _gparams())
    assert sum(offs.values()) == pytest.approx(0.0, abs=1e-12)  # zero-sum across the field
    vals = [offs[f"d{g}"] for g in range(1, 11)]
    assert vals == sorted(vals, reverse=True)  # pole gets the biggest boost
    # log decay: the P1-P2 gap dwarfs the P9-P10 gap
    assert (vals[0] - vals[1]) > 3 * (vals[8] - vals[9])


def test_grid_offsets_circuit_modulation_direction():
    qpos = {"a": 1, "b": 2, "c": 3}
    p = _gparams(beta=1.0)
    monaco = model_v2.grid_offsets(qpos, 0.5, p)   # processional -> amplified
    neutral = model_v2.grid_offsets(qpos, 1.0, p)
    chaotic = model_v2.grid_offsets(qpos, 2.0, p)  # high churn -> dampened
    assert monaco["a"] > neutral["a"] > chaotic["a"]
    # beta=0 switches the modulation off entirely
    flat = _gparams(beta=0.0)
    assert model_v2.grid_offsets(qpos, 0.5, flat) == model_v2.grid_offsets(qpos, 2.0, flat)


def test_grid_offsets_zero_weight_and_empty():
    qpos = {"a": 1, "b": 2, "c": 3}
    assert model_v2.grid_offsets(qpos, 1.0, _gparams(w=0.0)) == {"a": 0.0, "b": 0.0, "c": 0.0}
    assert model_v2.grid_offsets({}, 1.0, _gparams()) == {}
```

**Step 4.2: Verify fail** — `python -m pytest tests/test_model_v2.py -q -k grid_offsets` → AttributeError.

**Step 4.3: Implement.** In `src/compute/model_v2.py`, after `classify_status` (module level), add — and add `"grid_offsets"` to `__all__`:

```python
def grid_offsets(quali_pos: dict[str, int], disp_ratio: float, params: dict) -> dict[str, float]:
    """Causal track-position term: additive log-worth offsets from grid slots.

    ``x(g) = -(ln g - mean ln g)`` — a centered power-law decay in grid
    position — scaled by ``w_grid`` and amplified at processional circuits
    (low displacement ratio) via ``disp_ratio ** (-grid_circuit_beta)``.
    Zero-sum across the field, so it shifts relative order, not overall level.
    """
    w = params["w_grid"]
    if w <= 0.0 or not quali_pos:
        return dict.fromkeys(quali_pos, 0.0)
    logs = {d: math.log(g) for d, g in quali_pos.items()}
    mean_log = sum(logs.values()) / len(logs)
    scale = w * (max(disp_ratio, 1e-6) ** (-params["grid_circuit_beta"]))
    return {d: scale * (mean_log - lg) for d, lg in logs.items()}
```

**Step 4.4: Verify + four gates. Step 4.5: Commit** — `git commit -am "feat: grid_offsets — circuit-modulated grid-advantage term"`

---

## Task 5: `HistoryFilter.step(snapshot_after_quali=...)`

The post-quali backtest protocol needs snapshots taken AFTER the quali observation (legitimate conditioning — quali precedes the race), and every snapshot now carries the circuit's `disp_ratio` so offsets can be applied downstream. Default `False` keeps the current pre-quali protocol byte-identical.

**Files:**
- Modify: `src/compute/model_v2.py`
- Modify: `tests/test_model_v2.py`

**Step 5.1: Failing tests** (reuse the file's existing `_rrace`/`_rrow`/`_two_car_race` helpers; add a quali builder):

```python
def _quali(season, rnd, order):
    return {
        "season": str(season),
        "round": str(rnd),
        "results": [
            {"driverId": d, "constructorId": "car_" + d, "position": i + 1}
            for i, d in enumerate(order)
        ],
    }


def test_snapshot_after_quali_sees_the_quali_shock():
    # 5 races of champ>underdog; round 6 quali flips the order.
    pre, post = (model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2)) for _ in range(2))
    for rnd in range(1, 6):
        race = _two_car_race(2020, rnd, "champ", "underdog")
        pre.step(race, _quali(2020, rnd, ["champ", "underdog"]))
        post.step(race, _quali(2020, rnd, ["champ", "underdog"]))
    race6 = _two_car_race(2020, 6, "underdog", "champ")
    q6 = _quali(2020, 6, ["underdog", "champ"])
    snap_pre = pre.step(race6, q6)
    snap_post = post.step(race6, q6, snapshot_after_quali=True)
    # pre-quali snapshot can't know about the shock; post-quali one narrows the gap
    gap_pre = snap_pre["drivers"]["champ"][0] - snap_pre["drivers"]["underdog"][0]
    gap_post = snap_post["drivers"]["champ"][0] - snap_post["drivers"]["underdog"][0]
    assert gap_post < gap_pre
    # the quali is observed exactly once either way: end states must agree
    assert pre.engine.driver("champ").mu == pytest.approx(post.engine.driver("champ").mu)
    assert pre.engine.driver("underdog").var == pytest.approx(post.engine.driver("underdog").var)


def test_snapshot_carries_disp_ratio():
    # A single circuit's ratio equals the global mean by construction, so any
    # one-circuit history snapshots 1.0 (neutral); Task 3's tests cover the
    # non-neutral value math. Here we only pin the key's presence + source.
    hf = model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2))
    snap = hf.step(_two_car_race(2020, 1, "a", "b"), None)
    assert snap["disp_ratio"] == 1.0  # first visit: neutral
    snap2 = hf.step(_two_car_race(2020, 2, "a", "b"), None)
    assert snap2["disp_ratio"] == 1.0
```

(Note: `_two_car_race` builds its race via `_rrace` — confirm the helper's circuit id if a circuit-specific assertion is added.)

**Step 5.2: Verify fail** — `python -m pytest tests/test_model_v2.py -q -k "snapshot_after or disp_ratio"`.

**Step 5.3: Implement.** In `HistoryFilter`, extract the quali observation into a private method and re-order `step`:

```python
    def _observe_quali(self, quali: dict | None) -> None:
        p = self.params
        if quali is None or p["w_qual"] <= 0.0:
            return
        qentries: list[tuple[str, str]] = []
        qseen: set[str] = set()
        for q in sorted(quali["results"], key=lambda q: q["position"]):
            if q["driverId"] not in qseen:
                qseen.add(q["driverId"])
                qentries.append((q["driverId"], q["constructorId"]))
        self.engine.observe_order(qentries, depth=int(p["depth_qual"]), weight=p["w_qual"])
```

`step` gains the keyword `*, snapshot_after_quali: bool = False`. Flow becomes:

1. dynamics (unchanged)
2. rows filtering (unchanged)
3. `if snapshot_after_quali: self._observe_quali(quali)`
4. snapshot (unchanged computation) — dict gains `"disp_ratio": self.circuits.disp_ratio(circuit)`
5. `if not snapshot_after_quali: self._observe_quali(quali)` (replaces the old inline channel-1 block)
6. channels 2/3 + reliability/circuit (unchanged)

Update the class docstring: the snapshot is race-morning knowledge by default; with `snapshot_after_quali=True` it is post-quali-Saturday knowledge (the quali channel fires before the snapshot instead of after, never twice).

**Step 5.4: Verify** — full `python -m pytest -q` (existing snapshot tests must be untouched; the snapshot dict is only extended). Four gates.

**Step 5.5: Commit** — `git commit -am "feat: post-quali snapshot mode + disp_ratio in HistoryFilter.step"`

---

## Task 6: `compute_podigami` emits the `postQuali` block

**Files:**
- Modify: `src/compute/compute_podigami.py`
- Modify: `tests/test_compute_podigami.py`
- Possibly regenerate: `data/podigami.json` (only if the committed inputs already cover a next-round quali — check in Step 6.5)

**Step 6.1: Failing tests** (append to `tests/test_compute_podigami.py`; reuse `scenario_v2`, `rr_from`):

```python
# --- postQuali block --------------------------------------------------------------


def q_entry(season, rnd, order, cid_map=None):
    """A qualifying.json entry: drivers in classification order."""
    return {
        "season": str(season),
        "round": str(rnd),
        "results": [
            {"driverId": d, "constructorId": (cid_map or {}).get(d, "car_" + d), "position": i + 1}
            for i, d in enumerate(order)
        ],
    }


SCHED_R6 = {
    "season": "2025",
    "totalRounds": 6,
    "races": [
        {"round": "5", "circuitId": "testring", "raceName": "Test GP"},
        {"round": "6", "circuitId": "monaco", "raceName": "Monaco GP"},
    ],
}


@pytest.fixture
def scenario_post_quali(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    cid = con["driverConstructor"]
    quali = [q_entry(2025, 6, ["eli", "alf", "bob", "cas", "dan"], cid)]
    return podiums, combos, grid, con, rres, quali


def test_post_quali_null_without_next_round_quali(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    res = cp.compute(
        podiums, combos, grid, constructor_data=con, race_results=rres, schedule=SCHED_R6
    )
    assert res["postQuali"] is None
    # also null when there's no schedule at all
    res2 = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert res2["postQuali"] is None


def test_post_quali_block_present_and_shaped(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    res = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    pq = res["postQuali"]
    assert pq is not None
    assert (pq["season"], pq["round"], pq["raceName"]) == ("2025", "6", "Monaco GP")
    assert 0.0 <= pq["chanceNextRaceNew"] <= 100.0
    assert pq["candidates"] and all(
        p["gridPosition"] >= 1 for c in pq["candidates"] for p in c["perDriver"]
    )
    form = {d["driverId"]: d for d in pq["driverForm"]}
    assert set(form) == {"eli", "alf", "bob", "cas", "dan"}  # exactly the quali entrants
    assert form["eli"]["gridPosition"] == 1
    probs = [c["prob"] for c in pq["candidates"]]
    assert probs == sorted(probs, reverse=True)


def test_post_quali_leaves_top_level_untouched(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    base = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=[], schedule=SCHED_R6,
    )
    withq = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    for k in ("chanceNextRaceNew", "candidates", "driverForm", "asOf"):
        assert base[k] == withq[k]


def test_post_quali_deterministic(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    kw = dict(constructor_data=con, race_results=rres, qualifying=quali, schedule=SCHED_R6)
    assert cp.compute(podiums, combos, grid, **kw) == cp.compute(podiums, combos, grid, **kw)


def test_post_quali_pole_shock_lifts_underdog(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    res = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    pre = {d["driverId"]: d["weight"] for d in res["driverForm"]}
    post = {d["driverId"]: d["weight"] for d in res["postQuali"]["driverForm"]}
    # eli (never-podiumed rookie) stuck pole: info + grid term must lift the weight
    assert post["eli"] > pre["eli"]


def test_post_quali_substitute_driver_gets_title_cased_name(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    cid = dict(con["driverConstructor"], zed_zephyr="teamC")
    quali = [q_entry(2025, 6, ["alf", "bob", "cas", "zed_zephyr"], cid)]
    res = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    form = {d["driverId"]: d for d in res["postQuali"]["driverForm"]}
    assert form["zed_zephyr"]["name"] == "Zed Zephyr"
    assert form["zed_zephyr"]["gridPosition"] == 4


def test_post_quali_needs_three_entrants(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    quali = [q_entry(2025, 6, ["alf", "bob"], con["driverConstructor"])]
    res = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    assert res["postQuali"] is None


def test_post_quali_payload_satisfies_schema(scenario_post_quali):
    from datalib import REGISTRY

    podiums, combos, grid, con, rres, quali = scenario_post_quali
    res = cp.compute(
        podiums, combos, grid, constructor_data=con,
        race_results=rres, qualifying=quali, schedule=SCHED_R6,
    )
    REGISTRY["podigami.json"].validate_python(res)  # must not raise
```

Note `SCHED_R6` races lack most ScheduleRace fields — that's fine for `compute` (plain dicts, only `round`/`circuitId`/`raceName` read), matching the existing `test_v2_uses_next_circuit_from_schedule` style.

**Step 6.2: Verify fail** — `python -m pytest tests/test_compute_podigami.py -q -k post_quali` → KeyError `postQuali`.

**Step 6.3: Implement** in `src/compute/compute_podigami.py`:

(a) Replace `_next_circuit` with:

```python
def _next_race(schedule: dict | None, as_of_season: int, as_of_round: int) -> dict | None:
    """The first scheduled race after ``asOf``, or None if unknown."""
    if not schedule:
        return None
    races = schedule.get("races") or []
    sched_season = int(schedule.get("season", 0))
    if sched_season == as_of_season:
        upcoming = [r for r in races if int(r["round"]) > as_of_round]
    elif sched_season > as_of_season:
        upcoming = list(races)
    else:
        return None
    if not upcoming:
        return None
    return min(upcoming, key=lambda r: int(r["round"]))
```

(b) In `_v2_next_race_model`: `next_race = _next_race(schedule, last_season, last_round)`; `circuit = next_race.get("circuitId") if next_race else None` (dynamics condition `if circuit is not None and sched_season > last_season:` unchanged). Return dict gains `"hf": hf, "next_race": next_race, "next_season": sched_season` (extend the docstring's Returns line).

(c) Module-level helpers:

```python
def _title_from_id(driver_id: str) -> str:
    """Display-name fallback for a driver we've never seen a name for."""
    return " ".join(w.capitalize() for w in driver_id.split("_"))
```

```python
def _post_quali_block(
    v2: dict,
    qualifying: list[dict] | None,
    seen: set[tuple[str, str, str]],
    nm,
    season_pod: dict[str, int],
    recent_pod: dict[str, int],
    cid_name: dict[str, str],
    con_strength: dict[str, float],
    using_constructors: bool,
) -> dict | None:
    """Grid-aware prediction for the next race, or None before its quali exists.

    Entrants are exactly the qualifying participants with the constructor each
    qualified for (handles seat swaps/substitutes). Two effects on top of the
    already-advanced filter state in ``v2["hf"]``: the quali order through the
    standard rating channel, then grid_offsets folded into the means. Seeded
    with the backtest convention so the output is a deterministic function of
    its inputs.

    NOTE: mutates v2["hf"] (the quali observation) — call only after every
    pre-quali value has been extracted from ``v2``.
    """
    nxt = v2["next_race"]
    if nxt is None or not qualifying:
        return None
    season, rnd = str(v2["next_season"]), str(nxt["round"])
    q = next((e for e in qualifying if e["season"] == season and e["round"] == rnd), None)
    if q is None:
        return None

    hf, params = v2["hf"], v2["params"]
    qpos: dict[str, int] = {}
    qcid: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    for row in sorted(q["results"], key=lambda r: r["position"]):
        d = row["driverId"]
        if d in qpos:
            continue
        qpos[d] = row["position"]
        qcid[d] = row["constructorId"]
        entries.append((d, row["constructorId"]))
    if len(entries) < 3:
        return None

    # Information effect: the fresh quali order through the standard channel.
    hf.engine.observe_order(entries, depth=int(params["depth_qual"]), weight=params["w_qual"])

    circuit = nxt.get("circuitId")
    delta = params["chaos_gamma"] * hf.circuits.dnf_logodds_delta(circuit) if circuit else 0.0
    temp = hf.circuits.temp(circuit, params["chaos_eta"]) if circuit else 1.0
    disp = hf.circuits.disp_ratio(circuit) if circuit else 1.0

    # Causal track-position effect: grid offsets folded into the means.
    offsets = model_v2.grid_offsets(qpos, disp, params)
    mu_var: dict[str, tuple[float, float]] = {}
    p_fin: dict[str, float] = {}
    for d in qpos:
        mu, var = hf.engine.combined(d, qcid[d])
        mu_var[d] = (mu + offsets[d], var)
        p_fin[d] = hf.p_finish_adjusted(d, qcid[d], delta)

    seed = SEED + int(season) * 100 + int(rnd)
    out = model_v2.predict_race(
        sorted(qpos), mu_var, p_fin, temp, params, seen, n_draws=N_DRAWS, seed=seed
    )

    def entry(d: str) -> dict:
        e: dict = {
            "driverId": d,
            "name": nm(d),
            "weight": round(math.exp(mu_var[d][0]), 3),
            "seasonPodiums": season_pod.get(d, 0),
            "recentPodiums": recent_pod.get(d, 0),
            "constructorId": qcid[d],
        }
        if using_constructors:
            e["constructor"] = cid_name.get(qcid[d], "")
            e["constructorStrength"] = round(con_strength.get(d, 0), 3)
        e["finishProb"] = round(p_fin[d], 3)
        e["uncertainty"] = round(math.sqrt(mu_var[d][1]), 3)
        e["gridPosition"] = qpos[d]
        return e

    candidates = [
        {
            "driverIds": list(t),
            "names": [nm(d) for d in t],
            "prob": round(100 * p, 3),
            "perDriver": [entry(d) for d in t],
        }
        for t, p in out["ranked_new"][:TOP_CANDIDATES]
    ]
    driver_form = sorted((entry(d) for d in sorted(qpos)), key=lambda x: -x["weight"])
    return {
        "season": season,
        "round": rnd,
        "raceName": nxt.get("raceName", ""),
        "chanceNextRaceNew": round(100 * out["p_new"], 1),
        "candidates": candidates,
        "driverForm": driver_form,
    }
```

(d) In `compute()`:
- `nm` fallback chain becomes `return name_by_id.get(d) or grid_name.get(d) or _title_from_id(d)`.
- Initialize `cid_to_name: dict[str, str] = {}` next to `constructor_name` (the `using_constructors` branch currently creates it locally — hoist the empty init so it's always bound).
- After `driver_form` is built (all pre-quali values extracted), add:

```python
    post_quali = None
    if v2 is not None:
        post_quali = _post_quali_block(
            v2, qualifying, seen, nm, season_pod, recent_pod,
            cid_to_name, con_strength, using_constructors,
        )
```

- Payload dict: insert `"postQuali": post_quali,` after `"driverForm": driver_form,`.

**Step 6.4: Verify** — `python -m pytest tests/test_compute_podigami.py -q` then full suite + four gates.

**Step 6.5: Regen check** — run `python src/compute/compute_podigami.py` and `git diff --stat data/podigami.json`. Expected: **no diff** (develop's committed `qualifying.json` doesn't cover the round after its `asOf`, so the new code path writes the same `"postQuali": null` the canonical dump already emitted). If there IS a diff, inspect it (it means a next-round quali exists in committed data) and commit the regenerated file with this task.

**Step 6.6: Commit** — `git commit -am "feat: compute postQuali grid-aware prediction block"`

---

## Task 7: Guard quali trigger in `check_update_due.py`

**Files:**
- Modify: `src/check_update_due.py`
- Modify: `tests/test_check_update_due.py`

**Step 7.1: Failing tests** (append; reuse `at`/`ASOF_*`):

```python
# --- post-quali trigger -------------------------------------------------------


def qsched(*rounds, season="2026"):
    """Schedule dict from (round, race_date, race_time, quali_date, quali_time)."""
    return {
        "season": season,
        "totalRounds": len(rounds),
        "races": [
            {"round": r, "date": d, "time": t, "qualifyingDate": qd, "qualifyingTime": qt}
            for (r, d, t, qd, qt) in rounds
        ],
    }


# Round 10 races Sunday 13:00; quali Saturday 14:00 (all UTC).
R10 = ("10", "2026-07-19", "13:00:00Z", "2026-07-18", "14:00:00Z")
PQ_R10 = {"season": "2026", "round": "10", "raceName": "Belgian Grand Prix"}


def test_quali_not_due_before_session():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 13:00")) is False


def test_quali_not_due_inside_buffer():
    # quali start + 90min buffer = 15:30
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 15:00")) is False


def test_quali_due_past_buffer_when_uncovered():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 15:31")) is True


def test_quali_not_due_when_post_quali_covers_the_round():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, PQ_R10, at("2026-07-18 16:00")) is False


def test_quali_due_when_post_quali_covers_an_older_round():
    s = qsched(R10)
    stale = {"season": "2026", "round": "9", "raceName": "R9"}
    assert is_post_quali_update_due(s, ASOF_R9, stale, at("2026-07-18 16:00")) is True


def test_quali_missing_fields_never_fires():
    # pre-rollout schedule: quali fields null -> trigger stays quiet forever
    s = qsched(("10", "2026-07-19", "13:00:00Z", None, None))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_garbage_time_never_fires():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", "not-a-time"))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_missing_time_defaults_to_end_of_day():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", ""))
    # 23:59:59Z + 90min buffer -> not due Saturday evening, due Sunday 02:00
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 23:00")) is False
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 02:00")) is True


def test_quali_garbage_asof_never_fires():
    # unlike the race trigger, no asOf means we can't locate the "next" race
    s = qsched(R10)
    assert is_post_quali_update_due(s, {}, None, at("2026-07-18 16:00")) is False


def test_quali_targets_the_race_after_asof_only():
    # R10's quali passed but R10 is already in the data -> next race is R11,
    # whose quali is in the future -> not due.
    r11 = ("11", "2026-08-02", "13:00:00Z", "2026-08-01", "14:00:00Z")
    s = qsched(R10, r11)
    asof_r10 = {"season": "2026", "round": "10", "raceName": "Belgian Grand Prix"}
    assert is_post_quali_update_due(s, asof_r10, None, at("2026-07-19 20:00")) is False


def test_quali_season_rollover():
    # data holds last season's finale; the opener's quali just finished
    s = qsched(("1", "2027-03-07", "04:00:00Z", "2027-03-06", "05:00:00Z"), season="2027")
    assert is_post_quali_update_due(s, ASOF_PREV, None, at("2027-03-06 06:31")) is True
```

Also change the file's top import to `from check_update_due import is_post_quali_update_due, is_update_due` (single import line — a mid-file import would trip ruff E402).

**Step 7.2: Verify fail** — `python -m pytest tests/test_check_update_due.py -q` → ImportError.

**Step 7.3: Implement** in `src/check_update_due.py`. Below `RESULTS_BUFFER`:

```python
# How long after the scheduled qualifying start the classification is assumed
# published. Quali runs ~1h; API publish lag is minutes. Being early is harmless
# (same self-terminating no-op as RESULTS_BUFFER), being late only delays the
# post-quali refresh, so 90min errs toward promptness.
QUALI_BUFFER = timedelta(minutes=90)
```

After `is_update_due`:

```python
def _next_race_entry(schedule: dict, have: tuple[int, int]) -> dict | None:
    """The first scheduled race strictly after ``have`` (season, round), or None."""
    try:
        season = int(schedule["season"])
    except (KeyError, ValueError, TypeError):
        return None
    best: tuple[int, dict] | None = None
    for race in schedule.get("races", []):
        try:
            rnd = int(race["round"])
        except (KeyError, ValueError, TypeError):
            continue
        if (season, rnd) <= have:
            continue
        if best is None or rnd < best[0]:
            best = (rnd, race)
    return best[1] if best else None


def is_post_quali_update_due(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> bool:
    """True when the next race's qualifying should be classified by ``now`` but
    ``podigami.json``'s ``postQuali`` doesn't cover that round yet.

    Fail-safe: any missing/garbage input means "don't fire" — unlike the race
    trigger, there is no data-loss risk in staying quiet (the pre-quali
    prediction remains live), and a schedule without quali fields (pre-rollout)
    must never wedge the loop. A garbage ``asOf`` also stays quiet: without it
    the "next" race is unknowable, and the race trigger already covers that case.
    """
    try:
        have = (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        return False
    race = _next_race_entry(schedule, have)
    if race is None:
        return False
    start = _race_start(race.get("qualifyingDate") or "", race.get("qualifyingTime") or "")
    if start is None or now < start + QUALI_BUFFER:
        return False
    if post_quali:
        try:
            covered = (int(post_quali["season"]), int(post_quali["round"]))
        except (KeyError, ValueError, TypeError):
            covered = None
        if covered == (int(schedule["season"]), int(race["round"])):
            return False
    return True
```

`main()` becomes:

```python
def main() -> int:  # pragma: no cover - thin CLI glue exercised in CI, not unit tests
    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})

    now = datetime.now(UTC)
    race_due = is_update_due(schedule, asof, now)
    quali_due = is_post_quali_update_due(schedule, asof, podigami.get("postQuali"), now)
    due = race_due or quali_due
    print(
        f"update due: {due} (race={race_due} quali={quali_due} "
        f"asOf season={asof.get('season')} round={asof.get('round')})"
    )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"due={'true' if due else 'false'}\n")
    return 0
```

Update the module docstring (two independent triggers, single `due` output).

**Step 7.4: Verify + four gates. Step 7.5: Commit** — `git commit -am "feat: post-quali trigger in the update guard (90min buffer)"`

---

## Task 8: Backtest — post-quali protocol, rungs, gate, `--tune-v2-grid`

**Files:**
- Modify: `src/compute/backtest.py`
- Modify: `tests/test_backtest.py`

`data/model_eval.json` is NOT touched here (no backtest run) — `test_committed_eval_shows_improvement_over_product` keeps passing on the old file; the ladder gains rows only when Task 9 reruns it.

**Step 8.1: Failing tests** (append to `tests/test_backtest.py`):

```python
# --- post-quali protocol ----------------------------------------------------------


def _q_for(season, rnd, order):
    return {
        "season": str(season),
        "round": str(rnd),
        "results": [
            {"driverId": d, "constructorId": c, "position": i + 1}
            for i, (d, c) in enumerate(order)
        ],
    }


def _quali_informative_history():
    """Two team-pairs alternate dominance per round; quali reveals which state
    the race is in, so only a post-quali snapshot can predict the flip rounds."""
    a_side = [("a", "t1"), ("b", "t1"), ("c", "t2"), ("d", "t2")]
    c_side = [("c", "t2"), ("d", "t2"), ("a", "t1"), ("b", "t1")]
    rresults, quali_map, trio_keys = [], {}, {}
    for season in (2010, 2011):
        for rnd in range(1, 16):
            order = a_side if rnd % 2 == 0 else c_side
            rows = [_rrow_v2(d, c, i + 1, i + 1) for i, (d, c) in enumerate(order)]
            rresults.append(
                {
                    "season": str(season),
                    "round": str(rnd),
                    "raceName": "GP",
                    "date": "",
                    "circuitId": "ring",
                    "results": rows,
                }
            )
            quali_map[(str(season), str(rnd))] = _q_for(season, rnd, order)
            trio_keys[(str(season), str(rnd))] = tuple(sorted(d for d, _ in order[:3]))
    return rresults, quali_map, trio_keys


def test_post_quali_protocol_beats_pre_quali_on_quali_informative_history():
    rresults, quali_map, trio_keys = _quali_informative_history()
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2, w_grid=0.0)
    pre = backtest.score_window_v2(rresults, quali_map, trio_keys, (2011, 2011), params)
    post = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), params, post_quali=True
    )
    ll_pre = backtest.metrics.log_loss([r["p_true"] for r in pre])
    ll_post = backtest.metrics.log_loss([r["p_true"] for r in post])
    assert ll_post < ll_pre


def test_grid_term_sharpens_on_grid_follows_finish_history():
    # finish always == quali order, but the order rotates so long-run ratings
    # equalise: the causal grid term is the only stable signal.
    drivers = [("a", "t1"), ("b", "t1"), ("c", "t2"), ("d", "t2")]
    rresults, quali_map, trio_keys = [], {}, {}
    for season in (2010, 2011):
        for rnd in range(1, 16):
            order = drivers[rnd % 4 :] + drivers[: rnd % 4]  # rotate the grid
            rows = [_rrow_v2(d, c, i + 1, i + 1) for i, (d, c) in enumerate(order)]
            rresults.append(
                {
                    "season": str(season),
                    "round": str(rnd),
                    "raceName": "GP",
                    "date": "",
                    "circuitId": "ring",
                    "results": rows,
                }
            )
            quali_map[(str(season), str(rnd))] = _q_for(season, rnd, order)
            trio_keys[(str(season), str(rnd))] = tuple(sorted(d for d, _ in order[:3]))
    base = dict(backtest.model_v2.DEFAULT_PARAMS_V2, w_grid=0.0)
    grid = dict(backtest.model_v2.DEFAULT_PARAMS_V2, w_grid=0.4)
    r0 = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), base, post_quali=True
    )
    r1 = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), grid, post_quali=True
    )
    p0 = sum(r["p_true"] for r in r0) / len(r0)
    p1 = sum(r["p_true"] for r in r1) / len(r1)
    assert p1 > p0


def test_rungs_v2_postquali_shape():
    names = [name for name, _ in backtest.RUNGS_V2_POSTQUALI]
    assert names == ["v2 post-quali (ratings)", "v2 post-quali +grid"]
    by = dict(backtest.RUNGS_V2_POSTQUALI)
    assert by["v2 post-quali (ratings)"] == {"w_grid": 0.0}
    assert by["v2 post-quali +grid"] == {}


def _races_for(trio_keys):
    return [race(int(s), int(r), *trio) for (s, r), trio in sorted(trio_keys.items())]


def test_evaluate_appends_post_quali_rungs_and_gate():
    rresults, quali_map, trio_keys = _quali_informative_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    res = backtest.evaluate(races, active, (2011, 2011), v2_data=(rresults, quali_map))
    names = [name for name, _ in res["ladder"]]
    assert names[-2:] == ["v2 post-quali (ratings)", "v2 post-quali +grid"]
    assert isinstance(res["postQuali"]["gridAccepted"], bool)
    # the pre-quali chosen selection is untouched by the new rungs
    assert res["chosenName"] in ("PL + tuned (chosen)", "v2 full")


def test_evaluate_without_v2_reports_no_post_quali():
    races, active = _small_races()
    res = backtest.evaluate(races, active, (2011, 2012))
    assert res["postQuali"] is None


def test_tune_v2_grid_touches_only_the_grid_knobs():
    rresults, quali_map, trio_keys = _quali_informative_history()
    winner = backtest.tune_v2_grid(
        rresults, quali_map, trio_keys, (2010, 2010), sweeps=1, verbose=False
    )
    assert winner["w_grid"] in backtest.V2_GRID_TUNE_GRID["w_grid"]
    assert winner["grid_circuit_beta"] in backtest.V2_GRID_TUNE_GRID["grid_circuit_beta"]
    for k, v in backtest.model_v2.DEFAULT_PARAMS_V2.items():
        if k not in ("w_grid", "grid_circuit_beta"):
            assert winner[k] == v


def test_main_tune_v2_grid_flag_prints_winner(monkeypatch, capsys):
    rresults, quali_map, trio_keys = _quali_informative_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: (rresults, quali_map))
    rc = backtest.main(["--tune-v2-grid"])
    assert rc == 0
    assert "Best grid knobs" in capsys.readouterr().out
```

Note: `_quali_informative_history` starts in 2010 and `backtest.main` computes `val = (2010, 2018)`, `test = (2019, 2011 latest)`. For the `--tune-v2-grid` main test that's fine (tuning uses `val` and the window filter simply keeps 2010–2011 races). Also update `test_evaluate_reports_full_ladder`? No — it passes `v2_data=None`, unchanged.

**Step 8.2: Verify fail** — `python -m pytest tests/test_backtest.py -q` → AttributeError on `RUNGS_V2_POSTQUALI` etc.

**Step 8.3: Implement** in `src/compute/backtest.py`:

(a) After `RUNGS_V2` / `V2_TUNE_GRID`:

```python
# Post-quali protocol rungs: quali observed BEFORE the snapshot (legitimate
# conditioning — qualifying precedes the race) with grid offsets applied.
# The ratings rung is the acceptance-gate baseline for the grid term.
RUNGS_V2_POSTQUALI = [
    ("v2 post-quali (ratings)", {"w_grid": 0.0}),
    ("v2 post-quali +grid", {}),
]

# Per-knob grids for --tune-v2-grid (the other 18 knobs stay frozen).
V2_GRID_TUNE_GRID: dict[str, list] = {
    "w_grid": [0.0, 0.05, 0.1, 0.2, 0.4],
    "grid_circuit_beta": [0.0, 0.5, 1.0],
}
```

(b) `score_window_v2` signature gains `post_quali=False` (after `with_rank=False`), docstring notes the protocol, and the body changes:

```python
        snap = hf.step(race, quali_map.get(rk), snapshot_after_quali=post_quali)
```

and, right after `mu_var = {...}` inside the scoring branch:

```python
            if post_quali:
                quali = quali_map.get(rk)
                if quali:
                    qpos: dict[str, int] = {}
                    for q in sorted(quali["results"], key=lambda q: q["position"]):
                        qpos.setdefault(q["driverId"], q["position"])
                    qpos = {d: g for d, g in qpos.items() if d in mu_var}
                    offs = model_v2.grid_offsets(qpos, snap["disp_ratio"], params)
                    mu_var = {d: (mv[0] + offs.get(d, 0.0), mv[1]) for d, mv in mu_var.items()}
```

(c) `evaluate()`: initialise `post_quali_info = None` before the `if v2_data is not None:` branch. Inside, after the existing gate block:

```python
        post_rows: dict[str, dict] = {}
        for name, overrides in RUNGS_V2_POSTQUALI:
            params = dict(model_v2.DEFAULT_PARAMS_V2, **overrides)
            recs = score_window_v2(
                rresults, quali_map, keys, test, params, with_rank=True, post_quali=True
            )
            ladder.append((name, summarize(recs)))
            post_rows[name] = ladder[-1][1]
        ratings, grid = post_rows["v2 post-quali (ratings)"], post_rows["v2 post-quali +grid"]
        # Grid-term acceptance gate: +grid ships only if it wins BOTH headline scores.
        post_quali_info = {
            "gridAccepted": bool(
                grid["logLoss"] <= ratings["logLoss"] and grid["brierNew"] <= ratings["brierNew"]
            )
        }
```

and add `"postQuali": post_quali_info,` to the return dict.

(d) `tune_v2_grid` — mirror `tune_v2` but iterate `V2_GRID_TUNE_GRID` and score with `post_quali=True`:

```python
def tune_v2_grid(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict:
    """Coordinate descent over ONLY the two grid knobs (post-quali protocol),
    with the 18 locked v2 knobs frozen."""
    best = dict(model_v2.DEFAULT_PARAMS_V2)
    best_j = v2_objective(
        score_window_v2(rresults, quali_map, trio_keys, val, best, post_quali=True)
    )
    if verbose:
        print(f"start J={best_j:.4f}")
    for sweep in range(sweeps):
        for knob, grid in V2_GRID_TUNE_GRID.items():
            for value in grid:
                if value == best[knob]:
                    continue
                trial = dict(best, **{knob: value})
                j = v2_objective(
                    score_window_v2(rresults, quali_map, trio_keys, val, trial, post_quali=True)
                )
                if j < best_j:
                    best_j, best = j, trial
            if verbose:
                print(f"  sweep {sweep + 1} {knob} -> {best[knob]}  (J={best_j:.4f})")
    return best
```

(e) `main()`: add the flag + branch (after the `--tune-v2` branch):

```python
    ap.add_argument(
        "--tune-v2-grid",
        action="store_true",
        help="coordinate-descent the two grid knobs (post-quali protocol) on the validation window",
    )
```

```python
    if args.tune_v2_grid:
        if v2_data is None:
            print("race_results.json missing - run src/fetch/fetch_race_results.py first")
            return 1
        winner = tune_v2_grid(v2_data[0], v2_data[1], trio_keys_from(races), val)
        print("Best grid knobs (lock these into model_v2.DEFAULT_PARAMS_V2):")
        print({k: winner[k] for k in ("w_grid", "grid_circuit_beta")})
        return 0
```

(f) `main()` reporting, after the ladder print — **prints only, NEVER asserts** (constraint 4):

```python
    if res.get("postQuali") is not None:
        by = dict(ladder)
        pre, post = by["v2 full"], by["v2 post-quali +grid"]
        sane = post["logLoss"] <= pre["logLoss"]
        print(
            f"\npost-quali gate: gridAccepted={res['postQuali']['gridAccepted']}"
            f" | post-vs-pre logLoss {post['logLoss']:.3f} vs {pre['logLoss']:.3f}"
            f"{' OK' if sane else '  WARNING: post-quali scored worse than pre-quali'}"
        )
```

**Step 8.4: Verify** — `python -m pytest tests/test_backtest.py -q` then full suite + four gates. (The two synthetic-history tests are the slowest here; if either behaves marginally, widen the histories — do NOT weaken the inequality assertions.)

**Step 8.5: Commit** — `git commit -am "feat: post-quali backtest protocol, ladder rungs, gate + --tune-v2-grid"`

---## Task 9: Real-data tuning, gate verdict, lock knobs, regen everything

The one heavyweight task: sync data with `main`, tune the two knobs on 2010–2018, apply the gate, lock, and regenerate `model_eval.json` + `podigami.json`. Everything (knob values + `ModelParamsV2` schema + both regenerated files + test constants) lands in ONE commit (constraint 2).

**Files:**
- Modify: `data/*` (sync from origin/main), `data/schedule.json` (refetch)
- Modify: `src/compute/model_v2.py` (locked knob values)
- Modify: `src/datalib/schemas.py` (ModelParamsV2 += 2 required)
- Modify: `tests/test_datalib.py` (model-eval union test uses `_GRID_KNOBS`)
- Regenerate: `data/model_eval.json`, `data/podigami.json`

**Step 9.1: Sync data from main** (develop's `data/` drifts behind main between promotions — expected):

```
git fetch origin main
git checkout origin/main -- data/
python src/fetch/fetch_schedule.py     # restore the quali fields main's schedule.json lacks
git status                             # expect: modified data/* (main's newer asOf etc.)
```

Do NOT run the test suite yet — main's `podigami.json` predates the Task 2 schema (missing required params keys), so validation fails until Step 9.5's regen. That's expected mid-task state.

**Step 9.2: Run the tuner** (long: a full `score_window_v2` pass per candidate over 2010–2018; run in background, capture output):

```
python src/compute/backtest.py --tune-v2-grid | tee tune_v2_grid.log
```

Record the winning `{w_grid, grid_circuit_beta}`.

**Step 9.3: Lock the knobs.** Edit `DEFAULT_PARAMS_V2` in `src/compute/model_v2.py`: replace the provisional `0.1` / `0.5` with the tuned values and rewrite the comment to match the `--tune-v2` style (locked by the walk-forward tuner, date, J improvement from the log).

**Step 9.4: Schema + tests.** `ModelParamsV2` in `src/datalib/schemas.py`: after `t_wild: float` add `w_grid: float` and `grid_circuit_beta: float`; update its docstring ("The 20 locked knobs..."). In `tests/test_datalib.py::test_model_eval_params_union_and_chosen_model`, change to `ModelParamsV2.model_validate({**_V2_KNOBS, **_GRID_KNOBS})`.

**Step 9.5: Regenerate + gate verdict:**

```
python src/compute/backtest.py | tee backtest_full.log     # writes data/model_eval.json
python src/compute/compute_podigami.py                     # writes data/podigami.json
```

Read the gate line in the output:
- **`gridAccepted=True`** → done; the ladder's `v2 post-quali +grid` row is the FAQ citation.
- **`gridAccepted=False`** → per spec, lock `w_grid` to `0.0` in `DEFAULT_PARAMS_V2` (keep the tuned `grid_circuit_beta` value as documentation; it's inert at w=0), rerun both regen commands, and note the verdict in the knob comment. The feature degrades to the ratings-only post-quali update — everything else in this plan still ships.

Also check the `post-vs-pre logLoss` sanity print: if post-quali scores WORSE than pre-quali on test, stop and investigate before shipping (that inverts the feature's premise).

Expect `postQuali` in the regenerated `podigami.json` to be `null` (no next-round quali exists mid-week). Verify `race_results.json` / `qualifying.json` stayed compact (single-line; external-formatter memory).

**Step 9.6: Full verify** — all four gates green now.

**Step 9.7: Commit**

```
git add data/ src/compute/model_v2.py src/datalib/schemas.py tests/test_datalib.py
git commit -m "feat: lock tuned grid knobs (w_grid=<X>, beta=<Y>); regen model_eval + podigami with post-quali rungs"
```

(Include the gate verdict + tuned J numbers in the commit body.)

---

## Task 10: Next-race box shows the qualifying time

**Files:**
- Modify: `src/build/build_podigami_html.py` (render_next_race)
- Modify: `tests/test_build_podigami.py`

**Step 10.1: Failing tests:**

```python
SCHED_ONE = {
    "season": "2026",
    "totalRounds": 16,
    "races": [
        {
            "round": "10", "raceName": "Belgian Grand Prix",
            "date": "2026-07-19", "time": "13:00:00Z",
            "qualifyingDate": "2026-07-18", "qualifyingTime": "14:00:00Z",
            "circuitId": "spa", "circuitName": "Spa-Francorchamps",
            "locality": "Spa", "country": "Belgium",
            "lat": "50", "long": "5", "url": "",
            "trackPath": "", "trackViewBox": "0 0 100 100", "lengthKm": 7.004,
        }
    ],
}


def test_next_race_shows_quali_session():
    out = bp.render_next_race(SCHED_ONE, {"season": "2026", "round": "9"})
    assert 'class="nr-quali"' in out
    assert "Qualifying:" in out
    assert "Sat 18 Jul" in out and "14:00 UTC" in out


def test_next_race_without_quali_fields_has_no_line():
    sched = {
        "season": "2026",
        "totalRounds": 16,
        "races": [
            {k: v for k, v in SCHED_ONE["races"][0].items()
             if k not in ("qualifyingDate", "qualifyingTime")}
        ],
    }
    out = bp.render_next_race(sched, {"season": "2026", "round": "9"})
    assert "nr-quali" not in out
```

**Step 10.2: Verify fail. Step 10.3: Implement** — in `render_next_race`, before the return, build:

```python
    quali_line = ""
    qd = nxt.get("qualifyingDate")
    if qd:
        try:
            q = dt.datetime.strptime(qd, "%Y-%m-%d")
        except ValueError:
            q = None
        if q is not None:
            qt = (nxt.get("qualifyingTime") or "")[:5]
            when = f"{q:%a} {q.day} {q:%b}" + (f" &middot; {qt} UTC" if qt else "")
            quali_line = f'<div class="nr-quali">Qualifying: {when}</div>'
```

and insert `{quali_line}` in the f-string right after the `nr-when` div (inside `nr-main`).

**Step 10.4: Verify** (`tests/test_build_podigami.py` + `tests/test_build_output.py`) + four gates. **Step 10.5: Commit** — `git commit -am "feat: qualifying session time in the next-race box"`

---

## Task 11: Hero badge/delta, grid-aware candidates, main() wiring

**Files:**
- Modify: `src/build/build_podigami_html.py` (render_hero, render_candidates, main)
- Modify: `tests/test_build_podigami.py`
- Modify: `tests/test_build_output.py` (conditional dist test — constraint 3)

**Step 11.1: Failing tests** (`tests/test_build_podigami.py`):

```python
def _hero_top():
    return {
        "prob": 3.5,
        "perDriver": [
            pd("antonelli", "Andrea Kimi Antonelli", "mercedes", 6),
            pd("norris", "Lando Norris", "mclaren", 2),
            pd("russell", "George Russell", "mercedes", 3),
        ],
    }


def test_render_hero_post_quali_badge_and_delta_up():
    out = bp.render_hero(_hero_top(), 71.0, META, pre_chance=52.0)
    assert "hc-updated" in out and "Updated after qualifying" in out
    assert "hc-delta-up" in out and "was 52%" in out and "before the grid was set" in out
    assert "71%" in out


def test_render_hero_delta_down_and_flat():
    down = bp.render_hero(_hero_top(), 40.0, META, pre_chance=52.0)
    assert "hc-delta-down" in down
    flat = bp.render_hero(_hero_top(), 52.4, META, pre_chance=52.0)  # both round to 52
    assert "hc-delta-flat" in flat and "&mdash;" in flat


def test_render_hero_default_has_no_post_quali_markup():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert "hc-updated" not in out and "hc-delta" not in out


def _grid_cands():
    return [
        {
            "prob": 3.0,
            "names": ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
            "perDriver": [
                {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), "gridPosition": 3},
                {**pd("norris", "Lando Norris", "mclaren"), "gridPosition": 1},
                {**pd("russell", "George Russell", "mercedes"), "gridPosition": 7},
            ],
        }
    ]


def test_render_candidates_grid_aware_badge_and_chips():
    out = bp.render_candidates(_grid_cands(), META, grid_aware=True)
    assert "panel-badge" in out and "grid-aware" in out
    assert out.count('class="cd-grid"') == 3
    assert ">P1<" in out and ">P3<" in out and ">P7<" in out


def test_render_candidates_default_has_no_grid_markup():
    cands = _grid_cands()
    for p in cands[0]["perDriver"]:
        p.pop("gridPosition")
    out = bp.render_candidates(cands, META)
    assert "panel-badge" not in out and "cd-grid" not in out
```

And in `tests/test_build_output.py` (find the file's existing dist-test style and append; MUST be conditional — constraint 3):

```python
def test_post_quali_hero_state_matches_data(dist, data):
    """The rendered hero must mirror the committed postQuali state exactly —
    conditional on the data so the update job's pytest run stays green whether
    the block is live or null (the #178 stall-class guardrail)."""
    html_text = (dist / "index.html").read_text(encoding="utf-8")
    if data["podigami"].get("postQuali"):
        assert "hc-updated" in html_text
        assert "cd-grid" in html_text
    else:
        assert "hc-updated" not in html_text
        assert "cd-grid" not in html_text
```

**Step 11.2: Verify fail. Step 11.3: Implement:**

`render_hero` — new signature `def render_hero(top, chance, meta, acc_badge="", pre_chance=None):`; before the return build:

```python
    updated = ""
    delta = ""
    if pre_chance is not None:
        updated = '<span class="hc-updated">&#9889; Updated after qualifying</span>'
        if round(chance) > round(pre_chance):
            cls, arrow = "up", "&#8593;"
        elif round(chance) < round(pre_chance):
            cls, arrow = "down", "&#8595;"
        else:
            cls, arrow = "flat", "&mdash;"
        delta = (
            f'<span class="hc-delta hc-delta-{cls}">{arrow} was {pre_chance:.0f}% '
            f"before the grid was set</span>"
        )
```

and restructure the hero-chance div:

```python
        f'    <div class="hero-chance">{updated}<span class="hc-num">{chance:.0f}%</span>'
        ...existing hc-label span...
        f"      </span>{delta}</div>"
```

`render_candidates` — new signature `def render_candidates(cands, meta, form_html="", grid_aware=False):`. The h2 gains `badge = '<span class="panel-badge">grid-aware</span>' if grid_aware else ""` appended after "Most likely next combinations"'s info-tip. In the chip loop, after the cd-code span:

```python
            gp = p.get("gridPosition")
            grid_chip = f'<span class="cd-grid">P{gp}</span>' if gp else ""
```

append `{grid_chip}` inside the `.cd` span after the cd-code.

`main()` wiring — after `cands = data["candidates"]`:

```python
    post = data.get("postQuali")
    active_chance = post["chanceNextRaceNew"] if post else chance
    active_cands = post["candidates"] if post else cands
    active_form = post["driverForm"] if post else data["driverForm"]
```

then use them: `hero = render_hero(active_cands[0], active_chance, meta, acc_badge, pre_chance=chance if post else None) if active_cands else ""`; `form = render_form(active_form, ...)` (other args unchanged); `candidates = render_candidates(active_cands, meta, form, grid_aware=bool(post))`; final print uses `active_chance`.

(Top-level `chance` stays the pre-quali number — exactly what the delta line cites.)

**Step 11.4: Verify** — full `python -m pytest -q` (the dist fixture rebuilds; committed data has `postQuali: null` so the conditional test exercises the absence branch) + four gates.

**Step 11.5: Commit** — `git commit -am "feat: post-quali hero badge + movement line, grid-aware candidates"`

---

## Task 12: FAQ entry

**Files:**
- Modify: `src/build/build_podigami_html.py` (render_faq)
- Modify: `tests/test_build_podigami.py`

**Step 12.1: Failing tests:**

```python
EVAL_WITH_POSTQUALI = {
    **EVAL,
    "ladder": EVAL["ladder"]
    + [
        {"model": "v2 post-quali (ratings)", "n": 159, "top1": 0.14, "top3": 0.31,
         "top5": 0.43, "logLoss": 4.05},
        {"model": "v2 post-quali +grid", "n": 159, "top1": 0.15, "top3": 0.33,
         "top5": 0.45, "logLoss": 4.01},
    ],
}


def test_faq_post_quali_item_present_for_v2_and_cites_rung():
    out = bp.render_faq(V2_DATA, EVAL_WITH_POSTQUALI, 123, 456, 789, 20, 1950)
    assert "after qualifying" in out
    assert "33%" in out  # cites the "v2 post-quali +grid" rung's top3


def test_faq_post_quali_item_absent_for_v1():
    out = bp.render_faq({}, EVAL, 123, 456, 789, 20, 1950)
    assert "after qualifying" not in out


def test_faq_post_quali_item_tolerates_missing_rung():
    out = bp.render_faq(V2_DATA, EVAL, 123, 456, 789, 20, 1950)  # old eval, no rung
    assert "after qualifying" in out  # item still there, just uncited
```

**Step 12.2: Verify fail. Step 12.3: Implement** — in `render_faq`, after the `items = [...]` literal:

```python
    if is_v2:
        rung = next(
            (r for r in (ev.get("ladder") or []) if r.get("model") == "v2 post-quali +grid"),
            None,
        )
        cite = (
            f" In backtests, the grid-aware update places the actual podium trio in its "
            f"top&nbsp;3 {round(100 * rung['top3'])}% of the time."
            if rung
            else ""
        )
        items.insert(
            2,
            (
                "Why does the prediction update after qualifying?",
                "Qualifying is the most informative pre-race session: it reveals current pace "
                "and fixes the starting grid, whose track-position advantage has strong "
                "historical precedent. Once the grid is set, the model feeds the qualifying "
                "order through its rating engine and adds a grid-position term scaled by how "
                "processional the circuit historically is &mdash; stronger where overtaking "
                "is hard, weaker where the grid gets shuffled." + cite,
            ),
        )
```

**Step 12.4: Verify + four gates. Step 12.5: Commit** — `git commit -am "feat: FAQ entry for the post-quali prediction"`

---

## Task 13: CSS

**Files:**
- Modify: `assets/podigami.css`

**Step 13.1:** Read `assets/podigami.css` and `assets/style.css` first: confirm the token names used below exist (`--accent-bright`, `--accent`, `--muted`, `--surface-2`, `--border`, `--radius-sm`) and match the file's formatting conventions (selector style, section comments, where the 600px block lives). If the `optimal-color-contrast` skill is available, invoke it for the badge/delta colors; otherwise verify contrast ≥ 4.5:1 against the page background in both themes manually.

**Step 13.2: Implement** — add a section (adapt formatting to the file):

```css
/* --- Post-quali state (hero badge, delta, grid chips) --- */
.hc-updated{display:inline-flex;align-items:center;gap:.3rem;width:fit-content;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--accent-bright);border:1px solid var(--accent);border-radius:999px;padding:.15rem .55rem;margin-bottom:.4rem}
.hc-delta{display:block;font-size:.8rem;margin-top:.35rem;color:var(--muted)}
.hc-delta-up{color:var(--accent-bright)}
.hc-delta-down,.hc-delta-flat{color:var(--muted)}
.panel-badge{font-size:.62rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--accent-bright);border:1px solid var(--accent);border-radius:999px;padding:.12rem .5rem;margin-left:.5rem;vertical-align:middle}
.cd-grid{font-size:.62rem;font-weight:700;color:var(--muted);background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.05rem .3rem;margin-left:.2rem}
.nr-quali{font-size:.85rem;color:var(--muted);margin-top:.25rem}
```

and inside the existing `@media (max-width: 600px)` block:

```css
.hc-updated{font-size:.64rem}
.cd-grid{font-size:.58rem;padding:.03rem .25rem}
.hc-delta{font-size:.75rem}
```

No cache-busting work needed — CSS is routed through `_layout.asset()` (content-hash `?v=`) already.

**Step 13.3: Visual smoke** — `python src/build_site.py`, open `dist/index.html` (postQuali is null → only `.nr-quali` visible; the badge/delta/chips get their visual check in Task 15's synthetic run). Run `python -m pytest tests/test_mobile_css.py -q` to confirm no mobile regressions.

**Step 13.4: Verify + four gates. Step 13.5: Commit** — `git commit -am "feat: post-quali styles (badge, delta, grid chips, quali line)"`

---

## Task 14: README + RELEASE_NOTES

**Files:**
- Modify: `README.md`
- Modify: `RELEASE_NOTES.md`

**Step 14.1: README** — update every section the feature touches (read it first; expected: the `index.html` page description gains the post-quali update; the prediction-model paragraph gains the grid term + two ladder rungs; the automated-updates section gains the quali trigger + 90-min buffer; the file map gains nothing new — no new files outside tests). Keep the style of surrounding text.

**Step 14.2: RELEASE_NOTES** — add at the top (current head is `## 2026-07-10`):

```markdown
## 2026-07-15

### Features
- Post-qualifying grid-aware prediction: once the next race's qualifying is classified, the headline new-trio chance, candidate trios and driver form update automatically using the starting grid — with a circuit-aware grid-advantage term validated by the walk-forward backtest (#PR)
```

(Replace `#PR` with the real number at PR time — Task 16 amends it.)

**Step 14.3: Verify + four gates. Step 14.4: Commit** — `git commit -am "docs: README + release notes for the post-quali prediction"`

---

## Task 15: Full verification + synthetic-postQuali browser check

**Step 15.1: The four gates**, fresh:

```
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
PYTHONPATH=src python -m datalib.validate
python src/build_site.py
```

**Step 15.2: Synthetic browser check** (the committed data has `postQuali: null`, so the live-state UI needs an injected fixture). Write a throwaway script in the scratchpad (NOT the repo):

```python
# scratchpad/inject_postquali.py — synthesise a postQuali block from the real
# pre-quali candidates so the built page exercises the live-state UI.
import json, shutil
from pathlib import Path

DATA = Path("data/podigami.json")
shutil.copy(DATA, DATA.with_suffix(".json.bak"))
d = json.loads(DATA.read_text(encoding="utf-8"))
cands = json.loads(json.dumps(d["candidates"]))  # deep copy
for c in cands:
    for i, p in enumerate(c["perDriver"]):
        p["gridPosition"] = i * 3 + 1
cands[0], cands[1] = cands[1], cands[0]  # visible re-rank
form = json.loads(json.dumps(d["driverForm"]))
for i, p in enumerate(form):
    p["gridPosition"] = i + 1
d["postQuali"] = {
    "season": d["asOf"]["season"], "round": str(int(d["asOf"]["round"]) + 1),
    "raceName": "Synthetic Test GP",
    "chanceNextRaceNew": round(d["chanceNextRaceNew"] + 7.0, 1),
    "candidates": cands, "driverForm": form,
}
DATA.write_text(json.dumps(d), encoding="utf-8")
print("injected — rebuild now; restore with: git checkout -- data/podigami.json")
```

Then:

1. `python <scratchpad>/inject_postquali.py && python src/build_site.py`
2. Serve: `python -m http.server 8123 -d dist` (background)
3. Playwright (MCP): navigate `http://localhost:8123/`, screenshot at desktop width AND 375px. Verify: ⚡ badge, movement line with arrow + old %, "grid-aware" panel badge, `P1`-style chips on candidate rows, quali line in the next-race box, no layout overflow on mobile, badge legible in light AND dark theme.
4. **Restore**: `git checkout -- data/podigami.json` and delete the `.bak`; kill the server. Confirm `git status` clean except intended changes.
5. Rebuild clean: `python src/build_site.py` (back to the null-state page).

**Step 15.3:** Fix anything found (CSS tweaks → recommit Task 13's file), rerun the gates.

---

## Task 16: Ship — feature PR → develop, promotion → main (before Sat 2026-07-18)

**Step 16.1: Feature PR into develop** (squash; branch `feat/post-quali-grid-prediction` already carries the spec + this plan):

```
git push -u origin feat/post-quali-grid-prediction
gh pr create --title "feat: post-qualifying grid-aware prediction" --body "<PR-template body>"
```

Body follows `.github/pull_request_template.md` (Summary / Changes / Testing / Checklist). Amend the `#PR` placeholder in RELEASE_NOTES.md with the real number and push. Then:

```
gh pr checks --watch          # 7 required checks
gh pr merge --squash --delete-branch
git checkout develop && git pull
git branch -D feat/post-quali-grid-prediction   # if not auto-deleted locally
```

**Step 16.2: Promotion PR develop → main.** Data-conflict handling (main's auto-updates rewrite `data/` independently): Task 9 synced develop's data FROM main and no race happens between now and promotion (next race is Sunday), so conflicts should be empty-to-trivial. Recipe if they appear:

```
git checkout develop && git fetch origin
git merge origin/main            # three-way merge
# conflicts limited to data/*: keep develop's side — it IS main's data + the new schema fields
git checkout --ours data/ && git add data/
PYTHONPATH=src python -m datalib.validate && python -m pytest -q
git commit && git push
```

(Safety check first: `git show origin/main:data/podigami.json | python -c "import json,sys; print(json.load(sys.stdin)['asOf'])"` — if main's `asOf` advanced past develop's data, re-run Task 9's sync steps instead of blind `--ours`.)

```
gh pr create --base main --head develop --title "Release: post-qualifying grid-aware prediction" --body "<summary of bundled changes>"
gh pr checks --watch             # full 9 checks incl. CodeQL
gh pr merge --merge              # promotions use MERGE COMMITS (repo convention)
```

**Step 16.3: Verify deploy** — `gh run watch` on the `deploy.yml` run; then Playwright against the live site (fresh-cache note in memory): quali line visible in the next-race box, page otherwise unchanged (postQuali still null pre-Saturday).

**Step 16.4: Optional automation smoke** — `gh workflow run update.yml -f mode=auto -f force=true`; confirm the run goes green end-to-end (idempotent; likely no-op PR or clean data refresh). This proves the guard's new code path can't wedge the loop before Saturday runs it for real.

**Step 16.5: Saturday watch (2026-07-18).** Belgian GP quali per the refetched schedule (~14:00 UTC; confirm from `data/schedule.json`). Expected sequence: quali ends ~15:00 → guard fires at the first 15-min tick after `quali start + 90min` → `auto/update-data` PR opens with `postQuali` populated → auto-merge → deploy. Check ~2h after quali: hero shows the ⚡ badge + movement line. If nothing lands by ~3h: open the latest `update.yml` run and follow the silent-stall diagnosis path (memory: `auto-update-silent-stall`) — a red `Run tests` with a skipped PR step is a bug in this feature, not lag.

---

## Verification summary (what "done" means)

- [ ] All four gates green on develop AND main.
- [ ] `data/schedule.json` carries quali times; `data/model_eval.json` carries the two post-quali rungs; `data/podigami.json` carries the 20-knob params + `postQuali` key.
- [ ] Gate verdict recorded in the Task 9 commit body (and `w_grid=0` fallback applied if rejected).
- [ ] Live site: quali line pre-Saturday; badge + delta + grid chips after Saturday's auto-update.
- [ ] No stale local branches; RELEASE_NOTES + README updated in the feature PR.
