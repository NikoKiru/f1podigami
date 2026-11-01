"""Tests for the driver→constructor mapping in fetch_constructor_standings.

The round-indexed results endpoint (/{season}/{round}/results.json) can lag the
aggregate feeds for a while right after a race: /results/{pos} already lists the
new round's podium while /{round}/results is still empty. Building the map from
only the latest round would then return {}, switching the constructor overlay
off. The fetch must fall back to the last round that actually returns results
(team assignments are stable within a season, so an earlier round is correct).
"""

from fetch import fetch_constructor_standings as fcs


def _race(*pairs):
    """One Ergast race dict with (driverId, constructorId) result rows."""
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "Results": [
                            {"Driver": {"driverId": d}, "Constructor": {"constructorId": c}}
                            for d, c in pairs
                        ]
                    }
                ]
            }
        }
    }


_EMPTY = {"MRData": {"RaceTable": {"Races": []}}}


def _round_of(url: str) -> int:
    # ".../ergast/f1/{season}/{round}/results.json"
    return int(url.rstrip("/").split("/")[-2])


def test_driver_constructors_falls_back_to_last_non_empty_round(monkeypatch):
    responses = {
        9: _EMPTY,  # round-indexed endpoint still empty just after the race
        8: _race(("russell", "mercedes"), ("leclerc", "ferrari")),
    }
    queried: list[int] = []

    def fake_get(url, params=None):
        rnd = _round_of(url)
        queried.append(rnd)
        return responses[rnd]

    monkeypatch.setattr(fcs, "get", fake_get)
    monkeypatch.setattr(fcs.time, "sleep", lambda *_: None)

    mapping = fcs.fetch_driver_constructors(2026, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    assert mapping == {"russell": "mercedes", "leclerc": "ferrari"}
    assert queried == [9, 8]  # tried the latest first, then fell back exactly once


def test_driver_constructors_uses_latest_round_when_populated(monkeypatch):
    responses = {9: _race(("norris", "mclaren"))}
    queried: list[int] = []

    def fake_get(url, params=None):
        rnd = _round_of(url)
        queried.append(rnd)
        return responses[rnd]

    monkeypatch.setattr(fcs, "get", fake_get)
    monkeypatch.setattr(fcs.time, "sleep", lambda *_: None)

    mapping = fcs.fetch_driver_constructors(2026, [7, 8, 9])

    assert mapping == {"norris": "mclaren"}
    assert queried == [9]  # no fallback when the latest round has results


def test_driver_constructors_empty_when_no_round_has_results(monkeypatch):
    monkeypatch.setattr(fcs, "get", lambda url, params=None: _EMPTY)
    monkeypatch.setattr(fcs.time, "sleep", lambda *_: None)

    assert fcs.fetch_driver_constructors(2026, [1, 2, 3]) == {}


def test_standings_requests_bypass_the_response_cache(monkeypatch):
    """Standings are always the running season, so a cached body is always a
    risk and never a saving."""
    from fetch.api_cache import CACHE_BUSTER

    calls = []

    def fake_get(url, params):
        calls.append(params)
        return {"MRData": {"StandingsTable": {"StandingsLists": []}}}

    monkeypatch.setattr(fcs, "get", fake_get)
    fcs.fetch_standings(2026)
    assert calls and all(CACHE_BUSTER in p for p in calls)


def test_real_standings_are_written_after_a_single_round(monkeypatch):
    """Skipping round 1 left an empty file, which took every car out of the model
    for the whole week before round 2."""
    saved = {}
    row = {
        "points": "25",
        "position": "1",
        "wins": "1",
        "Constructor": {"constructorId": "ferrari", "name": "Ferrari"},
    }
    monkeypatch.setattr(fcs, "season_and_rounds", lambda: (2027, [1]))
    monkeypatch.setattr(fcs, "fetch_standings", lambda season: [row])
    monkeypatch.setattr(fcs, "fetch_driver_constructors", lambda season, rounds: {"a": "ferrari"})
    monkeypatch.setattr(fcs, "save_constructor_standings", saved.update)
    monkeypatch.setattr(fcs.time, "sleep", lambda _: None)
    assert fcs.main() == 0
    assert [c["constructorId"] for c in saved["constructors"]] == ["ferrari"]
    assert saved["driverConstructor"] == {"a": "ferrari"}
