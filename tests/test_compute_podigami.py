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


def test_no_constructor_payload_satisfies_schema(scenario):
    """Off-season (no constructor data) the payload omits constructor/constructorStrength;
    it must still validate, since save_podigami() validates before writing (regression guard)."""
    from datalib import REGISTRY

    podiums, combos, grid = scenario
    res = cp.compute(podiums, combos, grid, constructor_data=None)
    REGISTRY["podigami.json"].validate_python(res)  # must not raise


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


# --- v2 engine path -------------------------------------------------------------


def rr_from(podiums, all_drivers, cid_map=None):
    """Full-classification rows consistent with the podium scenario."""
    out = []
    for r in podiums:
        podium = [r[s]["driverId"] for s in ("p1", "p2", "p3")]
        order = podium + [d for d in all_drivers if d not in podium]
        rows = [
            {
                "driverId": d,
                "constructorId": (cid_map or {}).get(d, "car_" + d),
                "grid": i + 1,
                "position": i + 1,
                "laps": 50,
                "status": "Finished",
            }
            for i, d in enumerate(order)
        ]
        out.append(
            {
                "season": r["season"],
                "round": r["round"],
                "raceName": r["raceName"],
                "date": "",
                "circuitId": "testring",
                "results": rows,
            }
        )
    return out


@pytest.fixture
def scenario_v2(scenario_with_constructors):
    podiums, combos, grid, con = scenario_with_constructors
    drivers = [g["driverId"] for g in grid]
    rres = rr_from(podiums, drivers, con["driverConstructor"])
    return podiums, combos, grid, con, rres


def test_v2_path_engaged_when_race_results_present(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert res["params"]["model"] == "dbpl-v2"
    assert res["params"]["usingQualifying"] is False
    assert res["params"]["nDraws"] == 512
    assert set(cp.model_v2.DEFAULT_PARAMS_V2) <= set(res["params"])


def test_v2_falls_back_to_v1_without_race_results(scenario_v2):
    podiums, combos, grid, con, _ = scenario_v2
    v1 = cp.compute(podiums, combos, grid, constructor_data=con)
    v1_explicit = cp.compute(
        podiums, combos, grid, constructor_data=con, race_results=None, qualifying=None
    )
    assert v1 == v1_explicit
    assert v1["params"]["model"] == "plackett-luce"


def test_v2_candidates_are_unseen_sorted_valid(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert 0.0 <= res["chanceNextRaceNew"] <= 100.0
    cand = {tuple(sorted(c["driverIds"])) for c in res["candidates"]}
    assert ("alf", "bob", "cas") not in cand  # seen 2025 R4
    probs = [c["prob"] for c in res["candidates"]]
    assert probs == sorted(probs, reverse=True)


def test_v2_driver_entries_carry_reliability_fields(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    for d in res["driverForm"]:
        assert 0.0 < d["finishProb"] <= 1.0
        assert d["uncertainty"] > 0.0
        assert d["weight"] > 0.0
    form = {d["driverId"]: d["weight"] for d in res["driverForm"]}
    # alf leads the current season on the road; the rookie eli trails everyone
    assert form["alf"] > form["eli"]


def test_v2_payload_satisfies_schema(scenario_v2):
    from datalib import REGISTRY

    podiums, combos, grid, con, rres = scenario_v2
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    REGISTRY["podigami.json"].validate_python(res)  # must not raise


def test_v2_uses_next_circuit_from_schedule(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    sched = {
        "season": "2025",
        "totalRounds": 6,
        "races": [
            {"round": "5", "circuitId": "testring"},
            {"round": "6", "circuitId": "monaco"},
        ],
    }
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres, schedule=sched)
    assert res["params"]["circuitId"] == "monaco"
    no_sched = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert no_sched["params"]["circuitId"] is None


def test_v2_deterministic(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    r1 = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    r2 = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert r1 == r2


def test_v2_small_grid_yields_no_candidates(scenario_v2):
    podiums, combos, _, con, rres = scenario_v2
    grid = [{"driverId": d, "name": d.title()} for d in ("alf", "bob")]
    res = cp.compute(podiums, combos, grid, constructor_data=con, race_results=rres)
    assert res["candidates"] == []
    assert res["chanceNextRaceNew"] == 0.0


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
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
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
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=[],
        schedule=SCHED_R6,
    )
    withq = cp.compute(
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
    )
    for k in ("chanceNextRaceNew", "candidates", "driverForm", "asOf"):
        assert base[k] == withq[k]


def test_post_quali_deterministic(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    kw = {"constructor_data": con, "race_results": rres, "qualifying": quali, "schedule": SCHED_R6}
    assert cp.compute(podiums, combos, grid, **kw) == cp.compute(podiums, combos, grid, **kw)


# --- grid penalties ---------------------------------------------------------------


def test_apply_grid_penalties_place_drop_shifts_field():
    """A 2-place drop for P1: P2/P3 move up, the penalised car slots in behind."""
    qpos = {"a": 1, "b": 2, "c": 3, "d": 4}
    out = cp._apply_grid_penalties(qpos, [{"driverId": "a", "penaltyPlaces": 2}])
    assert out == {"b": 1, "c": 2, "a": 3, "d": 4}


def test_apply_grid_penalties_penalised_behind_unpenalised_on_same_slot():
    """FIA-style: quali P1 + 2 places targets slot 3, which the unpenalised P3
    car contests after moving up — the penalised car lines up behind it."""
    qpos = {"a": 1, "b": 2, "c": 3}
    out = cp._apply_grid_penalties(qpos, [{"driverId": "a", "penaltyPlaces": 2}])
    assert out == {"b": 1, "c": 2, "a": 3}


def test_apply_grid_penalties_back_of_grid_is_last():
    qpos = {"a": 1, "b": 2, "c": 3, "d": 4}
    out = cp._apply_grid_penalties(qpos, [{"driverId": "b", "backOfGrid": True}])
    assert out == {"a": 1, "c": 2, "d": 3, "b": 4}


def test_apply_grid_penalties_back_of_grid_behind_big_place_penalty():
    """Back-of-grid outranks even a place penalty that overshoots the field."""
    qpos = {"a": 1, "b": 2, "c": 3, "d": 4}
    pens = [{"driverId": "a", "penaltyPlaces": 10}, {"driverId": "b", "backOfGrid": True}]
    out = cp._apply_grid_penalties(qpos, pens)
    assert out == {"c": 1, "d": 2, "a": 3, "b": 4}


def test_apply_grid_penalties_noop_and_unknown_driver():
    qpos = {"a": 1, "b": 2, "c": 3}
    assert cp._apply_grid_penalties(qpos, []) == qpos
    assert cp._apply_grid_penalties(qpos, [{"driverId": "zzz", "penaltyPlaces": 5}]) == qpos


def test_post_quali_grid_penalties_move_grid_positions(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    kw = {"constructor_data": con, "race_results": rres, "qualifying": quali, "schedule": SCHED_R6}
    pens = [
        {
            "season": "2025",
            "round": "6",
            "penalties": [
                {"driverId": "eli", "penaltyPlaces": 3, "backOfGrid": None},
                {"driverId": "bob", "penaltyPlaces": None, "backOfGrid": True},
            ],
        }
    ]
    plain = cp.compute(podiums, combos, grid, **kw)
    pend = cp.compute(podiums, combos, grid, grid_penalties=pens, **kw)

    form = {d["driverId"]: d["gridPosition"] for d in pend["postQuali"]["driverForm"]}
    # quali eli,alf,bob,cas,dan -> eli drops 3 (to slot 4), bob to the back
    assert form == {"alf": 1, "cas": 2, "dan": 3, "eli": 4, "bob": 5}
    # only the causal grid term moves: the prediction changes, the pre-quali block doesn't
    assert pend["postQuali"]["chanceNextRaceNew"] != plain["postQuali"]["chanceNextRaceNew"]
    for k in ("chanceNextRaceNew", "candidates", "driverForm", "asOf"):
        assert pend[k] == plain[k]
    # the payload with penalties applied still satisfies the schema
    from datalib import REGISTRY

    REGISTRY["podigami.json"].validate_python(pend)


def test_post_quali_grid_penalties_other_round_ignored(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    kw = {"constructor_data": con, "race_results": rres, "qualifying": quali, "schedule": SCHED_R6}
    stale = [
        {
            "season": "2025",
            "round": "5",
            "penalties": [{"driverId": "eli", "penaltyPlaces": 3, "backOfGrid": None}],
        }
    ]
    assert cp.compute(podiums, combos, grid, grid_penalties=stale, **kw) == cp.compute(
        podiums, combos, grid, **kw
    )


def test_post_quali_pole_shock_lifts_underdog(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    res = cp.compute(
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
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
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
    )
    form = {d["driverId"]: d for d in res["postQuali"]["driverForm"]}
    assert form["zed_zephyr"]["name"] == "Zed Zephyr"
    assert form["zed_zephyr"]["gridPosition"] == 4


def test_post_quali_needs_three_entrants(scenario_v2):
    podiums, combos, grid, con, rres = scenario_v2
    quali = [q_entry(2025, 6, ["alf", "bob"], con["driverConstructor"])]
    res = cp.compute(
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
    )
    assert res["postQuali"] is None


def test_post_quali_payload_satisfies_schema(scenario_post_quali):
    from datalib import REGISTRY

    podiums, combos, grid, con, rres, quali = scenario_post_quali
    res = cp.compute(
        podiums,
        combos,
        grid,
        constructor_data=con,
        race_results=rres,
        qualifying=quali,
        schedule=SCHED_R6,
    )
    REGISTRY["podigami.json"].validate_python(res)  # must not raise
