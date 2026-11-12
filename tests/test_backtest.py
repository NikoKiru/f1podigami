"""Tests for the walk-forward backtest: no leakage, determinism, and an
integrity check that the committed evaluation shows a real improvement."""

import json
from pathlib import Path

from compute import backtest, model

DATA = Path(__file__).resolve().parents[1] / "data"


def race(season, rnd, p1, p2, p3):
    def mk(d):
        return {"driverId": d, "name": d.title()}

    return {
        "season": str(season),
        "round": str(rnd),
        "raceName": "GP",
        "p1": mk(p1),
        "p2": mk(p2),
        "p3": mk(p3),
    }


def _active_all(races, drivers):
    return {backtest.season_key(r): set(drivers) for r in races}


def test_no_future_leakage():
    prior = [race(2015, r, "a", "b", "c") for r in range(1, 4)]
    target = race(2016, 1, "a", "b", "z")
    races_a = prior + [target]
    races_b = races_a + [race(2017, 1, "z", "a", "b")]  # a future race
    drivers = ["a", "b", "c", "z"]
    win = (2016, 2016)

    rec_a = backtest.score_window(
        races_a, _active_all(races_a, drivers), backtest.lam_current, backtest.set_probs_pl, win
    )
    rec_b = backtest.score_window(
        races_b, _active_all(races_b, drivers), backtest.lam_current, backtest.set_probs_pl, win
    )
    assert len(rec_a) == 1
    # adding a race AFTER the target must not change the target's prediction
    assert rec_a == rec_b


def test_deterministic():
    races = [race(2015, r, "a", "b", "c") for r in range(1, 4)] + [race(2016, 1, "a", "b", "d")]
    active = _active_all(races, ["a", "b", "c", "d"])
    win = (2016, 2016)
    r1 = backtest.score_window(races, active, backtest.lam_current, backtest.set_probs_pl, win)
    r2 = backtest.score_window(races, active, backtest.lam_current, backtest.set_probs_pl, win)
    assert r1 == r2


def test_summarize_reports_expected_metrics():
    recs = [{"rank": 1, "p_true": 0.5, "sum_sq": 0.5, "q_new": 0.3, "is_new": 1.0}]
    s = backtest.summarize(recs)
    assert {"n", "top1", "top3", "top5", "logLoss", "brierSet", "brierNew"} <= s.keys()
    assert s["top1"] == 1.0


def test_pool_for_combines_active_and_podium_drivers():
    r = race(2016, 1, "a", "b", "z")  # z not in active
    active = {backtest.season_key(r): {"a", "b", "c"}}
    assert backtest.pool_for(r, active) == ["a", "b", "c", "z"]


def test_lam_recent_freq_counts_recent_podiums_only():
    per_driver = {"a": [(0, 2015, 0), (5, 2015, 1), (18, 2015, 2)]}
    pool = ["a", "b"]
    lam = backtest.lam_recent_freq(per_driver, pool, upto=10, _cs=2015)
    # only races with index in [upto-RECENT_WINDOW, upto) = [-10, 10) count: idx 0 and 5
    assert lam["a"] == 0.1 + 2
    assert lam["b"] == 0.1


def test_make_lam_tuned_delegates_to_model_strengths():
    per_driver = {"a": [(0, 2015, 0)]}
    pool = ["a"]
    params = {"halfLife": 4.0}
    fn = backtest.make_lam_tuned(params)
    expected = model.strengths(per_driver, pool, 5, 2015, params)
    assert fn(per_driver, pool, 5, 2015) == expected


def test_set_probs_product_normalizes_to_one():
    lam = {"a": 2.0, "b": 1.0, "c": 1.5, "d": 4.0}
    out = backtest.set_probs_product(lam, list(lam))
    assert abs(sum(out.values()) - 1.0) < 1e-9
    # the highest-weight trio (a, d, and whichever of b/c is larger) should win
    assert max(out, key=out.get) == ("a", "c", "d")


def test_load_reads_and_sorts_races(tmp_path, monkeypatch):
    races_json = [
        race(2016, 2, "a", "b", "c"),
        race(2015, 1, "a", "b", "c"),
    ]
    podiums_path = tmp_path / "podiums.json"
    podiums_path.write_text(json.dumps(races_json), encoding="utf-8")
    driver_races_path = tmp_path / "driver_races.json"
    driver_races_path.write_text(
        json.dumps({"drivers": {"a": {"races": [2015001, 2016002]}}}), encoding="utf-8"
    )
    monkeypatch.setattr(backtest, "PODIUMS_PATH", podiums_path)
    monkeypatch.setattr(backtest, "DRIVER_RACES_PATH", driver_races_path)

    races, active = backtest.load()

    assert [(int(r["season"]), int(r["round"])) for r in races] == [(2015, 1), (2016, 2)]
    assert active == {2015001: {"a"}, 2016002: {"a"}}


def _small_races():
    drivers = ["a", "b", "c", "d"]
    races = []
    for season in (2010, 2011, 2012):
        for r in range(1, 4):
            races.append(race(season, r, "a", "b", "c"))
    races.append(race(2012, 4, "a", "b", "d"))
    active = {backtest.season_key(r): set(drivers) for r in races}
    return races, active


def test_tune_returns_valid_param_dict():
    races, active = _small_races()
    winner = backtest.tune(races, active, (2011, 2012))
    assert set(model.DEFAULT_PARAMS) <= set(winner)
    assert winner["temperature"] in backtest.TEMPS


def test_evaluate_reports_full_ladder():
    races, active = _small_races()
    res = backtest.evaluate(races, active, (2011, 2012))
    names = [name for name, _ in res["ladder"]]
    assert names == [
        "recent-frequency",
        "current (product)",
        "plackett-luce",
        "PL + tuned (chosen)",
    ]
    assert "logLoss" in res["chosen"]
    assert 0.0 <= res["baseRate"] <= 1.0
    assert isinstance(res["calibration"], list)


def test_main_tune_flag_prints_and_returns_zero(monkeypatch, capsys):
    races, active = _small_races()
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: None)
    rc = backtest.main(["--tune"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Best validation params" in out


def test_main_default_writes_eval_and_returns_zero(monkeypatch, capsys):
    races, active = _small_races()
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: None)
    saved = {}
    monkeypatch.setattr(backtest, "save_model_eval", lambda payload: saved.update(payload))

    rc = backtest.main([])

    assert rc == 0
    assert "chosen" in saved
    assert "ladder" in saved
    out = capsys.readouterr().out
    assert "Model params" in out


def test_committed_eval_shows_improvement_over_product():
    """Integrity: the shipped model_eval.json must show the chosen model beating
    the current product baseline on the held-out test window."""
    ev = json.loads((DATA / "model_eval.json").read_text(encoding="utf-8"))
    by = {row["model"]: row for row in ev["ladder"]}
    product = by["current (product)"]
    chosen = by["PL + tuned (chosen)"]
    assert chosen["logLoss"] <= product["logLoss"]  # better proper score
    assert chosen["top5"] >= product["top5"]  # at least as good at ranking


# --- v2 rungs -------------------------------------------------------------------


def _rrow_v2(did, cid, grid, pos, laps=50, status="Finished"):
    return {
        "driverId": did,
        "constructorId": cid,
        "grid": grid,
        "position": pos,
        "laps": laps,
        "status": status,
    }


def _synthetic_v2_history():
    """Two teams, four drivers, the same a>b>c>d order every race for 2 seasons."""
    rresults, trio_keys = [], {}
    order = [("a", "t1"), ("b", "t1"), ("c", "t2"), ("d", "t2")]
    for season in (2010, 2011):
        for rnd in range(1, 16):
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
            trio_keys[(str(season), str(rnd))] = ("a", "b", "c")
    return rresults, trio_keys


def test_score_window_v2_learns_the_dominant_trio():
    rresults, trio_keys = _synthetic_v2_history()
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2)
    recs = backtest.score_window_v2(rresults, {}, trio_keys, (2011, 2011), params)
    assert len(recs) == 15
    assert all(r["is_new"] == 0.0 for r in recs)  # trio was seen in 2010 already
    ll = backtest.metrics.log_loss([r["p_true"] for r in recs])
    # 4 drivers -> 4 possible trios -> uniform logLoss = log 4 = 1.386; the
    # engine must have learned the a>b>c ordering long ago.
    assert ll < 0.9


def test_score_window_v2_is_deterministic():
    rresults, trio_keys = _synthetic_v2_history()
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2)
    r1 = backtest.score_window_v2(rresults, {}, trio_keys, (2011, 2011), params)
    r2 = backtest.score_window_v2(rresults, {}, trio_keys, (2011, 2011), params)
    assert r1 == r2


def test_score_window_v2_rank_pass_ranks_dominant_trio_first():
    rresults, trio_keys = _synthetic_v2_history()
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2)
    recs = backtest.score_window_v2(rresults, {}, trio_keys, (2011, 2011), params, with_rank=True)
    assert recs[-1]["rank"] == 1
    assert recs[-1]["sum_sq"] is not None
    s = backtest.summarize(recs)  # the v1 summariser must accept v2 recs verbatim
    assert s["n"] == 15 and s["top1"] > 0.9


def test_rungs_v2_ablation_ladder_shape():
    names = [name for name, _ in backtest.RUNGS_V2]
    assert names == ["v2 pace", "v2 +attrition", "v2 +chaos", "v2 full", "v2 +adaptive car"]
    by = dict(backtest.RUNGS_V2)
    assert by["v2 full"] == {}
    # The adaptive rung carries the validation-tuned knobs; the shipped default
    # keeps them dormant because the test-window gate rejected them.
    assert by["v2 +adaptive car"] == backtest.ADAPTIVE_CAR
    assert backtest.ADAPTIVE_CAR["con_adapt_gain"] > 0.0
    assert backtest.model_v2.DEFAULT_PARAMS_V2["con_adapt_gain"] == 0.0
    # the pace rung must disable attrition, quali, chaos and wild-race mixing
    pace = by["v2 pace"]
    assert pace["w_attr"] == 0.0 and pace["w_qual"] == 0.0
    assert pace["chaos_eta"] == 0.0 and pace["p_wild"] == 0.0


def test_v2_objective_penalises_wrong_confident_novelty():
    good = [{"p_true": 0.5, "q_new": 0.1, "is_new": 0.0}]
    bad = [{"p_true": 0.5, "q_new": 0.9, "is_new": 0.0}]
    assert backtest.v2_objective(bad) > backtest.v2_objective(good)


# --- post-quali protocol ----------------------------------------------------------


def _q_for(season, rnd, order):
    return {
        "season": str(season),
        "round": str(rnd),
        "results": [
            {"driverId": d, "constructorId": c, "position": i + 1} for i, (d, c) in enumerate(order)
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
    grid = dict(backtest.model_v2.DEFAULT_PARAMS_V2, w_grid=0.4, grid_fit=0.0)
    r0 = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), base, post_quali=True
    )
    r1 = backtest.score_window_v2(
        rresults, quali_map, trio_keys, (2011, 2011), grid, post_quali=True
    )
    p0 = sum(r["p_true"] for r in r0) / len(r0)
    p1 = sum(r["p_true"] for r in r1) / len(r1)
    assert p1 > p0


def _history(starts):
    """(rresults, quali_map, trio_keys) from [(season, rnd, quali order, start order)];
    every race finishes in the order it started."""
    rresults, quali_map, trio_keys = [], {}, {}
    for season, rnd, q_order, start, with_grid in starts:
        rows = [_rrow_v2(d, c, i + 1 if with_grid else 0, i + 1) for i, (d, c) in enumerate(start)]
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
        quali_map[(str(season), str(rnd))] = _q_for(season, rnd, q_order)
        trio_keys[(str(season), str(rnd))] = tuple(sorted(d for d, _ in start[:3]))
    return rresults, quali_map, trio_keys


def _penalty_history(with_grid):
    """The pole-sitter of every round is sent to the back and the finish follows
    the start order, while the qualifying order rotates so long-run ratings
    equalise: only the grid the race really started from says who is on the
    podium. ``with_grid=False`` blanks the grid column of the classification."""
    drivers = [("a", "t1"), ("b", "t1"), ("c", "t2"), ("d", "t2")]
    starts = []
    for season in (2010, 2011):
        for rnd in range(1, 16):
            q_order = drivers[rnd % 4 :] + drivers[: rnd % 4]
            starts.append((season, rnd, q_order, q_order[1:] + q_order[:1], with_grid))
    return _history(starts)


def _mean_p_true(history, **overrides):
    params = dict(backtest.model_v2.DEFAULT_PARAMS_V2, **overrides)
    recs = backtest.score_window_v2(*history, (2011, 2011), params, post_quali=True)
    return sum(r["p_true"] for r in recs) / len(recs)


def test_post_quali_scores_the_grid_the_race_started_from():
    # With the grid column, the penalised pole-sitter is known to start last.
    # Without it the qualifying order stands in, and puts him on pole. Grid-aware
    # learning is off, so the grid can only reach the forecast as its offsets.
    real = _mean_p_true(_penalty_history(True), grid_fit=0.0)
    stand_in = _mean_p_true(_penalty_history(False), grid_fit=0.0)
    assert real > stand_in


def test_grid_fit_stops_the_slot_being_counted_twice():
    # a and b start and finish on the front row all season, c and d behind them.
    # The plain pass credits the front row to the ratings of a and b and then
    # adds the front row again on race day. Then the grid flips: only ratings
    # learned net of the grid can follow it.
    front, back = [("a", "t1"), ("b", "t1")], [("c", "t2"), ("d", "t2")]
    starts = [(2010, rnd, front + back, front + back, True) for rnd in range(1, 16)]
    starts.append((2011, 1, back + front, back + front, True))
    history = _history(starts)
    assert _mean_p_true(history, grid_fit=1.0) > _mean_p_true(history, grid_fit=0.0)


def test_rungs_v2_postquali_shape():
    names = [name for name, _ in backtest.RUNGS_V2_POSTQUALI]
    assert names == [
        "v2 post-quali (ratings)",
        "v2 post-quali +grid",
        "v2 post-quali +grid fit",
    ]
    by = dict(backtest.RUNGS_V2_POSTQUALI)
    assert by["v2 post-quali (ratings)"] == {"w_grid": 0.0}
    # the grid rung is the shipped model with grid-aware learning switched off
    assert by["v2 post-quali +grid"] == {"grid_fit": 0.0}
    assert by["v2 post-quali +grid fit"] == {}
    assert backtest.model_v2.DEFAULT_PARAMS_V2["grid_fit"] > 0.0


def _races_for(trio_keys):
    return [race(int(s), int(r), *trio) for (s, r), trio in sorted(trio_keys.items())]


def test_evaluate_appends_post_quali_rungs_and_gate():
    rresults, quali_map, trio_keys = _quali_informative_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    res = backtest.evaluate(races, active, (2011, 2011), v2_data=(rresults, quali_map))
    names = [name for name, _ in res["ladder"]]
    assert names[-3:] == [
        "v2 post-quali (ratings)",
        "v2 post-quali +grid",
        "v2 post-quali +grid fit",
    ]
    gate = res["postQuali"]
    assert isinstance(gate["gridAccepted"], bool)
    assert isinstance(gate["gridFitAccepted"], bool)
    # the champion is the last rung whose gate held, in order
    if not gate["gridAccepted"]:
        assert gate["champion"] == "v2 post-quali (ratings)"
    elif gate["gridFitAccepted"]:
        assert gate["champion"] == "v2 post-quali +grid fit"
    else:
        assert gate["champion"] == "v2 post-quali +grid"
    # whatever the gates say, the site cites the rung its live params reproduce
    assert gate["served"] == "v2 post-quali +grid fit"
    assert dict(backtest.RUNGS_V2_POSTQUALI)[gate["served"]] == {}
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
    assert set(backtest.V2_GRID_TUNE_GRID) == {"w_grid", "grid_circuit_beta", "grid_fit"}
    for knob, grid in backtest.V2_GRID_TUNE_GRID.items():
        assert winner[knob] in grid
    for k, v in backtest.model_v2.DEFAULT_PARAMS_V2.items():
        if k not in backtest.V2_GRID_TUNE_GRID:
            assert winner[k] == v


def test_grid_tune_grid_reaches_past_the_locked_weight():
    # The first tune locked w_grid at the top of its grid, which hid that the
    # optimum lay beyond it. A locked value on the edge is a grid that is too short.
    locked = backtest.model_v2.DEFAULT_PARAMS_V2
    for knob, grid in backtest.V2_GRID_TUNE_GRID.items():
        assert locked[knob] in grid
    assert max(backtest.V2_GRID_TUNE_GRID["w_grid"]) > locked["w_grid"]
    assert max(backtest.V2_GRID_TUNE_GRID["grid_fit"]) > locked["grid_fit"]


def test_main_names_the_post_quali_champion(monkeypatch, capsys):
    rresults, quali_map, trio_keys = _quali_informative_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: (rresults, quali_map))
    saved = {}
    monkeypatch.setattr(backtest, "save_model_eval", lambda payload: saved.update(payload))

    assert backtest.main([]) == 0

    assert saved["postQualiModel"] == "v2 post-quali +grid fit"
    assert saved["postQualiModel"] in [row["model"] for row in saved["ladder"]]
    assert "gridFitAccepted=" in capsys.readouterr().out


def test_committed_eval_names_a_post_quali_rung_it_carries():
    ev = json.loads((DATA / "model_eval.json").read_text(encoding="utf-8"))
    served = ev.get("postQualiModel")
    if served is not None:  # a file from before the gates named one has none
        assert served in [row["model"] for row in ev["ladder"]]


def test_main_tune_v2_grid_flag_prints_winner(monkeypatch, capsys):
    rresults, quali_map, trio_keys = _quali_informative_history()
    races = _races_for(trio_keys)
    active = _active_all(races, ["a", "b", "c", "d"])
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
    monkeypatch.setattr(backtest, "load_v2", lambda: (rresults, quali_map))
    rc = backtest.main(["--tune-v2-grid"])
    assert rc == 0
    assert "Best grid knobs" in capsys.readouterr().out
