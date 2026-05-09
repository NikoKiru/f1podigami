"""Fetch final WDC driver standings for every completed F1 season (1950-2025).

Writes data/standings.json — one entry per season with up to 10 ordered drivers.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

API_ROOT = "https://api.jolpi.ca/ergast/f1"
SLEEP_BETWEEN = 1.0
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1_podigami/0.2 (https://github.com/local/f1_podigami)"

FIRST_SEASON = 1950
LAST_COMPLETED_SEASON = 2025  # 2026 in progress as of 2026-05-09

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "standings.json"
TOP_N = 10


def get(url: str, params: dict | None = None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, params=params or {}, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0 ** attempt
            print(f"  [{resp.status_code}] backoff {wait:.1f}s ({attempt + 1}/{MAX_BACKOFF_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def fetch_season_final(season: int) -> dict:
    data = get(f"{API_ROOT}/{season}/driverStandings.json", {"limit": 30})
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return {"season": str(season), "drivers": []}
    standings = lists[0]["DriverStandings"][:TOP_N]
    drivers = []
    for entry in standings:
        d = entry["Driver"]
        drivers.append(
            {
                "position": int(entry["position"]),
                "driverId": d["driverId"],
                "name": f"{d['givenName']} {d['familyName']}",
                "points": entry["points"],
                "wins": entry["wins"],
            }
        )
    return {"season": str(season), "round": lists[0].get("round"), "drivers": drivers}


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    flagged: list[str] = []

    for season in range(FIRST_SEASON, LAST_COMPLETED_SEASON + 1):
        entry = fetch_season_final(season)
        out.append(entry)
        champ = entry["drivers"][0]["name"] if entry["drivers"] else "<none>"
        print(f"  {season}: {champ} (top {len(entry['drivers'])})")
        if len(entry["drivers"]) < 3:
            flagged.append(entry["season"])
        time.sleep(SLEEP_BETWEEN)

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Wrote {OUT_PATH}")
    print(f"  seasons: {len(out)}")
    if flagged:
        print(f"  WARN seasons with <3 drivers in standings: {flagged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
