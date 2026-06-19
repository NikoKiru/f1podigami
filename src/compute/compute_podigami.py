"""Predict the next likely brand-new podium trio ("podigami").

Model (chosen by backtesting 1950-2026 — see the plan; recency dominates,
career history adds noise, a mild current-season boost helps):

    weight(d) = ALPHA
              + sum over d's past podiums of 0.5 ** (races_ago / HALF_LIFE)
              + SEASON_BOOST * (podiums this season)

    trio score  w(T) = weight(a) * weight(b) * weight(c)
    P(T)        = w(T) / sum over all C(grid, 3) trios
    P(new race) = sum of P(T) for trios never seen on a podium together

Inputs : data/podiums.json, data/combos.json, data/current_drivers.json
Output : data/podigami.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
OUT_PATH = DATA_DIR / "podigami.json"

ALPHA = 0.1
HALF_LIFE = 8.0          # races; podium influence halves every 8 races
SEASON_BOOST = 0.5       # extra weight per podium scored this season
RECENT_WINDOW = 10       # races, for the "recent form" display stat
TOP_CANDIDATES = 12


def trio_key(ids: list[str]) -> tuple[str, str, str]:
    return tuple(sorted(ids))  # type: ignore[return-value]


def compute(podiums: list[dict], combos: list[dict],
            grid: list[dict]) -> dict:
    """Pure core: returns the podigami.json payload. No file IO."""
    races = sorted(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    n = len(races)
    current = max(int(r["season"]) for r in races)

    pod_idx: dict[str, list[int]] = defaultdict(list)
    name_by_id: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()
    for i, r in enumerate(races):
        ids = [r[s]["driverId"] for s in ("p1", "p2", "p3")]
        for s in ("p1", "p2", "p3"):
            name_by_id[r[s]["driverId"]] = r[s]["name"]
        seen.add(trio_key(ids))
        for d in ids:
            pod_idx[d].append(i)

    grid_name = {d["driverId"]: d["name"] for d in grid}
    grid_ids = sorted(grid_name)

    def nm(d: str) -> str:
        return name_by_id.get(d) or grid_name.get(d, d)

    # races_ago is measured from the (hypothetical) next race at index n.
    weight: dict[str, float] = {}
    season_pod: dict[str, int] = {}
    recent_pod: dict[str, int] = {}
    for d in grid_ids:
        idxs = pod_idx.get(d, [])
        recency = sum(0.5 ** ((n - j) / HALF_LIFE) for j in idxs)
        sp = sum(1 for j in idxs if int(races[j]["season"]) == current)
        weight[d] = ALPHA + recency + SEASON_BOOST * sp
        season_pod[d] = sp
        recent_pod[d] = sum(1 for j in idxs if (n - j) <= RECENT_WINDOW)

    # Normalise the product score over every trio on the current grid.
    total = 0.0
    scored: list[tuple[tuple[str, str, str], float]] = []
    for c in combinations(grid_ids, 3):
        w = weight[c[0]] * weight[c[1]] * weight[c[2]]
        scored.append((c, w))
        total += w

    chance_new = 0.0
    candidates: list[dict] = []
    for c, w in scored:
        p = (w / total) if total else 0.0
        if c not in seen:
            chance_new += p
            candidates.append(
                {
                    "driverIds": list(c),
                    "names": [nm(d) for d in c],
                    "prob": round(100 * p, 3),
                    "perDriver": [
                        {
                            "name": nm(d),
                            "weight": round(weight[d], 3),
                            "seasonPodiums": season_pod[d],
                            "recentPodiums": recent_pod[d],
                        }
                        for d in c
                    ],
                }
            )
    candidates.sort(key=lambda x: -x["prob"])

    driver_form = sorted(
        (
            {
                "driverId": d,
                "name": nm(d),
                "weight": round(weight[d], 3),
                "seasonPodiums": season_pod[d],
                "recentPodiums": recent_pod[d],
            }
            for d in grid_ids
        ),
        key=lambda x: -x["weight"],
    )

    # Per-season debut trios (podigamis), grouped from combos[].firstRace.
    by_season: dict[str, list[dict]] = defaultdict(list)
    for c in combos:
        fr = c["firstRace"]
        by_season[fr["season"]].append(
            {
                "driverIds": c["driverIds"],
                "names": c["drivers"],
                "firstRace": {"round": fr["round"], "raceName": fr["raceName"]},
            }
        )
    for s in by_season:
        by_season[s].sort(key=lambda e: int(e["firstRace"]["round"]))
    season_counts = {s: len(v) for s, v in by_season.items()}

    seasons_all = [int(r["season"]) for r in races]
    last = races[-1]

    return {
        "currentSeason": str(current),
        "asOf": {
            "season": last["season"],
            "round": last["round"],
            "raceName": last["raceName"],
        },
        "params": {"alpha": ALPHA, "halfLife": HALF_LIFE, "seasonBoost": SEASON_BOOST},
        "gridSize": len(grid_ids),
        "chanceNextRaceNew": round(100 * chance_new, 1),
        "candidates": candidates[:TOP_CANDIDATES],
        "driverForm": driver_form,
        "bySeason": dict(by_season),
        "seasonCounts": season_counts,
        "seasonRange": [min(seasons_all), max(seasons_all)],
    }


def main() -> int:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    combos = json.loads(COMBOS_PATH.read_text(encoding="utf-8"))
    grid_doc = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    grid = grid_doc["drivers"]

    payload = compute(podiums, combos, grid)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUT_PATH}")
    print(f"  season {payload['currentSeason']} grid: {payload['gridSize']} drivers")
    print(f"  P(next race is a brand-new trio): {payload['chanceNextRaceNew']}%")
    print("  Top 5 predicted new trios:")
    for c in payload["candidates"][:5]:
        print(f"    {c['prob']:5.2f}%  {' / '.join(c['names'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
