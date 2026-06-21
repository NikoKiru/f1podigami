"""Data integrity checks on the committed data/*.json the site builds from."""

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"

DATASETS = [
    "podiums.json",
    "combos.json",
    "soulmates.json",
    "current_drivers.json",
    "podigami.json",
    "driver_races.json",
    "overdue.json",
    "schedule.json",
]


def test_schedule_shape():
    sched = load("schedule.json")
    assert {"season", "totalRounds", "races"} <= sched.keys()
    assert sched["races"], "schedule has no races"
    for r in sched["races"]:
        assert {"round", "raceName", "date", "circuitName", "country"} <= r.keys()
        assert r["date"][:4].isdigit() and len(r["date"]) == 10  # YYYY-MM-DD
    # most circuits should resolve to a drawn track outline
    with_track = sum(1 for r in sched["races"] if r.get("trackPath"))
    assert with_track >= len(sched["races"]) * 0.8


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", DATASETS)
def test_dataset_exists_and_wellformed(name):
    path = DATA / name
    assert path.is_file(), f"missing dataset: {name}"
    data = load(name)
    assert data, f"{name} is empty"


def test_combos_shape():
    combos = load("combos.json")
    assert isinstance(combos, list) and combos
    for c in combos:
        assert {"drivers", "count", "lastRace", "races"} <= c.keys()
        assert len(c["drivers"]) == 3, "a combo must be exactly three drivers"
        assert len(set(c["drivers"])) == 3, "the three drivers must be distinct"
        assert isinstance(c["count"], int) and c["count"] > 0


def test_combos_sorted_by_count_desc():
    counts = [c["count"] for c in load("combos.json")]
    assert counts == sorted(counts, reverse=True), "combos must be ranked by count"


def test_combo_count_matches_races_listed():
    for c in load("combos.json"):
        assert c["count"] == len(c["races"]), (
            f"count {c['count']} != {len(c['races'])} races for {c['drivers']}"
        )


def test_podiums_shape():
    podiums = load("podiums.json")
    assert isinstance(podiums, list) and podiums
    for p in podiums:
        assert {"season", "round", "raceName", "p1", "p2", "p3"} <= p.keys()
        assert p["season"].isdigit()
