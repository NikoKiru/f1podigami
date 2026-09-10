# Race-Day Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Have a run already waiting when a race or qualifying result is published, and keep watching until it arrives, instead of waiting hours for GitHub's next scheduled slot. Still Jolpica-only.

**Architecture:** The guard (`src/check_update_due.py`) arms **3 h before** each scheduled race and qualifying session (it used to arm after them). A run that lands in that window holds its runner in `src/wait_for_results.py`, which now waits for either a race or a qualifying session and polls for up to **5 h**. If it times out with the session still unpublished, `update.yml` dispatches a **successor run** with the built-in token, bounded to 12 h after the session's scheduled start. A new first step waits for any in-flight data PR to merge, so a successor never computes on a stale `main`. This is PR 2 of 3 from `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md` (Section 4).

**Tech Stack:** Python 3.11+ (stdlib + `requests`), pytest, GitHub Actions + `gh` CLI.

## Global Constraints

- Python `>=3.11`; ruff `>=0.15.22,<0.16`, line length 100, rules `E,W,F,I,UP,B,C4` (no lambda assignment: E731). `python -m ruff check .` and `python -m ruff format --check .` must pass.
- No new dependencies.
- Tests offline; inject time and network (see the existing `Clock` in `tests/test_wait_for_results.py`). No test may depend on committed `data/` values.
- Values fixed by the spec: arm **3 h** before the scheduled start (`ARM_BEFORE`); watcher budget **5 h**; poll every **3 min**; in-flight PR wait **≤ 15 min**; `update` job `timeout-minutes: 345`; successor only while **< 12 h** after the pending session's scheduled start (`SUCCESSOR_WINDOW`), and only after the watcher **timed out** (`published=false`). That last condition prevents a hot loop when upstream has the data but the pipeline still doesn't cover it.
- The successor dispatch uses `secrets.GITHUB_TOKEN` (`workflow_dispatch` is exempt from GitHub's no-retrigger rule; needs `permissions: actions: write`).
- Branch `feat/race-day-watcher` from an up-to-date `develop` (after PR 1 merged); PR into `develop`; promote only when no qualifying or race is within 48 h.
- Every PR updates `RELEASE_NOTES.md`, and README/CLAUDE.md where they describe behaviour.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
  ```

---

## File Structure

| File | Responsibility |
|---|---|
| `src/check_update_due.py` (rewrite) | Arming window, quali target, pending sessions, successor decision; CLI `--successor` |
| `tests/test_check_update_due.py` (rewrite) | Guard semantics under the new window |
| `src/wait_for_results.py` (modify) | Wait for a race *or* qualifying; 5 h budget; `published=` output |
| `tests/test_wait_for_results.py` (extend) | Target selection, qualifying poll, output |
| `.github/workflows/update.yml` (modify) | `wait` input, `actions: write`, in-flight wait, watcher condition, timeout, successor |
| `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md` | Docs |

---

### Task 0: Branch

- [ ] **Step 1: Branch from develop**

```bash
git switch develop && git pull
git switch -c feat/race-day-watcher
```

---

### Task 1: Guard — arm 3 h early, name the pending sessions

**Files:**
- Rewrite: `src/check_update_due.py`
- Rewrite: `tests/test_check_update_due.py`

**Interfaces:**
- Produces (Task 2 and Plan 3 rely on these names):
  - `ARM_BEFORE: timedelta` (3 h), `SUCCESSOR_WINDOW: timedelta` (12 h)
  - `session_start(date: str, time: str) -> datetime | None`: the old private `_race_start`, made public because Plan 3's fetcher reuses it; same behaviour
  - `latest_armed_round(schedule: dict, now: datetime) -> tuple[int, int] | None` (replaces `latest_finished_round`)
  - `is_update_due(schedule: dict, asof: dict, now: datetime) -> bool`
  - `next_quali_target(schedule: dict, asof: dict, post_quali: dict | None, now: datetime) -> tuple[int, int] | None`
  - `is_post_quali_update_due(schedule, asof, post_quali, now) -> bool`
  - `pending_session_starts(schedule, asof, post_quali, now) -> list[datetime]`
  - `is_successor_due(schedule, asof, post_quali, now) -> bool`
  - CLI: `python src/check_update_due.py` → `due=`; `python src/check_update_due.py --successor` → `successor=` (both to `$GITHUB_OUTPUT`)
- Removes: `RESULTS_BUFFER`, `QUALI_BUFFER`, `latest_finished_round` (only `wait_for_results.py` and the tests used them; Task 2 updates the watcher).

- [ ] **Step 1: Rewrite the tests (they fail against the old guard)**

Replace `tests/test_check_update_due.py` entirely with:

```python
"""Tests for the race-aware update guard (check_update_due).

The guard decides, with no network call, whether a pending session is newer than
what the committed data already reflects (podigami.json's ``asOf``). It arms
``ARM_BEFORE`` (3h) ahead of each scheduled race and qualifying session so a run
is already waiting when results appear: GitHub starts only a handful of scheduled
runs a day. ``is_successor_due`` bounds the hand-over chain between runs.
"""

from datetime import UTC, datetime

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_check_update_due.py -q`
Expected: collection error, `ImportError: cannot import name 'ARM_BEFORE'`.

- [ ] **Step 3: Rewrite the guard**

Replace `src/check_update_due.py` entirely with:

```python
"""Decide whether an update is due — a cheap, no-network CI guard.

The scheduled poll runs this first: it reads the committed schedule and the latest
race already reflected in the data, and reports whether an update should run. Only
then does the workflow run the full (network) update. Two independent triggers feed
a single ``due`` output:

- :func:`is_update_due` — the newest race whose watch window is open (it opens
  ``ARM_BEFORE`` the scheduled start) is newer than what we have.
- :func:`is_post_quali_update_due` — the next race's qualifying window is open
  but ``podigami.json``'s ``postQuali`` block doesn't cover that round yet
  (fail-safe, so any missing/garbage input just stays quiet).

The window opens *before* the session on purpose: GitHub starts only a handful of
scheduled runs a day, so being quick means already waiting when results appear.
A run that lands in the window holds its runner in ``wait_for_results.py`` and
acts only once the data is actually published.

All take loaded dicts (no IO) so they are trivially unit-testable; :func:`main`
loads the data, ORs the two triggers, and writes ``due=true|false`` to
``$GITHUB_OUTPUT``. ``--successor`` instead reports whether a session is still
pending inside ``SUCCESSOR_WINDOW`` — update.yml's cue to dispatch the next run
itself rather than wait for the scheduler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# How far ahead of a session's scheduled start the guard arms. Since 2026-08-27
# GitHub has delivered only ~6-7 of our 96 daily cron slots, at unpredictable
# times, so a run has to be in place *before* results appear. Replaying 14 days
# of real scheduled runs, arming 3h early with a 5h watcher puts a run in place
# for 93% of races and 91% of qualifying sessions (55% for the old
# arm-after-the-flag / 2h budget). Early costs only idle runner time: the
# watcher acts on nothing until the round is published.
ARM_BEFORE = timedelta(hours=3)

# A run that times out with a session still unpublished dispatches its own
# successor (update.yml), but only until this long after the session's
# scheduled start — which bounds the chain. 12h spans Jolpica's slowest publish
# this season (~7h after the flag, 2026 Italian GP) with room to spare.
SUCCESSOR_WINDOW = timedelta(hours=12)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def session_start(date: str, time: str) -> datetime | None:
    """Parse a session's scheduled start as a tz-aware UTC datetime.

    ``date`` is ``YYYY-MM-DD``; ``time`` is e.g. ``04:00:00Z`` (may be empty).
    A missing time defaults to end-of-day UTC, so an unknown-time session (only
    ever far-future, before the API sets a time) arms late — conservative. Bad
    values yield ``None`` (session skipped).
    """
    if not date:
        return None
    t = time or "23:59:59Z"
    try:
        return datetime.fromisoformat(f"{date}T{t}".replace("Z", "+00:00"))
    except ValueError:
        return None


def _have(asof: dict) -> tuple[int, int]:
    """``asOf`` as a numeric (season, round). A missing/garbage asOf means "we
    have nothing", so any armed race counts as newer."""
    try:
        return (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        return (-1, -1)


def _race_by_round(schedule: dict, rnd: int) -> dict | None:
    for race in schedule.get("races", []):
        try:
            if int(race["round"]) == rnd:
                return race
        except (KeyError, ValueError, TypeError):
            continue
    return None


def latest_armed_round(schedule: dict, now: datetime) -> tuple[int, int] | None:
    """The newest ``(season, round)`` whose race window is open by ``now``, or None.

    Shared by :func:`is_update_due` (is it newer than what we have?) and the
    watcher (which round should it wait for the API to publish?).
    """
    try:
        season = int(schedule["season"])
    except (KeyError, ValueError, TypeError):
        return None

    latest: tuple[int, int] | None = None
    for race in schedule.get("races", []):
        start = session_start(race.get("date", ""), race.get("time", ""))
        if start is None or now < start - ARM_BEFORE:
            continue  # window not open yet, or unparseable
        try:
            key = (season, int(race["round"]))
        except (KeyError, ValueError, TypeError):
            continue
        if latest is None or key > latest:
            latest = key
    return latest


def is_update_due(schedule: dict, asof: dict, now: datetime) -> bool:
    """True if the newest race whose window is open is newer than ``asof``.

    Compared NUMERICALLY — a string compare would order round "9" after "10".
    """
    latest_due = latest_armed_round(schedule, now)
    if latest_due is None:
        return False  # no window open this season yet (early/empty season)
    return latest_due > _have(asof)


def _next_race_entry(schedule: dict, have: tuple[int, int]) -> dict | None:
    """The first scheduled race strictly after ``have`` (season, round), or None."""
    try:
        season = int(schedule["season"])
    except (KeyError, ValueError, TypeError):
        return None
    best: tuple[int, dict] | None = None
    for race in schedule.get("races", []):
        try:
            rnd = int(race["round"])
        except (KeyError, ValueError, TypeError):
            continue
        if (season, rnd) <= have:
            continue
        if best is None or rnd < best[0]:
            best = (rnd, race)
    return best[1] if best else None


def next_quali_target(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> tuple[int, int] | None:
    """The ``(season, round)`` whose qualifying window is open but uncovered, or None.

    Fail-safe: any missing/garbage input means None — unlike the race trigger,
    staying quiet loses nothing (the pre-quali prediction remains live), and a
    schedule without quali fields must never wedge the loop. A garbage ``asOf``
    also stays quiet: without it the "next" race is unknowable, and the race
    trigger already covers that case.
    """
    try:
        have = (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        return None
    race = _next_race_entry(schedule, have)
    if race is None:
        return None
    start = session_start(race.get("qualifyingDate") or "", race.get("qualifyingTime") or "")
    if start is None or now < start - ARM_BEFORE:
        return None
    target = (int(schedule["season"]), int(race["round"]))
    if post_quali:
        try:
            covered = (int(post_quali["season"]), int(post_quali["round"]))
        except (KeyError, ValueError, TypeError):
            covered = None
        if covered == target:
            return None
    return target


def is_post_quali_update_due(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> bool:
    """True when the next race's qualifying window is open but ``postQuali``
    doesn't cover that round yet."""
    return next_quali_target(schedule, asof, post_quali, now) is not None


def pending_session_starts(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> list[datetime]:
    """Scheduled starts of the sessions the data still lacks (race and/or qualifying)."""
    starts: list[datetime] = []
    race = latest_armed_round(schedule, now)
    if race is not None and race > _have(asof):
        entry = _race_by_round(schedule, race[1])
        start = entry and session_start(entry.get("date", ""), entry.get("time", ""))
        if start:
            starts.append(start)
    quali = next_quali_target(schedule, asof, post_quali, now)
    if quali is not None:
        entry = _race_by_round(schedule, quali[1])
        start = entry and session_start(
            entry.get("qualifyingDate") or "", entry.get("qualifyingTime") or ""
        )
        if start:
            starts.append(start)
    return starts


def is_successor_due(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> bool:
    """True while a session is pending and ``now`` is inside its SUCCESSOR_WINDOW."""
    return any(
        now < start + SUCCESSOR_WINDOW
        for start in pending_session_starts(schedule, asof, post_quali, now)
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI glue
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--successor",
        action="store_true",
        help="report successor=true|false (a session still pending) instead of due",
    )
    args = ap.parse_args(argv)

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})
    post = podigami.get("postQuali")
    now = datetime.now(UTC)

    if args.successor:
        key = "successor"
        value = is_successor_due(schedule, asof, post, now)
        print(f"successor due: {value} (asOf season={asof.get('season')} round={asof.get('round')})")
    else:
        key = "due"
        race_due = is_update_due(schedule, asof, now)
        quali_due = is_post_quali_update_due(schedule, asof, post, now)
        value = race_due or quali_due
        print(
            f"update due: {value} (race={race_due} quali={quali_due} "
            f"asOf season={asof.get('season')} round={asof.get('round')})"
        )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={'true' if value else 'false'}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run the guard tests to verify they pass**

Run: `python -m pytest tests/test_check_update_due.py -q`
Expected: `33 passed`.

- [ ] **Step 5: Commit (the watcher still imports the removed name, so fix it in Task 2 before pushing)**

```bash
python -m ruff check src/check_update_due.py tests/test_check_update_due.py
python -m ruff format src/check_update_due.py tests/test_check_update_due.py
git add src/check_update_due.py tests/test_check_update_due.py
git commit -m "Arm the update guard 3h before each race and qualifying session" -m "GitHub starts only a handful of scheduled runs a day, so a run has to be
waiting before results appear. Adds the pending-session and successor
helpers the workflow uses to hand over between runs.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 2: Watcher — race or qualifying, 5 h, report `published`

**Files:**
- Modify: `src/wait_for_results.py`
- Test: `tests/test_wait_for_results.py` (append)

**Interfaces:**
- Consumes: `latest_armed_round`, `next_quali_target` (Task 1).
- Produces (Plan 3 extends these): `wait_target(schedule: dict, podigami: dict, now: datetime) -> tuple[str, int, int] | None` (`("race"|"qualifying", season, round)`); `_fetch_last_qualifying(season: int) -> object | None`; `_get_json(url: str, params: dict | None = None) -> object | None`; `report(published: str) -> None` (writes `published=<value>`; this plan uses `"true"`/`"false"`, Plan 3 adds `"fast"`); `POLL_TIMEOUT_S = 5 * 60 * 60`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_wait_for_results.py`, replace the import line
`from wait_for_results import latest_published_round, wait_for_round` with:

```python
from datetime import UTC, datetime

from wait_for_results import latest_published_round, wait_for_round, wait_target
```

Then append to the end of the file:

```python
# --- what to wait for (race first, then qualifying) --------------------------------

SCHEDULE = {
    "season": "2026",
    "races": [
        {"round": "13", "date": "2026-09-06", "time": "13:00:00Z",
         "qualifyingDate": "2026-09-05", "qualifyingTime": "14:00:00Z"},
        {"round": "14", "date": "2026-09-13", "time": "13:00:00Z",
         "qualifyingDate": "2026-09-12", "qualifyingTime": "14:00:00Z"},
    ],
}


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_wait_target_is_the_armed_race_newer_than_the_data():
    podigami = {"asOf": {"season": "2026", "round": "12"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-06 10:00")) == ("race", 2026, 13)


def test_wait_target_falls_back_to_the_next_qualifying():
    podigami = {"asOf": {"season": "2026", "round": "13"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 11:00")) == ("qualifying", 2026, 14)


def test_nothing_to_wait_for_once_post_quali_covers_the_round():
    """The quali-day short-circuit: a covered round must not hold the runner."""
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 18:00")) is None


def test_nothing_to_wait_for_before_any_window_opens():
    podigami = {"asOf": {"season": "2026", "round": "13"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 10:59")) is None


# --- the qualifying poll: two cache-busted requests, only the last row -------------


class _Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_qualifying_poll_reads_only_the_final_row(monkeypatch):
    import wait_for_results as wfr
    from fetch.api_cache import CACHE_BUSTER

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        rnd = "3" if params.get("offset") is not None else "1"
        return _Resp({"MRData": {"total": "45", "RaceTable": {"Races": [{"round": rnd}]}}})

    monkeypatch.setattr(wfr.requests, "get", fake_get)
    assert latest_published_round(wfr._fetch_last_qualifying(2026)) == 3
    assert all("2026/qualifying.json" in url for url, _ in calls)
    assert calls[1][1]["offset"] == 44 and calls[1][1]["limit"] == 1
    assert all(CACHE_BUSTER in params for _, params in calls)


def test_qualifying_poll_is_none_on_garbage(monkeypatch):
    import wait_for_results as wfr

    monkeypatch.setattr(wfr.requests, "get", lambda url, params=None, timeout=None: _Resp({"nope": 1}))
    assert wfr._fetch_last_qualifying(2026) is None


def test_report_tells_the_workflow_whether_the_round_was_seen(tmp_path, monkeypatch):
    import wait_for_results as wfr

    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    wfr.report("false")
    wfr.report("true")
    assert out.read_text(encoding="utf-8").splitlines() == ["published=false", "published=true"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_wait_for_results.py -q`
Expected: collection error — `ImportError: cannot import name 'latest_finished_round' from 'check_update_due'` (Task 1 removed it), later `wait_target` missing.

- [ ] **Step 3: Update the watcher**

In `src/wait_for_results.py`:

(a) Replace the module docstring with:

```python
"""Hold the update run until the pending session actually appears upstream.

Why this exists
---------------
``update.yml`` polls on a 15-min cron, but GitHub delivers only a handful of
scheduled slots a day (~6-7 of 96 since 2026-08-27, at unpredictable times), so a
run that fetches *before* the API has published a session can cost hours before
the next attempt. That is how the 2026 Italian GP took ~7h to reach the site.

Rather than fight the cron (denser schedules are throttled the same way), the
guard arms 3h before each race and qualifying session
(``check_update_due.ARM_BEFORE``) and the update job holds its runner here,
polling the API itself until the pending round shows up, then runs the pipeline
exactly once. If the budget runs out first it reports ``published=false`` and
update.yml hands over to a successor run, so the watch never lapses between
scheduled slots.

We poll aggregate feeds — ``/{season}/last/results.json`` for a race, the last
row of ``/{season}/qualifying.json`` for qualifying. The round-indexed endpoints
can sit empty for hours while the aggregates already carry the round (#178).

Timing out is not an error: the pipeline runs anyway (idempotent).
"""
```

(b) Add `import os` to the stdlib imports (keep them sorted: `argparse, json, os, sys, time`), and change the guard import to:

```python
from check_update_due import is_update_due, latest_armed_round, next_quali_target
```

(c) Replace the budget comment and constants with:

```python
# Poll every 3 min for up to 5h. The interval is well inside the API's rate
# limits; the budget lets a run that armed 3h before a race cover the race and
# the usual publish lag, and fits update.yml's 345-min job timeout together with
# the in-flight-PR wait (<=15 min) and the pipeline (~20 min).
POLL_INTERVAL_S = 180
POLL_TIMEOUT_S = 5 * 60 * 60
```

(d) Replace `_fetch_last_results` and `main` with:

```python
def _get_json(url: str, params: dict | None = None) -> object | None:
    """One cache-busted GET; None on any failure (the poll just tries again).

    Cache-busted: the API caches each feed per request-variant with a long TTL,
    so an un-nonced poll re-reads the same stale body every interval and waits
    out the entire budget on a session that is already published (#239).
    """
    try:
        resp = requests.get(url, params=fresh(params), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"  fetch failed ({exc}); will retry")
        return None


def _fetch_last_results(season: int) -> object | None:
    """The season's most recent classified race; None on failure."""
    return _get_json(f"{API_ROOT}/{season}/last/results.json")


def _fetch_last_qualifying(season: int) -> object | None:
    """The season's newest qualifying row (one ``Races`` entry); None on failure.

    Reads the aggregate feed's row count, then only its final row: two requests
    per poll instead of paging the whole season.
    """
    url = f"{API_ROOT}/{season}/qualifying.json"
    head = _get_json(url, {"limit": 1})
    try:
        total = int(head["MRData"]["total"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError):
        return None
    if total < 1:
        return head  # no rows yet: latest_published_round reads None
    return _get_json(url, {"limit": 1, "offset": total - 1})


def wait_target(schedule: dict, podigami: dict, now: datetime) -> tuple[str, int, int] | None:
    """What this run should wait for — ``(kind, season, round)`` — or None.

    A race newer than ``asOf`` whose window is open comes first (the guard's own
    rule, so the two can't disagree); otherwise the next race's qualifying, if its
    window is open and ``postQuali`` doesn't cover it yet. Nothing pending means
    return at once, holding no runner.
    """
    asof = podigami.get("asOf") or {}
    if is_update_due(schedule, asof, now):
        season, rnd = latest_armed_round(schedule, now)  # not None when due
        return ("race", season, rnd)
    quali = next_quali_target(schedule, asof, podigami.get("postQuali"), now)
    if quali is not None:
        return ("qualifying", quali[0], quali[1])
    return None


def report(published: str) -> None:
    """Tell update.yml whether the round was seen ("true") or the watch timed out
    ("false"); anything but "true" lets it hand over to a successor run."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"published={published}\n")


def main() -> int:  # pragma: no cover - thin CLI glue exercised in CI, not unit tests
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=float, default=POLL_TIMEOUT_S, help="seconds")
    ap.add_argument("--interval", type=float, default=POLL_INTERVAL_S, help="seconds")
    args = ap.parse_args()

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))

    target = wait_target(schedule, podigami, datetime.now(UTC))
    if target is None:
        print("Nothing pending upstream; nothing to wait for.")
        report("true")
        return 0

    kind, season, rnd = target

    def fetch() -> object | None:
        if kind == "race":
            return _fetch_last_results(season)
        return _fetch_last_qualifying(season)

    print(f"Waiting for {season} round {rnd} {kind} to appear upstream...")
    published = wait_for_round(rnd, fetch, timeout_s=args.timeout, interval_s=args.interval)
    if published:
        seen = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
        print(f"Round {rnd} {kind} seen upstream at {seen}; running the pipeline.")
    else:
        # Not a failure: the pipeline is idempotent and update.yml hands over to a
        # successor run while the session is still inside its window.
        print(f"Round {rnd} {kind} still unpublished after the budget; running anyway.")
    report("true" if published else "false")
    return 0
```

(`latest_published_round` and `wait_for_round` stay exactly as they are.)

- [ ] **Step 4: Run the watcher and guard tests**

Run: `python -m pytest tests/test_wait_for_results.py tests/test_check_update_due.py -q`
Expected: all pass, including the existing `test_the_poll_request_bypasses_the_response_cache` (its `fake_get(url, **kwargs)` still sees the nonce, because `_get_json` passes `params=fresh(params)`).

- [ ] **Step 5: Commit**

```bash
python -m ruff check src/wait_for_results.py tests/test_wait_for_results.py
python -m ruff format src/wait_for_results.py tests/test_wait_for_results.py
git add src/wait_for_results.py tests/test_wait_for_results.py
git commit -m "Let the watcher wait for qualifying too, for up to 5h" -m "Reports published=true|false so the workflow can hand over to a successor
run when a session is still unpublished at the end of the budget.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 3: Workflow — in-flight wait, watcher condition, timeout, successor

**Files:**
- Modify: `.github/workflows/update.yml`

- [ ] **Step 1: Add the `wait` dispatch input**

Under `on.workflow_dispatch.inputs`, after `force`, add:

```yaml
      wait:
        description: "Hold the runner and poll upstream like a scheduled run (successor runs set this)"
        type: boolean
        default: false
```

- [ ] **Step 2: Grant `actions: write`**

In the top-level `permissions:` block, add:

```yaml
  actions: write # a watch that times out dispatches its own successor run (see the update job)
```

- [ ] **Step 3: Timeout and the in-flight PR wait**

In the `update` job, replace the `timeout-minutes` comment and value with:

```yaml
    # 15 min in-flight-PR wait + 5h watcher + ~20 min pipeline/PR/tests, under
    # GitHub's 6h job cap.
    timeout-minutes: 345
```

Insert this as the **first** step of the `update` job, before `actions/checkout`:

```yaml
      # A successor run is dispatched at the very end of the run before it, often
      # before that run's data PR has auto-merged. Checking out main now would
      # compute on data that is about to change, so wait for the PR first. Give
      # up after 15 min: a PR that never merges is the watchdog's to report.
      - name: Wait for an in-flight data PR to merge
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          for _ in $(seq 1 30); do
            open="$(gh pr list --repo "$GITHUB_REPOSITORY" --head auto/update-data \
              --state open --json number --jq 'length')"
            if [ "$open" = "0" ]; then
              echo "No data PR in flight."
              exit 0
            fi
            echo "A data PR is still open; waiting 30s..."
            sleep 30
          done
          echo "Data PR still open after 15 min; continuing (the watchdog reports a stuck PR)."
```

- [ ] **Step 4: The watcher step**

Replace the comment block and the `Wait for the finished race to be published upstream` step with:

```yaml
      # GitHub starts only a handful of scheduled runs a day, so the guard arms 3h
      # before each race and qualifying session and a run that lands in that window
      # holds its runner here, polling until the session is published (up to 5h).
      # Scheduled runs and successor runs (wait=true) only: a human dispatch should
      # act now, and `full` is a reconciliation, not a session.
      - name: Wait for the pending session to be published upstream
        id: wait
        if: needs.check.outputs.mode != 'full' && (github.event_name == 'schedule' || inputs.wait)
        run: python src/wait_for_results.py
```

- [ ] **Step 5: The successor steps**

Append after `Run tests` (the last step of the `update` job):

```yaml
      # When the watch timed out with the session still unpublished, the next
      # scheduled slot can be hours away, so hand over to a fresh run right away.
      # Only after a full watch (published != 'true'): if upstream already had the
      # data and the pipeline still doesn't cover it, an instant re-run would just
      # loop, and the scheduled runs retry that case instead. The guard bounds the
      # chain to 12h after the session's scheduled start.
      - name: Check whether a session is still pending
        id: successor
        if: >-
          needs.check.outputs.mode != 'full'
          && (github.event_name == 'schedule' || inputs.wait)
          && steps.wait.outputs.published != 'true'
        run: python src/check_update_due.py --successor
      - name: Hand over to a successor run
        if: steps.successor.outputs.successor == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh workflow run update.yml --repo "$GITHUB_REPOSITORY" -f mode=auto -f wait=true
```

- [ ] **Step 6: Check the YAML structure**

Run:
```bash
python -c "import yaml; wf=yaml.safe_load(open('.github/workflows/update.yml',encoding='utf-8')); u=wf['jobs']['update']; print(u['timeout-minutes'], [s.get('name', s.get('uses')) for s in u['steps']]); print(wf['permissions']); print(list(wf[True]['workflow_dispatch']['inputs']))"
```
Expected: `345`; the first step is `Wait for an in-flight data PR to merge`; the last two are `Check whether a session is still pending`, `Hand over to a successor run`; permissions include `actions: write`; inputs `['mode', 'force', 'wait']`. (PyYAML parses the `on:` key as `True`.)

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "Hand a timed-out watch over to a successor run" -m "Also waits for an in-flight data PR before checkout and raises the job
timeout to 345 min for the 5h watcher.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 4: Docs, verification, PR

**Files:** `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md`

- [ ] **Step 1: CLAUDE.md**

1. In the `check` job bullet of "### Automated data updates (`update.yml`)", replace `and proceeds only when a race that should have results by now is newer than `podigami.json`'s `asOf`.` with:

```markdown
and proceeds only when a pending session is newer than the data: a race newer than `podigami.json`'s `asOf`, or the next race's qualifying not yet covered by `postQuali`. The guard **arms 3 h before each session's scheduled start** (`ARM_BEFORE`), so a run is already waiting when results appear.
```
and replace `` `workflow_dispatch` takes `mode` (auto/full) + `force`. `` with `` `workflow_dispatch` takes `mode` (auto/full), `force`, and `wait` (hold the runner like a scheduled run — successor runs set it). ``

2. Replace the heading `#### The cron is ~1/hour, not every 15 min — don't design around the schedule` with `#### The cron is a handful of runs a day, not every 15 min — don't design around the schedule`, and add this paragraph right after the existing first paragraph (the 2026-07-19 measurement):

```markdown
It got worse: from **2026-08-27** GitHub delivered only **~6–7 of 96 slots a day** (gaps: median 39 min, p90 4.2 h, max 11.9 h — `docs/research/2026-09-08-live-data-latency.md`). That regime is why the guard now arms *before* sessions and why a timed-out watch hands over to a successor run rather than waiting for the next slot.
```

3. Replace the paragraph that starts `**Fix (#206): wait in-run rather than retry across runs.**` and the six bullets under it (from `- It polls an **aggregate** feed` through `- Trigger on demand:`) with:

```markdown
**Fix (#206, extended #<PR>): wait in-run rather than retry across runs.** `src/wait_for_results.py` polls every 3 min for up to **5 h** until the pending round appears — `/{season}/last/results.json` for a race, the last row of `/{season}/qualifying.json` for qualifying — then the pipeline runs once. Notes:
- It polls **aggregate** feeds on purpose — the round-indexed endpoints lag for hours (see #178 below).
- The guard arms **3 h before** each race and qualifying session (`check_update_due.ARM_BEFORE`). Replaying 14 days of the post-2026-08-27 scheduler, that puts a run in place when the data lands for **93% of races / 91% of qualifying sessions**. Arming early costs only idle runner time.
- A timeout is **not** a failure: the pipeline runs anyway (idempotent) and the watcher reports `published=false`. The job then **dispatches a successor run** (`gh workflow run update.yml -f mode=auto -f wait=true`, built-in token, `actions: write`) while the session is < 12 h past its scheduled start (`SUCCESSOR_WINDOW`). Only after a *timed-out* watch: if upstream already had the data and the pipeline still doesn't cover it, an instant re-run would loop, so the scheduled runs retry that case.
- The `update` job's first step waits (≤ 15 min) for any open `auto/update-data` PR to merge, so a successor never computes on a `main` that is about to change.
- It runs on **scheduled events and successor dispatches** (`wait=true`), not for `mode=full` or a plain human dispatch, which stays snappy.
- The `update` job carries `timeout-minutes: 345` (15 min PR wait + 5 h watcher + ~20 min pipeline, under GitHub's 6 h cap).
- Trigger on demand: `gh workflow run update.yml -f mode=auto -f force=true` (or `-f mode=full`; add `-f wait=true` to hold the runner and poll).
```

- [ ] **Step 2: README.md**

In the `update.yml` row of the workflow table, replace:

```markdown
polls every 15 min for a newly-finished race (1h40 buffer) *or* a just-completed qualifying session (90-min buffer, to publish the post-qualifying prediction update). When a race is due it waits in-run for the results to be published upstream, then opens an auto-merging PR;
```
with:
```markdown
arms 3 h before every race and qualifying session (the post-qualifying prediction update included), so a run is already waiting when results appear. It polls upstream in-run for up to 5 h and hands over to a fresh run if the results still aren't out, then opens an auto-merging PR;
```

- [ ] **Step 3: RELEASE_NOTES.md**

Under the current date heading (create it at the top if missing), in `### Improvements`:

```markdown
- **Race and qualifying results should now reach the site soon after the API publishes them, not at GitHub's next scheduled run.** Since late August GitHub has started only ~6–7 of the refresh workflow's 96 scheduled runs a day, at unpredictable times, which is how the 2026 Italian GP took ~7 hours to appear. The refresh now arms 3 hours *before* each race and qualifying session, so a run is usually already waiting (93% of races, replaying two weeks of real scheduled runs). It polls for up to 5 hours, and if the results still aren't out it starts its own successor run instead of waiting for the next slot, for up to 12 hours after the session (#<PR>)
```

- [ ] **Step 4: Full verification**

```bash
python -m ruff check .
python -m ruff format --check .
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
```
Expected: all green.

- [ ] **Step 5: Dry-run the CLIs against the real data**

```bash
python src/check_update_due.py
python src/check_update_due.py --successor
```
Expected: two lines like `update due: … (race=… quali=… asOf season=2026 round=13)` and `successor due: …`. No traceback.

- [ ] **Step 6: Commit, PR, fill in the number, merge, promote, clean up**

```bash
git add CLAUDE.md README.md RELEASE_NOTES.md
git commit -m "Document the race-day watcher" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
git push -u origin feat/race-day-watcher
gh pr create --base develop --title "Arm the data refresh before each session and keep watching until results land" --body-file - <<'EOF'
## Summary
PR 2 of 3 from `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md`. GitHub now starts only ~6–7 of our 96 scheduled refresh runs a day, so the guard arms 3 h before each race and qualifying session, the watcher waits up to 5 h (race or qualifying), and a timed-out watch hands over to a successor run, bounded to 12 h after the session. Still Jolpica-only.

## Changes
- `check_update_due.py`: `ARM_BEFORE` (3 h) replaces the post-session buffers; `next_quali_target`, `pending_session_starts`, `is_successor_due`; `--successor` CLI
- `wait_for_results.py`: waits for the pending race or qualifying (last row of the aggregate qualifying feed), 5 h budget, reports `published=`
- `update.yml`: `wait` input, `actions: write`, in-flight data PR wait before checkout, `timeout-minutes: 345`, successor dispatch after a timed-out watch
- Docs: CLAUDE.md, README, RELEASE_NOTES

## Testing
- `python -m pytest -q` (guard tests rewritten for the new window; watcher target selection, qualifying poll and `published` output added)
- `python -m ruff check .` / `python -m ruff format --check .`
- `PYTHONPATH=src python -m datalib.validate`
- CLI dry runs of `check_update_due.py` with and without `--successor`

## Checklist
- [x] Lint and format pass
- [x] Tests pass
- [x] No security issues introduced (successor dispatch uses the built-in token; chain bounded to 12 h and only after a timed-out watch)
- [x] RELEASE_NOTES.md updated

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
EOF
```

Then:

1. Replace `#<PR>` in `CLAUDE.md` and `RELEASE_NOTES.md` with the printed number; `git commit -am "Reference #<number> in the release note"` (with the trailer) and `git push`.
2. `gh pr checks <number> --watch` (7 checks), then `gh pr merge <number> --squash --delete-branch`.
   Prove the merged workflow still runs against `main`'s older scripts. There the successor check just prints the old `update due` line, so no successor is dispatched:
   ```bash
   gh workflow run update.yml -f mode=auto -f force=true
   sleep 20; run=$(gh run list --workflow=update.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run watch "$run" --exit-status
   ```
   Expected: green. If it fails, revert the merge on `develop` immediately.
3. Promote only when no qualifying or race is within the next 48 h:
   ```bash
   gh pr create --base main --head develop --title "Promote develop to main: race-day watcher" \
     --body "Promotes #<number>: the refresh arms 3 h before each race and qualifying session, watches up to 5 h, and hands a timed-out watch over to a successor run (bounded to 12 h). No data files change."
   gh pr checks <promotion number> --watch   # all 9 required checks
   gh pr merge <promotion number> --merge
   ```
4. Confirm the next scheduled run logs the new guard line: `gh run list --workflow=update.yml --limit 3`, then `gh run view <id> --log | grep "update due"`.
5. `git switch develop && git pull && git branch -d feat/race-day-watcher`.
