"""Fetch the current season's racing grid (the real seats, not reserves).

The podigami predictor needs the live grid so the candidate pool stays current.
Ergast's /{season}/drivers.json lists everyone with *any* session entry (FP1
reserves, test drivers), which floods the pool with drivers who will never
podium. Instead we take the union of the drivers who actually started the last
few completed rounds — that is the ~20-seat racing grid.

A driver back from an absence longer than that window (Hadjar sat out 2026
R12-R14) has not started any of those rounds, so once qualifying for the next
race is in data/qualifying.json its entrants join the grid too. Their name,
code and number come from the season's driver list.

Current season + latest rounds are read from data/podiums.json (no guessing).

Writes data/current_drivers.json:
{"season": "2026", "drivers": [{driverId, name, code?, number?}]}.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import save_current_drivers  # noqa: E402
from fetch.api_cache import fresh  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
SLEEP_BETWEEN = 1.0
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.2 (https://github.com/local/f1podigami)"
ROUNDS_BACK = 3  # union the last N completed rounds to catch seat rotations

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
QUALIFYING_PATH = DATA_DIR / "qualifying.json"
OUT_PATH = DATA_DIR / "current_drivers.json"


def get(url: str, params: dict | None = None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, params=params or {}, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0**attempt
            print(
                f"  [{resp.status_code}] backoff {wait:.1f}s ({attempt + 1}/{MAX_BACKOFF_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def season_and_recent_rounds(today_year: int | None = None) -> tuple[int, list[int]]:
    """(season, last completed rounds) to build the grid from.

    Off-season the calendar year has no completed rounds yet, so fall back to the
    latest season that has podiums — otherwise the grid (and with it the landing
    page's prediction hero) would be wiped empty until round 1 of the new season.
    """
    year = today_year if today_year is not None else datetime.date.today().year
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
    if not rounds and podiums:
        year = max(int(p["season"]) for p in podiums)
        rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
    return year, rounds[-ROUNDS_BACK:]


def pending_qualifiers(season: int, rounds: list[int]) -> tuple[str, list[str]] | None:
    """(season, driverIds) of a qualifying session newer than the last race, if any.

    ``season``/``rounds`` are what the grid is built from. The newest qualifying
    round after the last of them is the next race's entry list, which can hold a
    driver none of those rounds had: one back from an absence, or a rookie at the
    opener (whose grid is still last season's).
    """
    last = (season, max(rounds, default=0))
    qualifying = json.loads(QUALIFYING_PATH.read_text(encoding="utf-8"))
    newer = [q for q in qualifying if (int(q["season"]), int(q["round"])) > last]
    if not newer:
        return None
    q = max(newer, key=lambda q: (int(q["season"]), int(q["round"])))
    return str(q["season"]), [r["driverId"] for r in q["results"]]


def _entry(d: dict) -> dict:
    """{name, code, number} from the API's Driver object.

    ``code`` (the 3-letter TLA) and ``number`` (permanent car number) may be
    absent for some drivers, in which case the key is omitted.
    """
    entry: dict = {"name": f"{d['givenName']} {d['familyName']}"}
    if d.get("code"):
        entry["code"] = d["code"]
    if d.get("permanentNumber"):
        entry["number"] = d["permanentNumber"]
    return entry


def fetch_round_drivers(season: int, rnd: int) -> dict[str, dict]:
    """Return {driverId: {name, code, number}} for one round's starters."""
    data = get(f"{API_ROOT}/{season}/{rnd}/results.json", fresh({"limit": 100}))
    lists = data["MRData"]["RaceTable"]["Races"]
    if not lists:
        return {}
    return {r["Driver"]["driverId"]: _entry(r["Driver"]) for r in lists[0].get("Results", [])}


def fetch_season_drivers(season: str) -> dict[str, dict]:
    """Return {driverId: {name, code, number}} for everyone entered in a season.

    Reserves who only ran a practice session are in this list too, so it is a
    lookup for known entrants, never the grid itself. An aggregate feed rather
    than the round-indexed qualifying one, which can lag for hours (#178).
    """
    data = get(f"{API_ROOT}/{season}/drivers.json", fresh({"limit": 100}))
    return {d["driverId"]: _entry(d) for d in data["MRData"]["DriverTable"]["Drivers"]}


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    season, rounds = season_and_recent_rounds()

    grid: dict[str, dict] = {}
    for rnd in rounds:
        grid.update(fetch_round_drivers(season, rnd))
        time.sleep(SLEEP_BETWEEN)

    pending = pending_qualifiers(season, rounds)
    missing = [d for d in pending[1] if d not in grid] if pending else []
    if missing:
        roster = fetch_season_drivers(pending[0])
        for driver_id in missing:
            if driver_id in roster:
                grid[driver_id] = roster[driver_id]
                print(f"  {driver_id}: qualified for the next race, added to the grid")
            else:
                print(f"  {driver_id}: qualified but is not in the {pending[0]} driver list")

    drivers = [{"driverId": k, **v} for k, v in sorted(grid.items())]
    out = {"season": str(season), "drivers": drivers}
    save_current_drivers(out)
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}, rounds {rounds}: {len(drivers)} drivers on the grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
