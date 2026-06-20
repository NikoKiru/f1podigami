"""Rank never-happened podium trios by how statistically overdue they are.

    score(A,B,C) = races_together * rate_A * rate_B * rate_C
        races_together = number of races all three started together
        rate_d         = career podiums / career starts

A high score with zero actual shared podiums = "should have happened, but never
did". The score is a ranking heuristic (it ignores the 3-slot podium
constraint), so the page shows the concrete races_together and per-driver rates
as the real numbers.

Two lists: all-time near-misses (pool = top podium-getters) and current-grid
trios that are still possible.

Inputs : data/podiums.json, data/combos.json, data/current_drivers.json,
         data/driver_races.json
Output : data/overdue.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
RACES_PATH = DATA_DIR / "driver_races.json"
OUT_PATH = DATA_DIR / "overdue.json"

POOL_N = 60  # all-time pool: top drivers by career podiums
TOP_N = 15  # how many trios to keep per list


def _rank(pool: list[str], existing: set, info: dict, top_n: int) -> list[dict]:
    """Rank unseen, overlapping trios from `pool` by overdue score."""
    out = []
    for trio in combinations(sorted(pool), 3):
        if trio in existing:
            continue
        a, b, c = trio
        shared = info[a]["set"] & info[b]["set"] & info[c]["set"]
        rt = len(shared)
        if rt == 0:
            continue
        score = rt * info[a]["rate"] * info[b]["rate"] * info[c]["rate"]
        if score <= 0:
            continue
        out.append(
            {
                "driverIds": list(trio),
                "names": [info[d]["name"] for d in trio],
                "racesTogether": rt,
                "score": round(score, 4),
                "perDriver": [
                    {
                        "name": info[d]["name"],
                        "podiums": info[d]["podiums"],
                        "starts": info[d]["starts"],
                        "rate": round(info[d]["rate"], 4),
                    }
                    for d in trio
                ],
            }
        )
    out.sort(key=lambda e: -e["score"])
    return out[:top_n]


def compute(
    podiums: list[dict],
    combos: list[dict],
    grid: list[dict],
    driver_races: dict,
    pool_n: int = POOL_N,
    top_n: int = TOP_N,
) -> dict:
    """Pure core: returns the overdue.json payload. No file IO."""
    podium_count: Counter[str] = Counter()
    name_by_id: dict[str, str] = {}
    for r in podiums:
        for slot in ("p1", "p2", "p3"):
            d = r[slot]
            podium_count[d["driverId"]] += 1
            name_by_id[d["driverId"]] = d["name"]

    races = driver_races["drivers"]
    info: dict[str, dict] = {}
    for did, rec in races.items():
        starts = rec.get("starts", 0)
        if starts <= 0:
            continue
        podiums_n = podium_count.get(did, 0)
        info[did] = {
            "name": name_by_id.get(did) or rec.get("name", did),
            "podiums": podiums_n,
            "starts": starts,
            "rate": podiums_n / starts,
            "set": set(rec.get("races", [])),
        }

    existing = {tuple(sorted(c["driverIds"])) for c in combos}

    # all-time pool: top by career podiums among drivers we have race data for
    ranked_ids = sorted(info, key=lambda d: (-info[d]["podiums"], d))
    all_time_pool = ranked_ids[:pool_n]

    grid_pool = [d["driverId"] for d in grid if d["driverId"] in info]

    last = max(podiums, key=lambda r: (int(r["season"]), int(r["round"])))

    return {
        "params": {"poolN": pool_n, "topN": top_n},
        "asOf": {"season": last["season"], "round": last["round"], "raceName": last["raceName"]},
        "allTime": _rank(all_time_pool, existing, info, top_n),
        "currentGrid": _rank(grid_pool, existing, info, top_n),
    }


def main() -> int:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    combos = json.loads(COMBOS_PATH.read_text(encoding="utf-8"))
    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))["drivers"]
    driver_races = json.loads(RACES_PATH.read_text(encoding="utf-8"))

    payload = compute(podiums, combos, grid, driver_races)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUT_PATH}")
    for key in ("allTime", "currentGrid"):
        print(f"\nTop 5 {key} overdue trios:")
        for e in payload[key][:5]:
            rates = " / ".join(f"{p['rate'] * 100:.0f}%" for p in e["perDriver"])
            print(
                f"  score {e['score']:6.2f}  raced {e['racesTogether']:>3}x  "
                f"{' / '.join(e['names'])}  [{rates}]"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
