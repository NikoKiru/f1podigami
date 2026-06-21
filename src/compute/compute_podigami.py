"""Predict the next likely brand-new podium trio ("podigami").

The probability that a trio is the next podium *set* is computed with a
Plackett-Luce model over per-driver strengths (see src/compute/model.py); the
strength + aggregation choices were validated by a walk-forward backtest
(src/compute/backtest.py). P(new) = the probability mass on trios never seen on
a podium together.

A live-only constructor/teammate overlay nudges the current grid by this
season's standings (it can't be backtested without historical team data, so it
is flagged in the output ``params``).

Inputs : data/podiums.json, data/combos.json, data/current_drivers.json,
         data/constructor_standings.json (optional)
Output : data/podigami.json  (schema unchanged from before)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
CONSTRUCTOR_PATH = DATA_DIR / "constructor_standings.json"
OUT_PATH = DATA_DIR / "podigami.json"

RECENT_WINDOW = 10  # races, for the "recent form" display stat
TOP_CANDIDATES = 12


def trio_key(ids) -> tuple[str, str, str]:
    return model.trio_key(ids)


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


def compute(
    podiums: list[dict], combos: list[dict], grid: list[dict], constructor_data: dict | None = None
) -> dict:
    """Pure core: returns the podigami.json payload. No file IO."""
    races = sorted(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    n = len(races)
    current = max(int(r["season"]) for r in races)

    per_driver = model.index_podiums(races)
    name_by_id: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()
    for r in races:
        for s in ("p1", "p2", "p3"):
            name_by_id[r[s]["driverId"]] = r[s]["name"]
        seen.add(trio_key(r[s]["driverId"] for s in ("p1", "p2", "p3")))

    grid_name = {d["driverId"]: d["name"] for d in grid}
    grid_ids = sorted(grid_name)

    def nm(d: str) -> str:
        return name_by_id.get(d) or grid_name.get(d, d)

    con_strength, driver_cid = _build_constructor_strength(constructor_data, current)
    using_constructors = bool(con_strength)
    constructor_name: dict[str, str] = {}
    if using_constructors:
        cid_to_name = {c["constructorId"]: c["name"] for c in constructor_data["constructors"]}
        constructor_name = {d: cid_to_name.get(driver_cid.get(d, ""), "") for d in grid_ids}

    # Validated Plackett-Luce strengths for the next race (index n), then the
    # live-only constructor/teammate overlay nudges the current grid.
    lam = model.strengths(per_driver, grid_ids, n, current, model.DEFAULT_PARAMS)
    if using_constructors:
        lam = model.apply_car_overlay(lam, driver_cid, con_strength)
    if model.DEFAULT_PARAMS["temperature"] != 1.0:
        lam = model.temper(lam, model.DEFAULT_PARAMS["temperature"])

    season_pod: dict[str, int] = {}
    recent_pod: dict[str, int] = {}
    for d in grid_ids:
        idxs = [idx for idx, _se, _po in per_driver.get(d, ()) if idx < n]
        season_pod[d] = sum(1 for idx in idxs if int(races[idx]["season"]) == current)
        recent_pod[d] = sum(1 for idx in idxs if (n - idx) <= RECENT_WINDOW)

    def _driver_entry(d: str) -> dict:
        entry: dict = {
            "driverId": d,
            "name": nm(d),
            "weight": round(lam[d], 3),
            "seasonPodiums": season_pod[d],
            "recentPodiums": recent_pod[d],
            "constructorId": driver_cid.get(d, ""),
        }
        if using_constructors:
            entry["constructor"] = constructor_name.get(d, "")
            entry["constructorStrength"] = round(con_strength.get(d, 0), 3)
        return entry

    set_probs = model.all_set_probs(lam, grid_ids)
    ranked, chance_new = model.rank_and_new(set_probs, seen)

    candidates: list[dict] = []
    for t, p in ranked:
        if t in seen:
            continue
        candidates.append(
            {
                "driverIds": list(t),
                "names": [nm(d) for d in t],
                "prob": round(100 * p, 3),
                "perDriver": [_driver_entry(d) for d in t],
            }
        )
        if len(candidates) >= TOP_CANDIDATES:
            break

    driver_form = sorted(
        (_driver_entry(d) for d in grid_ids),
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
        "params": {
            "model": "plackett-luce",
            "alpha": model.DEFAULT_PARAMS["alpha"],
            "halfLife": model.DEFAULT_PARAMS["halfLife"],
            "offSeason": model.DEFAULT_PARAMS["offSeason"],
            "seasonBoost": model.DEFAULT_PARAMS["seasonBoost"],
            "temperature": model.DEFAULT_PARAMS["temperature"],
            "usingConstructors": using_constructors,
            "carOverlay": using_constructors,
        },
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
