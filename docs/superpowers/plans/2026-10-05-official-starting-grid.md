# Official Starting Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The post-qualifying prediction uses F1's official starting grid (penalties applied, drivers without a lap time included) automatically. It is picked up from OpenF1 after qualifying and re-checked on race morning until the start.

**Architecture:** A new fail-closed fetcher writes `data/starting_grids.json` from OpenF1 `starting_grid`, and `compute_podigami` prefers that grid over `grid_penalties.json`. The update guard gets a "grid" trigger. The watcher gets a "grid" watch on Saturday and a grid re-check inside the race watch on Sunday. Both report `published=grid`, after which `update.yml` hands over to a successor. Spec: `docs/superpowers/specs/2026-10-05-official-starting-grid-design.md`.

**Tech Stack:** Python 3.11+, Pydantic v2 (`src/datalib`), `requests` through `src/fetch/openf1.py`, pytest, ruff, GitHub Actions.

## Global Constraints

- Run every command from the worktree root: `C:\Users\dknik\Documents\projects\f1_podigami\.claude\worktrees\official-starting-grid`.
- Fail closed: any doubt about OpenF1 data writes nothing, and the prediction keeps qualifying order plus `grid_penalties.json`.
- All OpenF1 access goes through `src/fetch/openf1.py`. Never add a second client or extra sleeps.
- No network in build or tests. Tests replay `tests/fixtures/openf1/*.json.gz`.
- `save_*` output must stay a byte-identical fixed point. `data/starting_grids.json` is committed as exactly `[]` with no trailing newline.
- `update.yml` steps added now must be inert with `main`'s older scripts (the develop window).
- Lint and format: `python -m ruff check .` and `python -m ruff format --check .` (line length 100).
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The PR updates `RELEASE_NOTES.md`, `README.md` and `CLAUDE.md`.

---

### Task 1: `starting_grids.json` dataset

**Files:**
- Modify: `src/datalib/schemas.py` (new section after `retirements.json`)
- Modify: `src/datalib/repository.py` (import, `REGISTRY`, load/save)
- Modify: `src/datalib/__init__.py` (exports)
- Create: `data/starting_grids.json` (content exactly `[]`)
- Test: `tests/test_datalib.py`

**Interfaces:**
- Produces: `StartingGridRow{driverId: str, constructorId: str, position: int}`; `StartingGridRace{season: str, round: str, grid: list[StartingGridRow]}`; `REGISTRY["starting_grids.json"]`; `load_starting_grids() -> list[StartingGridRace]`; `save_starting_grids(data) -> None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_datalib.py`)

```python
# --- starting_grids.json (F1's official grid, via OpenF1) ------------------------


def _official_grid(*driver_ids):
    return {
        "season": "2026",
        "round": "17",
        "grid": [
            {"driverId": d, "constructorId": "car_" + d, "position": i + 1}
            for i, d in enumerate(driver_ids)
        ],
    }


def test_save_starting_grids_roundtrips(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_starting_grids([_official_grid("max_verstappen", "hamilton", "antonelli")])
    raw = (tmp_path / "starting_grids.json").read_text(encoding="utf-8")
    adapter = REGISTRY["starting_grids.json"]
    dumped = adapter.dump_python(adapter.validate_python(json.loads(raw)), mode="json")
    assert json.dumps(dumped, indent=2, ensure_ascii=False) == raw
    assert repository.load_starting_grids()[0].grid[2].driverId == "antonelli"


def test_starting_grids_at_rest_is_an_empty_list(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_starting_grids([])
    assert (tmp_path / "starting_grids.json").read_text(encoding="utf-8") == "[]"


def test_starting_grid_must_be_a_complete_grid():
    adapter = REGISTRY["starting_grids.json"]
    good = _official_grid("a", "b", "c")
    adapter.validate_python([good])  # must not raise
    rows = good["grid"]
    for bad_rows in (
        [],  # no cars
        [rows[0], rows[2]],  # positions 1, 3: a gap
        [*rows, {**rows[0], "driverId": "d"}],  # position 1 twice
        [rows[0], rows[1], {**rows[0], "position": 3}],  # driver a twice
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python([{**good, "grid": bad_rows}])
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_datalib.py -k "starting_grid" -p no:cacheprovider`
Expected: FAIL with `KeyError: 'starting_grids.json'` / `AttributeError: ... save_starting_grids`.

- [ ] **Step 3: Add the schema** (in `src/datalib/schemas.py`, after the `RetirementRace` class and before the `unconfirmed.json` section)

```python
# --- starting_grids.json ------------------------------------------------------


class StartingGridRow(_Base):
    driverId: str
    constructorId: str
    position: int


class StartingGridRace(_Base):
    """F1's official starting grid for one race: penalties applied, as published.

    Written by ``fetch/fetch_starting_grid.py`` from OpenF1's ``starting_grid``.
    That endpoint mirrors the "Starting grid" page F1 puts up a few hours after
    qualifying, once the FIA has applied grid penalties, and updates on race
    morning (pit-lane starts, power-unit elements fitted overnight). The
    post-qualifying prediction uses it instead of ``grid_penalties.json`` for its
    round. One entry per round, kept as history.
    """

    season: str
    round: str
    grid: list[StartingGridRow]

    @model_validator(mode="after")
    def _a_complete_grid(self) -> StartingGridRace:
        if sorted(row.position for row in self.grid) != list(range(1, len(self.grid) + 1)):
            raise ValueError("grid positions must run 1..N with no gaps or repeats")
        drivers = [row.driverId for row in self.grid]
        if not drivers or len(set(drivers)) != len(drivers):
            raise ValueError("a grid needs at least one car, each driver once")
        return self
```

- [ ] **Step 4: Register it** (in `src/datalib/repository.py`)

Add `StartingGridRace,` to the `from .schemas import (...)` list (after `Soulmates,`). Add this `REGISTRY` entry after `"retirements.json"`:

```python
    "starting_grids.json": TypeAdapter(list[StartingGridRace]),
```

Append to the end of the file:

```python
def load_starting_grids() -> list[StartingGridRace]:
    return _load("starting_grids.json")


def save_starting_grids(data: Any) -> None:
    _save("starting_grids.json", data)
```

- [ ] **Step 5: Export it** (in `src/datalib/__init__.py`)

In the `from .repository import (...)` list, add `load_starting_grids,` after `load_soulmates,` and `save_starting_grids,` after `save_soulmates,`. In `from .schemas import (...)`, add `StartingGridRace,` and `StartingGridRow,` after `Soulmates,`. In `__all__`, after `"save_unconfirmed",` add:

```python
    "load_starting_grids",
    "save_starting_grids",
```

and after `"UnconfirmedRound",` add:

```python
    "StartingGridRace",
    "StartingGridRow",
```

- [ ] **Step 6: Commit the empty dataset**

Create `data/starting_grids.json` with the exact content `[]` and no newline. The generic `test_dataset_roundtrips_byte_identical` and `test_registry_covers_every_committed_dataset` then cover it.

- [ ] **Step 7: Run the datalib tests**

Run: `python -m pytest tests/test_datalib.py -p no:cacheprovider`
Expected: all pass (the round-trip test now includes `starting_grids.json`).

- [ ] **Step 8: Lint, format, commit**

```bash
python -m ruff check --fix src/datalib tests/test_datalib.py
python -m ruff format src/datalib tests/test_datalib.py
git add src/datalib data/starting_grids.json tests/test_datalib.py
git commit -m "Add the starting_grids.json dataset for F1's official grid" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The OpenF1 grid fetcher

**Files:**
- Create: `src/fetch/fetch_starting_grid.py`
- Modify: `src/update.py` (`STEPS`)
- Test: `tests/test_fetch_starting_grid.py`

**Interfaces:**
- Consumes: Task 1's `load_starting_grids`, `save_starting_grids`, `REGISTRY`; `fetch_openf1.map_drivers(entrants, current) -> dict[int, dict] | None`, `fetch_openf1.match_session(sessions, date, time) -> dict | None`, `fetch_openf1.newest_started(schedule, now, date_key, time_key) -> dict | None`; `check_update_due.session_start(date, time) -> datetime | None`.
- Produces:
  - `target_race(schedule: dict, podiums: list[dict], now: datetime) -> dict | None`
  - `build_grid(race: dict, season: str, current: list[dict], client=openf1) -> dict | None`
  - `committed_grid(grids, season, rnd) -> dict | None`
  - `fresh_grid(race: dict, season: str, current: list[dict], grids: list[dict], client=openf1) -> dict | None`. Task 5's watcher calls this with four positional arguments.
  - `upsert(grids, entry) -> list[dict]`
  - `moved(entry, qualifying) -> list[str]`
  - `main(argv=None, client=openf1) -> int`

- [ ] **Step 1: Write the failing tests** (create `tests/test_fetch_starting_grid.py`)

```python
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


def test_moved_names_everyone_not_starting_where_he_qualified():
    def rows(*pairs):
        return [{"driverId": d, "constructorId": "x", "position": p} for d, p in pairs]

    entry = {"season": "2026", "round": "16", "grid": rows(("a", 1), ("c", 2), ("b", 3), ("d", 4))}
    quali = [{"season": "2026", "round": "16", "results": rows(("a", 1), ("b", 2), ("c", 3))}]
    assert fsg.moved(entry, quali) == ["c P3 -> P2", "b P2 -> P3", "d (no lap time) P4"]
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
    assert "Not starting where they qualified" in out


def test_main_rewrites_nothing_when_the_grid_is_unchanged(monza_saturday, capsys):
    fsg.main(SATURDAY_EVENING, client=FakeClient())
    first = (monza_saturday / "starting_grids.json").read_text(encoding="utf-8")
    fsg.main(SATURDAY_EVENING, client=FakeClient())
    assert (monza_saturday / "starting_grids.json").read_text(encoding="utf-8") == first
    assert "nothing new" in capsys.readouterr().out


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
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_fetch_starting_grid.py -p no:cacheprovider`
Expected: collection error, `ModuleNotFoundError: No module named 'fetch.fetch_starting_grid'`.

- [ ] **Step 3: Write the fetcher** (create `src/fetch/fetch_starting_grid.py`)

```python
"""Record F1's official starting grid for the next race, from OpenF1.

The post-qualifying prediction needs the grid the race will really start from.
F1 publishes it on formula1.com a few hours after qualifying, once the FIA has
applied grid penalties. It updates it on race morning when a car moves to a
pit-lane start or takes new power-unit elements (4 of the first 16 rounds of
2026). OpenF1's ``starting_grid`` mirrors that page, keyed by the qualifying
session. In all 16 rounds it matched the grid each race actually started from,
pit-lane starters included. This writes it to data/starting_grids.json, where
compute_podigami uses it instead of the hand-entered data/grid_penalties.json.

Fail closed, always. Any of these writes nothing, and the prediction keeps
using the qualifying order plus grid_penalties.json:

- OpenF1 is unreachable or hasn't published the grid yet;
- no single qualifying session matches;
- a car number, surname or team won't map;
- the positions aren't exactly 1..N;
- the grid isn't exactly the cars that took part in qualifying.

``fresh_grid`` is the one comparison that decides whether anything is new. This
script writes what it returns, and the watcher (wait_for_results.py) ends a watch
on it, so the two can never disagree about whether the grid changed.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from check_update_due import session_start  # noqa: E402
from datalib import (  # noqa: E402
    REGISTRY,
    load_current_drivers,
    load_podiums,
    load_qualifying,
    load_schedule,
    load_starting_grids,
    repository,
    save_starting_grids,
)
from fetch import openf1  # noqa: E402
from fetch.fetch_openf1 import map_drivers, match_session, newest_started  # noqa: E402

DATASET = "starting_grids.json"


def target_race(schedule: dict, podiums: list[dict], now: datetime) -> dict | None:
    """The race whose grid matters now: qualifying started, race not yet. Else None.

    That is the newest scheduled race whose qualifying has started, unless it has
    already been classified or its scheduled start has passed. Once the lights go
    out the grid is history, and OpenF1 is closed to free clients while a session
    is live anyway.
    """
    race = newest_started(schedule, now, "qualifyingDate", "qualifyingTime")
    if race is None:
        return None
    key = (str(schedule["season"]), race["round"])
    if any((p["season"], p["round"]) == key for p in podiums):
        return None
    start = session_start(race.get("date") or "", race.get("time") or "")
    if start is None or now >= start:
        return None
    return race


def build_grid(race: dict, season: str, current: list[dict], client=openf1) -> dict | None:
    """``{"season", "round", "grid"}`` from OpenF1, or None to write nothing.

    ``current`` is current_drivers.json's ``drivers``. Cars are mapped through the
    qualifying session's entrants, which list every car on the grid, including
    one that set no lap time.
    """
    rnd = race["round"]
    quali = match_session(
        client.sessions(int(season), "Qualifying") or [],
        race.get("qualifyingDate") or "",
        race.get("qualifyingTime"),
    )
    if quali is None:
        print(f"  OpenF1: no single qualifying session matches round {rnd}")
        return None
    rows = client.starting_grid(quali["session_key"])
    if not rows:
        print(f"  OpenF1: no starting grid for round {rnd} yet")
        return None
    drivers = map_drivers(client.drivers(quali["session_key"]) or [], current)
    if drivers is None:
        return None
    grid = []
    for row in rows:
        car, position = row.get("driver_number"), row.get("position")
        if car not in drivers or not isinstance(position, int):
            print(f"  OpenF1: unusable starting-grid row {row!r} for round {rnd}")
            return None
        mapped = drivers[car]
        grid.append(
            {
                "driverId": mapped["driverId"],
                "constructorId": mapped["constructorId"],
                "position": position,
            }
        )
    grid.sort(key=lambda g: g["position"])
    if [g["position"] for g in grid] != list(range(1, len(grid) + 1)):
        print(f"  OpenF1: the round {rnd} grid positions don't run 1..{len(grid)}")
        return None
    if sorted(row["driver_number"] for row in rows) != sorted(drivers):
        print(f"  OpenF1: the round {rnd} grid isn't exactly the cars that qualified")
        return None
    return {"season": season, "round": rnd, "grid": grid}


def committed_grid(grids: list[dict], season: str, rnd: str) -> dict | None:
    """The grid data/starting_grids.json already holds for a round, if any."""
    return next((g for g in grids if (g["season"], g["round"]) == (season, rnd)), None)


def fresh_grid(
    race: dict, season: str, current: list[dict], grids: list[dict], client=openf1
) -> dict | None:
    """OpenF1's grid for ``race`` when it differs from the committed one, else None."""
    built = build_grid(race, season, current, client)
    if built is None:
        return None
    ours = committed_grid(grids, season, race["round"])
    if ours is not None and ours["grid"] == built["grid"]:
        return None
    return built


def upsert(grids: list[dict], entry: dict) -> list[dict]:
    """``grids`` with ``entry`` in place of its round's grid, in round order."""
    key = (entry["season"], entry["round"])
    kept = [g for g in grids if (g["season"], g["round"]) != key]
    return sorted([*kept, entry], key=lambda g: (int(g["season"]), int(g["round"])))


def moved(entry: dict, qualifying: list[dict]) -> list[str]:
    """For the log: every driver who doesn't start where he qualified."""
    key = (entry["season"], entry["round"])
    quali = next((q for q in qualifying if (q["season"], q["round"]) == key), None)
    if quali is None:
        return []
    qpos = {row["driverId"]: row["position"] for row in quali["results"]}
    return [
        f"{g['driverId']} P{qpos[g['driverId']]} -> P{g['position']}"
        if g["driverId"] in qpos
        else f"{g['driverId']} (no lap time) P{g['position']}"
        for g in entry["grid"]
        if qpos.get(g["driverId"]) != g["position"]
    ]


def _log_moves(entry: dict) -> None:
    """Print who starts somewhere other than where he qualified. Never raises."""
    try:
        shifted = moved(entry, [q.model_dump() for q in load_qualifying()])
    except Exception:  # noqa: BLE001 - this is only a log line
        return
    if shifted:
        print("  Not starting where they qualified: " + ", ".join(shifted))


def main(argv: list[str] | None = None, client=openf1) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--now", help="ISO-8601 instant to act as 'now' (rehearsals)")
    args = ap.parse_args(argv)
    if os.environ.get("JOLPICA_ONLY") == "true":
        # update.yml sets this when an earlier data PR is still unmerged after the
        # in-flight wait: this checkout may lack that PR's grid, and writing it again
        # would only re-push the same rows and restart the PR's checks.
        print("Official starting grid: skipped (an earlier data PR is still open).")
        return 0
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)

    schedule = load_schedule().model_dump()
    race = target_race(schedule, [p.model_dump() for p in load_podiums()], now)
    if race is None:
        print("Official starting grid: no race between its qualifying and its start.")
        return 0
    season = str(schedule["season"])
    has_file = (repository.DATA_DIR / DATASET).exists()
    grids = [g.model_dump() for g in load_starting_grids()] if has_file else []
    current = [d.model_dump() for d in load_current_drivers().drivers]

    try:
        entry = fresh_grid(race, season, current, grids, client)
        payload = upsert(grids, entry) if entry is not None else None
        if payload is not None:
            REGISTRY[DATASET].validate_python(payload)
    except Exception:  # noqa: BLE001 - a grid surprise must never break the pipeline
        traceback.print_exc()
        print("Official starting grid: failed; data/starting_grids.json left as it was.")
        return 0
    if payload is None:
        print(f"Official starting grid for round {race['round']}: nothing new.")
        return 0

    save_starting_grids(payload)
    print(f"Official starting grid for round {race['round']}: {len(entry['grid'])} cars written.")
    _log_moves(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `python -m pytest tests/test_fetch_starting_grid.py -p no:cacheprovider`
Expected: all pass, including the 13 real-data rounds.

- [ ] **Step 5: Add the pipeline step** (in `src/update.py` `STEPS`, between "Fetching constructor standings" and "Computing podigami")

```python
    ("Fetching constructor standings", "fetch/fetch_constructor_standings.py"),
    # After current drivers and the schedule are refreshed: the grid maps cars by
    # number and finds the race that sits between its qualifying and its start.
    ("Fetching the official starting grid", "fetch/fetch_starting_grid.py"),
    ("Computing podigami", "compute/compute_podigami.py"),
```

Run: `python -m pytest tests/test_build_links.py -p no:cacheprovider`
Expected: PASS (`update.STEPS` scripts all exist).

- [ ] **Step 6: Lint, format, commit**

```bash
python -m ruff check --fix src/fetch/fetch_starting_grid.py src/update.py tests/test_fetch_starting_grid.py
python -m ruff format src/fetch/fetch_starting_grid.py src/update.py tests/test_fetch_starting_grid.py
git add src/fetch/fetch_starting_grid.py src/update.py tests/test_fetch_starting_grid.py
git commit -m "Fetch F1's official starting grid from OpenF1" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The prediction uses the official grid

**Files:**
- Modify: `src/compute/compute_podigami.py` (docstring, path constant, `_post_quali_block`, `compute`, `main`)
- Modify: `src/datalib/schemas.py` (`DriverStrength.gridPosition` comment)
- Test: `tests/test_compute_podigami.py`

**Interfaces:**
- Consumes: the `starting_grids.json` shape from Task 1 (plain dicts).
- Produces: `compute(..., starting_grids: list[dict] | None = None)` and `_post_quali_block(..., starting_grids: list[dict] | None = None)`.

- [ ] **Step 1: Write the failing tests** (append to the end of `tests/test_compute_podigami.py`)

```python
# --- official starting grid -----------------------------------------------------------


def _official(season, rnd, order, cid_map=None):
    """A starting_grids.json payload: drivers in grid order."""
    return [
        {
            "season": str(season),
            "round": str(rnd),
            "grid": [
                {
                    "driverId": d,
                    "constructorId": (cid_map or {}).get(d, "car_" + d),
                    "position": i + 1,
                }
                for i, d in enumerate(order)
            ],
        }
    ]


def _kw(con, rres, quali):
    return {"constructor_data": con, "race_results": rres, "qualifying": quali, "schedule": SCHED_R6}


def test_official_grid_gives_the_same_prediction_as_the_same_grid_from_penalties(
    scenario_post_quali,
):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    cid = con["driverConstructor"]
    pens = [
        {
            "season": "2025",
            "round": "6",
            "penalties": [
                {"driverId": "eli", "penaltyPlaces": 3, "backOfGrid": None},
                {"driverId": "bob", "penaltyPlaces": None, "backOfGrid": True},
            ],
        }
    ]
    via_pens = cp.compute(podiums, combos, grid, grid_penalties=pens, **_kw(con, rres, quali))
    official = _official(2025, 6, ["alf", "cas", "dan", "eli", "bob"], cid)
    via_grid = cp.compute(podiums, combos, grid, starting_grids=official, **_kw(con, rres, quali))
    assert via_grid == via_pens


def test_official_grid_wins_over_hand_entered_penalties(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    pens = [
        {
            "season": "2025",
            "round": "6",
            "penalties": [{"driverId": "eli", "penaltyPlaces": 3, "backOfGrid": None}],
        }
    ]
    # F1's grid is the plain qualifying order: the penalty entry is out of date.
    official = _official(2025, 6, ["eli", "alf", "bob", "cas", "dan"], con["driverConstructor"])
    both = cp.compute(
        podiums,
        combos,
        grid,
        grid_penalties=pens,
        starting_grids=official,
        **_kw(con, rres, quali),
    )
    assert both == cp.compute(podiums, combos, grid, **_kw(con, rres, quali))


def test_official_grid_adds_a_driver_without_a_lap_time(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    cid = dict(con["driverConstructor"], zed_zephyr="teamA")
    official = _official(2025, 6, ["eli", "alf", "bob", "cas", "dan", "zed_zephyr"], cid)
    res = cp.compute(podiums, combos, grid, starting_grids=official, **_kw(con, rres, quali))
    form = {d["driverId"]: d for d in res["postQuali"]["driverForm"]}
    assert set(form) == {"eli", "alf", "bob", "cas", "dan", "zed_zephyr"}
    assert form["zed_zephyr"]["gridPosition"] == 6
    assert form["zed_zephyr"]["constructorId"] == "teamA"
    assert form["zed_zephyr"]["constructorStrength"] == pytest.approx(1.0)


def test_official_grid_leaves_out_a_qualifier_who_will_not_start(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    official = _official(2025, 6, ["eli", "alf", "bob", "cas"], con["driverConstructor"])
    res = cp.compute(podiums, combos, grid, starting_grids=official, **_kw(con, rres, quali))
    assert {d["driverId"] for d in res["postQuali"]["driverForm"]} == {"eli", "alf", "bob", "cas"}
    assert all("dan" not in c["driverIds"] for c in res["postQuali"]["candidates"])


def test_official_grid_for_another_round_is_ignored(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    stale = _official(2025, 5, ["dan", "cas", "bob", "alf", "eli"], con["driverConstructor"])
    assert cp.compute(
        podiums, combos, grid, starting_grids=stale, **_kw(con, rres, quali)
    ) == cp.compute(podiums, combos, grid, **_kw(con, rres, quali))


def test_official_grid_still_honours_retirements(scenario_post_quali):
    podiums, combos, grid, con, rres, quali = scenario_post_quali
    cid = dict(con["driverConstructor"], zed_zephyr="teamA")
    official = _official(2025, 6, ["eli", "alf", "bob", "cas", "dan", "zed_zephyr"], cid)
    res = cp.compute(
        podiums,
        combos,
        grid,
        starting_grids=official,
        retirements=_retirements(2025, 6, "zed_zephyr"),
        **_kw(con, rres, quali),
    )
    form = {d["driverId"]: d["gridPosition"] for d in res["postQuali"]["driverForm"]}
    assert "zed_zephyr" not in form
    assert form == {"eli": 1, "alf": 2, "bob": 3, "cas": 4, "dan": 5}


def test_official_grid_payload_is_deterministic_and_valid(scenario_post_quali):
    from datalib import REGISTRY

    podiums, combos, grid, con, rres, quali = scenario_post_quali
    cid = dict(con["driverConstructor"], zed_zephyr="teamA")
    official = _official(2025, 6, ["alf", "eli", "bob", "cas", "dan", "zed_zephyr"], cid)
    a = cp.compute(podiums, combos, grid, starting_grids=official, **_kw(con, rres, quali))
    b = cp.compute(podiums, combos, grid, starting_grids=official, **_kw(con, rres, quali))
    assert a == b
    REGISTRY["podigami.json"].validate_python(a)  # must not raise
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_compute_podigami.py -k official -p no:cacheprovider`
Expected: FAIL with `TypeError: compute() got an unexpected keyword argument 'starting_grids'`.

- [ ] **Step 3: Implement**

In the module docstring of `src/compute/compute_podigami.py`, change the Inputs lines to:

```python
Inputs : data/podiums.json, data/combos.json, data/current_drivers.json,
         data/constructor_standings.json, data/race_results.json,
         data/qualifying.json, data/schedule.json, data/grid_penalties.json,
         data/retirements.json, data/starting_grids.json
         (the last six optional)
```

After `RETIREMENTS_PATH = DATA_DIR / "retirements.json"` add:

```python
STARTING_GRIDS_PATH = DATA_DIR / "starting_grids.json"
```

In `_post_quali_block`, add `starting_grids: list[dict] | None = None,` as the last parameter (after `retirements`). Replace the docstring's first paragraph sentence "Entrants are exactly the qualifying participants with the constructor each qualified for (handles seat swaps/substitutes)." with:

```python
    Entrants are the qualifying participants, with the constructor each qualified
    for (handles seat swaps/substitutes). Once F1 has published the official
    starting grid (``starting_grids``), the entrants are exactly that grid's cars:
    a driver with no lap time is added, and a qualifier who won't start leaves.
```

and the paragraph ending "adjusted by any ``grid_penalties`` entry for this season/round." with:

```python
    The quali order feeds the rating channel untouched — a penalised driver
    still demonstrated that pace — but the causal grid term and the displayed
    ``gridPosition`` use the actual starting slots: F1's official grid for this
    season/round when published, else the classification adjusted by any
    ``grid_penalties`` entry.
```

Replace this block:

```python
    # Actual starting slots: quali classification adjusted for grid penalties.
    pens = next(
        (
            e["penalties"]
            for e in (grid_penalties or [])
            if e["season"] == season and e["round"] == rnd
        ),
        [],
    )
    gpos = _apply_grid_penalties(qpos, pens)
```

with:

```python
    # Actual starting slots. F1's official grid once it is published: penalties
    # applied, drivers without a lap time on it, a non-starter off it. Until then,
    # the quali classification adjusted for the hand-entered grid penalties.
    official = next(
        (
            e["grid"]
            for e in (starting_grids or [])
            if e["season"] == season and e["round"] == rnd
        ),
        None,
    )
    if official:
        gpos = {row["driverId"]: row["position"] for row in official}
        for row in official:
            qcid.setdefault(row["driverId"], row["constructorId"])
    else:
        pens = next(
            (
                e["penalties"]
                for e in (grid_penalties or [])
                if e["season"] == season and e["round"] == rnd
            ),
            [],
        )
        gpos = _apply_grid_penalties(qpos, pens)
```

In the retirements block, change `if d in qpos` to `if d in gpos`. Change `running = [d for d in sorted(qpos) if d not in retired]` to:

```python
    running = [d for d in sorted(gpos) if d not in retired]
```

In `compute(...)`, add `starting_grids: list[dict] | None = None,` after `retirements`, and pass `starting_grids=starting_grids,` to `_post_quali_block` after `retirements=retirements,`.

In `main()`, after the `retirements` loading block add:

```python
    starting_grids = None
    if STARTING_GRIDS_PATH.exists():
        starting_grids = json.loads(STARTING_GRIDS_PATH.read_text(encoding="utf-8"))
```

and pass `starting_grids=starting_grids,` to `compute(...)` after `retirements=retirements,`.

In `src/datalib/schemas.py`, replace the `gridPosition` comment in `DriverStrength` with:

```python
    # Post-quali only: the driver's starting slot. F1's official grid
    # (data/starting_grids.json) once published, else the qualifying
    # classification adjusted for any grid penalties (data/grid_penalties.json).
```

- [ ] **Step 4: Run the compute tests**

Run: `python -m pytest tests/test_compute_podigami.py -p no:cacheprovider`
Expected: all pass, including every pre-existing post-quali, penalty and retirement test.

- [ ] **Step 5: Check the committed prediction is unchanged** (the dataset is `[]`, so the output must be byte-identical)

Run: `python src/compute/compute_podigami.py` then `git status --short data/`
Expected: no change to `data/podigami.json`.

- [ ] **Step 6: Lint, format, commit**

```bash
python -m ruff check --fix src/compute/compute_podigami.py src/datalib/schemas.py tests/test_compute_podigami.py
python -m ruff format src/compute/compute_podigami.py src/datalib/schemas.py tests/test_compute_podigami.py
git add src/compute/compute_podigami.py src/datalib/schemas.py tests/test_compute_podigami.py
git commit -m "Use F1's official starting grid for the post-quali prediction" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Guard trigger for a missing official grid

**Files:**
- Modify: `src/check_update_due.py`
- Test: `tests/test_check_update_due.py`

**Interfaces:**
- Produces:
  - `next_grid_target(schedule: dict, asof: dict, post_quali: dict | None, grids: Sequence[dict], now: datetime) -> tuple[int, int] | None`
  - `read_grids(data_dir: Path = DATA_DIR) -> list[dict]`
  - `pending_session_starts(schedule, asof, post_quali, now, unconfirmed=(), grids=())`
  - `is_successor_due(schedule, asof, post_quali, now, unconfirmed=(), grids=())`
  - CLI `--now <ISO>`. Task 5's watcher imports `next_grid_target`, `read_grids`, `ARM_BEFORE` and `session_start`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_check_update_due.py`)

```python
# --- official starting grid -------------------------------------------------------

from check_update_due import next_grid_target  # noqa: E402

GRID_R10 = [{"season": "2026", "round": "10", "grid": []}]


def test_grid_due_once_post_quali_covers_the_round():
    assert next_grid_target(qsched(R10), ASOF_R9, PQ_R10, [], at("2026-07-18 16:00")) == (2026, 10)


def test_grid_not_due_once_the_official_grid_is_in():
    assert next_grid_target(qsched(R10), ASOF_R9, PQ_R10, GRID_R10, at("2026-07-18 16:00")) is None


def test_grid_not_due_before_post_quali_covers_the_round():
    """Qualifying itself is still pending: that is the quali trigger's job."""
    assert next_grid_target(qsched(R10), ASOF_R9, None, [], at("2026-07-18 16:00")) is None
    stale = {"season": "2026", "round": "9", "raceName": "R9"}
    assert next_grid_target(qsched(R10), ASOF_R9, stale, [], at("2026-07-18 16:00")) is None


def test_grid_trigger_hands_over_to_the_race_window():
    # The race starts 13:00 Sunday; from 10:00 the race watch re-checks the grid itself.
    assert next_grid_target(qsched(R10), ASOF_R9, PQ_R10, [], at("2026-07-19 09:59")) == (2026, 10)
    assert next_grid_target(qsched(R10), ASOF_R9, PQ_R10, [], at("2026-07-19 10:00")) is None


def test_grid_trigger_is_fail_safe():
    assert next_grid_target(qsched(R10), {}, PQ_R10, [], at("2026-07-18 16:00")) is None
    garbage = [{"season": "x", "round": "10"}, {"nope": 1}]
    assert next_grid_target(qsched(R10), ASOF_R9, PQ_R10, garbage, at("2026-07-18 16:00")) == (
        2026,
        10,
    )
    bad_time = qsched(("10", "2026-07-19", "not-a-time", "2026-07-18", "14:00:00Z"))
    assert next_grid_target(bad_time, ASOF_R9, PQ_R10, [], at("2026-07-18 16:00")) is None


def test_pending_starts_include_a_missing_official_grid():
    # Saturday evening, quali covered, no grid yet: pending since the quali start.
    now = at("2026-07-18 18:00")
    assert pending_session_starts(qsched(R10), ASOF_R9, PQ_R10, now) == [at("2026-07-18 14:00")]
    assert pending_session_starts(qsched(R10), ASOF_R9, PQ_R10, now, (), GRID_R10) == []
    assert is_successor_due(qsched(R10), ASOF_R9, PQ_R10, now) is True


def test_read_grids_is_fail_safe(tmp_path):
    assert cud.read_grids(tmp_path) == []
    (tmp_path / "starting_grids.json").write_text("not json", encoding="utf-8")
    assert cud.read_grids(tmp_path) == []
    (tmp_path / "starting_grids.json").write_text(json.dumps(GRID_R10), encoding="utf-8")
    assert cud.read_grids(tmp_path) == GRID_R10


def _write_saturday_evening(data_dir):
    (data_dir / "schedule.json").write_text(json.dumps(qsched(R10)), encoding="utf-8")
    (data_dir / "podigami.json").write_text(
        json.dumps({"asOf": ASOF_R9, "postQuali": PQ_R10}), encoding="utf-8"
    )


def test_main_due_true_from_a_missing_official_grid_alone(tmp_path, monkeypatch):
    _write_saturday_evening(tmp_path)
    monkeypatch.setattr(cud, "DATA_DIR", tmp_path)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    cud.main(["--now", "2026-07-18T18:00:00+00:00"])

    assert out.read_text(encoding="utf-8").splitlines() == ["due=true"]


def test_main_quiet_once_the_official_grid_is_in(tmp_path, monkeypatch):
    _write_saturday_evening(tmp_path)
    (tmp_path / "starting_grids.json").write_text(json.dumps(GRID_R10), encoding="utf-8")
    monkeypatch.setattr(cud, "DATA_DIR", tmp_path)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    cud.main(["--now", "2026-07-18T18:00:00+00:00"])

    assert out.read_text(encoding="utf-8").splitlines() == ["due=false"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_check_update_due.py -p no:cacheprovider`
Expected: collection error, `ImportError: cannot import name 'next_grid_target'`.

- [ ] **Step 3: Implement** (in `src/check_update_due.py`)

Update the module docstring. Replace "Three independent triggers feed a single ``due`` output:" with "Four independent triggers feed a single ``due`` output:", and add this bullet after the `is_post_quali_update_due` bullet:

```python
- :func:`next_grid_target` — ``postQuali`` covers the next race, but F1's official
  starting grid for it isn't in ``data/starting_grids.json`` yet, until that race's
  own window opens (the race watch re-checks the grid from then on).
```

Also change "loads the data, ORs the three triggers" to "loads the data, ORs the four triggers", and add to the `main` description: "``--now`` overrides the clock for rehearsals."

Add `next_grid_target` after `is_post_quali_update_due`:

```python
def next_grid_target(
    schedule: dict,
    asof: dict,
    post_quali: dict | None,
    grids: Sequence[dict],
    now: datetime,
) -> tuple[int, int] | None:
    """The ``(season, round)`` still waiting for F1's official starting grid, or None.

    Due once ``postQuali`` covers the next race (its qualifying is in) while
    data/starting_grids.json has no grid for it. F1 publishes the grid a few hours
    after qualifying. Due only until that race's own window opens (``ARM_BEFORE``
    its start), because from then on the race watch re-checks the grid itself
    until the lights go out. Fail-safe like :func:`next_quali_target`.
    """
    try:
        have = (int(asof["season"]), int(asof["round"]))
        covered = (int(post_quali["season"]), int(post_quali["round"]))  # type: ignore[index]
    except (KeyError, ValueError, TypeError):
        return None
    race = _next_race_entry(schedule, have)
    if race is None:
        return None
    target = (int(schedule["season"]), int(race["round"]))
    if covered != target:
        return None
    start = session_start(race.get("date", ""), race.get("time", ""))
    if start is None or now >= start - ARM_BEFORE:
        return None
    for g in grids:
        try:
            if (int(g["season"]), int(g["round"])) == target:
                return None
        except (KeyError, ValueError, TypeError):
            continue
    return target
```

Replace `read_unconfirmed` with a shared reader plus two thin wrappers:

```python
def _read_list(name: str, data_dir: Path) -> list[dict]:
    """A committed list dataset as plain dicts; [] when absent or unreadable."""
    try:
        data = json.loads((data_dir / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def read_unconfirmed(data_dir: Path = DATA_DIR) -> list[dict]:
    """data/unconfirmed.json as plain dicts; [] when absent or unreadable."""
    return _read_list("unconfirmed.json", data_dir)


def read_grids(data_dir: Path = DATA_DIR) -> list[dict]:
    """data/starting_grids.json as plain dicts; [] when absent or unreadable."""
    return _read_list("starting_grids.json", data_dir)
```

In `pending_session_starts`, add the parameter `grids: Sequence[dict] = (),` after `unconfirmed`. Extend the docstring's first line to say "...plus the qualifying start of a race still waiting for its official grid, and the session end of each round still awaiting Jolpica's confirmation." Insert this before the `for e in unconfirmed:` loop:

```python
    grid = next_grid_target(schedule, asof, post_quali, grids, now)
    if grid is not None:
        entry = _race_by_round(schedule, grid[1])
        if entry:
            start = session_start(
                entry.get("qualifyingDate") or "", entry.get("qualifyingTime") or ""
            )
            if start:
                starts.append(start)
```

In `is_successor_due`, add `grids: Sequence[dict] = (),` after `unconfirmed`. Pass it as `pending_session_starts(schedule, asof, post_quali, now, unconfirmed, grids)`.

In `main()`, add the argument after `--fail-on-stale`:

```python
    ap.add_argument("--now", help="ISO-8601 instant to act as 'now' (rehearsals)")
```

Replace `unconfirmed = read_unconfirmed(DATA_DIR)` / `now = datetime.now(UTC)` with:

```python
    unconfirmed = read_unconfirmed(DATA_DIR)
    grids = read_grids(DATA_DIR)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
```

Change the successor line to `value = is_successor_due(schedule, asof, post, now, unconfirmed, grids)`. Replace the due branch with:

```python
        key = "due"
        race_due = is_update_due(schedule, asof, now)
        quali_due = is_post_quali_update_due(schedule, asof, post, now)
        grid_due = next_grid_target(schedule, asof, post, grids, now) is not None
        confirm_due = is_confirmation_due(unconfirmed)
        value = race_due or quali_due or grid_due or confirm_due
        print(
            f"update due: {value} (race={race_due} quali={quali_due} grid={grid_due} "
            f"confirm={confirm_due} asOf season={asof.get('season')} round={asof.get('round')})"
        )
```

- [ ] **Step 4: Run the guard tests**

Run: `python -m pytest tests/test_check_update_due.py -p no:cacheprovider`
Expected: all pass (the pre-existing tests are unaffected: their `postQuali`/time combinations never open a grid target).

- [ ] **Step 5: Lint, format, commit**

```bash
python -m ruff check --fix src/check_update_due.py tests/test_check_update_due.py
python -m ruff format src/check_update_due.py tests/test_check_update_due.py
git add src/check_update_due.py tests/test_check_update_due.py
git commit -m "Arm the update guard until the official starting grid is in" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Watcher: the grid watch and the race-morning re-check

**Files:**
- Modify: `src/wait_for_results.py`
- Test: `tests/test_wait_for_results.py`

**Interfaces:**
- Consumes: `fetch_starting_grid.fresh_grid(race, season, current, grids)` (Task 2, positional); `next_grid_target`, `read_grids`, `ARM_BEFORE`, `session_start` (Task 4).
- Produces:
  - `wait_target(schedule, podigami, now, unconfirmed=(), grids=(), jolpica_only=False)`
  - `choose_source(kind, published_round, rnd, openf1_ready, *, jolpica_only, grid_ready=None, before_start=False)`
  - `watch_budget(kind, schedule, rnd, now, timeout_s) -> float`
  - `_scheduled_race(schedule, rnd) -> dict | None`
  - `_grid_ready(schedule, season, rnd, grids) -> bool`
  - the report value `published=grid`, consumed by Task 6's `update.yml`.

- [ ] **Step 1: Update the one test whose meaning changes, and write the new failing tests**

In `tests/test_wait_for_results.py`, replace `test_nothing_to_wait_for_once_post_quali_covers_the_round` with:

```python
def test_nothing_to_wait_for_once_post_quali_and_the_official_grid_cover_the_round():
    """The quali-day short-circuit: a fully covered round must not hold the runner."""
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    grids = [{"season": "2026", "round": "14", "grid": []}]
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 18:00"), (), grids) is None


def test_wait_target_waits_for_the_official_grid_after_qualifying():
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 18:00")) == ("grid", 2026, 14)


def test_an_open_data_pr_skips_the_grid_watch():
    """Only OpenF1 can end a grid watch, and JOLPICA_ONLY switches OpenF1 off."""
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 18:00"), jolpica_only=True) is None


def test_the_race_watch_takes_over_from_the_grid_watch():
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    assert wait_target(SCHEDULE, podigami, at("2026-09-13 10:00")) == ("race", 2026, 14)
```

Append to the end of the file:

```python
# --- the official starting grid ------------------------------------------------------

from wait_for_results import watch_budget  # noqa: E402


def test_a_grid_watch_ends_only_on_a_new_grid():
    assert choose_source("grid", None, 14, lambda: True, jolpica_only=False, grid_ready=lambda: True) == "grid"
    assert choose_source("grid", None, 14, lambda: True, jolpica_only=False, grid_ready=lambda: False) is None
    # Neither results feed ends a grid watch.
    assert choose_source("grid", 14, 14, lambda: True, jolpica_only=False, grid_ready=lambda: False) is None


def test_the_race_watch_republishes_a_revised_grid_before_the_start():
    def watch(published, grid_ready, before_start):
        return choose_source(
            "race",
            published,
            14,
            lambda: False,
            jolpica_only=False,
            grid_ready=grid_ready,
            before_start=before_start,
        )

    assert watch(13, lambda: True, True) == "grid"
    assert watch(13, lambda: True, False) is None  # lights out: the grid is history
    assert watch(13, lambda: False, True) is None
    assert watch(14, lambda: True, True) == "jolpica"  # results still win


def test_an_open_data_pr_disables_every_grid_check():
    asked = []

    def grid_ready():
        asked.append(1)
        return True

    assert choose_source("grid", None, 14, lambda: False, jolpica_only=True, grid_ready=grid_ready) is None
    assert (
        choose_source(
            "race", 13, 14, lambda: False, jolpica_only=True, grid_ready=grid_ready, before_start=True
        )
        is None
    )
    assert asked == []


def test_a_confirmation_watch_never_checks_the_grid():
    assert (
        choose_source(
            "confirm-race",
            13,
            14,
            lambda: False,
            jolpica_only=False,
            grid_ready=lambda: True,
            before_start=True,
        )
        is None
    )


def test_a_grid_watch_hands_the_runner_back_before_the_race_window():
    five_hours = 5 * 3600
    # R14 starts 13:00 Sunday; its window opens 10:00. At 08:00 only 2 h remain.
    assert watch_budget("grid", SCHEDULE, 14, at("2026-09-13 08:00"), five_hours) == 2 * 3600
    assert watch_budget("grid", SCHEDULE, 14, at("2026-09-12 18:00"), five_hours) == five_hours
    assert watch_budget("grid", SCHEDULE, 14, at("2026-09-13 11:00"), five_hours) == 0
    assert watch_budget("race", SCHEDULE, 14, at("2026-09-13 08:00"), five_hours) == five_hours
    assert watch_budget("grid", SCHEDULE, 99, at("2026-09-13 08:00"), five_hours) == five_hours


def test_report_grid(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    report("grid")
    assert out.read_text(encoding="utf-8") == "published=grid\n"


def test_grid_readiness_follows_fresh_grid(tmp_path, monkeypatch):
    import wait_for_results as wfr
    from fetch import fetch_starting_grid

    _only_drivers_on_disk(tmp_path, monkeypatch)
    seen = []

    def fresh(race, season, current, grids):
        seen.append((race["round"], season, grids))
        return {"season": season, "round": race["round"], "grid": []}

    monkeypatch.setattr(fetch_starting_grid, "fresh_grid", fresh)
    committed = [{"season": "2026", "round": "13", "grid": []}]
    assert wfr._grid_ready(SCHEDULE, 2026, 14, committed) is True
    assert seen == [("14", "2026", committed)]

    monkeypatch.setattr(fetch_starting_grid, "fresh_grid", lambda *a, **k: None)
    assert wfr._grid_ready(SCHEDULE, 2026, 14, committed) is False


def test_grid_readiness_survives_a_failing_check(tmp_path, monkeypatch, capsys):
    import wait_for_results as wfr
    from fetch import fetch_starting_grid

    _only_drivers_on_disk(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("an OpenF1 surprise")

    monkeypatch.setattr(fetch_starting_grid, "fresh_grid", boom)
    assert wfr._grid_ready(SCHEDULE, 2026, 14, []) is False
    assert "starting-grid check failed" in capsys.readouterr().out


def test_grid_is_never_ready_for_a_round_outside_the_schedule(tmp_path, monkeypatch):
    import wait_for_results as wfr
    from fetch import fetch_starting_grid

    _only_drivers_on_disk(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setattr(fetch_starting_grid, "fresh_grid", lambda *a, **k: asked.append(1))
    assert wfr._grid_ready(SCHEDULE, 2026, 99, []) is False
    assert asked == []
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_wait_for_results.py -p no:cacheprovider`
Expected: collection error, `ImportError: cannot import name 'watch_budget'`.

- [ ] **Step 3: Implement** (in `src/wait_for_results.py`)

Replace the `check_update_due` import with:

```python
from check_update_due import (
    ARM_BEFORE,
    is_update_due,
    latest_armed_round,
    next_grid_target,
    next_quali_target,
    read_grids,
    read_unconfirmed,
    session_start,
)
```

In the module docstring, add this section before "So ``published`` takes one of four values":

```python
The official starting grid
--------------------------
Once ``postQuali`` covers the next race but data/starting_grids.json has no
grid for it, the run waits for F1's official starting grid (``grid``). That is
OpenF1's mirror of the grid F1 publishes a few hours after qualifying. Only
OpenF1 can end that watch, so it never starts under ``JOLPICA_ONLY``. Its budget
ends when the race's own window opens (:func:`watch_budget`). From then on the
race watch re-checks the grid at every poll until the scheduled start, so a grid
revised on race morning (a pit-lane start, new power-unit elements) still reaches
the prediction. Both report ``published=grid``: update.yml runs the pipeline,
then hands over if a session is still pending, which on race day resumes the
results watch. Whether there is a new grid is decided by
``fetch_starting_grid.fresh_grid``, the same comparison the pipeline's write
uses.
```

Change "So ``published`` takes one of four values: ``true`` (Jolpica has the round), ``fast`` (OpenF1 has it and the stewards are clear), ``false`` (the budget ran out) or ``none`` (nothing was pending to wait for)." to:

```python
So ``published`` takes one of five values: ``true`` (Jolpica has the round),
``fast`` (OpenF1 has it and the stewards are clear), ``grid`` (OpenF1 has an
official starting grid data/ lacks), ``false`` (the budget ran out) or ``none``
(nothing was pending to wait for).
```

Replace `wait_target` with:

```python
def wait_target(
    schedule: dict,
    podigami: dict,
    now: datetime,
    unconfirmed: Sequence[dict] = (),
    grids: Sequence[dict] = (),
    jolpica_only: bool = False,
) -> tuple[str, int, int] | None:
    """What this run should wait for — ``(kind, season, round)`` — or None.

    Checked in this order:

    1. A race newer than ``asOf`` whose window is open (the guard's own rule, so
       the two can't disagree).
    2. The next race's qualifying, if its window is open and ``postQuali``
       doesn't cover it yet.
    3. F1's official starting grid for that race, once ``postQuali`` covers it but
       data/starting_grids.json doesn't. Never with ``jolpica_only``: only OpenF1
       can end that watch.
    4. The oldest round OpenF1 filled that Jolpica hasn't confirmed yet.

    Nothing pending means return at once, holding no runner.
    """
    asof = podigami.get("asOf") or {}
    if is_update_due(schedule, asof, now):
        season, rnd = latest_armed_round(schedule, now)  # not None when due
        return ("race", season, rnd)
    post_quali = podigami.get("postQuali")
    quali = next_quali_target(schedule, asof, post_quali, now)
    if quali is not None:
        return ("qualifying", quali[0], quali[1])
    grid = None if jolpica_only else next_grid_target(schedule, asof, post_quali, grids, now)
    if grid is not None:
        return ("grid", grid[0], grid[1])
    for e in unconfirmed:
        try:
            return (f"confirm-{e['kind']}", int(e["season"]), int(e["round"]))
        except (KeyError, TypeError, ValueError):
            continue
    return None
```

Add `_scheduled_race` above `_openf1_ready`, and use it inside `_openf1_ready` in place of its inline `next(...)` lookup:

```python
def _scheduled_race(schedule: dict, rnd: int) -> dict | None:
    """The schedule.json entry for round ``rnd``, or None."""
    return next((r for r in schedule.get("races", []) if str(r.get("round")) == str(rnd)), None)
```

so `_openf1_ready` begins:

```python
    race = _scheduled_race(schedule, rnd)
    if race is None:
        return False
```

Add after `_openf1_ready`:

```python
def _grid_ready(schedule: dict, season: int, rnd: int, grids: Sequence[dict]) -> bool:
    """Does OpenF1 have an official starting grid for this round that data/ lacks?"""
    race = _scheduled_race(schedule, rnd)
    if race is None:
        return False
    try:
        # Imported lazily, inside this try, like _openf1_ready's fast-lane modules:
        # a grid surprise must never take the results watch down.
        from fetch import fetch_starting_grid

        current = json.loads((DATA_DIR / "current_drivers.json").read_text(encoding="utf-8"))
        fresh = fetch_starting_grid.fresh_grid(
            race, str(season), current.get("drivers", []), list(grids)
        )
        return fresh is not None
    except Exception as exc:  # noqa: BLE001 - an OpenF1 surprise must never break the watch
        print(f"  OpenF1 starting-grid check failed ({exc!r}); treating it as unchanged")
        return False
```

Replace `choose_source` with:

```python
def choose_source(
    kind: str,
    published_round: int | None,
    rnd: int,
    openf1_ready: Callable[[], bool],
    *,
    jolpica_only: bool,
    grid_ready: Callable[[], bool] | None = None,
    before_start: bool = False,
) -> str | None:
    """Which source, if any, ends this watch: "jolpica", "openf1", "grid" or None.

    Jolpica always wins. OpenF1 ends only a watch for a pending race or
    qualifying session — never a confirmation watch, which exists to wait for
    Jolpica — and never when ``jolpica_only`` is set. update.yml sets that when an
    earlier data PR is still unmerged after the in-flight wait: this checkout may
    then lack that fast result, and a second fast pipeline would re-push the same
    rows and restart the PR's checks, over and over.

    "grid" means OpenF1 has an official starting grid that data/ lacks. It alone
    ends a grid watch, and it also ends a race watch while ``before_start``, so a
    grid revised on race morning reaches the prediction before the lights go out.
    ``jolpica_only`` disables both, for the same loop reason. ``openf1_ready`` and
    ``grid_ready`` are called only when they could actually end the watch (they
    make network requests).
    """
    if kind == "grid":
        return "grid" if not jolpica_only and grid_ready is not None and grid_ready() else None
    if published_round is not None and published_round >= rnd:
        return "jolpica"
    if kind in ("race", "qualifying") and not jolpica_only and openf1_ready():
        return "openf1"
    if (
        kind == "race"
        and before_start
        and not jolpica_only
        and grid_ready is not None
        and grid_ready()
    ):
        return "grid"
    return None
```

Add after `choose_source`:

```python
def watch_budget(kind: str, schedule: dict, rnd: int, now: datetime, timeout_s: float) -> float:
    """How long this watch may hold the runner, in seconds.

    A grid watch hands the runner back by the time the race's own window opens
    (``ARM_BEFORE`` its start). The race watch re-checks the grid from then on, so
    a grid watch can never delay the results watch. Every other watch gets
    ``timeout_s``.
    """
    if kind != "grid":
        return timeout_s
    race = _scheduled_race(schedule, rnd)
    start = session_start(race.get("date") or "", race.get("time") or "") if race else None
    if start is None:
        return timeout_s
    return max(0.0, min(timeout_s, (start - ARM_BEFORE - now).total_seconds()))
```

In `report`'s docstring, add after the "fast" sentence: `"grid" if OpenF1 has an official starting grid the data lacks — update.yml runs the pipeline, then hands over if a session is still pending.`

In `main()`, after `unconfirmed = read_unconfirmed(DATA_DIR)` add `grids = read_grids(DATA_DIR)`. Change the target line to:

```python
    target = wait_target(
        schedule, podigami, datetime.now(UTC), unconfirmed, grids, jolpica_only
    )
```

Replace everything from `def ready() -> str | None:` through the final `return 0` with:

```python
    race = _scheduled_race(schedule, rnd)
    start = session_start(race.get("date") or "", race.get("time") or "") if race else None

    def ready() -> str | None:
        published = None
        if kind != "grid":  # a grid watch waits on OpenF1 alone
            feed = _fetch_last_results(season) if races_feed else _fetch_last_qualifying(season)
            published = latest_published_round(feed)
        return choose_source(
            kind,
            published,
            rnd,
            lambda: _openf1_ready(kind, schedule, season, rnd),
            jolpica_only=jolpica_only,
            grid_ready=lambda: _grid_ready(schedule, season, rnd, grids),
            before_start=start is not None and datetime.now(UTC) < start,
        )

    budget = watch_budget(kind, schedule, rnd, datetime.now(UTC), args.timeout)
    print(f"Waiting for {season} round {rnd} ({kind}) upstream...")
    source = wait_until(ready, timeout_s=budget, interval_s=args.interval)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    if source == "jolpica":
        print(f"Jolpica has round {rnd} ({kind}) at {stamp}; running the pipeline.")
        report("true")
    elif source == "openf1":
        print(f"OpenF1 has round {rnd} ({kind}), stewards clear, at {stamp}; fast lane.")
        report("fast")  # update.yml runs the pipeline, then hands over for confirmation
    elif source == "grid":
        print(
            f"OpenF1 has a new official starting grid for round {rnd} at {stamp}; "
            "running the pipeline."
        )
        report("grid")  # update.yml runs the pipeline, then hands over if anything is pending
    else:
        print(f"Round {rnd} ({kind}) still unpublished after the budget.")
        report("false")
    return 0
```

- [ ] **Step 4: Run the watcher tests**

Run: `python -m pytest tests/test_wait_for_results.py -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Lint, format, commit**

```bash
python -m ruff check --fix src/wait_for_results.py tests/test_wait_for_results.py
python -m ruff format src/wait_for_results.py tests/test_wait_for_results.py
git add src/wait_for_results.py tests/test_wait_for_results.py
git commit -m "Watch for the official starting grid, and re-check it on race morning" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Workflow hand-over, docs and release notes

**Files:**
- Modify: `.github/workflows/update.yml` (two steps after "Hand over to a confirmation run")
- Modify: `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md`

**Interfaces:**
- Consumes: `published=grid` (Task 5); `check_update_due.py --successor` (Task 4).

- [ ] **Step 1: Add the hand-over steps** (in `.github/workflows/update.yml`, directly after the "Hand over to a confirmation run" step, still inside the `update` job)

```yaml
      # The watch ended because OpenF1 published F1's official starting grid, or
      # revised it on race morning, and the pipeline above put it on the site.
      # Hand over if a session is still pending. On race day that resumes the
      # results watch this run left to republish the grid. By the successor's
      # in-flight wait the grid PR has normally merged (data PRs take ~1-2 min),
      # so its watch finds the grid unchanged and waits for results as usual. If
      # the PR is still open, that run is JOLPICA_ONLY, which also disables every
      # grid check, so the hand-over can't loop. No status function, like the
      # fast lane's: a failed pipeline ends red and alerts instead of handing
      # over. Safe in the develop window: main's older watcher never reports
      # `grid`, so neither step runs until the scripts are promoted.
      - name: Check whether a session is still pending after a grid update
        id: regrid
        if: steps.wait.outputs.published == 'grid'
        run: python src/check_update_due.py --successor
      - name: Hand over after a grid update
        if: steps.regrid.outputs.successor == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh workflow run update.yml --repo "$GITHUB_REPOSITORY" -f mode=auto -f wait=true
```

Also, in the comment above "Wait for the pending session to be published upstream", change "polling until the session is published (up to 5h)." to "polling until the session is published (up to 5h); between qualifying and the race it also waits for F1's official starting grid."

Run: `python -c "import yaml; d = yaml.safe_load(open('.github/workflows/update.yml', encoding='utf-8')); print([s.get('name') for s in d['jobs']['update']['steps']][-3:])"`
Expected: the last three step names end with `'Check whether a session is still pending after a grid update', 'Hand over after a grid update'`.

- [ ] **Step 2: CLAUDE.md**

In "Automated data updates (`update.yml`)", first bullet, change "or the next race's qualifying not yet covered by `postQuali`." to "the next race's qualifying not yet covered by `postQuali`, or that race's official starting grid not yet in `data/starting_grids.json`."

After the "#### OpenF1 fast lane (#327)" subsection (before "#### ⚠️ When a finished race doesn't appear"), add:

```markdown
#### Official starting grid

`src/fetch/fetch_starting_grid.py` records F1's official starting grid for the next race in `data/starting_grids.json`, one entry per round, kept as history. `compute_podigami` uses it instead of `data/grid_penalties.json` for that round's post-quali prediction:
- grid slots come straight from F1;
- drivers with no qualifying time are included;
- a qualifier who won't start is left out;
- the qualifying order still feeds the ratings.

- **Source.** OpenF1 `starting_grid`, keyed by the qualifying session, which mirrors formula1.com's "Starting grid" page. Research on 2026-10-05: in all 16 rounds of 2026 the F1.com page matched the grid each race started from (Jolpica's `grid`, pit-lane starters included), and OpenF1 matched the page. We don't scrape F1.com, because its Guidelines forbid reproducing results data "through scraping". Cars map through OpenF1's qualifying `drivers` list, which includes cars with no lap time, using the fast lane's `map_drivers`.
- **Timing.** F1 publishes the grid a few hours after qualifying. At Hungary 2026 it was still empty 1 h 10 m after the session and there 5 h 14 m after. It changed on race morning in 4 of 16 rounds, for pit-lane starts and power-unit elements fitted overnight.
- **Saturday.** The guard's `next_grid_target` is due once `postQuali` covers the next race and `starting_grids.json` lacks it, until `ARM_BEFORE` the race. The watcher's `grid` target, checked after qualifying and before confirmations, polls OpenF1 until the grid appears. `watch_budget` caps that watch at the race window, so it never delays the results watch.
- **Sunday.** The race watch also re-checks the grid at every poll until the scheduled start. A change ends the watch with `published=grid` and the pipeline republishes. Then `regrid` runs `check_update_due.py --successor`, and "Hand over after a grid update" dispatches a successor that resumes the race watch. The grid PR has normally merged by the successor's in-flight wait.
- **One comparison.** `fetch_starting_grid.fresh_grid` decides "is there a new grid" for both the fetcher and the watcher, so a watch never ends on a grid the pipeline won't write.
- **Fail closed.** Nothing is written when OpenF1 errors or returns 404, no single qualifying session matches, a car won't map, the positions aren't exactly 1..N, or the grid isn't exactly the qualifying entrants. `JOLPICA_ONLY` skips every grid check and write. The schema rejects gaps and repeated positions or drivers.
- **`grid_penalties.json` is now the fallback,** used only until the official grid exists. It is still worth filling in for penalties known before qualifying (e.g. power-unit changes), because the official grid comes hours later.
- **Measure it.** The watcher prints `OpenF1 has a new official starting grid for round N at <UTC>`, and the fetcher prints who isn't starting where they qualified.
- **Rehearse** with `python src/fetch/fetch_starting_grid.py --now <ISO>` and `python src/check_update_due.py --now <ISO>` on a copy of `data/` from before a race.
```

- [ ] **Step 3: README.md**

1. In "🔮 How the predictor works", **Grid** bullet, replace the sentence that starts "Known grid penalties (hand-curated in `data/grid_penalties.json`…" up to "…regardless of where they start." with: "The starting slots for this term are **F1's official starting grid** — penalties applied, drivers without a lap time included — picked up automatically a few hours after qualifying and re-checked until the start, so race-morning changes such as pit-lane starts count too; until it is published, hand-curated penalties in `data/grid_penalties.json` rebuild the grid from the qualifying order. The qualifying order itself still counts at face value — a penalised driver demonstrated that pace regardless of where they start."
2. In the Architecture mermaid `FETCH` subgraph add `        FSG["fetch_starting_grid"]:::fetch` after the `FO` line, and after `OF -.-> FO` add `    OF -.-> FSG`.
3. In the CI table's `update.yml` row, after "(the post-qualifying prediction update included)," insert "then waits for F1's official starting grid and re-checks it until the start,".
4. In the File map **Fetch** rows, after the `fetch_driver_races.py` row add:

```markdown
| `src/fetch/fetch_openf1.py` | OpenF1 fast lane: fill the newest race/qualifying before Jolpica publishes |
| `src/fetch/fetch_starting_grid.py` | F1's official starting grid (penalties applied) for the next race, via OpenF1 → `data/starting_grids.json` |
```

5. In "📡 Data source", append to the OpenF1 paragraph: " The post-qualifying prediction's starting grid is F1's official one, from OpenF1's mirror of formula1.com's starting-grid page."
6. Update both test counts (`968`) to the number `python -m pytest` reports in Task 7.

- [ ] **Step 4: RELEASE_NOTES.md** (new heading at the top, under `# Release Notes`)

```markdown
## 2026-10-05

### Features
- **The post-qualifying prediction now uses F1's official starting grid automatically.** Grid penalties no longer have to be entered by hand. A few hours after qualifying, the official grid (penalties applied) is picked up from OpenF1, which mirrors formula1.com's starting-grid page. It is checked again until the start, so race-morning changes such as pit-lane starts still reach the prediction. Drivers who set no qualifying time are now part of it too. Across all 16 races of 2026 so far, the official grid matched the grid each race started from every time. The hand-entered penalties had missed changes in four of the seven races since the post-qualifying prediction launched (#NNN)
```

(`#NNN` is replaced with the PR number in Task 8.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/update.yml CLAUDE.md README.md RELEASE_NOTES.md
git commit -m "Hand over after a grid update; document the official starting grid" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Verify on real data (no commit unless a fix is needed)

- [ ] **Step 1: Full local gate**

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
PYTHONPATH=src python -m datalib.validate
python src/build_site.py
```

Expected: ruff clean; all tests pass (note the count for README); "Validated 18 datasets OK."; the build succeeds. Then set the README test counts and amend nothing; commit the count change separately:
`git commit -am "README: test count" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

- [ ] **Step 2: Rehearse Malaysia (R16) against live OpenF1.** Copy `src/` to a scratch dir. Fill its `data/` from main's commit `3535812`, which has R16 qualifying but not the race: `git show 3535812:data/<file> > <scratch>/data/<file>` for every file in `git ls-tree --name-only 3535812 data/`. Add `[]` as `starting_grids.json`. Then run:

```bash
python <scratch>/src/check_update_due.py --now 2026-10-03T20:00:00+00:00
python <scratch>/src/fetch/fetch_starting_grid.py --now 2026-10-03T20:00:00+00:00
python <scratch>/src/compute/compute_podigami.py
```

Expected:
- The guard prints `grid=True` and `update due: True`.
- The fetcher writes 22 cars and names Hadjar P3 -> P8, Colapinto P15 -> P21 and Lindblad P16 -> P22.
- `postQuali.driverForm[].gridPosition` equals F1.com's grid: VER 1, HAM 2, ANT 3, LEC 4, NOR 5, PIA 6, RUS 7, HAD 8, GAS 9, BOR 10, LAW 11, ALO 12, SAI 13, STR 14, HUL 15, BEA 16, OCO 17, ALB 18, BOT 19, PER 20, COL 21, LIN 22.

- [ ] **Step 3: Rehearse Madrid (R14) the same way.** Use the last `main` commit before the R14 race result: `git log origin/main --format="%h %ad %s" --date=iso-strict --until=2026-09-13T13:00:00Z -1 -- data/qualifying.json`, with `--now 2026-09-12T22:00:00+00:00`. Expected:
- `postQuali.driverForm` has 22 drivers, Stroll and Bearman included.
- The grid matches F1.com: NOR 1, ANT 2, VER 3, HAM 4, LEC 5, RUS 6, PIA 7, LAW 8, COL 9, LIN 10, HUL 11, BOR 12, OCO 13, GAS 14, TSU 15, ALB 16, ALO 17, PER 18, BOT 19, SAI 20, STR 21, BEA 22.

---

### Task 8: Ship

- [ ] **Step 1:** Request a code review (superpowers:requesting-code-review) and address the findings.
- [ ] **Step 2:** Push the branch and open a PR to `develop` using the PR template (Summary / Changes / Testing / Checklist). Replace `#NNN` in RELEASE_NOTES with the PR number, then commit and push.
- [ ] **Step 3:** Wait for the 7 required checks to pass (`gh pr checks <n> --watch`), then merge. Prove the develop window with a forced update run: `gh workflow run update.yml -f mode=auto -f force=true`. The run must be green, with no grid step running.
- [ ] **Step 4:** Open the promotion PR `develop → main` and wait for all 9 checks. If `data/` conflicts, regenerate it rather than picking a side. Merge, confirm `deploy.yml` succeeded, then run another forced update and confirm `fetch_starting_grid` prints "no race between its qualifying and its start."
- [ ] **Step 5:** Update the memory notes (`f1com-starting-grid.md`, `post-quali-prediction.md`), delete the merged local branch, and remove the worktree.
