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
