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


# --- cache bypass -------------------------------------------------------------


def _capture_quali_pages(monkeypatch):
    calls = []

    def fake_get(url, params):
        calls.append(params)
        return {"MRData": {"total": "1", "RaceTable": {"Races": []}}}

    monkeypatch.setattr(fq, "get", fake_get)
    monkeypatch.setattr(fq.time, "sleep", lambda *_: None)
    return calls


def test_mutable_season_qualifying_bypasses_the_response_cache(monkeypatch):
    """Qualifying drives the post-quali hero, so a cached body holds the grid
    back for an hour after the session."""
    from fetch.api_cache import CACHE_BUSTER

    calls = _capture_quali_pages(monkeypatch)
    fq.fetch_season_races(2026, fresh_data=True)
    assert calls and all(CACHE_BUSTER in p for p in calls)


# --- confirming rounds OpenF1 filled ------------------------------------------


def test_only_fetched_qualifying_rounds_are_confirmed(tmp_path, monkeypatch):
    """A session that came back empty isn't fetched, so its round stays pending."""
    import json

    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fq, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fq, "OUT_PATH", tmp_path / "qualifying.json")
    monkeypatch.setattr(fq.time, "sleep", lambda *_: None)
    committed = [{"season": "2026", "round": "13", "results": []}]
    (tmp_path / "qualifying.json").write_text(json.dumps(committed), encoding="utf-8")

    def fake_season(season, *, fresh_data=False):
        if season != 2026:
            return []
        return [
            dict(_ERGAST_QUALI_RACE, season="2026", round="14"),
            dict(_ERGAST_QUALI_RACE, season="2026", round="15", QualifyingResults=[]),
        ]

    monkeypatch.setattr(fq, "fetch_season_races", fake_season)
    pending = {
        "kind": "qualifying",
        "pending": ["qualifying"],
        "since": "2026-09-12T15:00:00+00:00",
    }
    repository.save_unconfirmed(
        [{"season": "2026", "round": "14", **pending}, {"season": "2026", "round": "15", **pending}]
    )

    assert fq.main([]) == 0
    assert [(u.round, u.pending) for u in repository.load_unconfirmed()] == [("15", ["qualifying"])]


def test_settled_season_qualifying_stays_cacheable(monkeypatch):
    from fetch.api_cache import CACHE_BUSTER

    calls = _capture_quali_pages(monkeypatch)
    fq.fetch_season_races(1994)
    assert calls and not any(CACHE_BUSTER in p for p in calls)
