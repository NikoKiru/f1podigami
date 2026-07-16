"""Decide whether an update is due — a cheap, no-network CI guard.

The scheduled poll runs this first: it reads the committed schedule and the latest
race already reflected in the data, and reports whether an update should run. Only
then does the workflow run the full (network) update. Two independent triggers feed
a single ``due`` output:

- :func:`is_update_due` — a finished race that *should have results by now* is
  newer than what we have (the primary, data-loss-sensitive trigger).
- :func:`is_post_quali_update_due` — the next race's qualifying should be
  classified by now but ``podigami.json``'s ``postQuali`` block doesn't cover that
  round yet (refreshes the pre-race prediction with the grid; fail-safe, so any
  missing/garbage input just stays quiet).

Both take loaded dicts (no IO) so they are trivially unit-testable; :func:`main`
loads the data, ORs the two triggers, and writes ``due=true|false`` to
``$GITHUB_OUTPUT``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# A race is assumed to have published results once this long has elapsed since
# its scheduled start. 2h is long enough that a normal GP is over (race time is
# capped at 2h running / 3h elapsed, and most finish well inside 2h) so we never
# poll mid-race, and short enough to pick results up promptly. Being early is
# harmless: update.py is idempotent and an empty commit is skipped, so an early
# "due" just yields a self-terminating no-op run.
RESULTS_BUFFER = timedelta(hours=2)

# How long after the scheduled qualifying start the classification is assumed
# published. Quali runs ~1h; API publish lag is minutes. Being early is harmless
# (same self-terminating no-op as RESULTS_BUFFER), being late only delays the
# post-quali refresh, so 90min errs toward promptness.
QUALI_BUFFER = timedelta(minutes=90)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _race_start(date: str, time: str) -> datetime | None:
    """Parse a race's scheduled start as a tz-aware UTC datetime.

    ``date`` is ``YYYY-MM-DD``; ``time`` is e.g. ``04:00:00Z`` (may be empty).
    A missing time defaults to end-of-day UTC, so an unknown-time race (only ever
    far-future, before the API sets a session time) is treated as finished well
    after its date — conservative. Bad values yield ``None`` (race skipped).
    """
    if not date:
        return None
    t = time or "23:59:59Z"
    try:
        return datetime.fromisoformat(f"{date}T{t}".replace("Z", "+00:00"))
    except ValueError:
        return None


def is_update_due(schedule: dict, asof: dict, now: datetime) -> bool:
    """True if a race that should have results by ``now`` is newer than ``asof``.

    ``schedule``: parsed ``schedule.json`` for the current season.
    ``asof``:     the latest race already reflected in the data — i.e.
                  ``podigami.json``'s ``asOf`` (``{"season", "round", ...}``).
    ``now``:      tz-aware UTC datetime.
    """
    try:
        season = int(schedule["season"])
    except (KeyError, ValueError, TypeError):
        return False

    # (season, round) we already have. Compared NUMERICALLY — a string compare
    # would order round "9" after "10". A missing/garbage asOf means "we have
    # nothing", so any finished race is due.
    try:
        have = (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        have = (-1, -1)

    latest_due: tuple[int, int] | None = None
    for race in schedule.get("races", []):
        start = _race_start(race.get("date", ""), race.get("time", ""))
        if start is None or now < start + RESULTS_BUFFER:
            continue  # not started, mid-race, or unparseable -> no results yet
        try:
            key = (season, int(race["round"]))
        except (KeyError, ValueError, TypeError):
            continue
        if latest_due is None or key > latest_due:
            latest_due = key

    if latest_due is None:
        return False  # nothing has finished this season yet (early/empty season)
    return latest_due > have


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


def is_post_quali_update_due(
    schedule: dict, asof: dict, post_quali: dict | None, now: datetime
) -> bool:
    """True when the next race's qualifying should be classified by ``now`` but
    ``podigami.json``'s ``postQuali`` doesn't cover that round yet.

    Fail-safe: any missing/garbage input means "don't fire" — unlike the race
    trigger, there is no data-loss risk in staying quiet (the pre-quali
    prediction remains live), and a schedule without quali fields (pre-rollout)
    must never wedge the loop. A garbage ``asOf`` also stays quiet: without it
    the "next" race is unknowable, and the race trigger already covers that case.
    """
    try:
        have = (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        return False
    race = _next_race_entry(schedule, have)
    if race is None:
        return False
    start = _race_start(race.get("qualifyingDate") or "", race.get("qualifyingTime") or "")
    if start is None or now < start + QUALI_BUFFER:
        return False
    if post_quali:
        try:
            covered = (int(post_quali["season"]), int(post_quali["round"]))
        except (KeyError, ValueError, TypeError):
            covered = None
        if covered == (int(schedule["season"]), int(race["round"])):
            return False
    return True


def main() -> int:  # pragma: no cover - thin CLI glue exercised in CI, not unit tests
    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})

    now = datetime.now(UTC)
    race_due = is_update_due(schedule, asof, now)
    quali_due = is_post_quali_update_due(schedule, asof, podigami.get("postQuali"), now)
    due = race_due or quali_due
    print(
        f"update due: {due} (race={race_due} quali={quali_due} "
        f"asOf season={asof.get('season')} round={asof.get('round')})"
    )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"due={'true' if due else 'false'}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
