"""Tests for the full-race-classification fetcher (model v2 raw input)."""

from fetch import fetch_race_results as frr

_ERGAST_RACE = {
    "season": "1950",
    "round": "1",
    "raceName": "British Grand Prix",
    "date": "1950-05-13",
    "Circuit": {"circuitId": "silverstone", "circuitName": "Silverstone Circuit"},
    "Results": [
        {
            "number": "2",
            "position": "1",
            "positionText": "1",
            "points": "9",
            "Driver": {"driverId": "farina", "givenName": "Nino", "familyName": "Farina"},
            "Constructor": {"constructorId": "alfa", "name": "Alfa Romeo"},
            "grid": "1",
            "laps": "70",
            "status": "Finished",
        },
        {
            "number": "5",
            "position": "12",
            "positionText": "R",
            "points": "0",
            "Driver": {"driverId": "leslie_johnson", "givenName": "L", "familyName": "Johnson"},
            "Constructor": {"constructorId": "erf", "name": "ERA"},
            "grid": "0",
            "laps": "2",
            "status": "Supercharger",
        },
        {
            "number": "7",
            "position": "13",
            "positionText": "D",
            "points": "0",
            "Driver": {"driverId": "cheater", "givenName": "C", "familyName": "Heater"},
            "Constructor": {"constructorId": "erf", "name": "ERA"},
            "grid": "4",
            "laps": "70",
            "status": "Disqualified",
        },
    ],
}


def test_race_entry_maps_contract_shape():
    entry = frr.race_entry(_ERGAST_RACE)
    assert entry["season"] == "1950"
    assert entry["round"] == "1"
    assert entry["raceName"] == "British Grand Prix"
    assert entry["date"] == "1950-05-13"
    assert entry["circuitId"] == "silverstone"

    finisher, retiree, dsq = entry["results"]
    assert finisher == {
        "driverId": "farina",
        "constructorId": "alfa",
        "grid": 1,
        "position": 1,
        "laps": 70,
        "status": "Finished",
    }
    # a retirement keeps its row: grid 0 (pit-lane/unknown), laps done, verbatim status
    assert retiree["position"] is None
    assert retiree["grid"] == 0
    assert retiree["laps"] == 2
    assert retiree["status"] == "Supercharger"
    # non-numeric positionText (DSQ) is preserved as position None with status verbatim
    assert dsq["position"] is None
    assert dsq["status"] == "Disqualified"


def test_accumulate_page_concatenates_results_split_across_pages():
    """Ergast pages by result *row*, so one race's Results can span two pages."""
    merged: dict = {}
    page1 = [dict(_ERGAST_RACE, Results=_ERGAST_RACE["Results"][:2])]
    page2 = [dict(_ERGAST_RACE, Results=_ERGAST_RACE["Results"][2:])]
    frr.accumulate_page(merged, page1)
    frr.accumulate_page(merged, page2)
    (race,) = merged.values()
    assert [r["Driver"]["driverId"] for r in race["Results"]] == [
        "farina",
        "leslie_johnson",
        "cheater",
    ]


def test_merge_entries_replaces_refetched_races_and_keeps_older_seasons():
    old_1950 = {"season": "1950", "round": "1", "raceName": "Old", "results": []}
    old_2025 = {"season": "2025", "round": "1", "raceName": "Stale", "results": []}
    fresh_2025 = {"season": "2025", "round": "1", "raceName": "Fresh", "results": []}
    new_2025 = {"season": "2025", "round": "2", "raceName": "New", "results": []}

    merged = frr.merge_entries([old_1950, old_2025], [fresh_2025, new_2025])

    assert [(r["season"], r["round"], r["raceName"]) for r in merged] == [
        ("1950", "1", "Old"),
        ("2025", "1", "Fresh"),
        ("2025", "2", "New"),
    ]


def test_merge_entries_sorts_numerically_not_lexically():
    r2 = {"season": "2025", "round": "2", "results": []}
    r10 = {"season": "2025", "round": "10", "results": []}
    assert frr.merge_entries([r10], [r2]) == [r2, r10]
