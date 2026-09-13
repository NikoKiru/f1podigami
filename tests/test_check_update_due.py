"""Tests for the race-aware update guard (check_update_due).

The guard decides, with no network call, whether a pending session is newer than
what the committed data already reflects (podigami.json's ``asOf``). It arms
``ARM_BEFORE`` (3h) ahead of each scheduled race and qualifying session so a run
is already waiting when results appear: GitHub starts only a handful of scheduled
runs a day. ``is_successor_due`` bounds the hand-over chain between runs.
"""

import json
from datetime import UTC, datetime

import check_update_due as cud
from check_update_due import (
    ARM_BEFORE,
    SUCCESSOR_WINDOW,
    is_post_quali_update_due,
    is_successor_due,
    is_update_due,
    latest_armed_round,
    next_quali_target,
    pending_session_starts,
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


ASOF_R9 = {"season": "2026", "round": "9", "raceName": "R9"}
ASOF_PREV = {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP"}


def test_the_window_and_the_successor_bound():
    assert ARM_BEFORE.total_seconds() == 3 * 3600
    assert SUCCESSOR_WINDOW.total_seconds() == 12 * 3600


def test_future_race_not_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-01 12:00")) is False


def test_race_not_due_before_its_window_opens():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 00:59")) is False


def test_race_due_once_its_window_opens():
    # A run landing now holds its runner and polls. Early costs idle runner time;
    # late costs a scheduler gap that has been measured at hours.
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 01:00")) is True


def test_race_stays_due_during_and_after_the_race():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 05:00")) is True
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 07:00")) is True


# --- latest_armed_round: the (season, round) the watcher should wait for.


def test_latest_armed_round_is_newest_race_with_an_open_window():
    s = sched(*[(str(r), f"2026-03-0{r}", "04:00:00Z") for r in range(1, 4)])
    assert latest_armed_round(s, at("2026-03-03 07:00")) == (2026, 3)


def test_latest_armed_round_ignores_races_whose_window_is_still_shut():
    s = sched(("1", "2026-03-01", "04:00:00Z"), ("2", "2026-03-08", "04:00:00Z"))
    assert latest_armed_round(s, at("2026-03-08 00:30")) == (2026, 1)


def test_latest_armed_round_none_before_any_window():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert latest_armed_round(s, at("2026-03-01 12:00")) is None


def test_race_already_in_data_not_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    asof_r1 = {"season": "2026", "round": "1", "raceName": "R1"}
    assert is_update_due(s, asof_r1, at("2026-03-08 07:00")) is False


def test_latest_round_compared_numerically_not_lexically():
    # Rounds 1..10 armed; data has round 9. Numeric: 10 > 9 -> due.
    s = sched(*[(str(r), "2026-03-08", "04:00:00Z") for r in range(1, 11)])
    assert is_update_due(s, ASOF_R9, at("2026-03-08 07:00")) is True


def test_season_rollover_due():
    s = sched(("1", "2027-03-07", "04:00:00Z"), season="2027")
    assert is_update_due(s, ASOF_PREV, at("2027-03-07 07:00")) is True


def test_empty_season_not_due():
    assert is_update_due(sched(), ASOF_PREV, at("2026-03-01 12:00")) is False


def test_missing_time_opens_the_window_late_that_day():
    # No time -> end-of-day UTC (conservative), so the window opens at 20:59:59.
    s = sched(("1", "2026-03-08", ""))
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 12:00")) is False
    assert is_update_due(s, ASOF_PREV, at("2026-03-08 21:00")) is True


def test_unparseable_time_skipped():
    s = sched(("1", "2026-03-08", "not-a-time"))
    assert is_update_due(s, ASOF_PREV, at("2026-03-09 12:00")) is False


def test_garbage_asof_treated_as_nothing_due():
    s = sched(("1", "2026-03-08", "04:00:00Z"))
    assert is_update_due(s, {}, at("2026-03-08 07:00")) is True


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
ASOF_R10 = {"season": "2026", "round": "10", "raceName": "Belgian Grand Prix"}


def test_quali_not_due_before_its_window_opens():
    assert is_post_quali_update_due(qsched(R10), ASOF_R9, None, at("2026-07-18 10:59")) is False


def test_quali_due_once_its_window_opens():
    assert is_post_quali_update_due(qsched(R10), ASOF_R9, None, at("2026-07-18 11:00")) is True


def test_quali_due_after_the_session_when_uncovered():
    assert is_post_quali_update_due(qsched(R10), ASOF_R9, None, at("2026-07-18 15:31")) is True


def test_quali_not_due_when_post_quali_covers_the_round():
    assert is_post_quali_update_due(qsched(R10), ASOF_R9, PQ_R10, at("2026-07-18 16:00")) is False


def test_quali_due_when_post_quali_covers_an_older_round():
    stale = {"season": "2026", "round": "9", "raceName": "R9"}
    assert is_post_quali_update_due(qsched(R10), ASOF_R9, stale, at("2026-07-18 16:00")) is True


def test_quali_missing_fields_never_fires():
    s = qsched(("10", "2026-07-19", "13:00:00Z", None, None))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_garbage_time_never_fires():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", "not-a-time"))
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-19 12:00")) is False


def test_quali_missing_time_defaults_to_end_of_day():
    s = qsched(("10", "2026-07-19", "13:00:00Z", "2026-07-18", ""))
    # 23:59:59Z - 3h -> the window opens at 20:59:59 on the Saturday.
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 20:00")) is False
    assert is_post_quali_update_due(s, ASOF_R9, None, at("2026-07-18 21:00")) is True


def test_quali_garbage_asof_never_fires():
    assert is_post_quali_update_due(qsched(R10), {}, None, at("2026-07-18 16:00")) is False


def test_quali_targets_the_race_after_asof_only():
    r11 = ("11", "2026-08-02", "13:00:00Z", "2026-08-01", "14:00:00Z")
    s = qsched(R10, r11)
    assert is_post_quali_update_due(s, ASOF_R10, None, at("2026-07-19 20:00")) is False


def test_quali_season_rollover():
    s = qsched(("1", "2027-03-07", "04:00:00Z", "2027-03-06", "05:00:00Z"), season="2027")
    assert is_post_quali_update_due(s, ASOF_PREV, None, at("2027-03-06 06:31")) is True


def test_next_quali_target_names_the_round():
    s = qsched(R10)
    assert next_quali_target(s, ASOF_R9, None, at("2026-07-18 12:00")) == (2026, 10)
    assert next_quali_target(s, ASOF_R9, PQ_R10, at("2026-07-18 16:00")) is None


# --- successor runs -------------------------------------------------------------


def test_pending_starts_list_the_uncovered_sessions():
    s = qsched(R10)
    # Saturday evening, postQuali missing: the qualifying session is pending.
    assert pending_session_starts(s, ASOF_R9, None, at("2026-07-18 16:00")) == [
        at("2026-07-18 14:00")
    ]
    # Sunday evening, quali covered: the race is pending.
    assert pending_session_starts(s, ASOF_R9, PQ_R10, at("2026-07-19 16:00")) == [
        at("2026-07-19 13:00")
    ]
    # Once asOf covers the race, nothing is.
    assert pending_session_starts(s, ASOF_R10, None, at("2026-07-19 16:00")) == []


def test_successor_due_only_inside_the_window():
    s = qsched(R10)
    # The race started 13:00 Sunday, so the chain may continue until 01:00 Monday.
    assert is_successor_due(s, ASOF_R9, PQ_R10, at("2026-07-20 00:59")) is True
    assert is_successor_due(s, ASOF_R9, PQ_R10, at("2026-07-20 01:00")) is False


def test_successor_not_due_when_nothing_is_pending():
    assert is_successor_due(qsched(R10), ASOF_R10, None, at("2026-07-19 16:00")) is False


# --- main(): the CLI glue writes the right $GITHUB_OUTPUT key -----------------


def _write_minimal_data(data_dir):
    (data_dir / "schedule.json").write_text(
        json.dumps(sched(("1", "2026-03-08", "04:00:00Z"))), encoding="utf-8"
    )
    (data_dir / "podigami.json").write_text(json.dumps({"asOf": ASOF_PREV}), encoding="utf-8")


def test_main_writes_due_output(tmp_path, monkeypatch):
    _write_minimal_data(tmp_path)
    monkeypatch.setattr(cud, "DATA_DIR", tmp_path)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    cud.main([])

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    key, _, value = lines[0].partition("=")
    assert key == "due"
    assert value in ("true", "false")


def test_main_successor_writes_successor_output(tmp_path, monkeypatch):
    _write_minimal_data(tmp_path)
    monkeypatch.setattr(cud, "DATA_DIR", tmp_path)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    cud.main(["--successor"])

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    key, _, value = lines[0].partition("=")
    assert key == "successor"
    assert value in ("true", "false")


# --- OpenF1 rounds awaiting Jolpica ---------------------------------------------

from check_update_due import is_confirmation_due, stale_unconfirmed  # noqa: E402

UNCONFIRMED_R10 = {
    "season": "2026",
    "round": "10",
    "kind": "race",
    "pending": ["race_results"],
    "since": "2026-07-19T15:00:00+00:00",
}


def test_an_unconfirmed_round_keeps_the_guard_armed():
    assert is_confirmation_due([]) is False
    assert is_confirmation_due([UNCONFIRMED_R10]) is True


def test_a_round_unconfirmed_for_over_48h_is_stale():
    assert stale_unconfirmed([UNCONFIRMED_R10], at("2026-07-21 15:00")) == []
    assert len(stale_unconfirmed([UNCONFIRMED_R10], at("2026-07-21 15:01"))) == 1


def test_the_successor_waits_for_confirmation_inside_the_window():
    s = qsched(R10)
    # Jolpica hasn't confirmed; the chain may run until 12h after the session ended.
    assert is_successor_due(s, ASOF_R10, None, at("2026-07-20 02:59"), [UNCONFIRMED_R10]) is True
    assert is_successor_due(s, ASOF_R10, None, at("2026-07-20 03:00"), [UNCONFIRMED_R10]) is False
