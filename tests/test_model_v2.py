"""Unit tests for the v2 dynamic Bayesian rating engine (pure math, no IO).

The observe_order expectations are hand-derived from the truncated
Plackett-Luce gradient/Hessian with equal priors (worths all 1), where
prefix sums reduce to simple fractions — see inline comments.
"""

import pytest

from compute import model_v2
from compute.model_v2 import (
    DEFAULT_PARAMS_V2,
    REG_RESET_SEASONS,
    RatingEngine,
    classify_status,
    lineage_root,
)


def engine(**overrides):
    params = dict(DEFAULT_PARAMS_V2)
    params.update(overrides)
    return RatingEngine(params)


# --- params + constants -------------------------------------------------------


def test_default_params_have_exactly_the_locked_knobs():
    assert set(DEFAULT_PARAMS_V2) == {
        "sigma0_drv",
        "sigma0_con",
        "rookie_mu",
        "newteam_mu",
        "tau_drv",
        "tau_con",
        "season_var_drv",
        "season_var_con",
        "reg_var_con",
        "depth_race",
        "w_attr",
        "depth_qual",
        "w_qual",
        "rel_half_life",
        "chaos_gamma",
        "chaos_eta",
        "p_wild",
        "t_wild",
        "w_grid",
        "grid_circuit_beta",
    }


def test_reg_reset_seasons_are_the_big_rule_changes():
    assert REG_RESET_SEASONS == {1961, 1966, 1989, 2009, 2014, 2022, 2026}


# --- lineage -------------------------------------------------------------------


def test_lineage_roots_track_team_rebrands():
    assert lineage_root("rb") == lineage_root("toro_rosso")
    assert lineage_root("alphatauri") == lineage_root("toro_rosso")
    assert lineage_root("aston_martin") == lineage_root("jordan")
    assert lineage_root("racing_point") == lineage_root("force_india")
    assert lineage_root("mercedes") == lineage_root("brawn")
    assert lineage_root("alpine") == lineage_root("benetton")


def test_lineage_root_is_identity_for_continuous_teams():
    assert lineage_root("ferrari") == "ferrari"
    assert lineage_root("mclaren") == "mclaren"
    assert lineage_root("williams") == "williams"


def test_engine_reuses_constructor_state_across_rebrand():
    eng = engine()
    st1 = eng.constructor("toro_rosso")
    st2 = eng.constructor("rb")
    assert st1 is st2


# --- status classification -----------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Finished", "finished"),
        ("+1 Lap", "finished"),
        ("+2 Laps", "finished"),
        ("Lapped", "finished"),  # ran to the flag, laps down (old-style classification)
        ("Not classified", "finished"),  # insufficient distance, but the car survived
        ("Accident", "inc"),
        ("Collision", "inc"),
        ("Collision damage", "inc"),
        ("Spun off", "inc"),
        ("Physical", "inc"),  # driver-side condition, not a car failure
        ("Disqualified", "dsq"),
        ("Did not start", "excluded"),
        ("Did not qualify", "excluded"),
        ("Withdrew", "excluded"),
        ("Engine", "mech"),
        ("Gearbox", "mech"),
        ("Some brand new failure mode", "mech"),  # unknown strings default to mech
    ],
)
def test_classify_status(status, expected):
    assert classify_status(status) == expected


# --- observe_order: gradients and state movement -------------------------------


_ROOKIE = DEFAULT_PARAMS_V2["rookie_mu"]  # every fresh driver starts here; only
# the *delta* from this prior is the update the tests below measure.


def test_winner_gains_loser_drops_symmetrically():
    # m=2, equal priors: g = +-1/2, h = 1/4 for both -> exactly mirrored steps.
    eng = engine()
    eng.observe_order([("a", "car_a"), ("b", "car_b")])
    da, db = eng.driver("a"), eng.driver("b")
    assert (da.mu - _ROOKIE) > 0 > (db.mu - _ROOKIE)
    assert da.mu - _ROOKIE == pytest.approx(_ROOKIE - db.mu, rel=1e-12)
    v0 = DEFAULT_PARAMS_V2["sigma0_drv"] ** 2
    assert da.var < v0 and db.var < v0
    assert da.var == pytest.approx(db.var, rel=1e-12)


def test_attrition_sign_flips_direction():
    # sign=-1: first listed = first failure -> their rating must FALL.
    eng = engine()
    eng.observe_order([("a", "car_a"), ("b", "car_b")], sign=-1)
    assert eng.driver("a").mu < _ROOKIE < eng.driver("b").mu


def test_depth_truncation_treats_tail_as_unranked():
    # depth=1 over 3 equal entries: only stage 1 is scored, so both non-winners
    # get the identical (grad, hess) = (-1/3, 2/9) -> identical states.
    eng = engine()
    eng.observe_order([("a", "ca"), ("b", "cb"), ("c", "cc")], depth=1)
    b, c = eng.driver("b"), eng.driver("c")
    assert b.mu == pytest.approx(c.mu, rel=1e-12)
    assert b.var == pytest.approx(c.var, rel=1e-12)
    assert b.mu < _ROOKIE < eng.driver("a").mu


def test_weight_scales_the_update():
    full = engine()
    half = engine()
    full.observe_order([("a", "ca"), ("b", "cb")])
    half.observe_order([("a", "ca"), ("b", "cb")], weight=0.5)
    ratio = (half.driver("a").mu - _ROOKIE) / (full.driver("a").mu - _ROOKIE)
    assert 0.4 < ratio < 0.62  # ~half, softened by the Kalman denominator
    assert half.driver("a").var > full.driver("a").var  # weaker evidence -> less shrink


def test_constructor_gets_one_step_with_summed_gradient():
    # 4 equal entries; A (1st) and D (4th) share constructor X.
    # Hand-derived: g_X = 3/4 - 13/12 = -1/3, h_X = 3/16 + 95/144 = 61/72.
    eng = engine()
    eng.observe_order([("a", "x"), ("b", "y"), ("c", "z"), ("d", "x")])
    v0 = DEFAULT_PARAMS_V2["sigma0_con"] ** 2
    g_x, h_x = -1.0 / 3.0, 61.0 / 72.0
    expected_mu = DEFAULT_PARAMS_V2["newteam_mu"] + v0 * g_x / (1.0 + v0 * h_x)
    assert eng.constructor("x").mu == pytest.approx(expected_mu, rel=1e-9)
    assert eng.constructor("x").var == pytest.approx(v0 / (1.0 + v0 * h_x), rel=1e-9)


def test_observe_order_noops_on_degenerate_input():
    eng = engine()
    eng.observe_order([("a", "ca")])  # single entry: nothing to rank
    eng.observe_order([("a", "ca"), ("b", "cb")], weight=0.0)
    assert eng.driver("a").mu == DEFAULT_PARAMS_V2["rookie_mu"]
    assert eng.driver("a").var == DEFAULT_PARAMS_V2["sigma0_drv"] ** 2


# --- dynamics ------------------------------------------------------------------


def test_advance_race_adds_tau_squared():
    eng = engine()
    d, c = eng.driver("a"), eng.constructor("ca")
    vd, vc = d.var, c.var
    eng.advance_race()
    assert d.var == pytest.approx(vd + DEFAULT_PARAMS_V2["tau_drv"] ** 2)
    assert c.var == pytest.approx(vc + DEFAULT_PARAMS_V2["tau_con"] ** 2)


def test_advance_season_inflates_more_on_regulation_reset():
    p = DEFAULT_PARAMS_V2
    reg, normal = engine(), engine()
    for eng in (reg, normal):
        eng.driver("a")
        eng.constructor("ca")
    v_drv = reg.driver("a").var
    v_con = reg.constructor("ca").var

    reg.advance_season(2022)  # regulation reset year
    normal.advance_season(2021)

    assert reg.driver("a").var == pytest.approx(v_drv + p["season_var_drv"])
    assert normal.driver("a").var == pytest.approx(v_drv + p["season_var_drv"])
    assert normal.constructor("ca").var == pytest.approx(v_con + p["season_var_con"])
    assert reg.constructor("ca").var == pytest.approx(
        v_con + p["season_var_con"] + p["reg_var_con"]
    )


def test_priors_are_the_configured_ones():
    eng = engine()
    assert eng.driver("rookie").mu == DEFAULT_PARAMS_V2["rookie_mu"]
    assert eng.constructor("newteam").mu == DEFAULT_PARAMS_V2["newteam_mu"]
    mu_s, var_s = eng.combined("rookie", "newteam")
    assert mu_s == pytest.approx(DEFAULT_PARAMS_V2["rookie_mu"] + DEFAULT_PARAMS_V2["newteam_mu"])
    assert var_s == pytest.approx(
        DEFAULT_PARAMS_V2["sigma0_drv"] ** 2 + DEFAULT_PARAMS_V2["sigma0_con"] ** 2
    )


def test_variance_never_leaves_clamp_bounds():
    eng = engine(sigma0_drv=10.0)  # var 100 would exceed the ceiling
    assert eng.driver("a").var <= 25.0
    for _ in range(200):
        eng.observe_order([("a", "ca"), ("b", "cb")])
    assert eng.driver("a").var >= 1e-6


# --- model_v2 exposes the v1 set-probability bridge ----------------------------


def test_v1_bridge_functions_are_reexported():
    # predict_race (Task 7) must share the exact 6-permutation math with v1.
    assert model_v2.model.pl_set_prob is not None
    assert model_v2.model.all_set_probs is not None


# --- ReliabilityTracker ---------------------------------------------------------


def _steady_field(n_teams=8):
    """Rows for a stable background field: one clean finisher per team."""
    return [(f"bg{i}", f"bgcar{i}", "finished") for i in range(n_teams)]


def test_fresh_driver_gets_the_era_rate():
    tr = model_v2.ReliabilityTracker(half_life=20.0)
    # Establish a nonzero era: every race one background driver has a mech DNF.
    for _ in range(30):
        tr.observe_race(_steady_field() + [("crasher", "fragile", "mech")])
    fresh = tr.p_finish("never_seen", "never_seen_car")
    seasoned_clean = tr.p_finish("bg0", "bgcar0")
    assert 0.5 < fresh < 1.0
    # A driver with a long clean record must beat the era prior.
    assert seasoned_clean > fresh


def test_constructor_mech_dnfs_hit_both_of_its_drivers():
    tr = model_v2.ReliabilityTracker(half_life=20.0)
    for _ in range(20):
        tr.observe_race(
            _steady_field()
            + [("d1", "weakcar", "mech"), ("d2", "weakcar", "finished")]
            + [("d3", "strongcar", "finished"), ("d4", "strongcar", "finished")]
        )
    # d2 never failed personally, but the shared car drags them down too.
    assert tr.p_finish("d2", "weakcar") < tr.p_finish("d4", "strongcar")
    assert tr.p_finish("d1", "weakcar") < tr.p_finish("d3", "strongcar")


def test_incident_hazard_is_personal_not_car_wide():
    tr = model_v2.ReliabilityTracker(half_life=20.0)
    for _ in range(20):
        tr.observe_race(
            _steady_field() + [("wild", "shared", "inc"), ("calm", "shared", "finished")]
        )
    assert tr.p_finish("wild", "shared") < tr.p_finish("calm", "shared")


def test_old_dnf_decays_toward_the_era_rate():
    hl = 10.0
    tr = model_v2.ReliabilityTracker(half_life=hl)
    for _ in range(20):  # warm up a stable era
        tr.observe_race(_steady_field() + [("someone", "somecar", "mech")])
    # "a" and "b" join; "a" crashes once, then both run clean.
    tr.observe_race(_steady_field() + [("a", "cara", "inc"), ("b", "carb", "finished")])
    gap_early = tr.p_finish("b", "carb") - tr.p_finish("a", "cara")
    for _ in range(int(hl)):
        tr.observe_race(
            _steady_field()
            + [("a", "cara", "finished"), ("b", "carb", "finished"), ("someone", "somecar", "mech")]
        )
    gap_late = tr.p_finish("b", "carb") - tr.p_finish("a", "cara")
    assert 0 < gap_late < 0.7 * gap_early  # the lone incident's pull has ~halved


def test_dsq_counts_as_a_clean_start_for_reliability():
    tr = model_v2.ReliabilityTracker(half_life=20.0)
    for _ in range(15):
        tr.observe_race(_steady_field() + [("naughty", "finecar", "dsq")])
    # DSQ is a classification event, not a car failure: no reliability penalty.
    assert tr.p_finish("naughty", "finecar") >= tr.p_finish("bg0", "bgcar0") - 1e-9


# --- CircuitStats ----------------------------------------------------------------


def test_unknown_circuit_is_neutral():
    cs = model_v2.CircuitStats()
    assert cs.temp("nowhere", eta=1.0) == 1.0
    assert cs.dnf_logodds_delta("nowhere") == 0.0


def test_high_displacement_circuit_gets_higher_temperature():
    cs = model_v2.CircuitStats()
    for _ in range(20):
        cs.observe_race("calm", starters=20, dnfs=2, mean_disp=2.0)
        cs.observe_race("wild", starters=20, dnfs=2, mean_disp=6.0)
    assert cs.temp("wild", eta=1.0) > 1.0
    assert cs.temp("wild", eta=1.0) > cs.temp("calm", eta=1.0)
    # eta < 1 softens the deviation from neutral
    assert 1.0 < cs.temp("wild", eta=0.5) < cs.temp("wild", eta=1.0)


def test_dnf_delta_positive_for_attritional_circuit_and_shrunk_by_visits():
    seasoned = model_v2.CircuitStats()
    for _ in range(20):
        seasoned.observe_race("normal", starters=20, dnfs=2, mean_disp=None)
        seasoned.observe_race("carnage", starters=20, dnfs=8, mean_disp=None)
    one_visit = model_v2.CircuitStats()
    for _ in range(20):
        one_visit.observe_race("normal", starters=20, dnfs=2, mean_disp=None)
    one_visit.observe_race("carnage", starters=20, dnfs=8, mean_disp=None)

    assert seasoned.dnf_logodds_delta("carnage") > 0
    assert seasoned.dnf_logodds_delta("normal") < 0
    # One visit must be shrunk much closer to neutral than twenty.
    assert 0 < one_visit.dnf_logodds_delta("carnage") < seasoned.dnf_logodds_delta("carnage")


def test_temperature_clamps_hold_under_extreme_displacement():
    cs = model_v2.CircuitStats()
    for _ in range(50):
        cs.observe_race("insane", starters=20, dnfs=0, mean_disp=50.0)
        cs.observe_race("frozen", starters=20, dnfs=0, mean_disp=0.01)
    assert cs.temp("insane", eta=1.0) <= 2.2
    assert cs.temp("frozen", eta=1.0) >= 0.5


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
    monaco = model_v2.grid_offsets(qpos, 0.5, p)  # processional -> amplified
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


# --- HistoryFilter ----------------------------------------------------------------


def _rrow(did, cid, grid, pos, laps, status):
    return {
        "driverId": did,
        "constructorId": cid,
        "grid": grid,
        "position": pos,
        "laps": laps,
        "status": status,
    }


def _rrace(season, rnd, circuit, rows):
    return {
        "season": str(season),
        "round": str(rnd),
        "raceName": f"Race {rnd}",
        "date": "",
        "circuitId": circuit,
        "results": rows,
    }


def _two_car_race(season, rnd, winner, loser):
    return _rrace(
        season,
        rnd,
        "somewhere",
        [
            _rrow(winner, "car_" + winner, 1, 1, 50, "Finished"),
            _rrow(loser, "car_" + loser, 2, 2, 50, "Finished"),
        ],
    )


def test_step_snapshot_predates_the_race_outcome():
    hf = model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2))
    for rnd in range(1, 6):
        hf.step(_two_car_race(2020, rnd, "champ", "underdog"), None)
    # Underdog finally wins round 6 - but the snapshot must not know that yet.
    snap = hf.step(_two_car_race(2020, 6, "underdog", "champ"), None)
    assert snap["drivers"]["champ"][0] > snap["drivers"]["underdog"][0]
    assert snap["season"] == 2020
    # ...while the engine, after the update, has narrowed the gap.
    gap_before = snap["drivers"]["champ"][0] - snap["drivers"]["underdog"][0]
    gap_after = hf.engine.driver("champ").mu - hf.engine.driver("underdog").mu
    assert gap_after < gap_before


def test_step_applies_race_vs_season_dynamics():
    p = dict(DEFAULT_PARAMS_V2)
    hf = model_v2.HistoryFilter(p)
    hf.step(_two_car_race(2020, 1, "a", "b"), None)
    var_after_r1 = hf.engine.driver("a").var + hf.engine.constructor("car_a").var

    snap2 = hf.step(_two_car_race(2020, 2, "a", "b"), None)
    assert snap2["drivers"]["a"][1] == pytest.approx(
        var_after_r1 + p["tau_drv"] ** 2 + p["tau_con"] ** 2
    )
    var_after_r2 = hf.engine.driver("a").var + hf.engine.constructor("car_a").var

    snap3 = hf.step(_two_car_race(2021, 1, "a", "b"), None)  # 2021: no reg reset
    assert snap3["drivers"]["a"][1] == pytest.approx(
        var_after_r2 + p["season_var_drv"] + p["season_var_con"]
    )


def test_dsq_and_dns_channel_visibility():
    p = dict(DEFAULT_PARAMS_V2)
    hf = model_v2.HistoryFilter(p)
    race = _rrace(
        2020,
        1,
        "somewhere",
        [
            _rrow("winner", "cw", 1, 1, 50, "Finished"),
            _rrow("second", "cs", 2, 2, 50, "Finished"),
            _rrow("cheat", "cc", 3, None, 50, "Disqualified"),
            _rrow("ghost", "cg", 0, None, 0, "Did not start"),
        ],
    )
    hf.step(race, None)
    # DSQ: absent from pace and attrition -> rating untouched...
    assert hf.engine.driver("cheat").mu == p["rookie_mu"]
    # ...but visible to reliability as a clean start (same as the winner's record).
    assert hf.reliability.p_finish("cheat", "cc") == pytest.approx(
        hf.reliability.p_finish("winner", "cw")
    )
    # DNS: absent everywhere - rating untouched AND reliability never saw them.
    assert hf.engine.driver("ghost").mu == p["rookie_mu"]
    assert hf.reliability.p_finish("ghost", "cg") == pytest.approx(
        hf.reliability.p_finish("total_stranger", "strange_car")
    )


def test_attrition_order_and_pace_direction():
    # The tuner zeroed w_attr in the shipped defaults; force the channel on
    # here because this test verifies the attrition *mechanism* itself.
    p = dict(DEFAULT_PARAMS_V2, w_attr=0.5)
    hf = model_v2.HistoryFilter(p)
    race = _rrace(
        2020,
        1,
        "somewhere",
        [
            _rrow("a", "ca", 1, 1, 50, "Finished"),
            _rrow("b", "cb", 2, 2, 50, "Finished"),
            _rrow("c", "cc", 3, 3, 50, "Finished"),
            _rrow("d", "cd", 4, None, 10, "Engine"),
            _rrow("e", "ce", 5, None, 5, "Engine"),
        ],
    )
    hf.step(race, None)
    drv = hf.engine.driver
    # Pace: finishing order is respected.
    assert drv("a").mu > drv("b").mu > drv("c").mu
    # Attrition: e failed before d, so e is punished harder; both fell below prior.
    assert drv("e").mu < drv("d").mu < p["rookie_mu"]


def test_qualifying_channel_moves_ratings():
    on = model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2))
    off = model_v2.HistoryFilter(dict(DEFAULT_PARAMS_V2, w_qual=0.0))
    race = _two_car_race(2020, 1, "a", "b")
    quali = {
        "season": "2020",
        "round": "1",
        "results": [
            {"driverId": "b", "constructorId": "car_b", "position": 1},
            {"driverId": "a", "constructorId": "car_a", "position": 2},
        ],
    }
    on.step(race, quali)
    off.step(race, quali)
    # b out-qualified a, so with the quali channel on, b must end up better off.
    assert on.engine.driver("b").mu > off.engine.driver("b").mu
    assert on.engine.driver("a").mu < off.engine.driver("a").mu


# --- predict_race -------------------------------------------------------------------


_MUS = {"a": 0.5, "b": 0.2, "c": 0.0, "d": -0.3, "e": -0.6}


def _predict(p_fin_a=1.0, seen=frozenset()):
    import math as _math

    params = dict(DEFAULT_PARAMS_V2, p_wild=0.0)
    entrants = sorted(_MUS)
    mu_var = {d: (m, 0.0) for d, m in _MUS.items()}
    p_fin = dict.fromkeys(_MUS, 1.0)
    p_fin["a"] = p_fin_a
    return model_v2.predict_race(entrants, mu_var, p_fin, 1.0, params, set(seen), n_draws=64), _math


def test_predict_race_bridge_matches_v1_closed_form():
    out, math_ = _predict()
    lam = {d: math_.exp(m) for d, m in _MUS.items()}
    exact = model_v2.model.all_set_probs(lam, sorted(_MUS))
    assert out["draws_used"] == 64
    assert sum(out["trio_probs"].values()) == pytest.approx(1.0, abs=1e-9)
    for trio, p in exact.items():
        assert out["trio_probs"][trio] == pytest.approx(p, abs=1e-9)


def test_predict_race_p_new_is_exact_complement_of_seen():
    seen = {("a", "b", "c"), ("c", "d", "e")}
    out, _ = _predict(seen=seen)
    expected = 1.0 - out["trio_probs"][("a", "b", "c")] - out["trio_probs"][("c", "d", "e")]
    assert out["p_new"] == pytest.approx(expected, abs=1e-12)
    assert all(t not in seen for t, _ in out["ranked_new"])
    probs = [p for _, p in out["ranked_new"]]
    assert probs == sorted(probs, reverse=True)


def test_predict_race_is_deterministic():
    out1, _ = _predict(seen={("a", "b", "c")})
    out2, _ = _predict(seen={("a", "b", "c")})
    assert out1 == out2


def test_predict_race_dnf_risk_drains_a_drivers_trios():
    sure, _ = _predict(p_fin_a=1.0)
    risky, _ = _predict(p_fin_a=0.5)
    assert risky["trio_probs"][("a", "b", "c")] < sure["trio_probs"][("a", "b", "c")]
    # mass moves to trios without a
    assert risky["trio_probs"][("b", "c", "d")] > sure["trio_probs"][("b", "c", "d")]
