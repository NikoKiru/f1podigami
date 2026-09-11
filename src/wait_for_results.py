"""Hold the update run until the pending session actually appears upstream.

Why this exists
---------------
``update.yml`` polls on a 15-min cron, but GitHub delivers only a handful of
scheduled slots a day (~6-7 of 96 since 2026-08-27, at unpredictable times), so a
run that fetched *before* the API had published a session previously had to wait
for the next surviving cron slot — about an hour at the 2026 Italian GP, on top
of Jolpica's own ~5h45 publish lag that this module does not touch (that gap is
the OpenF1 fast lane's target, not this one's).

Rather than fight the cron (denser schedules are throttled the same way), the
guard arms 3h before each race and qualifying session
(``check_update_due.ARM_BEFORE``) and the update job holds its runner here,
polling the API itself until the pending round shows up, then runs the pipeline
exactly once. If the budget runs out first it reports ``published=false`` and
update.yml hands the run over to a successor immediately, skipping the
pipeline, so a later link in the chain (or the next scheduled run, once the
chain's window elapses) runs it instead — the watch never lapses between
scheduled slots, and two pipelines never race Jolpica's hourly rate limit
minutes apart. A run whose watcher finds nothing pending at all reports
``published=none`` and also skips the pipeline.

We poll aggregate feeds — ``/{season}/last/results.json`` for a race, the last
row of ``/{season}/qualifying.json`` for qualifying. The round-indexed endpoints
can sit empty for hours while the aggregates already carry the round (#178).

Timing out is not an error: the successor chain (or the next scheduled run)
covers it. Only once the successor window has already elapsed does this run's
own pipeline run anyway (idempotent), as a last-resort fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from check_update_due import is_update_due, latest_armed_round, next_quali_target
from fetch.api_cache import fresh

API_ROOT = "https://api.jolpi.ca/ergast/f1"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Poll every 3 min for up to 5h. The interval is well inside the API's rate
# limits; the budget lets a run that armed 3h before a race cover the race and
# the usual publish lag, and fits update.yml's 345-min job timeout together with
# the in-flight-PR wait (<=15 min) and the pipeline (~20 min).
POLL_INTERVAL_S = 180
POLL_TIMEOUT_S = 5 * 60 * 60


def latest_published_round(payload: object) -> int | None:
    """The round number of the most recent race in a ``last/results`` body.

    Fail-safe: any missing/garbage shape reads as "nothing published yet", so a
    malformed response just keeps the watcher waiting instead of crashing the run.
    """
    try:
        races = payload["MRData"]["RaceTable"]["Races"]  # type: ignore[index]
        return int(races[0]["round"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def wait_for_round(
    target: int,
    fetch: Callable[[], object | None],
    *,
    timeout_s: float = POLL_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll ``fetch`` until the feed reports round >= ``target``.

    Returns True as soon as the round is published, False if the budget runs out.
    Never sleeps when the data is already there, and stops before a sleep that
    would overrun ``timeout_s`` rather than spinning past it.
    """
    deadline = now() + timeout_s
    while True:
        published = latest_published_round(fetch())
        if published is not None and published >= target:
            return True
        if now() + interval_s > deadline:
            return False
        sleep(interval_s)


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
    """Tell update.yml what happened: "true" if the round was seen upstream,
    "false" if the watch timed out, or "none" if nothing was pending to wait
    for. Only "false" lets update.yml hand over to a successor run."""
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
        report("none")
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
        # Not a failure: update.yml hands over to a successor run while the
        # session is still inside its window, skipping the pipeline here; only
        # once that window has elapsed does update.yml run the pipeline anyway
        # (idempotent), as a fallback.
        print(f"Round {rnd} {kind} still unpublished after the budget.")
    report("true" if published else "false")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
