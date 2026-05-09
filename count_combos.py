"""Aggregate per-race podiums into unique 3-driver combinations (order independent)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
IN_PATH = DATA_DIR / "podiums.json"
OUT_PATH = DATA_DIR / "combos.json"


def main() -> int:
    podiums = json.loads(IN_PATH.read_text(encoding="utf-8"))

    combos: dict[tuple[str, str, str], dict] = {}
    name_by_id: dict[str, str] = {}

    for race in podiums:
        ids = sorted([race["p1"]["driverId"], race["p2"]["driverId"], race["p3"]["driverId"]])
        for slot in ("p1", "p2", "p3"):
            name_by_id[race[slot]["driverId"]] = race[slot]["name"]
        key = tuple(ids)
        combo = combos.setdefault(
            key,
            {"driverIds": list(key), "count": 0, "races": []},
        )
        combo["count"] += 1
        combo["races"].append(
            {"season": race["season"], "round": race["round"], "raceName": race["raceName"]}
        )

    out = []
    for key, combo in combos.items():
        names = [name_by_id[d] for d in combo["driverIds"]]
        names_alpha = sorted(names)
        races_chrono = sorted(combo["races"], key=lambda r: (int(r["season"]), int(r["round"])))
        last = races_chrono[-1]
        first = races_chrono[0]
        out.append(
            {
                "drivers": names_alpha,
                "driverIds": combo["driverIds"],
                "count": combo["count"],
                "lastRace": last,
                "firstRace": first,
                "lastRaceKey": int(last["season"]) * 1000 + int(last["round"]),
                "races": races_chrono,
            }
        )

    out.sort(key=lambda c: (-c["count"], " | ".join(c["drivers"]).lower()))

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    total_races = sum(c["count"] for c in out)
    print(f"Wrote {OUT_PATH}")
    print(f"  unique combinations: {len(out)}")
    print(f"  total podiums covered: {total_races} (expected {len(podiums)})")
    print()
    print("Top 10 by count:")
    for i, c in enumerate(out[:10], 1):
        last = c["lastRace"]
        print(f"  {i:2}. {c['count']:3}x  {' / '.join(c['drivers'])}  (last: {last['season']} {last['raceName']})")
    print()
    print("Top 10 most recent combos:")
    by_recent = sorted(out, key=lambda c: -c["lastRaceKey"])
    for i, c in enumerate(by_recent[:10], 1):
        last = c["lastRace"]
        print(f"  {i:2}. {last['season']} R{last['round']:>2}  {' / '.join(c['drivers'])}  ({c['count']}x)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
