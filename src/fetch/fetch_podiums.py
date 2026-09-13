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
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import save_podiums  # noqa: E402
from fetch.api_cache import fresh  # noqa: E402
from fetch.unconfirmed import confirm_on_disk  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100
SLEEP_BETWEEN = 1.0
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.1 (https://github.com/local/f1podigami)"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT_PATH = DATA_DIR / "podiums.json"
RESULTS_PATH = DATA_DIR / "race_results.json"


def get(url: str, params: dict) -> dict:
    """GET with exponential backoff on 429/5xx."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0**attempt
            print(
                f"  [{resp.status_code}] backoff {wait:.1f}s (attempt {attempt + 1}/{MAX_BACKOFF_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url} after {MAX_BACKOFF_RETRIES} retries")


def fetch_all_for_position(
    position: int, season: int | None = None, *, fresh_data: bool = False
) -> list[dict]:
    """Page through every Race that has a finisher at the given position.

    Uses Ergast's path-style position filter: /results/{position}.json
    When ``season`` is given, scopes to /{season}/results/{position}.json so we
    fetch only that season instead of all of history.

    ``fresh_data`` bypasses the API's response cache (see fetch.api_cache). This
    file decides ``asOf``, so a cached body here costs a whole cron hour: the run
    finds no new race and opens a PR that changes nothing.
    """
    races: list[dict] = []
    offset = 0
    total = None
    base = f"{API_ROOT}/{season}" if season is not None else API_ROOT
    while True:
        params = {"limit": PAGE_SIZE, "offset": offset}
        data = get(
            f"{base}/results/{position}.json",
            fresh(params) if fresh_data else params,
        )
        mr = data["MRData"]
        if total is None:
            total = int(mr["total"])
            print(f"position={position}: {total} races to fetch")
        page = mr["RaceTable"]["Races"]
        races.extend(page)
        offset += PAGE_SIZE
        print(
            f"  position={position} offset={offset}/{total} (+{len(page)} races, total {len(races)})"
        )
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


def resolve_driver_name(driver_id: str) -> str:
    """Look up one driver's display name from the API.

    Only reached for a driver who appears nowhere else in podiums.json — three
    of them in all of history (Portago, Ayulo, Bettenhausen), because a shared
    drive was their only podium.
    """
    data = get(f"{API_ROOT}/drivers/{driver_id}.json", {})
    drivers = data["MRData"]["DriverTable"]["Drivers"]
    if not drivers:
        raise RuntimeError(f"API knows no driver {driver_id!r}")
    d = drivers[0]
    return f"{d['givenName']} {d['familyName']}"


def backfill_shared() -> int:
    """Fill coDrivers on the committed podiums.json from race_results.json.

    Shared drives are a closed set of pre-1961 races, and race_results.json
    already records every driver at the shared car's position — so this needs no
    historical re-fetch, just the local join.
    """
    podiums = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))

    name_by_id = {r[s]["driverId"]: r[s]["name"] for r in podiums for s in ("p1", "p2", "p3")}

    shared: dict[tuple[str, str], dict[str, list[str]]] = {}
    for race in results:
        by_pos: dict[int, list[str]] = {}
        for row in race["results"]:
            if row["position"] in (1, 2, 3):
                by_pos.setdefault(row["position"], []).append(row["driverId"])
        extra = {f"p{p}": ids[1:] for p, ids in by_pos.items() if len(ids) > 1}
        if extra:
            shared[(race["season"], race["round"])] = extra

    unknown = sorted(
        {d for slots in shared.values() for ids in slots.values() for d in ids} - set(name_by_id)
    )
    for driver_id in unknown:
        name_by_id[driver_id] = resolve_driver_name(driver_id)
        print(f"  resolved {driver_id} -> {name_by_id[driver_id]}")
        time.sleep(SLEEP_BETWEEN)

    filled = 0
    for race in podiums:
        race.pop("coDrivers", None)
        slots = shared.get((race["season"], race["round"]))
        if not slots:
            continue
        race["coDrivers"] = {
            slot: [{"driverId": d, "name": name_by_id[d]} for d in ids]
            for slot, ids in sorted(slots.items())
        }
        filled += 1

    save_podiums(podiums)
    print(f"Backfilled shared drives into {OUT_PATH}: {filled} races")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="rebuild the entire history from 1950 instead of fetching incrementally",
    )
    parser.add_argument(
        "--backfill-shared",
        action="store_true",
        help="fill coDrivers from the committed race_results.json (no full re-fetch)",
    )
    args = parser.parse_args(argv)

    if args.backfill_shared:
        return backfill_shared()

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

    received: dict[tuple[str, str], set[int]] = {}
    # season is None only for the unscoped history rebuild, which is immutable.
    for season in seasons_to_fetch:
        live = season is not None and season >= date.today().year
        for position in (1, 2, 3):
            for race in fetch_all_for_position(position, season, fresh_data=live):
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
                received.setdefault(key, set()).add(position)
                extras = [driver_record(r) for r in results[1:]]
                if extras:
                    entry.setdefault("coDrivers", {})[f"p{position}"] = extras
            time.sleep(SLEEP_BETWEEN)

    races_sorted = sorted(by_race.values(), key=lambda r: (int(r["season"]), int(r["round"])))

    complete: list[dict] = []
    incomplete: list[dict] = []
    for r in races_sorted:
        if r["p1"] and r["p2"] and r["p3"]:
            complete.append(r)
        else:
            incomplete.append(r)

    for r in complete:
        if not r.get("coDrivers"):
            r.pop("coDrivers", None)

    save_podiums(complete)

    # A round OpenF1 filled is confirmed once the API returned all three steps.
    confirm_on_disk("podiums", {k for k, got in received.items() if got == {1, 2, 3}})

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
