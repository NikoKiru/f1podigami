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
    rc = backtest.main(["--tune"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Best validation params" in out


def test_main_default_writes_eval_and_returns_zero(monkeypatch, capsys):
    races, active = _small_races()
    monkeypatch.setattr(backtest, "load", lambda: (races, active))
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
