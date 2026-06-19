"""End-to-end integrity checks on the data the pipeline produces.

These validate that every compute stage stays internally consistent and that
the stages agree with each other (combos derive from podiums, podigami derives
from combos + the current grid, etc.).
"""

from itertools import combinations

import pytest

from conftest import load_data


def trio(ids):
    return tuple(sorted(ids))


# --- podiums -------------------------------------------------------------------

def test_podiums_three_distinct_drivers_per_race():
    for p in load_data("podiums.json"):
        ids = [p[s]["driverId"] for s in ("p1", "p2", "p3")]
        assert len(set(ids)) == 3, f"duplicate podium driver in {p['season']} R{p['round']}"
        assert int(p["round"]) >= 1
        assert p["raceName"].strip()


# --- combos derive from podiums ------------------------------------------------

def test_every_podium_maps_to_one_combo():
    podiums = load_data("podiums.json")
    combos = load_data("combos.json")
    by_key = {trio(c["driverIds"]): c for c in combos}
    assert len(by_key) == len(combos), "combo keys must be unique"
    assert sum(c["count"] for c in combos) == len(podiums)
    for p in podiums:
        k = trio(p[s]["driverId"] for s in ("p1", "p2", "p3"))
        assert k in by_key, f"podium trio {k} missing from combos"


def test_combo_first_last_race_consistent():
    for c in load_data("combos.json"):
        chrono = sorted(c["races"], key=lambda r: (int(r["season"]), int(r["round"])))
        assert c["firstRace"]["raceName"] == chrono[0]["raceName"]
        assert c["lastRace"]["raceName"] == chrono[-1]["raceName"]
        last = chrono[-1]
        assert c["lastRaceKey"] == int(last["season"]) * 1000 + int(last["round"])
        assert c["driverIds"] == sorted(c["driverIds"])


# --- soulmates -----------------------------------------------------------------

def test_soulmates_matrix_square_and_symmetric():
    sm = load_data("soulmates.json")
    n = len(sm["drivers"])
    m = sm["matrix"]
    assert len(m) == n and all(len(row) == n for row in m)
    for i in range(n):
        assert m[i][i] == 0, "no self-pairings on the diagonal"
        for j in range(n):
            assert m[i][j] == m[j][i], "co-podium matrix must be symmetric"
    assert sm["max"] == max(v for row in m for v in row)


def test_soulmates_top_pairs_sorted_within_max():
    sm = load_data("soulmates.json")
    counts = [p["count"] for p in sm["topPairs"]]
    assert counts == sorted(counts, reverse=True)
    assert all(c <= sm["max"] for c in counts)


# --- current grid --------------------------------------------------------------

def test_current_drivers_matches_latest_season():
    podiums = load_data("podiums.json")
    grid = load_data("current_drivers.json")
    latest = max(int(p["season"]) for p in podiums)
    assert grid["season"] == str(latest)
    assert len(grid["drivers"]) >= 10
    for d in grid["drivers"]:
        assert d["driverId"] and d["name"]


# --- podigami derives from combos + grid ---------------------------------------

def test_podigami_headline_is_a_probability():
    pg = load_data("podigami.json")
    assert 0.0 <= pg["chanceNextRaceNew"] <= 100.0
    assert {"alpha", "halfLife", "seasonBoost"} <= pg["params"].keys()


def test_podigami_candidates_are_genuinely_new_and_on_the_grid():
    pg = load_data("podigami.json")
    grid_ids = {d["driverId"] for d in load_data("current_drivers.json")["drivers"]}
    existing = {trio(c["driverIds"]) for c in load_data("combos.json")}
    probs = [c["prob"] for c in pg["candidates"]]
    assert probs == sorted(probs, reverse=True), "candidates must rank by probability"
    for c in pg["candidates"]:
        assert len(c["driverIds"]) == 3 and len(set(c["driverIds"])) == 3
        assert set(c["driverIds"]) <= grid_ids, "candidate uses a non-grid driver"
        assert trio(c["driverIds"]) not in existing, "candidate already happened — not new"
        assert len(c["perDriver"]) == 3 and len(c["names"]) == 3


def test_podigami_driverform_covers_the_grid():
    pg = load_data("podigami.json")
    grid_ids = {d["driverId"] for d in load_data("current_drivers.json")["drivers"]}
    form_ids = {d["driverId"] for d in pg["driverForm"]}
    assert form_ids == grid_ids
    weights = [d["weight"] for d in pg["driverForm"]]
    assert weights == sorted(weights, reverse=True)


def test_podigami_by_season_accounts_for_every_combo():
    pg = load_data("podigami.json")
    combos = load_data("combos.json")
    assert sum(pg["seasonCounts"].values()) == len(combos)
    assert set(pg["bySeason"]) == set(pg["seasonCounts"])
    for season, entries in pg["bySeason"].items():
        assert len(entries) == pg["seasonCounts"][season]
        for e in entries:
            assert len(e["driverIds"]) == 3
            assert {"round", "raceName"} <= e["firstRace"].keys()


def test_podigami_season_range_matches_history():
    pg = load_data("podigami.json")
    seasons = [int(p["season"]) for p in load_data("podiums.json")]
    assert pg["seasonRange"] == [min(seasons), max(seasons)]
    assert pg["currentSeason"] == str(max(seasons))
    assert pg["asOf"]["season"] == pg["currentSeason"]
