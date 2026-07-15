"""Tests for the schedule fetcher's pure race transform (no network)."""

from fetch import fetch_schedule as fs

RACE_API = {
    "round": "10",
    "raceName": "Belgian Grand Prix",
    "date": "2026-07-19",
    "time": "13:00:00Z",
    "url": "https://en.wikipedia.org/wiki/2026_Belgian_Grand_Prix",
    "Circuit": {
        "circuitId": "spa",
        "circuitName": "Circuit de Spa-Francorchamps",
        "Location": {"lat": "50.4372", "long": "5.97139", "locality": "Spa", "country": "Belgium"},
    },
    "Qualifying": {"date": "2026-07-18", "time": "14:00:00Z"},
}


def test_build_race_carries_qualifying_session():
    entry = fs.build_race(RACE_API, [])
    assert entry["qualifyingDate"] == "2026-07-18"
    assert entry["qualifyingTime"] == "14:00:00Z"


def test_build_race_without_qualifying_yields_none():
    race = {k: v for k, v in RACE_API.items() if k != "Qualifying"}
    entry = fs.build_race(race, [])
    assert entry["qualifyingDate"] is None
    assert entry["qualifyingTime"] is None


def test_build_race_qualifying_date_without_time():
    race = dict(RACE_API, Qualifying={"date": "2026-07-18"})
    entry = fs.build_race(race, [])
    assert entry["qualifyingDate"] == "2026-07-18"
    assert entry["qualifyingTime"] is None


def test_schedule_race_schema_accepts_both_shapes():
    from datalib import ScheduleRace

    legacy = {
        "round": "1",
        "raceName": "GP",
        "date": "2026-03-08",
        "time": "04:00:00Z",
        "circuitId": "x",
        "circuitName": "X",
        "locality": "L",
        "country": "C",
        "lat": "0",
        "long": "0",
        "url": "",
    }
    assert ScheduleRace.model_validate(legacy).qualifyingDate is None
    withq = dict(legacy, qualifyingDate="2026-03-07", qualifyingTime="07:00:00Z")
    assert ScheduleRace.model_validate(withq).qualifyingTime == "07:00:00Z"
