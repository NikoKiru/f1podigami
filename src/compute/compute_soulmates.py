"""Compute the soulmate matrix.

For each pair of top-N drivers, count races where both finished on the podium.
Sort drivers chronologically by median podium year so era-mates cluster as
visible blocks on the chart's diagonal.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PODIUMS_PATH = ROOT / "data" / "podiums.json"
OUT_PATH = ROOT / "data" / "soulmates.json"
TOP_N = 40
TOP_PAIRS = 30


def main() -> int:
    races = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
    races.sort(key=lambda r: (int(r["season"]), int(r["round"])))

    totals: dict[str, int] = defaultdict(int)
    podium_years: dict[str, list[int]] = defaultdict(list)
    for r in races:
        for slot in ("p1", "p2", "p3"):
            d = r.get(slot)
            if d:
                totals[d["name"]] += 1
                podium_years[d["name"]].append(int(r["season"]))

    top_names = sorted(totals.keys(), key=lambda n: (-totals[n], n))[:TOP_N]
    top_set = set(top_names)

    def median_year(name: str) -> float:
        ys = sorted(podium_years[name])
        return ys[len(ys) // 2]

    sorted_names = sorted(top_names, key=lambda n: (median_year(n), -totals[n]))
    name_to_idx = {n: i for i, n in enumerate(sorted_names)}

    n = len(sorted_names)
    matrix = [[0] * n for _ in range(n)]
    pair_meta: dict[tuple[str, str], dict] = defaultdict(lambda: {"first": None, "last": None})

    for r in races:
        year = int(r["season"])
        names = [r.get(slot, {}).get("name") for slot in ("p1", "p2", "p3")]
        names = [nm for nm in names if nm and nm in top_set]
        for a, b in combinations(names, 2):
            ia, ib = name_to_idx[a], name_to_idx[b]
            matrix[ia][ib] += 1
            matrix[ib][ia] += 1
            key = tuple(sorted([a, b]))
            m = pair_meta[key]
            if m["first"] is None or year < m["first"]:
                m["first"] = year
            if m["last"] is None or year > m["last"]:
                m["last"] = year

    top_pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i][j] > 0:
                a, b = sorted_names[i], sorted_names[j]
                key = tuple(sorted([a, b]))
                m = pair_meta[key]
                top_pairs.append({
                    "a": a, "b": b,
                    "count": matrix[i][j],
                    "firstYear": m["first"],
                    "lastYear": m["last"],
                })
    top_pairs.sort(key=lambda p: (-p["count"], p["a"], p["b"]))

    max_pair = top_pairs[0]["count"] if top_pairs else 0

    output = {
        "drivers": [
            {"name": nm, "total": totals[nm], "medianYear": median_year(nm)}
            for nm in sorted_names
        ],
        "matrix": matrix,
        "max": max_pair,
        "topPairs": top_pairs[:TOP_PAIRS],
    }

    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    if top_pairs:
        p = top_pairs[0]
        print(f"  {n} drivers, top pair: {p['a']} & {p['b']} = {p['count']} ({p['firstYear']}-{p['lastYear']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
