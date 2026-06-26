"""Tests for calendar-year season detection in fetch scripts."""

import json  # noqa: F401

from fetch import fetch_constructor_standings as fcs  # noqa: F401
from fetch import fetch_current_drivers as fcd  # noqa: F401
from fetch import fetch_schedule as fs


def test_fetch_schedule_has_no_podiums_dependency():
    assert not hasattr(fs, "current_season"), "current_season() must be removed"
    assert not hasattr(fs, "PODIUMS_PATH"), "PODIUMS_PATH must be removed"


def test_season_and_recent_rounds_returns_calendar_year_with_rounds(tmp_path, monkeypatch):
    podiums = [
        {"season": "2025", "round": "21", "raceName": "Qatar GP",
         "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
         "p1": {}, "p2": {}, "p3": {}},
        {"season": "2026", "round": "1", "raceName": "Bahrain GP",
         "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

    year, rounds = fcd.season_and_recent_rounds(today_year=2026)

    assert year == 2026
    assert rounds == [1]


def test_season_and_recent_rounds_empty_when_no_current_year_rounds(tmp_path, monkeypatch):
    podiums = [
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
         "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

    year, rounds = fcd.season_and_recent_rounds(today_year=2026)

    assert year == 2026
    assert rounds == []
