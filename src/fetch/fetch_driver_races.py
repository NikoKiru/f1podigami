"""Fetch per-driver race-entry lists (which races each driver started).

The "overdue podium" feature needs two things podiums.json cannot provide:
how many races a set of drivers actually started together, and each driver's
career start count (the denominator for a podium rate).

Driver pool = the top POOL_N drivers by career podium count (for the all-time
near-misses list) plus the current grid (for the still-possible list).

Incremental: a historical driver's race list never changes, so drivers already
cached and not on the current grid are skipped. Only the current grid (whose
lists grow each race) and any new pool members are (re)fetched.

Writes data/driver_races.json:
  {"drivers": {"<id>": {"name": ..., "starts": N, "races": [season*1000+round, ...]}}}
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

API_ROOT = "https://api.jolpi.ca/ergast/f1"
SLEEP_BETWEEN = 1.0
PAGE = 100
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1_podigami/0.2 (https://github.com/local/f1_podigami)"
POOL_N = 60  # top drivers by career podiums included for the all-time list

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
OUT_PATH = DATA_DIR / "driver_races.json"


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


def fetch_driver(driver_id: str) -> dict:
    """All race entries for a driver -> {name, starts, races:[seasonKey,...]}."""
    races: list[int] = []
    name = driver_id
    offset = 0
    total = None
    while True:
        data = get(
            f"{API_ROOT}/drivers/{driver_id}/results.json", {"limit": PAGE, "offset": offset}
        )
        mr = data["MRData"]
        total = int(mr["total"])
        for race in mr["RaceTable"]["Races"]:
            races.append(int(race["season"]) * 1000 + int(race["round"]))
            results = race.get("Results")
            if results:
                d = results[0]["Driver"]
                name = f"{d['givenName']} {d['familyName']}"
        offset += PAGE
        if offset >= total:
            break
        time.sleep(SLEEP_BETWEEN)
    return {"name": name, "starts": total or len(races), "races": sorted(set(races))}


def main() -> int:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    grid_doc = json.loads(GRID_PATH.read_text(encoding="utf-8"))

    podium_count: Counter[str] = Counter()
    name_by_id: dict[str, str] = {}
    for r in podiums:
        for slot in ("p1", "p2", "p3"):
            d = r[slot]
            podium_count[d["driverId"]] += 1
            name_by_id[d["driverId"]] = d["name"]

    top_pool = [d for d, _ in podium_count.most_common(POOL_N)]
    grid_ids = {d["driverId"] for d in grid_doc["drivers"]}
    for d in grid_doc["drivers"]:
        name_by_id.setdefault(d["driverId"], d["name"])
    targets = sorted(set(top_pool) | grid_ids)

    existing = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("drivers", {})

    drivers: dict[str, dict] = {}
    fetched = cached = 0
    for driver_id in targets:
        if driver_id in existing and driver_id not in grid_ids:
            drivers[driver_id] = existing[driver_id]  # historical -> immutable
            cached += 1
            continue
        rec = fetch_driver(driver_id)
        if driver_id in name_by_id:
            rec["name"] = name_by_id[driver_id]
        drivers[driver_id] = rec
        fetched += 1
        print(f"  fetched {driver_id}: {rec['starts']} starts")
        time.sleep(SLEEP_BETWEEN)

    out = {"drivers": dict(sorted(drivers.items()))}
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print(f"  {len(drivers)} drivers ({fetched} fetched, {cached} cached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
