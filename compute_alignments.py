"""Compute per-race championship alignment.

For each completed season, find the longest matching prefix between each race's
top-10 (in order) and the season's final WDC top-10 (in order). Skips Indy 500.

Writes data/alignments.json — one entry per season, sorted newest first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
TOP10_PATH = DATA_DIR / "top10.json"
STANDINGS_PATH = DATA_DIR / "standings.json"
OUT_PATH = DATA_DIR / "alignments.json"


def match_length(race_ids: list[str | None], champ_ids: list[str]) -> int:
    """Longest L (>=0) such that race_ids[0:L] == champ_ids[0:L] and no None in prefix."""
    cap = min(len(race_ids), len(champ_ids))
    L = 0
    for i in range(cap):
        if race_ids[i] is None:
            break
        if race_ids[i] != champ_ids[i]:
            break
        L += 1
    return L


def main() -> int:
    races = json.loads(TOP10_PATH.read_text(encoding="utf-8"))
    standings = json.loads(STANDINGS_PATH.read_text(encoding="utf-8"))

    standings_by_season: dict[str, dict] = {s["season"]: s for s in standings}
    races_by_season: dict[str, list[dict]] = {}
    for r in races:
        races_by_season.setdefault(r["season"], []).append(r)

    out: list[dict] = []
    longest_overall = (0, None)

    for season_str in sorted(standings_by_season.keys(), key=int):
        sd = standings_by_season[season_str]
        champ_ids = [d["driverId"] for d in sd["drivers"]]
        champ_names = {d["driverId"]: d["name"] for d in sd["drivers"]}

        season_races = sorted(races_by_season.get(season_str, []), key=lambda r: int(r["round"]))
        race_entries: list[dict] = []
        indy_count = 0
        best_len = 0

        for race in season_races:
            if race["isIndy500"]:
                indy_count += 1
                continue
            race_ids = [(slot["driverId"] if slot else None) for slot in race["results"]]
            L = match_length(race_ids, champ_ids)
            entry = {
                "round": race["round"],
                "raceName": race["raceName"],
                "matchLength": L,
                "matchedDrivers": [
                    {"driverId": did, "name": champ_names.get(did, did)}
                    for did in champ_ids[:L]
                ],
            }
            race_entries.append(entry)
            if L > best_len:
                best_len = L

        perfect3 = sum(1 for r in race_entries if r["matchLength"] >= 3)
        best_races = [r for r in race_entries if r["matchLength"] == best_len and best_len > 0]

        if best_len > longest_overall[0]:
            for br in best_races:
                longest_overall = (best_len, {"season": season_str, **br})

        out.append(
            {
                "season": season_str,
                "championship": sd["drivers"],
                "perfectTop3Count": perfect3,
                "bestMatchLength": best_len,
                "bestMatchRaces": best_races,
                "indy500Count": indy_count,
                "totalRaces": len(season_races),
                "races": race_entries,
            }
        )

    out.sort(key=lambda s: int(s["season"]), reverse=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    total_seasons = len(out)
    total_perfect3 = sum(s["perfectTop3Count"] for s in out)
    print(f"Wrote {OUT_PATH}")
    print(f"  seasons covered: {total_seasons}")
    print(f"  total races with matchLength >= 3 (perfect top-3): {total_perfect3}")
    if longest_overall[1]:
        L, race = longest_overall
        print(f"  longest-ever match: top-{L} - {race['season']} R{race['round']} {race['raceName']}")
    print()
    print("Top 10 longest-match races:")
    flat = []
    for s in out:
        for r in s["races"]:
            if r["matchLength"] >= 3:
                flat.append((r["matchLength"], s["season"], r["round"], r["raceName"]))
    flat.sort(key=lambda t: (-t[0], int(t[1]), int(t[2])))
    for L, season, rnd, name in flat[:10]:
        print(f"  top-{L:<2}  {season} R{rnd:>2}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
