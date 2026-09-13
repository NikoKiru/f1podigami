"""The OpenF1 fast lane (src/fetch/fetch_openf1.py), replayed from frozen fixtures.

The byte-identical tests are the concrete "no discrepancy" guarantee: for every
2026 round the stewards' check lets through, the rows OpenF1 produces must equal
the rows Jolpica published — so Jolpica's later confirmation changes nothing.
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fetch.fetch_openf1 import build_qualifying, build_race, fill, map_drivers, match_session

FIX = Path(__file__).parent / "fixtures" / "openf1"


def _load(name):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


OPENF1 = _load("openf1_2026.json.gz")
JOLPICA = _load("jolpica_2026.json.gz")
NOW = datetime(2026, 9, 10, tzinfo=UTC)
CURRENT = JOLPICA["current_drivers"]["drivers"]
SCHEDULE = JOLPICA["schedule"]
RACES = {r["round"]: r for r in SCHEDULE["races"]}
HELD = {"6", "9"}  # Monaco: unserved penalties; Silverstone: post-race investigation


class FakeClient:
    """Replays openf1_2026.json.gz through fetch.openf1's interface."""

    def __init__(self, data, broken=()):
        self.data = data
        self.broken = set(broken)

    def sessions(self, year, name):
        return None if "sessions" in self.broken else self.data["sessions"].get(name, [])

    def session_result(self, key):
        return self.data["session_result"].get(str(key))

    def drivers(self, key):
        return self.data["drivers"].get(str(key))

    def race_control(self, key):
        return (
            None if "race_control" in self.broken else self.data["race_control"].get(str(key), [])
        )

    def starting_grid(self, key):
        return self.data["starting_grid"].get(str(key))


def jolpica(dataset, rnd):
    return next(r for r in JOLPICA[dataset] if r["round"] == rnd)


@pytest.mark.parametrize("rnd", [str(r) for r in range(1, 14) if str(r) not in HELD])
def test_race_rows_are_identical_to_jolpicas(rnd):
    built = build_race(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1))
    assert built is not None
    assert built["podium"] == jolpica("podiums", rnd)
    assert built["race"] == jolpica("race_results", rnd)


@pytest.mark.parametrize("rnd", sorted(HELD))
def test_the_stewards_check_holds_monaco_and_silverstone(rnd):
    assert build_race(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1)) is None


@pytest.mark.parametrize("rnd", [str(r) for r in range(1, 14)])
def test_qualifying_rows_match_jolpicas_by_position(rnd):
    built = build_qualifying(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1))
    theirs = sorted(jolpica("qualifying", rnd)["results"], key=lambda r: r["position"])
    if rnd == "4":  # OpenF1 omits Hadjar, who set no time; Jolpica lists him P22
        theirs = [r for r in theirs if r["driverId"] != "hadjar"]
    assert built["entry"]["results"] == theirs


def test_match_session_tolerates_a_moved_start_but_not_another_day():
    moved = [{"session_key": 1, "date_start": "2026-05-03T17:00:00+00:00", "is_cancelled": False}]
    assert match_session(moved, "2026-05-03", "20:00:00Z")["session_key"] == 1  # Miami 2026
    assert match_session(moved, "2026-05-04", "17:00:00Z") is None


def test_match_session_skips_cancelled_and_ambiguous_sessions():
    cancelled = [
        {"session_key": 1, "date_start": "2026-04-12T15:00:00+00:00", "is_cancelled": True}
    ]
    assert match_session(cancelled, "2026-04-12", "15:00:00Z") is None
    two = [
        {"session_key": 1, "date_start": "2026-04-12T15:00:00+00:00"},
        {"session_key": 2, "date_start": "2026-04-12T16:00:00+00:00"},
    ]
    assert match_session(two, "2026-04-12", "15:00:00Z") is None


def test_map_drivers_fails_closed():
    current = [{"driverId": "hulkenberg", "name": "Nico Hülkenberg", "number": "27"}]
    car = {"driver_number": 27, "last_name": "Hulkenberg", "team_name": "Audi"}
    assert map_drivers([car], current) == {
        27: {"driverId": "hulkenberg", "name": "Nico Hülkenberg", "constructorId": "audi"}
    }
    assert map_drivers([{**car, "driver_number": 99}], current) is None  # unknown car
    assert map_drivers([{**car, "last_name": "Bortoleto"}], current) is None  # someone else
    assert map_drivers([{**car, "team_name": "Sauber"}], current) is None  # unknown team


def test_nothing_is_written_while_openf1_is_down():
    client = FakeClient(OPENF1, broken={"sessions"})
    assert build_race(RACES["13"], "2026", CURRENT, NOW, client) is None
    assert build_qualifying(RACES["13"], "2026", CURRENT, NOW, client) is None


def test_nothing_is_written_without_race_control():
    assert (
        build_race(RACES["13"], "2026", CURRENT, NOW, FakeClient(OPENF1, broken={"race_control"}))
        is None
    )


def test_nothing_is_written_inside_the_live_window():
    # Monza's race session ends 15:00Z; OpenF1's free data opens at 15:30Z.
    early = datetime(2026, 9, 6, 15, 20, tzinfo=UTC)
    assert build_race(RACES["13"], "2026", CURRENT, early, FakeClient(OPENF1)) is None


def test_an_unknown_car_writes_nothing():
    current = [d for d in CURRENT if d["driverId"] != "russell"]
    assert build_race(RACES["13"], "2026", current, NOW, FakeClient(OPENF1)) is None


def _datasets(drop_race=None, drop_quali=None):
    def keep(rows, rnd):
        return [dict(r) for r in rows if r["round"] != rnd]

    return (
        keep(JOLPICA["podiums"], drop_race),
        keep(JOLPICA["race_results"], drop_race),
        keep(JOLPICA["qualifying"], drop_quali),
    )


def test_fill_writes_the_newest_race_and_records_it():
    podiums, race_results, qualifying = _datasets(drop_race="13")
    unconfirmed = []
    written = fill(
        SCHEDULE, CURRENT, podiums, race_results, qualifying, unconfirmed, NOW, FakeClient(OPENF1)
    )
    assert written == {"race"}
    assert podiums[-1] == jolpica("podiums", "13")
    assert race_results[-1] == jolpica("race_results", "13")
    assert unconfirmed == [
        {
            "season": "2026",
            "round": "13",
            "kind": "race",
            "pending": ["podiums", "race_results"],
            "since": "2026-09-06T15:00:00+00:00",
        }
    ]


def test_fill_writes_the_newest_qualifying_and_records_it():
    podiums, race_results, qualifying = _datasets(drop_quali="13")
    unconfirmed = []
    written = fill(
        SCHEDULE, CURRENT, podiums, race_results, qualifying, unconfirmed, NOW, FakeClient(OPENF1)
    )
    assert written == {"qualifying"}
    assert qualifying[-1]["round"] == "13"
    assert unconfirmed[0]["kind"] == "qualifying" and unconfirmed[0]["pending"] == ["qualifying"]


def test_fill_leaves_rounds_jolpica_already_has():
    podiums, race_results, qualifying = _datasets()
    assert (
        fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, [], NOW, FakeClient(OPENF1))
        == set()
    )


def test_fill_never_mixes_sources_within_a_round():
    """Jolpica delivered the podium but not the classification: wait for Jolpica."""
    podiums, race_results, qualifying = _datasets()
    race_results = [r for r in race_results if r["round"] != "13"]
    assert (
        fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, [], NOW, FakeClient(OPENF1))
        == set()
    )


def test_main_leaves_the_round_to_jolpica_while_a_data_pr_is_open(monkeypatch):
    """JOLPICA_ONLY (set by update.yml) must stop the fast lane before any data is read."""
    import fetch.fetch_openf1 as fetcher

    def must_not_run(*args, **kwargs):
        raise AssertionError("the fast lane ran although an earlier data PR is open")

    monkeypatch.setenv("JOLPICA_ONLY", "true")
    monkeypatch.setattr(fetcher, "fill", must_not_run)
    monkeypatch.setattr(fetcher, "load_schedule", must_not_run)
    assert fetcher.main([]) == 0


# --- report_filled: the confirmation hand-over's loop-safety signal ---------------


def test_report_filled_writes_the_written_kinds(tmp_path, monkeypatch):
    from fetch.fetch_openf1 import report_filled

    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    report_filled({"race"})
    assert out.read_text(encoding="utf-8") == "filled=race\n"


def test_report_filled_sorts_multiple_kinds(tmp_path, monkeypatch):
    from fetch.fetch_openf1 import report_filled

    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    report_filled({"race", "qualifying"})
    assert out.read_text(encoding="utf-8") == "filled=qualifying,race\n"


def test_report_filled_writes_nothing_when_nothing_was_filled(tmp_path, monkeypatch):
    from fetch.fetch_openf1 import report_filled

    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    report_filled(set())
    assert not out.exists() or out.read_text(encoding="utf-8") == ""


def test_report_filled_without_github_output_does_not_raise(monkeypatch):
    from fetch.fetch_openf1 import report_filled

    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    report_filled({"race"})  # must not raise
