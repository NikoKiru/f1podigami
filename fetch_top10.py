"""Fetch every F1 World Championship race's top-10 finishers since 1950.

Writes data/top10.json — one entry per race with up to 10 ordered finishers.
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
USER_AGENT = "f1_podigami/0.2 (https://github.com/local/f1_podigami)"
MAX_POSITION = 10

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "top10.json"


def get(url: str, params: dict) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0 ** attempt
            print(f"  [{resp.status_code}] backoff {wait:.1f}s ({attempt + 1}/{MAX_BACKOFF_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def fetch_all_for_position(position: int) -> list[dict]:
    races: list[dict] = []
    offset = 0
    total = None
    while True:
        data = get(f"{API_ROOT}/results/{position}.json", {"limit": PAGE_SIZE, "offset": offset})
        mr = data["MRData"]
        if total is None:
            total = int(mr["total"])
            print(f"position={position}: {total} races to fetch")
        page = mr["RaceTable"]["Races"]
        races.extend(page)
        offset += PAGE_SIZE
        print(f"  position={position} offset={offset}/{total} (+{len(page)})")
        if offset >= total or not page:
            break
        time.sleep(SLEEP_BETWEEN)
    return races


def driver_record(result_obj: dict) -> dict:
    d = result_obj["Driver"]
    return {"driverId": d["driverId"], "name": f"{d['givenName']} {d['familyName']}"}


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    by_race: dict[tuple[str, str], dict] = {}

    for position in range(1, MAX_POSITION + 1):
        for race in fetch_all_for_position(position):
            key = (race["season"], race["round"])
            entry = by_race.setdefault(
                key,
                {
                    "season": race["season"],
                    "round": race["round"],
                    "raceName": race["raceName"],
                    "isIndy500": race["raceName"] == "Indianapolis 500",
                    "results": [None] * MAX_POSITION,
                },
            )
            results = race.get("Results") or []
            if results:
                entry["results"][position - 1] = driver_record(results[0])
        time.sleep(SLEEP_BETWEEN)

    races_sorted = sorted(by_race.values(), key=lambda r: (int(r["season"]), int(r["round"])))
    OUT_PATH.write_text(json.dumps(races_sorted, indent=2, ensure_ascii=False), encoding="utf-8")

    indy = sum(1 for r in races_sorted if r["isIndy500"])
    short = sum(1 for r in races_sorted if any(s is None for s in r["results"]))
    seasons = sorted({int(r["season"]) for r in races_sorted})
    print()
    print(f"Wrote {OUT_PATH}")
    print(f"  total races: {len(races_sorted)}")
    print(f"  Indy 500 entries: {indy}")
    print(f"  races with <10 finishers: {short}")
    print(f"  season range: {seasons[0]}-{seasons[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
