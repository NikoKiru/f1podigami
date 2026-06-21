"""Unit tests for the podigami prediction model (pure compute, no IO)."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from compute import compute_podigami as cp  # noqa: E402


def race(season, rnd, p1, p2, p3, name="Test GP"):
    def mk(d):
        return {"driverId": d, "name": d.title()}

    return {
        "season": str(season),
        "round": str(rnd),
        "raceName": name,
        "p1": mk(p1),
        "p2": mk(p2),
        "p3": mk(p3),
    }


def combos_from(podiums):
    """Mimic count_combos.py just enough for the bySeason grouping."""
    agg = {}
    for r in podiums:
        ids = tuple(sorted(r[s]["driverId"] for s in ("p1", "p2", "p3")))
        e = agg.setdefault(ids, {"driverIds": list(ids), "races": []})
        e["races"].append({"season": r["season"], "round": r["round"], "raceName": r["raceName"]})
    out = []
    for ids, e in agg.items():
        chrono = sorted(e["races"], key=lambda x: (int(x["season"]), int(x["round"])))
        out.append(
            {
                "drivers": [d.title() for d in ids],
                "driverIds": e["driverIds"],
                "count": len(chrono),
                "firstRace": chrono[0],
                "lastRace": chrono[-1],
            }
        )
    return out


@pytest.fixture
def scenario():
    # alf/bob/cas are recent regulars; dan only podiumed long ago; eli is a
    # never-podiumed rookie on the grid.
    podiums = []
    for rnd in range(1, 6):  # old season: dan dominates
        podiums.append(race(2024, rnd, "dan", "alf", "bob"))
    # current season: alf/bob/cas trade podiums, never all three together
    podiums += [
        race(2025, 1, "alf", "bob", "dan"),
        race(2025, 2, "alf", "cas", "bob"),
        race(2025, 3, "bob", "cas", "alf"),
        race(2025, 4, "alf", "bob", "cas"),  # alf+bob+cas HAS happened -> seen
        race(2025, 5, "cas", "alf", "bob"),
    ]
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob", "cas", "dan", "eli")]
    return podiums, combos_from(podiums), grid


def test_all_trio_probabilities_sum_to_one(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    # Reconstruct total probability mass over every trio (new + already-seen).
    # P(new) + P(seen) must be 1, so P(new) must be a valid probability.
    assert 0.0 <= res["chanceNextRaceNew"] <= 100.0


def test_chance_is_a_probability(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    assert 0.0 <= res["chanceNextRaceNew"] <= 100.0


def test_recent_form_outranks_stale_history(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    form = {d["driverId"]: d["weight"] for d in res["driverForm"]}
    # alf podiumed all over the current season; dan only in the old season.
    assert form["alf"] > form["dan"]
    # the never-podiumed rookie sits at the alpha floor, below everyone active.
    assert form["eli"] == pytest.approx(cp.model.DEFAULT_PARAMS["alpha"])
    assert form["eli"] < form["cas"]


def test_seen_trio_excluded_and_new_trio_present(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    cand = {tuple(sorted(c["driverIds"])) for c in res["candidates"]}
    # alf+bob+cas already shared a podium (2025 R4) -> not a candidate.
    assert tuple(sorted(("alf", "bob", "cas"))) not in cand
    # alf+bob+cas+... a brand-new trio with the rookie should be offered.
    assert tuple(sorted(("alf", "bob", "eli"))) in cand


def test_candidate_probabilities_descending(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    probs = [c["prob"] for c in res["candidates"]]
    assert probs == sorted(probs, reverse=True)


def test_driver_entries_carry_id_and_constructor_id(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    # driverForm entries expose driverId + constructorId (needed by the
    # broadcast renderer to join codes/numbers and team colours)
    for d in res["driverForm"]:
        assert "driverId" in d
        assert "constructorId" in d  # "" when no constructor data
    # candidate perDriver entries carry the same join keys
    for c in res["candidates"]:
        for p in c["perDriver"]:
            assert "driverId" in p
            assert "constructorId" in p


def test_constructor_id_populated_with_standings(scenario_with_constructors):
    podiums, combos, grid, con = scenario_with_constructors
    res = cp.compute(podiums, combos, grid, constructor_data=con)
    form = {d["driverId"]: d for d in res["driverForm"]}
    assert form["alf"]["constructorId"] == "teamA"
    assert form["cas"]["constructorId"] == "teamB"


def test_by_season_groups_debut_trios(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid)
    # every combo's debut lands in exactly one season bucket
    assert sum(res["seasonCounts"].values()) == len(combos)
    assert set(res["bySeason"]) == set(res["seasonCounts"])


# --- edge cases ---------------------------------------------------------------


def test_grid_smaller_than_three_yields_no_candidates(scenario):
    podiums, combos, _ = scenario
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob")]
    res = cp.compute(podiums, combos, grid)
    assert res["candidates"] == []
    assert res["chanceNextRaceNew"] == 0.0
    assert res["gridSize"] == 2


def test_single_unseen_trio_is_certain():
    # a 3-driver grid whose trio has never appeared -> the next new combo is certain
    podiums = [race(2025, 1, "alf", "bob", "dan")]
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob", "cas")]
    res = cp.compute(podiums, combos_from(podiums), grid)
    assert res["chanceNextRaceNew"] == pytest.approx(100.0)
    assert tuple(sorted(res["candidates"][0]["driverIds"])) == ("alf", "bob", "cas")


def test_single_seen_trio_is_impossible():
    # the only possible trio on the grid has already happened -> 0% new
    podiums = [race(2025, 1, "alf", "bob", "cas")]
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob", "cas")]
    res = cp.compute(podiums, combos_from(podiums), grid)
    assert res["chanceNextRaceNew"] == pytest.approx(0.0)
    assert res["candidates"] == []


# --- constructor strength -----------------------------------------------------


def _con_data(season, constructors, driver_map):
    return {
        "season": str(season),
        "round": "5",
        "constructors": [
            {"constructorId": cid, "name": cid.title(), "points": pts, "position": i + 1, "wins": 0}
            for i, (cid, pts) in enumerate(constructors)
        ],
        "driverConstructor": driver_map,
    }


@pytest.fixture
def scenario_with_constructors(scenario):
    podiums, combos, grid = scenario
    con = _con_data(
        2025,
        [("teamA", 200), ("teamB", 100), ("teamC", 0)],
        {"alf": "teamA", "bob": "teamA", "cas": "teamB", "dan": "teamB", "eli": "teamC"},
    )
    return podiums, combos, grid, con


def test_constructor_boosts_top_team(scenario_with_constructors):
    podiums, combos, grid, con = scenario_with_constructors
    res_no = cp.compute(podiums, combos, grid, constructor_data=None)
    res_con = cp.compute(podiums, combos, grid, constructor_data=con)
    form_no = {d["driverId"]: d["weight"] for d in res_no["driverForm"]}
    form_con = {d["driverId"]: d["weight"] for d in res_con["driverForm"]}
    # alf is on teamA (200 pts, top); with constructors his weight should be higher
    assert form_con["alf"] > form_no["alf"]
    # eli is on teamC (0 pts); weight unchanged (multiplier = 1.0)
    assert form_con["eli"] == pytest.approx(form_no["eli"])


def test_constructor_data_surfaces_in_output(scenario_with_constructors):
    podiums, combos, grid, con = scenario_with_constructors
    res = cp.compute(podiums, combos, grid, constructor_data=con)
    assert res["params"]["usingConstructors"] is True
    form = {d["driverId"]: d for d in res["driverForm"]}
    assert form["alf"]["constructor"] == "Teama"
    assert form["alf"]["constructorStrength"] == pytest.approx(1.0)
    assert form["eli"]["constructorStrength"] == pytest.approx(0.0)


def test_constructor_preserves_probability_validity(scenario_with_constructors):
    podiums, combos, grid, con = scenario_with_constructors
    res = cp.compute(podiums, combos, grid, constructor_data=con)
    assert 0.0 <= res["chanceNextRaceNew"] <= 100.0


def test_no_constructor_data_falls_back(scenario):
    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid, constructor_data=None)
    assert res["params"]["usingConstructors"] is False
    form = res["driverForm"][0]
    assert "constructor" not in form
    assert "constructorStrength" not in form


def test_wrong_season_constructor_data_ignored(scenario):
    podiums, combos, grid = scenario
    con = _con_data(2020, [("teamA", 200)], {"alf": "teamA"})
    res = cp.compute(podiums, combos, grid, constructor_data=con)
    assert res["params"]["usingConstructors"] is False


def test_empty_constructors_list_ignored(scenario):
    podiums, combos, grid = scenario
    con = {"season": "2025", "round": "5", "constructors": [], "driverConstructor": {}}
    res = cp.compute(podiums, combos, grid, constructor_data=con)
    assert res["params"]["usingConstructors"] is False


def test_constructor_overlay_lifts_stronger_team_more():
    """The live car overlay lifts a top-team driver more than a weaker-team one
    (exact factors blur because of the teammate 'halo' blend)."""
    podiums = [
        race(2025, 1, "alf", "bob", "cas"),
        race(2025, 2, "alf", "bob", "cas"),
        race(2025, 3, "alf", "cas", "bob"),
    ]
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob", "cas")]
    con = _con_data(
        2025, [("teamA", 200), ("teamB", 50)], {"alf": "teamA", "bob": "teamA", "cas": "teamB"}
    )
    res_no = cp.compute(podiums, combos_from(podiums), grid, constructor_data=None)
    res_con = cp.compute(podiums, combos_from(podiums), grid, constructor_data=con)
    form_no = {d["driverId"]: d["weight"] for d in res_no["driverForm"]}
    form_con = {d["driverId"]: d["weight"] for d in res_con["driverForm"]}
    lift = {d: form_con[d] / form_no[d] for d in ("alf", "cas")}
    # both lifted above baseline, and the top team (teamA) is lifted more than teamB
    assert lift["alf"] > 1.0 and lift["cas"] > 1.0
    assert lift["alf"] > lift["cas"]
