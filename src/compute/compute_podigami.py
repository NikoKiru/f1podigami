"""Predict the next likely brand-new podium trio ("podigami").

Model (chosen by backtesting 1950-2026 — see the plan; recency dominates,
career history adds noise, a mild current-season boost helps):

    base(d)   = ALPHA
              + sum over d's past podiums of 0.5 ** (races_ago / HALF_LIFE)
              + SEASON_BOOST * (podiums this season)

    weight(d) = base(d) * (1 + CONSTRUCTOR_FACTOR * normalized_strength(d))

    where normalized_strength(d) = constructor_points / max_points  (0 to 1)

    trio score  w(T) = weight(a) * weight(b) * weight(c)
    P(T)        = w(T) / sum over all C(grid, 3) trios
    P(new race) = sum of P(T) for trios never seen on a podium together

Constructor strength is only applied when standings data exists for the
current season (at least 2 rounds completed).  At the start of a season
the model falls back to driver-only weights.

Inputs : data/podiums.json, data/combos.json, data/current_drivers.json,
         data/constructor_standings.json (optional)
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
CONSTRUCTOR_PATH = DATA_DIR / "constructor_standings.json"
OUT_PATH = DATA_DIR / "podigami.json"

ALPHA = 0.1
HALF_LIFE = 8.0          # races; podium influence halves every 8 races
SEASON_BOOST = 0.5       # extra weight per podium scored this season
CONSTRUCTOR_FACTOR = 0.5  # max multiplier boost for drivers on the top constructor
RECENT_WINDOW = 10       # races, for the "recent form" display stat
TOP_CANDIDATES = 12


def trio_key(ids: list[str]) -> tuple[str, str, str]:
    return tuple(sorted(ids))  # type: ignore[return-value]


def _build_constructor_strength(
    constructor_data: dict | None,
    current_season: int,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return (driverId → normalized strength 0-1, driverId → constructorId).

    Returns empty dicts when data is missing or not for the current season.
    """
    if not constructor_data:
        return {}, {}
    if int(constructor_data.get("season", 0)) != current_season:
        return {}, {}
    constructors = constructor_data.get("constructors", [])
    if not constructors:
        return {}, {}

    points_by_cid: dict[str, float] = {}
    for c in constructors:
        points_by_cid[c["constructorId"]] = c["points"]

    max_pts = max(points_by_cid.values()) if points_by_cid else 0
    if max_pts <= 0:
        return {}, {}

    driver_cid: dict[str, str] = constructor_data.get("driverConstructor", {})

    strength: dict[str, float] = {}
    for did, cid in driver_cid.items():
        strength[did] = points_by_cid.get(cid, 0) / max_pts

    return strength, driver_cid


def compute(podiums: list[dict], combos: list[dict],
            grid: list[dict],
            constructor_data: dict | None = None) -> dict:
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

    con_strength, driver_cid = _build_constructor_strength(constructor_data, current)
    using_constructors = bool(con_strength)

    # races_ago is measured from the (hypothetical) next race at index n.
    weight: dict[str, float] = {}
    season_pod: dict[str, int] = {}
    recent_pod: dict[str, int] = {}
    constructor_name: dict[str, str] = {}
    if using_constructors:
        cid_to_name = {c["constructorId"]: c["name"]
                       for c in constructor_data["constructors"]}
    for d in grid_ids:
        idxs = pod_idx.get(d, [])
        recency = sum(0.5 ** ((n - j) / HALF_LIFE) for j in idxs)
        sp = sum(1 for j in idxs if int(races[j]["season"]) == current)
        base = ALPHA + recency + SEASON_BOOST * sp
        multiplier = 1.0 + CONSTRUCTOR_FACTOR * con_strength.get(d, 0)
        weight[d] = base * multiplier
        season_pod[d] = sp
        recent_pod[d] = sum(1 for j in idxs if (n - j) <= RECENT_WINDOW)
        if using_constructors:
            cid = driver_cid.get(d, "")
            constructor_name[d] = cid_to_name.get(cid, "")

    # Normalise the product score over every trio on the current grid.
    total = 0.0
    scored: list[tuple[tuple[str, str, str], float]] = []
    for c in combinations(grid_ids, 3):
        w = weight[c[0]] * weight[c[1]] * weight[c[2]]
        scored.append((c, w))
        total += w

    def _driver_entry(d: str) -> dict:
        entry: dict = {
            "name": nm(d),
            "weight": round(weight[d], 3),
            "seasonPodiums": season_pod[d],
            "recentPodiums": recent_pod[d],
        }
        if using_constructors:
            entry["constructor"] = constructor_name.get(d, "")
            entry["constructorStrength"] = round(con_strength.get(d, 0), 3)
        return entry

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
                    "perDriver": [_driver_entry(d) for d in c],
                }
            )
    candidates.sort(key=lambda x: -x["prob"])

    driver_form = sorted(
        (
            {**{"driverId": d}, **_driver_entry(d)}
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
        "params": {"alpha": ALPHA, "halfLife": HALF_LIFE, "seasonBoost": SEASON_BOOST,
                   "constructorFactor": CONSTRUCTOR_FACTOR,
                   "usingConstructors": using_constructors},
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

    constructor_data = None
    if CONSTRUCTOR_PATH.exists():
        constructor_data = json.loads(CONSTRUCTOR_PATH.read_text(encoding="utf-8"))

    payload = compute(podiums, combos, grid, constructor_data)
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
