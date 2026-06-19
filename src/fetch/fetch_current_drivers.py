"""Fetch the current season's racing grid (the real seats, not reserves).

The podigami predictor needs the live grid so the candidate pool stays current.
Ergast's /{season}/drivers.json lists everyone with *any* session entry (FP1
reserves, test drivers), which floods the pool with drivers who will never
podium. Instead we take the union of the drivers who actually started the last
few completed rounds — that is the ~20-seat racing grid.

Current season + latest rounds are read from data/podiums.json (no guessing).

Writes data/current_drivers.json: {"season": "2026", "drivers": [{driverId, name}]}.
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
ROUNDS_BACK = 3  # union the last N completed rounds to catch seat rotations

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
OUT_PATH = DATA_DIR / "current_drivers.json"


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


def season_and_recent_rounds() -> tuple[int, list[int]]:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    season = max(int(p["season"]) for p in podiums)
    rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == season})
    return season, rounds[-ROUNDS_BACK:]


def fetch_round_drivers(season: int, rnd: int) -> dict[str, str]:
    data = get(f"{API_ROOT}/{season}/{rnd}/results.json", {"limit": 100})
    lists = data["MRData"]["RaceTable"]["Races"]
    if not lists:
        return {}
    out: dict[str, str] = {}
    for r in lists[0].get("Results", []):
        d = r["Driver"]
        out[d["driverId"]] = f"{d['givenName']} {d['familyName']}"
    return out


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    season, rounds = season_and_recent_rounds()

    grid: dict[str, str] = {}
    for rnd in rounds:
        grid.update(fetch_round_drivers(season, rnd))
        time.sleep(SLEEP_BETWEEN)

    drivers = [{"driverId": k, "name": v} for k, v in sorted(grid.items())]
    out = {"season": str(season), "drivers": drivers}
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}, rounds {rounds}: {len(drivers)} drivers on the grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
