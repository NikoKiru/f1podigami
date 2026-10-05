"""F1's official starting grid (src/fetch/fetch_starting_grid.py), replayed from frozen
OpenF1 fixtures.

The real-data test is the "no discrepancy" guarantee. For every 2026 round the
fixtures cover, the grid built from OpenF1 equals the one the race actually
started from, as Jolpica recorded it: grid slot and team, for every car.
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fetch import fetch_starting_grid as fsg

FIX = Path(__file__).parent / "fixtures" / "openf1"


def _load(name):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


OPENF1 = _load("openf1_2026.json.gz")
JOLPICA = _load("jolpica_2026.json.gz")
CURRENT = JOLPICA["current_drivers"]["drivers"]
RACES = {r["round"]: r for r in JOLPICA["schedule"]["races"]}
R1_QUALI_KEY = "11230"


class FakeClient:
    """Replays openf1_2026.json.gz through fetch.openf1's interface."""

    def __init__(self, grids=None, drivers=None, sessions=None):
        self.grids = OPENF1["starting_grid"] if grids is None else grids
        self.entrants = OPENF1["drivers"] if drivers is None else drivers
        self.all_sessions = OPENF1["sessions"] if sessions is None else sessions

    def sessions(self, year, name):
        return self.all_sessions.get(name, [])

    def drivers(self, key):
        return self.entrants.get(str(key))

    def starting_grid(self, key):
        return self.grids.get(str(key))


def r1_rows():
    """Round 1's OpenF1 grid rows, copied so a test can break them."""
    return [dict(row) for row in OPENF1["starting_grid"][R1_QUALI_KEY]]


def with_r1_rows(rows):
    return FakeClient(grids={**OPENF1["starting_grid"], R1_QUALI_KEY: rows})


def build_r1(client):
    return fsg.build_grid(RACES["1"], "2026", CURRENT, client)


# --- the grid itself -----------------------------------------------------------------


@pytest.mark.parametrize("rnd", [str(r) for r in range(1, 14)])
def test_the_grid_is_the_one_the_race_started_from(rnd):
    built = fsg.build_grid(RACES[rnd], "2026", CURRENT, FakeClient())
    started = next(r for r in JOLPICA["race_results"] if r["round"] == rnd)
    assert (built["season"], built["round"]) == ("2026", rnd)
    assert {g["driverId"]: (g["position"], g["constructorId"]) for g in built["grid"]} == {
        row["driverId"]: (row["grid"], row["constructorId"]) for row in started["results"]
    }
    assert [g["position"] for g in built["grid"]] == list(range(1, 23))


def test_drivers_without_a_lap_time_are_on_the_grid():
    """Australia 2026: Verstappen, Sainz and Stroll set no time but started 20th-22nd."""
    slots = {g["driverId"]: g["position"] for g in build_r1(FakeClient())["grid"]}
    assert (slots["max_verstappen"], slots["sainz"], slots["stroll"]) == (20, 21, 22)


# --- fail closed ---------------------------------------------------------------------


def test_nothing_without_a_matching_qualifying_session():
    assert build_r1(FakeClient(sessions={})) is None


def test_nothing_before_openf1_publishes_the_grid():
    assert build_r1(FakeClient(grids={})) is None
    assert build_r1(with_r1_rows([])) is None


def test_nothing_when_the_entrants_cannot_be_read():
    assert build_r1(FakeClient(drivers={})) is None


def test_an_unknown_car_fails_closed():
    rows = r1_rows()
    rows[0]["driver_number"] = 999
    assert build_r1(with_r1_rows(rows)) is None


def test_a_missing_position_fails_closed():
    rows = r1_rows()
    rows[0]["position"] = None
    assert build_r1(with_r1_rows(rows)) is None


def test_a_gap_in_the_grid_fails_closed():
    rows = r1_rows()
    rows[-1]["position"] = 30
    assert build_r1(with_r1_rows(rows)) is None


def test_a_repeated_slot_fails_closed():
    rows = r1_rows()
    rows[1]["position"] = rows[0]["position"]
    assert build_r1(with_r1_rows(rows)) is None


def test_a_grid_missing_a_qualifier_fails_closed():
    """Positions 1..21 still run cleanly, but one car that qualified has no slot."""
    rows = sorted(r1_rows(), key=lambda r: r["position"])[:-1]
    assert build_r1(with_r1_rows(rows)) is None


# --- what is new, and where it goes ----------------------------------------------------


def test_a_grid_is_fresh_when_none_is_committed():
    assert fsg.fresh_grid(RACES["1"], "2026", CURRENT, [], FakeClient()) == build_r1(FakeClient())


def test_an_unchanged_grid_is_not_fresh():
    committed = build_r1(FakeClient())
    assert fsg.fresh_grid(RACES["1"], "2026", CURRENT, [committed], FakeClient()) is None


def test_a_revised_grid_is_fresh():
    """Race morning: the committed Saturday grid differs from OpenF1's."""
    built = build_r1(FakeClient())
    saturday = {**built, "grid": [dict(g) for g in built["grid"]]}
    first, second = saturday["grid"][0], saturday["grid"][1]
    first["driverId"], second["driverId"] = second["driverId"], first["driverId"]
    assert fsg.fresh_grid(RACES["1"], "2026", CURRENT, [saturday], FakeClient()) == built


def test_another_rounds_grid_does_not_count():
    other = {**build_r1(FakeClient()), "round": "2"}
    assert fsg.fresh_grid(RACES["1"], "2026", CURRENT, [other], FakeClient()) is not None


def test_upsert_replaces_the_round_and_keeps_rounds_in_order():
    r9 = {"season": "2026", "round": "9", "grid": ["old"]}
    r10 = {"season": "2026", "round": "10", "grid": ["old"]}
    new_r10 = {"season": "2026", "round": "10", "grid": ["new"]}
    assert fsg.upsert([r10, r9], new_r10) == [r9, new_r10]
    r11 = {"season": "2026", "round": "11", "grid": ["new"]}
    assert fsg.upsert([r9], r11) == [r9, r11]


def test_moved_names_only_drivers_starting_behind_where_they_qualified():
    """The penalised and the timeless; a car promoted into a vacated slot is noise."""

    def rows(*pairs):
        return [{"driverId": d, "constructorId": "x", "position": p} for d, p in pairs]

    entry = {"season": "2026", "round": "16", "grid": rows(("a", 1), ("c", 2), ("b", 3), ("d", 4))}
    quali = [{"season": "2026", "round": "16", "results": rows(("a", 1), ("b", 2), ("c", 3))}]
    assert fsg.moved(entry, quali) == ["b P2 -> P3", "d (no lap time) P4"]
    assert fsg.moved(entry, []) == []


# --- which race ------------------------------------------------------------------------

SCHED = {
    "season": "2026",
    "races": [
        {
            "round": "16",
            "date": "2026-10-04",
            "time": "07:00:00Z",
            "qualifyingDate": "2026-10-03",
            "qualifyingTime": "08:00:00Z",
        },
        {
            "round": "17",
            "date": "2026-10-11",
            "time": "12:00:00Z",
            "qualifyingDate": "2026-10-10",
            "qualifyingTime": "13:00:00Z",
        },
    ],
}
R16_DONE = [{"season": "2026", "round": "16"}]


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_the_target_is_the_race_between_its_qualifying_and_its_start():
    assert fsg.target_race(SCHED, R16_DONE, at("2026-10-10 13:00"))["round"] == "17"
    assert fsg.target_race(SCHED, R16_DONE, at("2026-10-11 11:59"))["round"] == "17"


def test_no_target_before_qualifying_starts():
    assert fsg.target_race(SCHED, R16_DONE, at("2026-10-10 12:59")) is None


def test_no_target_once_the_race_has_started():
    assert fsg.target_race(SCHED, R16_DONE, at("2026-10-11 12:00")) is None


def test_no_target_once_the_race_is_classified():
    done = [*R16_DONE, {"season": "2026", "round": "17"}]
    assert fsg.target_race(SCHED, done, at("2026-10-11 11:00")) is None


# --- main(): the pipeline step ------------------------------------------------------------


def _valid_schedule():
    """The fixture schedule plus the place fields schedule.json also requires."""
    filler = {
        "circuitName": "x",
        "locality": "x",
        "country": "x",
        "lat": "0",
        "long": "0",
        "url": "https://example.invalid",
    }
    races = [{**filler, **r} for r in JOLPICA["schedule"]["races"]]
    return {"season": "2026", "totalRounds": len(races), "races": races}


@pytest.fixture
def monza_saturday(tmp_path, monkeypatch):
    """data/ as it stood on the evening of the 2026 Italian GP's qualifying."""
    from datalib import repository

    def write(name, payload):
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    write("schedule.json", _valid_schedule())
    write("podiums.json", [p for p in JOLPICA["podiums"] if p["round"] != "13"])
    write("current_drivers.json", JOLPICA["current_drivers"])
    write("qualifying.json", JOLPICA["qualifying"])
    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    monkeypatch.delenv("JOLPICA_ONLY", raising=False)
    return tmp_path


SATURDAY_EVENING = ["--now", "2026-09-05T20:00:00+00:00"]


def test_main_writes_the_official_grid(monza_saturday, capsys):
    assert fsg.main(SATURDAY_EVENING, client=FakeClient()) == 0
    written = json.loads((monza_saturday / "starting_grids.json").read_text(encoding="utf-8"))
    assert [(g["season"], g["round"]) for g in written] == [("2026", "13")]
    started = next(r for r in JOLPICA["race_results"] if r["round"] == "13")
    assert {g["driverId"]: g["position"] for g in written[0]["grid"]} == {
        row["driverId"]: row["grid"] for row in started["results"]
    }
    out = capsys.readouterr().out
    assert "22 cars written" in out
    assert "Starting behind where they qualified" in out


def test_main_rewrites_nothing_when_the_grid_is_unchanged(monza_saturday, capsys):
    fsg.main(SATURDAY_EVENING, client=FakeClient())
    first = (monza_saturday / "starting_grids.json").read_text(encoding="utf-8")
    fsg.main(SATURDAY_EVENING, client=FakeClient())
    assert (monza_saturday / "starting_grids.json").read_text(encoding="utf-8") == first
    assert "nothing new" in capsys.readouterr().out


def test_main_replaces_a_revised_grid(monza_saturday, capsys):
    """Race morning: the committed Saturday grid is replaced, not kept beside the new one."""
    fsg.main(SATURDAY_EVENING, client=FakeClient())
    path = monza_saturday / "starting_grids.json"
    saturday = json.loads(path.read_text(encoding="utf-8"))
    first, second = saturday[0]["grid"][0], saturday[0]["grid"][1]
    first["driverId"], second["driverId"] = second["driverId"], first["driverId"]
    path.write_text(json.dumps(saturday), encoding="utf-8")

    assert fsg.main(SATURDAY_EVENING, client=FakeClient()) == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == [fsg.build_grid(RACES["13"], "2026", CURRENT, FakeClient())]
    assert "22 cars written" in capsys.readouterr().out


def test_main_reads_a_now_without_a_timezone_as_utc(monza_saturday):
    assert fsg.main(["--now", "2026-09-05T20:00:00"], client=FakeClient()) == 0
    assert (monza_saturday / "starting_grids.json").exists()


def test_main_is_skipped_while_an_earlier_data_pr_is_open(monza_saturday, monkeypatch):
    monkeypatch.setenv("JOLPICA_ONLY", "true")
    assert fsg.main(SATURDAY_EVENING, client=FakeClient()) == 0
    assert not (monza_saturday / "starting_grids.json").exists()


def test_main_survives_an_openf1_surprise(monza_saturday, capsys):
    class Broken(FakeClient):
        def starting_grid(self, key):
            raise RuntimeError("an OpenF1 surprise")

    assert fsg.main(SATURDAY_EVENING, client=Broken()) == 0
    assert not (monza_saturday / "starting_grids.json").exists()
    assert "left as it was" in capsys.readouterr().out


def test_main_does_nothing_once_the_lights_go_out(monza_saturday):
    assert fsg.main(["--now", "2026-09-06T13:00:00+00:00"], client=FakeClient()) == 0
    assert not (monza_saturday / "starting_grids.json").exists()
