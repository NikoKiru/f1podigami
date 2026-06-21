"""Tests for the walk-forward backtest: no leakage, determinism, and an
integrity check that the committed evaluation shows a real improvement."""

import json
from pathlib import Path

from compute import backtest

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


def test_committed_eval_shows_improvement_over_product():
    """Integrity: the shipped model_eval.json must show the chosen model beating
    the current product baseline on the held-out test window."""
    ev = json.loads((DATA / "model_eval.json").read_text(encoding="utf-8"))
    by = {row["model"]: row for row in ev["ladder"]}
    product = by["current (product)"]
    chosen = by["PL + tuned (chosen)"]
    assert chosen["logLoss"] <= product["logLoss"]  # better proper score
    assert chosen["top5"] >= product["top5"]  # at least as good at ranking
