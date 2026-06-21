"""Unit tests for the Plackett-Luce model + strength estimator (pure)."""

import pytest

from compute import model


def race(season, rnd, p1, p2, p3):
    def mk(d):
        return {"driverId": d, "name": d.title()}

    return {"season": str(season), "round": str(rnd), "p1": mk(p1), "p2": mk(p2), "p3": mk(p3)}


# --- Plackett-Luce aggregation -----------------------------------------------


def test_pl_set_probs_sum_to_one_over_all_sets():
    pool = ["a", "b", "c", "d", "e"]
    lam = {d: 1.0 + i for i, d in enumerate(pool)}
    probs = model.all_set_probs(lam, pool)
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-9)


def test_equal_strengths_uniform_over_sets():
    pool = ["a", "b", "c", "d"]
    lam = dict.fromkeys(pool, 2.0)
    probs = model.all_set_probs(lam, pool)
    # C(4,3)=4 equally likely sets
    for p in probs.values():
        assert p == pytest.approx(0.25)


def test_single_possible_set_is_certain():
    lam = {"a": 1.0, "b": 2.0, "c": 3.0}
    probs = model.all_set_probs(lam, ["a", "b", "c"])
    assert probs[("a", "b", "c")] == pytest.approx(1.0)


def test_stronger_trio_more_likely():
    pool = ["a", "b", "c", "d"]
    lam = {"a": 5.0, "b": 5.0, "c": 5.0, "d": 0.1}
    probs = model.all_set_probs(lam, pool)
    assert probs[("a", "b", "c")] == max(probs.values())


# --- strength estimator ------------------------------------------------------


def test_no_podiums_sits_at_alpha_floor():
    races = [race(2024, 1, "x", "y", "z")]
    per = model.index_podiums(races)
    lam = model.strengths(per, ["w"], upto=1, current_season=2024)
    assert lam["w"] == pytest.approx(model.DEFAULT_PARAMS["alpha"])


def test_more_recent_podium_outweighs_older():
    races = [race(2024, r, "old", "x", "y") for r in range(1, 4)] + [
        race(2024, r, "new", "x", "y") for r in range(10, 13)
    ]
    per = model.index_podiums(races)
    lam = model.strengths(per, ["old", "new"], upto=len(races), current_season=2024)
    assert lam["new"] > lam["old"]


def test_off_season_decay_shrinks_last_year():
    # same number of podiums, same races-ago, but one set is a season older
    this_year = [race(2025, r, "d", "x", "y") for r in range(1, 4)]
    per = model.index_podiums(this_year)
    lam_now = model.strengths(per, ["d"], upto=3, current_season=2025)["d"]
    last_year = [race(2024, r, "d", "x", "y") for r in range(1, 4)]
    per2 = model.index_podiums(last_year)
    lam_old = model.strengths(per2, ["d"], upto=3, current_season=2025)["d"]
    assert lam_old < lam_now


def test_temper_identity_at_one():
    lam = {"a": 2.0, "b": 3.0}
    assert model.temper(lam, 1.0) == lam


def test_rank_and_new_splits_seen_and_new():
    lam = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 1.0}
    probs = model.all_set_probs(lam, ["a", "b", "c", "d"])
    seen = {("a", "b", "c")}
    ranked, p_new = model.rank_and_new(probs, seen)
    assert ranked[0][1] >= ranked[-1][1]  # sorted desc
    assert p_new == pytest.approx(sum(p for t, p in probs.items() if t not in seen))
