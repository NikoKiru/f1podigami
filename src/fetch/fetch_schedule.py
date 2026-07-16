"""Fetch the current season's race schedule + circuit outlines.

Pulls the season schedule from the Jolpica/Ergast API and, for each race,
matches its circuit to the bundled open f1-circuits dataset (by nearest
coordinates) to pre-compute a normalised SVG track outline. Everything the
landing-page "next race" box needs is baked into data/schedule.json so the
build stays offline.

Circuit outline data: f1-circuits by Tomislav Bačinger (ODbL).

Writes data/schedule.json:
{"season","totalRounds","races":[{round,raceName,date,time,qualifyingDate,
 qualifyingTime,circuitId,circuitName,locality,country,lat,long,lengthKm,
 trackPath,trackViewBox,url}]}.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from track_geo import VIEW_H, VIEW_W, geo_to_svg_path, nearest_circuit  # noqa: E402

from datalib import save_schedule  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.2 (https://github.com/local/f1podigami)"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CIRCUITS_PATH = DATA_DIR / "f1-circuits.geojson"
OUT_PATH = DATA_DIR / "schedule.json"


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


def build_race(race: dict, features: list[dict]) -> dict:
    circ = race["Circuit"]
    loc = circ["Location"]
    lat, lon = float(loc["lat"]), float(loc["long"])
    entry = {
        "round": race["round"],
        "raceName": race["raceName"],
        "date": race["date"],
        "time": race.get("time", ""),
        "qualifyingDate": (race.get("Qualifying") or {}).get("date"),
        "qualifyingTime": (race.get("Qualifying") or {}).get("time"),
        "circuitId": circ["circuitId"],
        "circuitName": circ["circuitName"],
        "locality": loc["locality"],
        "country": loc["country"],
        "lat": loc["lat"],
        "long": loc["long"],
        "url": race.get("url", ""),
        "trackPath": "",
        "trackViewBox": f"0 0 {VIEW_W} {VIEW_H}",
        "lengthKm": None,
    }
    feat = nearest_circuit(lat, lon, features)
    if feat:
        entry["trackPath"] = geo_to_svg_path(feat["geometry"]["coordinates"])
        length_m = feat.get("properties", {}).get("length")
        if length_m:
            entry["lengthKm"] = round(length_m / 1000, 3)
    return entry


def choose_season_races(fetch_races, year: int, today: datetime.date) -> tuple[int, list[dict]]:
    """Pick which season's calendar to publish, handling the season rollover.

    ``fetch_races(year) -> list`` returns the API's race list for a season.

    - Mid-season: the calendar year's schedule, unchanged.
    - Season complete (every race date passed): try ``year + 1`` so the site
      counts down to the next opener as soon as F1 publishes the calendar.
    - Calendar year not in the API yet (early January): fall back to ``year - 1``
      so we never write an empty schedule — an empty one breaks the next-race box
      and fails the data-integrity CI gate, stalling the update automation.
    """
    races = fetch_races(year)
    if not races:
        prev = fetch_races(year - 1)
        return (year - 1, prev) if prev else (year, races)
    if all(r["date"] < today.isoformat() for r in races):
        nxt = fetch_races(year + 1)
        if nxt:
            return year + 1, nxt
    return year, races


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    features = json.loads(CIRCUITS_PATH.read_text(encoding="utf-8"))["features"]

    def fetch_races(year: int) -> list[dict]:
        data = get(f"{API_ROOT}/{year}.json", {"limit": 100})
        return data["MRData"]["RaceTable"]["Races"]

    season, races = choose_season_races(
        fetch_races, datetime.date.today().year, datetime.date.today()
    )

    out = {
        "season": str(season),
        "totalRounds": len(races),
        "races": [build_race(r, features) for r in races],
    }
    save_schedule(out)
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}: {len(races)} rounds")
    n_tracks = sum(1 for r in out["races"] if r["trackPath"])
    print(f"  matched circuit outlines for {n_tracks}/{len(races)} rounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
