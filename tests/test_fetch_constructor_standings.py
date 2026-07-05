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
