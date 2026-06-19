"""Unit tests for the 'most overdue podium' model (pure compute, no IO)."""

import pytest

from compute import compute_overdue as co


def race(season, rnd, p1, p2, p3):
    mk = lambda d: {"driverId": d, "name": d.title()}
    return {"season": str(season), "round": str(rnd), "raceName": "GP",
            "p1": mk(p1), "p2": mk(p2), "p3": mk(p3)}


def combos_from(podiums):
    keys = {}
    for r in podiums:
        t = tuple(sorted(r[s]["driverId"] for s in ("p1", "p2", "p3")))
        keys.setdefault(t, {"driverIds": list(t)})
    return list(keys.values())


@pytest.fixture
def scenario():
    # alf/bob/cas overlap every race and podium often; dan only early; eli never overlaps.
    podiums = [
        race(2020, 1, "alf", "bob", "dan"),   # the trio alf+bob+dan HAS happened
        race(2020, 2, "alf", "bob", "yy"),
        race(2020, 3, "alf", "bob", "yy"),
        race(2020, 4, "alf", "cas", "yy"),
        race(2020, 5, "alf", "cas", "yy"),
        race(2020, 6, "bob", "cas", "yy"),
        race(2020, 100, "eli", "yy", "zz"),
        race(2020, 101, "eli", "yy", "zz"),
    ]
    # podium counts: alf5 bob4 cas3 dan1 eli2
    driver_races = {"drivers": {
        "alf": {"name": "Alf", "starts": 10, "races": [2020000 + i for i in range(1, 11)]},
        "bob": {"name": "Bob", "starts": 10, "races": [2020000 + i for i in range(1, 11)]},
        "cas": {"name": "Cas", "starts": 10, "races": [2020000 + i for i in range(1, 11)]},
        "dan": {"name": "Dan", "starts": 3,  "races": [2020001, 2020002, 2020003]},
        "eli": {"name": "Eli", "starts": 4,  "races": [2020100, 2020101, 2020102, 2020103]},
    }}
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob", "cas")]
    return podiums, combos_from(podiums), grid, driver_races


def ids(entry):
    return tuple(sorted(entry["driverIds"]))


def test_top_all_time_entry_score_and_overlap(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    top = res["allTime"][0]
    assert ids(top) == ("alf", "bob", "cas")
    assert top["racesTogether"] == 10
    # 10 * (5/10) * (4/10) * (3/10) = 0.6
    assert top["score"] == pytest.approx(10 * 0.5 * 0.4 * 0.3)


def test_existing_trio_excluded(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    assert ("alf", "bob", "dan") not in {ids(e) for e in res["allTime"]}


def test_non_overlapping_trio_excluded(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    # any trio containing eli has zero shared races -> never listed
    assert all("eli" not in e["driverIds"] for e in res["allTime"])


def test_results_ranked_by_score_desc(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    scores = [e["score"] for e in res["allTime"]]
    assert scores == sorted(scores, reverse=True)


def test_per_driver_stats_present(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    for e in res["allTime"]:
        assert len(e["perDriver"]) == 3
        for pd in e["perDriver"]:
            assert {"name", "podiums", "starts", "rate"} <= pd.keys()
            assert 0 <= pd["rate"] <= 1


def test_current_grid_list_only_uses_grid_drivers(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    grid_ids = {"alf", "bob", "cas"}
    assert res["currentGrid"], "expected at least one current-grid candidate"
    for e in res["currentGrid"]:
        assert set(e["driverIds"]) <= grid_ids


# --- additional edge cases ----------------------------------------------------

def _races(*keys):
    return {"name": "X", "starts": max(len(keys), 1), "races": list(keys)}


def test_zero_podium_driver_makes_score_zero_and_is_excluded():
    # cas never podiums -> rate 0 -> the only possible trio scores 0 -> dropped.
    podiums = [race(2020, 1, "alf", "bob", "yy"), race(2020, 2, "alf", "bob", "zz")]
    dr = {"drivers": {
        "alf": _races(2020001, 2020002, 2020003),
        "bob": _races(2020001, 2020002, 2020003),
        "cas": _races(2020001, 2020002, 2020003),  # starts 3, 0 podiums
    }}
    res = co.compute(podiums, combos_from(podiums), [], dr)
    assert res["allTime"] == []


def test_top_n_truncates_the_list():
    # 5 mutually overlapping podium drivers -> C(5,3)=10 candidate trios.
    drivers = ["d1", "d2", "d3", "d4", "d5"]
    podiums = [race(2020, i + 1, d, "yy", "zz") for i, d in enumerate(drivers)]
    keys = [2020001, 2020002, 2020003, 2020004, 2020005]
    dr = {"drivers": {d: {"name": d, "starts": 5, "races": keys} for d in drivers}}
    res = co.compute(podiums, combos_from(podiums), [], dr, top_n=3)
    assert len(res["allTime"]) == 3


def test_grid_driver_missing_race_data_is_skipped(scenario):
    podiums, combos, grid, dr = scenario
    grid = grid + [{"driverId": "ghost", "name": "Ghost"}]  # not in driver_races
    res = co.compute(podiums, combos, grid, dr)            # must not raise
    assert all("ghost" not in e["driverIds"] for e in res["currentGrid"])


def test_asof_and_params_reported(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr, pool_n=42, top_n=7)
    assert res["params"] == {"poolN": 42, "topN": 7}
    last = max(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    assert res["asOf"]["round"] == last["round"]
    assert res["asOf"]["season"] == last["season"]


def test_scores_and_rates_are_rounded(scenario):
    podiums, combos, grid, dr = scenario
    res = co.compute(podiums, combos, grid, dr)
    for e in res["allTime"]:
        assert round(e["score"], 4) == e["score"]
        for pd in e["perDriver"]:
            assert round(pd["rate"], 4) == pd["rate"]
