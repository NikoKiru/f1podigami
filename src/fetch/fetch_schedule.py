"""Fetch the current season's race schedule + circuit outlines.

Pulls the season schedule from the Jolpica/Ergast API and, for each race,
matches its circuit to the bundled open f1-circuits dataset (by nearest
coordinates) to pre-compute a normalised SVG track outline. Everything the
landing-page "next race" box needs is baked into data/schedule.json so the
build stays offline.

Circuit outline data: f1-circuits by Tomislav Bačinger (ODbL).

Writes data/schedule.json:
{"season","totalRounds","races":[{round,raceName,date,time,circuitId,
 circuitName,locality,country,lat,long,lengthKm,trackPath,trackViewBox,url}]}.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_geo import VIEW_H, VIEW_W, geo_to_svg_path, nearest_circuit  # noqa: E402

API_ROOT = "https://api.jolpi.ca/ergast/f1"
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1_podigami/0.2 (https://github.com/local/f1_podigami)"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
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


def current_season() -> int:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    return max(int(p["season"]) for p in podiums)


def build_race(race: dict, features: list[dict]) -> dict:
    circ = race["Circuit"]
    loc = circ["Location"]
    lat, lon = float(loc["lat"]), float(loc["long"])
    entry = {
        "round": race["round"],
        "raceName": race["raceName"],
        "date": race["date"],
        "time": race.get("time", ""),
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


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    season = current_season()

    features = json.loads(CIRCUITS_PATH.read_text(encoding="utf-8"))["features"]
    data = get(f"{API_ROOT}/{season}.json", {"limit": 100})
    races = data["MRData"]["RaceTable"]["Races"]

    out = {
        "season": str(season),
        "totalRounds": len(races),
        "races": [build_race(r, features) for r in races],
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}: {len(races)} rounds")
    n_tracks = sum(1 for r in out["races"] if r["trackPath"])
    print(f"  matched circuit outlines for {n_tracks}/{len(races)} rounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
