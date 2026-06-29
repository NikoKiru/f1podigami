"""Unit tests for the 'unlikeliest podium that happened' model (pure, no IO)."""

import pytest

from compute import compute_unlikeliest as cu


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


def combos_from(podiums):
    """Mimic count_combos: group podiums into unique trios with count + firstRace."""
    by_key: dict[tuple, dict] = {}
    for r in podiums:
        ids = sorted(r[s]["driverId"] for s in ("p1", "p2", "p3"))
        key = tuple(ids)
        c = by_key.setdefault(key, {"driverIds": list(ids), "count": 0, "races": []})
        c["count"] += 1
        c["races"].append({"season": r["season"], "round": r["round"], "raceName": r["raceName"]})
    out = []
    for c in by_key.values():
        chrono = sorted(c["races"], key=lambda x: (int(x["season"]), int(x["round"])))
        out.append(
            {
                "driverIds": c["driverIds"],
                "count": c["count"],
                "firstRace": chrono[0],
            }
        )
    return out


def _races(name, starts, keys):
    return {"name": name, "starts": starts, "races": list(keys)}


@pytest.fixture
def scenario():
    # ABC podium twice; ABD once (dan is a rare podium-getter).
    podiums = [
        race(2020, 1, "alf", "bob", "cas"),
        race(2020, 2, "alf", "bob", "cas"),
        race(2020, 5, "alf", "bob", "dan"),
    ]
    keys = [2020000 + i for i in range(1, 7)]  # all six started rounds 1..6
    driver_races = {
        "drivers": {
            "alf": _races("Alf", 6, keys),
            "bob": _races("Bob", 6, keys),
            "cas": _races("Cas", 6, keys),
            "dan": _races("Dan", 12, keys),  # 1 podium / 12 starts -> rate ~0.083
        }
    }
    return podiums, combos_from(podiums), driver_races


def ids(entry):
    return tuple(sorted(entry["driverIds"]))


def test_most_unlikely_trio_is_first(scenario):
    podiums, combos, dr = scenario
    res = cu.compute(podiums, combos, dr)
    # ABD: 6 * 0.5 * 0.5 * (1/12) = 0.125  <  ABC: 6 * 0.5 * 0.5 * (2/6) = 0.5
    top = res["trios"][0]
    assert ids(top) == ("alf", "bob", "dan")
    assert top["score"] == pytest.approx(0.125)
    assert top["count"] == 1
    assert top["racesTogether"] == 6


def test_results_ranked_by_score_ascending(scenario):
    podiums, combos, dr = scenario
    res = cu.compute(podiums, combos, dr)
    scores = [e["score"] for e in res["trios"]]
    assert scores == sorted(scores)


def test_happened_race_is_first_occurrence(scenario):
    podiums, combos, dr = scenario
    res = cu.compute(podiums, combos, dr)
    abd = next(e for e in res["trios"] if ids(e) == ("alf", "bob", "dan"))
    assert abd["happened"]["round"] == "5"
    assert abd["happened"]["season"] == "2020"
    abc = next(e for e in res["trios"] if ids(e) == ("alf", "bob", "cas"))
    assert abc["happened"]["round"] == "1"  # earliest of its two races
    assert abc["count"] == 2


def test_per_driver_stats_present_and_rounded(scenario):
    podiums, combos, dr = scenario
    res = cu.compute(podiums, combos, dr)
    for e in res["trios"]:
        assert len(e["perDriver"]) == 3
        for pd in e["perDriver"]:
            assert {"name", "podiums", "starts", "rate"} <= pd.keys()
            assert 0 < pd["rate"] <= 1
            assert round(pd["rate"], 4) == pd["rate"]
        assert round(e["score"], 4) == e["score"]


def test_trio_with_missing_driver_data_is_skipped():
    podiums = [
        race(2020, 1, "alf", "bob", "cas"),
        race(2020, 2, "alf", "bob", "ghost"),  # ghost absent from driver_races
    ]
    keys = [2020001, 2020002]
    dr = {
        "drivers": {
            "alf": _races("Alf", 2, keys),
            "bob": _races("Bob", 2, keys),
            "cas": _races("Cas", 2, keys),
        }
    }
    res = cu.compute(podiums, combos_from(podiums), dr)  # must not raise
    assert all("ghost" not in e["driverIds"] for e in res["trios"])
    assert len(res["trios"]) == 1  # only ABC survives


def test_races_together_floored_to_count():
    # The two podiumed together once, but driver_races lists no shared start
    # (a data gap). racesTogether must floor to count, never 0 -> score > 0.
    podiums = [race(2020, 1, "alf", "bob", "cas")]
    dr = {
        "drivers": {
            "alf": _races("Alf", 5, [2020001]),
            "bob": _races("Bob", 5, [2020002]),  # disjoint from alf/cas
            "cas": _races("Cas", 5, [2020003]),
        }
    }
    res = cu.compute(podiums, combos_from(podiums), dr)
    e = res["trios"][0]
    assert e["racesTogether"] == 1  # floored to count, not 0
    assert e["score"] > 0


def test_top_n_truncates():
    drivers = [f"d{i}" for i in range(5)]
    # five distinct one-off trios sharing two filler drivers
    podiums = [race(2020, i + 1, d, "yy", "zz") for i, d in enumerate(drivers)]
    keys = [2020000 + i for i in range(1, 6)]
    dr = {"drivers": {d: _races(d, 5, keys) for d in drivers + ["yy", "zz"]}}
    res = cu.compute(podiums, combos_from(podiums), dr, top_n=3)
    assert len(res["trios"]) == 3


def test_asof_and_params_reported(scenario):
    podiums, combos, dr = scenario
    res = cu.compute(podiums, combos, dr, top_n=7)
    assert res["params"] == {"topN": 7}
    last = max(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    assert res["asOf"]["round"] == last["round"]
    assert res["asOf"]["season"] == last["season"]
