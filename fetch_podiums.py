"""Fetch every F1 World Championship podium (P1/P2/P3) since 1950 from the Jolpica API.

Writes data/podiums.json — one entry per race with the three podium drivers.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

API_ROOT = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100
SLEEP_BETWEEN = 1.0
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1_podigami/0.1 (https://github.com/local/f1_podigami)"

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "podiums.json"


def get(url: str, params: dict) -> dict:
    """GET with exponential backoff on 429/5xx."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0 ** attempt
            print(f"  [{resp.status_code}] backoff {wait:.1f}s (attempt {attempt + 1}/{MAX_BACKOFF_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url} after {MAX_BACKOFF_RETRIES} retries")


def fetch_all_for_position(position: int) -> list[dict]:
    """Page through every Race that has a finisher at the given position.

    Uses Ergast's path-style position filter: /results/{position}.json
    """
    races: list[dict] = []
    offset = 0
    total = None
    while True:
        data = get(
            f"{API_ROOT}/results/{position}.json",
            {"limit": PAGE_SIZE, "offset": offset},
        )
        mr = data["MRData"]
        if total is None:
            total = int(mr["total"])
            print(f"position={position}: {total} races to fetch")
        page = mr["RaceTable"]["Races"]
        races.extend(page)
        offset += PAGE_SIZE
        print(f"  position={position} offset={offset}/{total} (+{len(page)} races, total {len(races)})")
        if offset >= total or not page:
            break
        time.sleep(SLEEP_BETWEEN)
    return races


def driver_record(result_obj: dict) -> dict:
    d = result_obj["Driver"]
    return {
        "driverId": d["driverId"],
        "name": f"{d['givenName']} {d['familyName']}",
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    by_race: dict[tuple[str, str], dict] = {}

    for position in (1, 2, 3):
        for race in fetch_all_for_position(position):
            key = (race["season"], race["round"])
            entry = by_race.setdefault(
                key,
                {
                    "season": race["season"],
                    "round": race["round"],
                    "raceName": race["raceName"],
                    "p1": None,
                    "p2": None,
                    "p3": None,
                },
            )
            results = race.get("Results") or []
            if not results:
                continue
            entry[f"p{position}"] = driver_record(results[0])
        time.sleep(SLEEP_BETWEEN)

    races_sorted = sorted(by_race.values(), key=lambda r: (int(r["season"]), int(r["round"])))

    complete: list[dict] = []
    incomplete: list[dict] = []
    for r in races_sorted:
        if r["p1"] and r["p2"] and r["p3"]:
            complete.append(r)
        else:
            incomplete.append(r)

    OUT_PATH.write_text(json.dumps(complete, indent=2, ensure_ascii=False), encoding="utf-8")

    seasons = sorted({int(r["season"]) for r in complete})
    print()
    print(f"Wrote {OUT_PATH}")
    print(f"  races with full podium: {len(complete)}")
    print(f"  races dropped (incomplete): {len(incomplete)}")
    if incomplete:
        for r in incomplete:
            missing = [p for p in ("p1", "p2", "p3") if not r[p]]
            print(f"    - {r['season']} R{r['round']} {r['raceName']} missing {missing}")
    if seasons:
        print(f"  season range: {seasons[0]}-{seasons[-1]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
