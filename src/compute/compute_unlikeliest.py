"""Rank podium trios that *did* happen by how statistically unlikely they were.

The mirror of ``compute_overdue.py``. Overdue scores trios that never happened;
this scores trios that *did*, by the same heuristic, and keeps the lowest:

    score(A,B,C) = races_together * rate_A * rate_B * rate_C
        races_together = number of races all three started together
        rate_d         = career podiums / career starts

A low score on a trio that nonetheless reached the rostrum together = "this
podium almost shouldn't have happened". ``score`` reads as an expected co-podium
count; comparing it to the actual ``count`` ("expected ~0.02, yet it happened")
is the why-it-was-unlikely framing the page shows.

races_together is floored to ``count``: three drivers who shared a podium N times
necessarily started together at least N times, so the floor corrects any gap in
driver_races without ever letting a happened trio score 0.

Inputs : data/podiums.json, data/combos.json, data/driver_races.json
Output : data/unlikeliest.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import save_unlikeliest  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
RACES_PATH = DATA_DIR / "driver_races.json"
OUT_PATH = DATA_DIR / "unlikeliest.json"

TOP_N = 30  # how many of the most unlikely trios to keep


def compute(
    podiums: list[dict],
    combos: list[dict],
    driver_races: dict,
    top_n: int = TOP_N,
) -> dict:
    """Pure core: returns the unlikeliest.json payload. No file IO."""
    podium_count: Counter[str] = Counter()
    name_by_id: dict[str, str] = {}
    for r in podiums:
        for slot in ("p1", "p2", "p3"):
            d = r[slot]
            podium_count[d["driverId"]] += 1
            name_by_id[d["driverId"]] = d["name"]

    info: dict[str, dict] = {}
    for did, rec in driver_races["drivers"].items():
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

    trios: list[dict] = []
    for combo in combos:
        ids = sorted(combo["driverIds"])
        if any(d not in info for d in ids):
            continue  # data gap: a driver with no race history -> skip the trio
        a, b, c = ids
        shared = info[a]["set"] & info[b]["set"] & info[c]["set"]
        count = combo["count"]
        # they podiumed together `count` times -> started together at least that often
        races_together = max(len(shared), count)
        score = races_together * info[a]["rate"] * info[b]["rate"] * info[c]["rate"]
        first = combo["firstRace"]
        trios.append(
            {
                "driverIds": list(ids),
                "names": [info[d]["name"] for d in ids],
                "racesTogether": races_together,
                "score": round(score, 4),
                "count": count,
                "happened": {
                    "season": first["season"],
                    "round": first["round"],
                    "raceName": first["raceName"],
                },
                "perDriver": [
                    {
                        "name": info[d]["name"],
                        "podiums": info[d]["podiums"],
                        "starts": info[d]["starts"],
                        "rate": round(info[d]["rate"], 4),
                    }
                    for d in ids
                ],
            }
        )

    trios.sort(key=lambda e: (e["score"], " | ".join(e["names"]).lower()))

    last = max(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    return {
        "params": {"topN": top_n},
        "asOf": {"season": last["season"], "round": last["round"], "raceName": last["raceName"]},
        "trios": trios[:top_n],
    }


def main() -> int:
    podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    combos = json.loads(COMBOS_PATH.read_text(encoding="utf-8"))
    driver_races = json.loads(RACES_PATH.read_text(encoding="utf-8"))

    payload = compute(podiums, combos, driver_races)
    save_unlikeliest(payload)

    print(f"Wrote {OUT_PATH}")
    print("\nTop 10 most unlikely podiums that happened:")
    for e in payload["trios"][:10]:
        rates = " / ".join(f"{p['rate'] * 100:.0f}%" for p in e["perDriver"])
        h = e["happened"]
        print(
            f"  score {e['score']:8.4f}  raced {e['racesTogether']:>3}x  count {e['count']}  "
            f"{' / '.join(e['names'])}  [{rates}]  ({h['season']} {h['raceName']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
