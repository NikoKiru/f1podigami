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
    load_race_results,
    load_schedule,
)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_dataset_loads_and_validates(name):
    """Every committed data/*.json parses and satisfies its schema."""
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not yet backfilled (run its fetcher)")
    raw = json.loads(path.read_text(encoding="utf-8"))
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


def test_combo_drivers_aligned_with_driver_ids():
    """drivers[i] must be the display name for driverIds[i] — parallel arrays must align."""
    name_by_id: dict[str, str] = {}
    for p in load_podiums():
        for slot in (p.p1, p.p2, p.p3):
            name_by_id[slot.driverId] = slot.name

    for c in load_combos():
        assert len(c.drivers) == len(c.driverIds)
        for i, driver_id in enumerate(c.driverIds):
            expected = name_by_id.get(driver_id)
            assert expected is not None, f"unknown driverId {driver_id!r}"
            assert c.drivers[i] == expected, (
                f"drivers[{i}]={c.drivers[i]!r} does not match "
                f"driverIds[{i}]={driver_id!r} (expected {expected!r})"
            )


def test_schedule_dates_well_formed_and_tracks_mostly_present():
    sched = load_schedule()
    assert sched.races, "schedule has no races"
    for r in sched.races:
        assert len(r.date) == 10 and r.date[:4].isdigit()  # YYYY-MM-DD
    # most circuits should resolve to a drawn track outline
    with_track = sum(1 for r in sched.races if r.trackPath)
    assert with_track >= len(sched.races) * 0.8


# Historical quirks where the podium record and the classification rows are known
# to disagree (shared drives, dead heats). Add (season, round) here only with a
# comment saying why. Expected to stay empty or tiny.
PODIUM_CROSSCHECK_SKIP: set[tuple[str, str]] = set()


def test_race_results_podiums_agree_with_podiums_dataset():
    """The v2 raw dataset and podiums.json must tell the same story about who
    finished 1-2-3 in every race both datasets cover."""
    podium_map = {
        (p.season, p.round): [p.p1.driverId, p.p2.driverId, p.p3.driverId] for p in load_podiums()
    }
    mismatches = []
    for race in load_race_results():
        rk = (race.season, race.round)
        if rk not in podium_map or rk in PODIUM_CROSSCHECK_SKIP:
            continue
        top3 = dict.fromkeys((1, 2, 3))
        for row in race.results:
            if row.position in top3 and top3[row.position] is None:
                top3[row.position] = row.driverId
        if [top3[1], top3[2], top3[3]] != podium_map[rk]:
            mismatches.append((rk, [top3[1], top3[2], top3[3]], podium_map[rk]))
    assert mismatches == [], f"{len(mismatches)} podium mismatches: {mismatches[:5]}"
