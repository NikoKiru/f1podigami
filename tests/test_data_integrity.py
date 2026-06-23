"""Semantic integrity of the committed datasets.

Shape and field types are enforced by the schemas in ``src/datalib`` (proven in
``test_datalib.py``). This file owns what a schema can't express — that every
dataset still validates, plus the ordering, cross-field, and data-quality
invariants — asserted against the typed objects the data layer returns.
"""

import json

import pytest

from datalib import (
    DATA_DIR,
    REGISTRY,
    load_combos,
    load_podiums,
    load_schedule,
)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_dataset_loads_and_validates(name):
    """Every committed data/*.json parses and satisfies its schema."""
    raw = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    REGISTRY[name].validate_python(raw)


def test_combos_are_three_distinct_drivers():
    for c in load_combos():
        assert len(c.drivers) == 3, "a combo must be exactly three drivers"
        assert len(set(c.drivers)) == 3, "the three drivers must be distinct"
        assert c.count > 0


def test_combos_sorted_by_count_desc():
    counts = [c.count for c in load_combos()]
    assert counts == sorted(counts, reverse=True), "combos must be ranked by count"


def test_combo_count_matches_races_listed():
    for c in load_combos():
        assert c.count == len(c.races), f"count {c.count} != {len(c.races)} races for {c.drivers}"


def test_podiums_seasons_are_year_digits():
    for p in load_podiums():
        assert p.season.isdigit()


def test_schedule_dates_well_formed_and_tracks_mostly_present():
    sched = load_schedule()
    assert sched.races, "schedule has no races"
    for r in sched.races:
        assert len(r.date) == 10 and r.date[:4].isdigit()  # YYYY-MM-DD
    # most circuits should resolve to a drawn track outline
    with_track = sum(1 for r in sched.races if r.trackPath)
    assert with_track >= len(sched.races) * 0.8
