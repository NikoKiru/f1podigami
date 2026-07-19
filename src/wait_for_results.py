"""Hold the update run until the finished race actually appears upstream.

Why this exists
---------------
``update.yml`` polls on a 15-min cron, but GitHub delivers only a fraction of
scheduled slots — observed ~13 of 76 on a race Sunday, with multi-hour overnight
gaps. So the retry cadence is really ~1/hour, and a run that fetches *before* the
API has published the race costs a full hour before the next attempt. That is
exactly what happened at the 2026 Belgian GP: the run fetched at 15:32Z, Jolpica
had nothing for round 10 yet, and the site did not go live until 16:25Z — ~100
minutes after the flag.

Rather than fight the cron (denser schedules are throttled the same way), the
update job holds its runner and polls the API itself until the round shows up,
then runs the pipeline exactly once. Cron then only has to land *one* slot in a
multi-hour window, which it reliably does.

We poll ``/{season}/last/results.json`` — an aggregate feed. The round-indexed
``/{season}/{round}/results.json`` endpoint can sit empty for hours after a race
while the aggregates already carry the round (see CLAUDE.md, issue #178), so
keying off it would defeat the whole point.

Timing out is not an error: the pipeline runs anyway (idempotent — a no-op run
just makes no data change), and the guard re-fires on the next tick.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from check_update_due import latest_finished_round

API_ROOT = "https://api.jolpi.ca/ergast/f1"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Poll every 3 min for up to 2h. The interval is well inside the API's rate
# limits and still tight enough that publication is noticed promptly; the budget
# comfortably covers the observed publish lag while staying far under the 6h
# GitHub job limit.
POLL_INTERVAL_S = 180
POLL_TIMEOUT_S = 2 * 60 * 60


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


def _fetch_last_results(season: int) -> object | None:
    """One request for the season's most recent classified race; None on failure."""
    try:
        resp = requests.get(f"{API_ROOT}/{season}/last/results.json", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"  fetch failed ({exc}); will retry")
        return None


def main() -> int:  # pragma: no cover - thin CLI glue exercised in CI, not unit tests
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=float, default=POLL_TIMEOUT_S, help="seconds")
    ap.add_argument("--interval", type=float, default=POLL_INTERVAL_S, help="seconds")
    args = ap.parse_args()

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})

    target = latest_finished_round(schedule, datetime.now(UTC))
    if target is None:
        print("No finished race this season yet; nothing to wait for.")
        return 0

    season, rnd = target
    try:
        have = (int(asof["season"]), int(asof["round"]))
    except (KeyError, ValueError, TypeError):
        have = (-1, -1)
    if target <= have:
        # Only the post-qualifying trigger fired; there is no race to wait for.
        print(f"Data already covers {season} round {rnd}; nothing to wait for.")
        return 0

    print(f"Waiting for {season} round {rnd} to appear upstream...")
    if wait_for_round(
        rnd,
        lambda: _fetch_last_results(season),
        timeout_s=args.timeout,
        interval_s=args.interval,
    ):
        print(f"Round {rnd} is published; running the pipeline.")
    else:
        # Not a failure: the pipeline is idempotent and the guard re-fires.
        print(f"Round {rnd} still unpublished after the budget; running anyway.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
