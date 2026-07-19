"""Tests for the race-aware update guard (check_update_due.is_update_due).

The guard decides, with no network call, whether a race that should have results
by now is newer than what the committed data already reflects (podigami.json's
``asOf``). Only then does the scheduled workflow run the full update.
"""

from datetime import UTC, datetime

from check_update_due import (
    is_post_quali_update_due,
    is_update_due,
    latest_finished_round,
)


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
    # Started 1h ago; buffer is 100min -> still racing, don't poll mid-race.
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 05:00")) is False


def test_race_due_shortly_after_a_typical_race_ends():
    # A GP runs ~100min. At 1h45 past the start the flag has fallen, so the
    # watcher must be allowed to arm — waiting a full 2h burns ~20min of every
    # race weekend for nothing.
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 05:45")) is True


def test_race_past_buffer_not_in_data_is_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is True


# --- latest_finished_round: the (season, round) the watcher should wait for.


def test_latest_finished_round_is_newest_race_past_the_buffer():
    s = sched(*[(str(r), f"2026-03-0{r}", "04:00:00Z") for r in range(1, 4)])
    assert latest_finished_round(s, at("2026-03-03 07:00")) == (2026, 3)


def test_latest_finished_round_ignores_races_still_inside_the_buffer():
    s = sched(("1", "2026-03-01", "04:00:00Z"), ("2", "2026-03-08", "04:00:00Z"))
    assert latest_finished_round(s, at("2026-03-08 04:30")) == (2026, 1)


def test_latest_finished_round_none_before_any_race():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert latest_finished_round(s, at("2026-03-01 12:00")) is None


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


# --- post-quali trigger -------------------------------------------------------


def qsched(*rounds, season="2026"):
    """Schedule dict from (round, race_date, race_time, quali_date, quali_time)."""
    return {
        "season": season,
        "totalRounds": len(rounds),
        "races": [
            {"round": r, "date": d, "time": t, "qualifyingDate": qd, "qualifyingTime": qt}
            for (r, d, t, qd, qt) in rounds
        ],
    }


# Round 10 races Sunday 13:00; quali Saturday 14:00 (all UTC).
R10 = ("10", "2026-07-19", "13:00:00Z", "2026-07-18", "14:00:00Z")
PQ_R10 = {"season": "2026", "round": "10", "raceName": "Belgian Grand Prix"}


def test_quali_not_due_before_session():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 13:00")) is False


def test_quali_not_due_inside_buffer():
    # quali start + 90min buffer = 15:30
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 15:00")) is False


def test_quali_due_past_buffer_when_uncovered():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 15:31")) is True


def test_quali_not_due_when_post_quali_covers_the_round():
    s = qsched(R10)
    assert is_post_quali_update_due(s, ASOF_R9, PQ_R10, at("2026-07-18 16:00")) is False


def test_quali_due_when_post_quali_covers_an_older_round():
    s = qsched(R10)
    stale = {"season": "2026", "round": "9", "raceName": "R9"}
    assert is_post_quali_update_due(s, ASOF_R9, stale, at("2026-07-18 16:00")) is True


def test_quali_missing_fields_never_fires():
    # pre-rollout schedule: quali fields null -> trigger stays quiet forever
    s = qsched(("10", "2026-07-19", "13:00:00Z", None, None))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_garbage_time_never_fires():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", "not-a-time"))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_missing_time_defaults_to_end_of_day():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", ""))
    # 23:59:59Z + 90min buffer -> not due Saturday evening, due Sunday 02:00
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 23:00")) is False
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 02:00")) is True


def test_quali_garbage_asof_never_fires():
    # unlike the race trigger, no asOf means we can't locate the "next" race
    s = qsched(R10)
    assert is_post_quali_update_due(s, {}, None, at("2026-07-18 16:00")) is False


def test_quali_targets_the_race_after_asof_only():
    # R10's quali passed but R10 is already in the data -> next race is R11,
    # whose quali is in the future -> not due.
    r11 = ("11", "2026-08-02", "13:00:00Z", "2026-08-01", "14:00:00Z")
    s = qsched(R10, r11)
    asof_r10 = {"season": "2026", "round": "10", "raceName": "Belgian Grand Prix"}
    assert is_post_quali_update_due(s, asof_r10, None, at("2026-07-19 20:00")) is False


def test_quali_season_rollover():
    # data holds last season's finale; the opener's quali just finished
    s = qsched(("1", "2027-03-07", "04:00:00Z", "2027-03-06", "05:00:00Z"), season="2027")
    assert is_post_quali_update_due(s, ASOF_PREV, None, at("2027-03-06 06:31")) is True
