"""Fetch F1 World Championship podiums (P1/P2/P3) from the Jolpica API.

Writes data/podiums.json — one entry per race with the three podium drivers.

By default this runs *incrementally*: it loads the existing podiums.json and
only fetches the latest season already on disk (which may have gained rounds)
plus any newer seasons. Past results are immutable, so older seasons are never
re-fetched. Pass --full to rebuild the whole history from 1950.
"""

from __future__ import annotations

import argparse
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


def fetch_all_for_position(position: int, season: int | None = None) -> list[dict]:
    """Page through every Race that has a finisher at the given position.

    Uses Ergast's path-style position filter: /results/{position}.json
    When ``season`` is given, scopes to /{season}/results/{position}.json so we
    fetch only that season instead of all of history.
    """
    races: list[dict] = []
    offset = 0
    total = None
    base = f"{API_ROOT}/{season}" if season is not None else API_ROOT
    while True:
        data = get(
            f"{base}/results/{position}.json",
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


def load_existing() -> dict[tuple[str, str], dict]:
    """Load podiums.json into a {(season, round): entry} map, if it exists."""
    if not OUT_PATH.exists():
        return {}
    existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {(r["season"], r["round"]): r for r in existing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="rebuild the entire history from 1950 instead of fetching incrementally",
    )
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    by_race: dict[tuple[str, str], dict] = {} if args.full else load_existing()

    # Decide which seasons to fetch. Past seasons are immutable, so we only
    # re-fetch the latest season we already have (it may have new rounds) and
    # trust the API to return any newer seasons via season-scoped requests.
    seasons_to_fetch: list[int | None]
    if args.full or not by_race:
        seasons_to_fetch = [None]  # unscoped = all of history
        print("Full fetch: pulling every season from 1950")
    else:
        latest = max(int(s) for s, _ in by_race)
        # Fetch the latest known season plus the next few in case a new season started.
        seasons_to_fetch = list(range(latest, latest + 2))
        print(f"Incremental fetch: latest season on disk is {latest}; fetching {seasons_to_fetch}")

    for season in seasons_to_fetch:
        for position in (1, 2, 3):
            for race in fetch_all_for_position(position, season):
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
