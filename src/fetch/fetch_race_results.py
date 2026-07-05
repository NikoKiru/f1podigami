"""Fetch full F1 race classifications (every entry, not just the podium).

Writes data/race_results.json — one entry per race with every result row:
who drove what, where they started (grid), where they finished (position,
null when unclassified), laps completed and the verbatim status string.
This is the raw input for the v2 prediction model (pace + attrition +
reliability channels all read from it).

By default this runs *incrementally*: it loads the existing race_results.json
and re-fetches only the latest season already on disk (which may have gained
rounds) plus the next one. Past results are immutable, so older seasons are
never re-fetched. Pass --full to rebuild the whole history from 1950.
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
from datalib import save_race_results  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100
SLEEP_BETWEEN = 1.1
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.1 (https://github.com/local/f1podigami)"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT_PATH = DATA_DIR / "race_results.json"

FIRST_SEASON = 1950


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


def race_entry(race: dict) -> dict:
    """Map one Ergast race (with merged Results) to the committed contract shape.

    ``position`` is numeric only when the entry was classified (positionText is
    a number); retirements/DNS/DSQ keep their row with position null and the
    status string verbatim.
    """
    rows = []
    for res in race.get("Results") or []:
        pt = res.get("positionText", "")
        rows.append(
            {
                "driverId": res["Driver"]["driverId"],
                "constructorId": res["Constructor"]["constructorId"],
                "grid": int(res.get("grid") or 0),
                "position": int(pt) if pt.isdigit() else None,
                "laps": int(res.get("laps") or 0),
                "status": res.get("status", ""),
            }
        )
    return {
        "season": race["season"],
        "round": race["round"],
        "raceName": race["raceName"],
        "date": race.get("date", ""),
        "circuitId": race["Circuit"]["circuitId"],
        "results": rows,
    }


def accumulate_page(merged: dict[tuple[str, str], dict], page: list[dict]) -> None:
    """Fold one API page into ``merged`` keyed by (season, round).

    The results endpoint pages by result *row*, so a single race's Results
    array can be split across consecutive pages — concatenate, never replace.
    """
    for race in page:
        key = (race["season"], race["round"])
        if key in merged:
            merged[key]["Results"].extend(race.get("Results") or [])
        else:
            copy = dict(race)
            copy["Results"] = list(race.get("Results") or [])
            merged[key] = copy


def fetch_season_races(season: int) -> list[dict]:
    """Page through /{season}/results.json and return merged Ergast race dicts."""
    merged: dict[tuple[str, str], dict] = {}
    offset = 0
    total = None
    while True:
        data = get(f"{API_ROOT}/{season}/results.json", {"limit": PAGE_SIZE, "offset": offset})
        mr = data["MRData"]
        if total is None:
            total = int(mr["total"])
            print(f"season {season}: {total} result rows")
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
        help="rebuild the entire history from 1950 instead of fetching incrementally",
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
        fetched.extend(race_entry(r) for r in fetch_season_races(season))
        time.sleep(SLEEP_BETWEEN)

    combined = merge_entries(existing, fetched)
    save_race_results(combined)

    n_rows = sum(len(r["results"]) for r in combined)
    seasons_out = sorted({int(r["season"]) for r in combined})
    print()
    print(f"Wrote {OUT_PATH}")
    print(f"  races: {len(combined)} ({n_rows} result rows)")
    if seasons_out:
        print(f"  season range: {seasons_out[0]}-{seasons_out[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
