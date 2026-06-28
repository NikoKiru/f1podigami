"""Tests for the race-aware update guard (check_update_due.is_update_due).

The guard decides, with no network call, whether a race that should have results
by now is newer than what the committed data already reflects (podigami.json's
``asOf``). Only then does the scheduled workflow run the full update.
"""

from datetime import UTC, datetime

from check_update_due import is_update_due


def at(s: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' as a tz-aware UTC datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def sched(*rounds, season="2026"):
    """Build a minimal schedule.json dict from (round, date, time) tuples."""
    return {
        "season": season,
        "totalRounds": len(rounds),
        "races": [{"round": r, "date": d, "time": t} for (r, d, t) in rounds],
    }


ASOF_R7 = {"season": "2026", "round": "7", "raceName": "Barcelona GP"}
ASOF_R9 = {"season": "2026", "round": "9", "raceName": "R9"}
ASOF_PREV = {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP"}


def test_future_race_not_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-01 12:00")) is False


def test_race_within_buffer_not_due():
    # Started 1h ago; buffer is 2h -> results not expected, don't poll mid-race.
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 05:00")) is False


def test_race_past_buffer_not_in_data_is_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is True


def test_race_past_buffer_already_in_data_not_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    asof_r1 = {"season": "2026", "round": "1", "raceName": "R1"}
    assert is_update_due(s, asof_r1, at("2026-03-08 07:00")) is False


def test_latest_round_compared_numerically_not_lexically():
    # Rounds 1..10 finished; data has round 9. Numeric: 10 > 9 -> due.
    # A lexical bug would pick max("1".."10") == "9", see "9" == "9" -> not due.
    s = sched(*[(str(r), "2026-03-08", "04:00:00Z") for r in range(1, 11)])
    assert is_update_due(s, ASOF_R9, at("2026-03-08 07:00")) is True


def test_season_rollover_due():
    # schedule.json is the new season; data still holds last year's finale.
    s = sched(("1", "2027-03-07", "04:00:00Z"), season="2027")
    assert is_update_due(s, ASOF_PREV, at("2027-03-07 07:00")) is True


def test_empty_season_not_due():
    assert is_update_due(sched(), ASOF_PREV, at("2026-03-01 12:00")) is False


def test_missing_time_not_finished_same_day():
    # No time -> defaults to end-of-day UTC, so same-day midday isn't "finished".
    s = sched(("1", "2026-03-08", ""))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 12:00")) is False


def test_missing_time_finished_next_day():
    s = sched(("1", "2026-03-08", ""))
    assert is_update_due(s, ASOF_PREV, at("2026-03-09 03:00")) is True


def test_unparseable_time_skipped():
    # A garbage time must not crash and must not count the race as finished.
    s = sched(("1", "2026-03-08", "not-a-time"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-09 12:00")) is False


def test_garbage_asof_treated_as_nothing_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, {}, at("2026-03-08 07:00")) is True


# --- fail-safe on malformed data: the guard must never crash, and "unsure"
# must mean "don't fire" (False), except a missing asOf which means "we have
# nothing" so a finished race is still due.


def test_empty_date_skipped():
    s = sched(("1", "", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is False


def test_non_numeric_season_not_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"), season="not-a-year")
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is False


def test_non_numeric_round_skipped():
    s = sched(("nope", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is False
