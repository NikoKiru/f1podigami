"""Decide whether an update is due — a cheap, no-network CI guard.

The scheduled poll runs this first: it reads the committed schedule and the latest
race already reflected in the data, and reports whether an update should run. Only
then does the workflow run the full (network) update. Three independent triggers
feed a single ``due`` output:

- :func:`is_update_due` — the newest race whose watch window is open (it opens
  ``ARM_BEFORE`` the scheduled start) is newer than what we have.
- :func:`is_post_quali_update_due` — the next race's qualifying window is open
  but ``podigami.json``'s ``postQuali`` block doesn't cover that round yet
  (fail-safe, so any missing/garbage input just stays quiet).
- :func:`is_confirmation_due` — a round OpenF1 filled (``data/unconfirmed.json``)
  is still waiting on Jolpica to confirm it.

The window opens *before* the session on purpose: GitHub starts only a handful of
scheduled runs a day, so being quick means already waiting when results appear.
A run that lands in the window holds its runner in ``wait_for_results.py`` and
acts only once the data is actually published.

All take loaded dicts (no IO) so they are trivially unit-testable; :func:`main`
loads the data, ORs the three triggers, and writes ``due=true|false`` to
``$GITHUB_OUTPUT``. ``--successor`` instead reports whether a session is still
pending inside ``SUCCESSOR_WINDOW`` — update.yml's cue to dispatch the next run
itself rather than wait for the scheduler. ``--fail-on-stale`` reports neither: it
exits 1 (and prints an ``::error::`` line the run's own logs surface, tripping the
existing auto-update-failure alert) when a round has sat unconfirmed for longer
than :data:`STALE_UNCONFIRMED`, and exits 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

# How far ahead of a session's scheduled start the guard arms. Since 2026-08-27
# GitHub has delivered only ~6-7 of our 96 daily cron slots, at unpredictable
# times, so a run has to be in place *before* results appear. Replaying 14 days
# of real scheduled runs, arming 3h early with a 5h watcher puts a run already
# waiting when the data lands in 93% of races and 91% of qualifying sessions
# (55% for the old arm-after-the-flag / 2h budget) — measured against OpenF1's
# publish time (docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md
# section 4), which this watcher does not poll. Against Jolpica's later, more
# variable publish, the successor hand-over keeps a watch alive across the
# gap, so coverage is at least as high. Early costs only idle runner time: the
# watcher acts on nothing until the round is published.
ARM_BEFORE = timedelta(hours=3)

# A run that times out with a session still unpublished dispatches its own
# successor (update.yml), but only until this long after the session's
# scheduled start — which bounds the chain. 12h spans Jolpica's slowest publish
# this season (~7h after the flag, 2026 Italian GP) with room to spare.
SUCCESSOR_WINDOW = timedelta(hours=12)

# A round OpenF1 filled must be confirmed by Jolpica within this long of its
# session ending, or the run fails loudly (reusing the auto-update-failure
# alert): Jolpica is down, or the two sources disagree about the round.
STALE_UNCONFIRMED = timedelta(hours=48)

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


def read_unconfirmed(data_dir: Path = DATA_DIR) -> list[dict]:
    """data/unconfirmed.json as plain dicts; [] when absent or unreadable."""
    path = data_dir / "unconfirmed.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def is_confirmation_due(unconfirmed: Sequence[dict]) -> bool:
    """True while any round's rows still await Jolpica."""
    return bool(unconfirmed)


def stale_unconfirmed(unconfirmed: Sequence[dict], now: datetime) -> list[str]:
    """Rounds still unconfirmed more than STALE_UNCONFIRMED after their session ended."""
    stale = []
    for e in unconfirmed:
        try:
            since = datetime.fromisoformat(e["since"])
        except (KeyError, TypeError, ValueError):
            stale.append(f"{e.get('season')} R{e.get('round')} (unreadable 'since')")
            continue
        if now - since > STALE_UNCONFIRMED:
            stale.append(
                f"{e['season']} R{e['round']} {e['kind']}: "
                f"{', '.join(e['pending'])} pending since {e['since']}"
            )
    return stale


def pending_session_starts(
    schedule: dict,
    asof: dict,
    post_quali: dict | None,
    now: datetime,
    unconfirmed: Sequence[dict] = (),
) -> list[datetime]:
    """Scheduled starts of the sessions the data still lacks (race and/or qualifying),
    plus the session end of each round still awaiting Jolpica's confirmation."""
    starts: list[datetime] = []
    race = latest_armed_round(schedule, now)
    if race is not None and race > _have(asof):
        entry = _race_by_round(schedule, race[1])
        if entry:
            start = session_start(entry.get("date", ""), entry.get("time", ""))
            if start:
                starts.append(start)
    quali = next_quali_target(schedule, asof, post_quali, now)
    if quali is not None:
        entry = _race_by_round(schedule, quali[1])
        if entry:
            start = session_start(
                entry.get("qualifyingDate") or "", entry.get("qualifyingTime") or ""
            )
            if start:
                starts.append(start)
    for e in unconfirmed:
        try:
            starts.append(datetime.fromisoformat(e["since"]))
        except (KeyError, TypeError, ValueError):
            continue
    return starts


def is_successor_due(
    schedule: dict,
    asof: dict,
    post_quali: dict | None,
    now: datetime,
    unconfirmed: Sequence[dict] = (),
) -> bool:
    """True while a session is pending and ``now`` is inside its SUCCESSOR_WINDOW."""
    return any(
        now < start + SUCCESSOR_WINDOW
        for start in pending_session_starts(schedule, asof, post_quali, now, unconfirmed)
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI glue
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--successor",
        action="store_true",
        help="report successor=true|false (a session still pending) instead of due",
    )
    ap.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="exit 1 when a round stays unconfirmed past STALE_UNCONFIRMED",
    )
    args = ap.parse_args(argv)

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})
    post = podigami.get("postQuali")
    unconfirmed = read_unconfirmed(DATA_DIR)
    now = datetime.now(UTC)

    if args.fail_on_stale:
        stale = stale_unconfirmed(unconfirmed, now)
        for line in stale:
            print(f"::error::Jolpica has not confirmed {line}")
        return 1 if stale else 0

    if args.successor:
        key = "successor"
        value = is_successor_due(schedule, asof, post, now, unconfirmed)
        print(
            f"successor due: {value} (asOf season={asof.get('season')} round={asof.get('round')})"
        )
    else:
        key = "due"
        race_due = is_update_due(schedule, asof, now)
        quali_due = is_post_quali_update_due(schedule, asof, post, now)
        confirm_due = is_confirmation_due(unconfirmed)
        value = race_due or quali_due or confirm_due
        print(
            f"update due: {value} (race={race_due} quali={quali_due} confirm={confirm_due} "
            f"asOf season={asof.get('season')} round={asof.get('round')})"
        )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={'true' if value else 'false'}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
