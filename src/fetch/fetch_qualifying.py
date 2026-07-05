"""Fetch F1 qualifying classifications (grid-setting session order).

Writes data/qualifying.json — one entry per race with each driver's
qualifying position. Coverage in the source API starts in 1994; earlier
seasons simply return zero rows and are skipped. Lap times are deliberately
not stored — the v2 model only consumes the session *order*.

By default this runs *incrementally*: it re-fetches only the latest season
already on disk plus the next one. Pass --full to rebuild 1994→ from scratch.
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
from datalib import save_qualifying  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100
SLEEP_BETWEEN = 1.1
# A --full run alongside the other fetchers can brush the API's hourly budget;
# 8 retries (~4 min of cumulative backoff) rides out a rolling throttle window
# where the fleet-wide 6 would give up and fail the scheduled update.
MAX_BACKOFF_RETRIES = 8
USER_AGENT = "f1podigami/0.1 (https://github.com/local/f1podigami)"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT_PATH = DATA_DIR / "qualifying.json"

FIRST_SEASON = 1994  # Ergast/Jolpica qualifying coverage starts here


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


def quali_entry(race: dict) -> dict:
    """Map one Ergast race's QualifyingResults to the committed contract shape."""
    return {
        "season": race["season"],
        "round": race["round"],
        "results": [
            {
                "driverId": q["Driver"]["driverId"],
                "constructorId": q["Constructor"]["constructorId"],
                "position": int(q["position"]),
            }
            for q in race.get("QualifyingResults") or []
        ],
    }


def accumulate_page(merged: dict[tuple[str, str], dict], page: list[dict]) -> None:
    """Fold one API page into ``merged`` keyed by (season, round), concatenating
    QualifyingResults split across row-paged responses."""
    for race in page:
        key = (race["season"], race["round"])
        if key in merged:
            merged[key]["QualifyingResults"].extend(race.get("QualifyingResults") or [])
        else:
            copy = dict(race)
            copy["QualifyingResults"] = list(race.get("QualifyingResults") or [])
            merged[key] = copy


def fetch_season_races(season: int) -> list[dict]:
    """Page through /{season}/qualifying.json; empty seasons return no races."""
    merged: dict[tuple[str, str], dict] = {}
    offset = 0
    total = None
    while True:
        data = get(f"{API_ROOT}/{season}/qualifying.json", {"limit": PAGE_SIZE, "offset": offset})
        mr = data["MRData"]
        if total is None:
            total = int(mr["total"])
            print(f"season {season}: {total} qualifying rows")
        page = mr["RaceTable"]["Races"]
        accumulate_page(merged, page)
        offset += PAGE_SIZE
        if offset >= total or not page:
            break
        time.sleep(SLEEP_BETWEEN)
    return [merged[k] for k in sorted(merged, key=lambda k: (int(k[0]), int(k[1])))]


def merge_entries(existing: list[dict], fetched: list[dict]) -> list[dict]:
    """Replace re-fetched races by (season, round), keep the rest, sort numerically."""
    by_race = {(r["season"], r["round"]): r for r in existing}
    for r in fetched:
        by_race[(r["season"], r["round"])] = r
    return [by_race[k] for k in sorted(by_race, key=lambda k: (int(k[0]), int(k[1])))]


def load_existing() -> list[dict]:
    if not OUT_PATH.exists():
        return []
    return json.loads(OUT_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help=f"rebuild the entire history from {FIRST_SEASON} instead of incrementally",
    )
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = [] if args.full else load_existing()
    if not existing:
        seasons = list(range(FIRST_SEASON, date.today().year + 1))
        print(f"Full fetch: pulling every season {FIRST_SEASON}-{seasons[-1]}")
    else:
        latest = max(int(r["season"]) for r in existing)
        seasons = [latest, latest + 1]
        print(f"Incremental fetch: latest season on disk is {latest}; fetching {seasons}")

    fetched: list[dict] = []
    for season in seasons:
        entries = [quali_entry(r) for r in fetch_season_races(season)]
        fetched.extend(e for e in entries if e["results"])
        time.sleep(SLEEP_BETWEEN)

    combined = merge_entries(existing, fetched)
    save_qualifying(combined)

    n_rows = sum(len(r["results"]) for r in combined)
    seasons_out = sorted({int(r["season"]) for r in combined})
    print()
    print(f"Wrote {OUT_PATH}")
    print(f"  races: {len(combined)} ({n_rows} qualifying rows)")
    if seasons_out:
        print(f"  season range: {seasons_out[0]}-{seasons_out[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
