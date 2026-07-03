"""Fetch current-season constructor standings and driver-constructor mapping.

The podigami predictor uses constructor strength to weight drivers: a driver
on a top constructor is more likely to podium regardless of personal form.

Reads data/podiums.json to determine the current season and latest round,
then fetches:
  1. /{season}/constructorStandings.json → championship points per team
  2. /{season}/{round}/results.json     → driver-to-constructor mapping

Writes data/constructor_standings.json.

Graceful no-op: if fewer than 2 rounds have been completed (too early in the
season for meaningful standings), the file is written with an empty
constructors list so downstream code can detect and skip.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import save_constructor_standings  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
SLEEP_BETWEEN = 1.0
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.2 (https://github.com/local/f1podigami)"
MIN_ROUNDS = 2

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
OUT_PATH = DATA_DIR / "constructor_standings.json"


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


def season_and_rounds(today_year: int | None = None) -> tuple[int, list[int]]:
    """(season, completed rounds) the standings should reflect.

    Off-season the calendar year has no completed rounds yet, so fall back to the
    latest season that has podiums — the final standings stay meaningful (compute
    matches them against the same latest-podium season) instead of being replaced
    by an empty file that switches the car overlay and team labels off.
    """
    year = today_year if today_year is not None else datetime.date.today().year
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
    if not rounds and podiums:
        year = max(int(p["season"]) for p in podiums)
        rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
    return year, rounds


def fetch_standings(season: int) -> list[dict]:
    data = get(f"{API_ROOT}/{season}/constructorStandings.json", {"limit": 100})
    lists = data["MRData"]["StandingsTable"].get("StandingsLists", [])
    if not lists:
        return []
    return lists[0].get("ConstructorStandings", [])


def fetch_driver_constructors(season: int, rnd: int) -> dict[str, str]:
    """Map driverId → constructorId from a specific round's results."""
    data = get(f"{API_ROOT}/{season}/{rnd}/results.json", {"limit": 100})
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return {}
    out: dict[str, str] = {}
    for r in races[0].get("Results", []):
        out[r["Driver"]["driverId"]] = r["Constructor"]["constructorId"]
    return out


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    season, rounds = season_and_rounds()

    if len(rounds) < MIN_ROUNDS:
        print(
            f"Only {len(rounds)} round(s) completed in {season}; too early for constructor standings."
        )
        out = {
            "season": str(season),
            "round": str(rounds[-1]) if rounds else "0",
            "constructors": [],
            "driverConstructor": {},
        }
        save_constructor_standings(out)
        print(f"Wrote empty {OUT_PATH}")
        return 0

    standings = fetch_standings(season)
    time.sleep(SLEEP_BETWEEN)

    driver_map = fetch_driver_constructors(season, rounds[-1])

    constructors = []
    for s in standings:
        c = s["Constructor"]
        constructors.append(
            {
                "constructorId": c["constructorId"],
                "name": c.get("name", c["constructorId"]),
                "points": float(s["points"]),
                "position": int(s["position"]),
                "wins": int(s.get("wins", 0)),
            }
        )

    out = {
        "season": str(season),
        "round": str(rounds[-1]),
        "constructors": constructors,
        "driverConstructor": driver_map,
    }
    save_constructor_standings(out)
    print(f"Wrote {OUT_PATH}")
    print(
        f"  season {season} R{rounds[-1]}: {len(constructors)} constructors, {len(driver_map)} driver mappings"
    )
    for c in constructors[:5]:
        print(f"    P{c['position']} {c['name']}: {c['points']} pts, {c['wins']} wins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
