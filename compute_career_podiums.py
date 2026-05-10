"""Precompute cumulative-podium trajectories for the top-N drivers.

Reads data/podiums.json, sorts races chronologically, and walks through
emitting one data point per podium event for each top-N driver. Output goes
to data/career_podiums.json with the shape consumed by build_charts.render_career_line_race.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
PODIUMS_PATH = ROOT / "data" / "podiums.json"
OUT_PATH = ROOT / "data" / "career_podiums.json"
TOP_N = 20
TOP_N_BREAKDOWN = 25


def main() -> int:
    races = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    races.sort(key=lambda r: (int(r["season"]), int(r["round"])))

    totals: dict[str, int] = defaultdict(int)
    p_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"p1": 0, "p2": 0, "p3": 0})
    first_year: dict[str, int] = {}
    last_year_seen: dict[str, int] = {}

    for r in races:
        year = int(r["season"])
        for slot in ("p1", "p2", "p3"):
            d = r.get(slot)
            if not d:
                continue
            name = d["name"]
            totals[name] += 1
            p_counts[name][slot] += 1
            if name not in first_year:
                first_year[name] = year
            last_year_seen[name] = year

    top_names = sorted(totals.keys(), key=lambda n: (-totals[n], n))[:TOP_N]
    top_set = set(top_names)
    breakdown_names = sorted(totals.keys(), key=lambda n: (-totals[n], n))[:TOP_N_BREAKDOWN]

    trajectories: dict[str, list[dict]] = {n: [{"x": 0, "y": 0}] for n in top_names}
    counts: dict[str, int] = defaultdict(int)
    year_markers: dict[int, int] = {}
    last_year = None

    for idx, r in enumerate(races, start=1):
        year = int(r["season"])
        if year != last_year:
            year_markers[idx] = year
            last_year = year
        for slot in ("p1", "p2", "p3"):
            d = r.get(slot)
            if not d or d["name"] not in top_set:
                continue
            name = d["name"]
            counts[name] += 1
            trajectories[name].append({
                "x": idx,
                "y": counts[name],
                "year": year,
                "raceName": r.get("raceName", ""),
                "round": r.get("round", ""),
            })

    final_idx = len(races)
    for name in top_names:
        if trajectories[name][-1]["x"] < final_idx:
            trajectories[name].append({
                "x": final_idx,
                "y": counts[name],
                "year": int(races[-1]["season"]),
                "raceName": "",
                "round": "",
            })

    output = {
        "totalRaces": len(races),
        "yearMarkers": {str(k): v for k, v in year_markers.items()},
        "drivers": [
            {"name": name, "total": totals[name], "data": trajectories[name]}
            for name in top_names
        ],
        "breakdown": [
            {
                "name": name,
                "p1": p_counts[name]["p1"],
                "p2": p_counts[name]["p2"],
                "p3": p_counts[name]["p3"],
                "total": totals[name],
                "firstYear": first_year[name],
                "lastYear": last_year_seen[name],
            }
            for name in breakdown_names
        ],
    }

    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  top {TOP_N} drivers across {len(races)} races")
    for name in top_names[:5]:
        print(f"    {name}: {totals[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
