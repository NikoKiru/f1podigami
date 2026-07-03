"""Tests for calendar-year season detection in fetch scripts."""

import datetime
import json  # noqa: F401

from fetch import fetch_constructor_standings as fcs  # noqa: F401
from fetch import fetch_current_drivers as fcd  # noqa: F401
from fetch import fetch_schedule as fs


def test_fetch_schedule_has_no_podiums_dependency():
    assert not hasattr(fs, "current_season"), "current_season() must be removed"
    assert not hasattr(fs, "PODIUMS_PATH"), "PODIUMS_PATH must be removed"


def test_season_and_recent_rounds_returns_calendar_year_with_rounds(tmp_path, monkeypatch):
    podiums = [
        {"season": "2025", "round": "21", "raceName": "Qatar GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2026", "round": "1", "raceName": "Bahrain GP", "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

    year, rounds = fcd.season_and_recent_rounds(today_year=2026)

    assert year == 2026
    assert rounds == [1]


def test_season_and_recent_rounds_falls_back_to_latest_podium_season(tmp_path, monkeypatch):
    # Off-season: the calendar year has no completed rounds yet. Falling back to
    # the latest season that actually has podiums keeps the grid populated all
    # winter instead of wiping current_drivers.json (and the landing hero) empty.
    podiums = [
        {"season": "2025", "round": "20", "raceName": "Vegas GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "21", "raceName": "Qatar GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "19", "raceName": "Brazil GP", "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

    year, rounds = fcd.season_and_recent_rounds(today_year=2026)

    assert year == 2025
    assert rounds == [20, 21, 22]


def test_season_and_recent_rounds_empty_when_no_podiums_at_all(tmp_path, monkeypatch):
    f = tmp_path / "podiums.json"
    f.write_text("[]")
    monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

    year, rounds = fcd.season_and_recent_rounds(today_year=2026)

    assert year == 2026
    assert rounds == []


# --- fetch_schedule.choose_season_races: season rollover -----------------------


def _fake_calendars(calendars: dict[int, list[dict]]):
    return lambda year: calendars.get(year, [])


def test_choose_season_races_keeps_current_season_mid_season():
    cal = {2026: [{"date": "2026-03-08"}, {"date": "2026-11-29"}]}
    season, races = fs.choose_season_races(_fake_calendars(cal), 2026, datetime.date(2026, 7, 1))
    assert (season, races) == (2026, cal[2026])


def test_choose_season_races_looks_ahead_once_season_is_complete():
    # Off-season with next year's calendar published: the site should count down
    # to the next opener instead of saying "season complete" all winter.
    cal = {
        2026: [{"date": "2026-03-08"}, {"date": "2026-11-29"}],
        2027: [{"date": "2027-03-07"}],
    }
    season, races = fs.choose_season_races(_fake_calendars(cal), 2026, datetime.date(2026, 12, 15))
    assert (season, races) == (2027, cal[2027])


def test_choose_season_races_stays_on_complete_season_until_next_published():
    cal = {2026: [{"date": "2026-03-08"}, {"date": "2026-11-29"}]}
    season, races = fs.choose_season_races(_fake_calendars(cal), 2026, datetime.date(2026, 12, 15))
    assert (season, races) == (2026, cal[2026])


def test_choose_season_races_falls_back_to_previous_season_in_early_january():
    # New calendar year, new season's schedule not yet in the API: never write an
    # empty schedule (it breaks the build and the data-integrity CI gate) — fall
    # back to the previous season, which renders as "season complete".
    cal = {2026: [{"date": "2026-03-08"}, {"date": "2026-11-29"}]}
    season, races = fs.choose_season_races(_fake_calendars(cal), 2027, datetime.date(2027, 1, 3))
    assert (season, races) == (2026, cal[2026])


def test_choose_season_races_does_not_look_ahead_on_final_race_day():
    cal = {
        2026: [{"date": "2026-03-08"}, {"date": "2026-11-29"}],
        2027: [{"date": "2027-03-07"}],
    }
    season, races = fs.choose_season_races(_fake_calendars(cal), 2026, datetime.date(2026, 11, 29))
    assert (season, races) == (2026, cal[2026])


def test_season_and_rounds_returns_calendar_year_with_rounds(tmp_path, monkeypatch):
    podiums = [
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2026", "round": "1", "raceName": "Bahrain GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2026", "round": "2", "raceName": "Saudi GP", "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcs, "PODIUMS_PATH", f)

    year, rounds = fcs.season_and_rounds(today_year=2026)

    assert year == 2026
    assert rounds == [1, 2]


def test_season_and_rounds_falls_back_to_latest_podium_season(tmp_path, monkeypatch):
    # Off-season fallback: keep last season's standings (team labels + car
    # overlay) instead of writing an empty constructor_standings.json.
    podiums = [
        {"season": "2025", "round": "21", "raceName": "Qatar GP", "p1": {}, "p2": {}, "p3": {}},
        {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP", "p1": {}, "p2": {}, "p3": {}},
    ]
    f = tmp_path / "podiums.json"
    f.write_text(json.dumps(podiums))
    monkeypatch.setattr(fcs, "PODIUMS_PATH", f)

    year, rounds = fcs.season_and_rounds(today_year=2026)

    assert year == 2025
    assert rounds == [21, 22]


def test_season_and_rounds_empty_when_no_podiums_at_all(tmp_path, monkeypatch):
    f = tmp_path / "podiums.json"
    f.write_text("[]")
    monkeypatch.setattr(fcs, "PODIUMS_PATH", f)

    year, rounds = fcs.season_and_rounds(today_year=2026)

    assert year == 2026
    assert rounds == []
