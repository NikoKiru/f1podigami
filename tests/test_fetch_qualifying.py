"""Tests for the qualifying-classification fetcher (model v2 raw input)."""

from fetch import fetch_qualifying as fq

_ERGAST_QUALI_RACE = {
    "season": "1994",
    "round": "1",
    "raceName": "Brazilian Grand Prix",
    "QualifyingResults": [
        {
            "number": "2",
            "position": "1",
            "Driver": {"driverId": "senna", "givenName": "Ayrton", "familyName": "Senna"},
            "Constructor": {"constructorId": "williams", "name": "Williams"},
            "Q1": "1:15.962",
        },
        {
            "number": "5",
            "position": "2",
            "Driver": {"driverId": "michael_schumacher", "givenName": "M", "familyName": "S"},
            "Constructor": {"constructorId": "benetton", "name": "Benetton"},
            "Q1": "1:16.290",
        },
    ],
}


def test_quali_entry_maps_contract_shape():
    entry = fq.quali_entry(_ERGAST_QUALI_RACE)
    assert entry == {
        "season": "1994",
        "round": "1",
        "results": [
            {"driverId": "senna", "constructorId": "williams", "position": 1},
            {"driverId": "michael_schumacher", "constructorId": "benetton", "position": 2},
        ],
    }


def test_quali_entry_tolerates_missing_results():
    entry = fq.quali_entry({"season": "1994", "round": "2"})
    assert entry == {"season": "1994", "round": "2", "results": []}


def test_merge_entries_replaces_refetched_and_sorts_numerically():
    old = {"season": "2025", "round": "1", "results": [{"x": 1}]}
    fresh = {"season": "2025", "round": "1", "results": []}
    r10 = {"season": "2025", "round": "10", "results": []}
    r2 = {"season": "2025", "round": "2", "results": []}

    merged = fq.merge_entries([old, r10], [fresh, r2])
    assert merged == [fresh, r2, r10]
