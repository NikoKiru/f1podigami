"""Predict the next likely brand-new podium trio ("podigami").

When the full race classifications are available (data/race_results.json),
predictions come from the v2 dynamic Bayesian rating engine
(src/compute/model_v2.py): driver+constructor Gaussian ratings filtered over
every race since 1950 plus qualifying, with per-driver DNF risk and circuit
character, aggregated by Rao-Blackwellised simulation. Without those datasets
it falls back to the original Plackett-Luce strengths model
(src/compute/model.py). Both are validated by the walk-forward backtest
(src/compute/backtest.py); P(new) = probability mass on trios never seen on a
podium together.

Inputs : data/podiums.json, data/combos.json, data/current_drivers.json,
         data/constructor_standings.json, data/race_results.json,
         data/qualifying.json, data/schedule.json (the last four optional)
Output : data/podigami.json
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import model  # noqa: E402
import model_v2  # noqa: E402

from datalib import save_podigami  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
CONSTRUCTOR_PATH = DATA_DIR / "constructor_standings.json"
RACE_RESULTS_PATH = DATA_DIR / "race_results.json"
QUALIFYING_PATH = DATA_DIR / "qualifying.json"
SCHEDULE_PATH = DATA_DIR / "schedule.json"
OUT_PATH = DATA_DIR / "podigami.json"

RECENT_WINDOW = 10  # races, for the "recent form" display stat
TOP_CANDIDATES = 12
N_DRAWS = 512  # prediction simulation draws (deterministic seed)
SEED = 20260704


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


def _next_race(schedule: dict | None, as_of_season: int, as_of_round: int) -> dict | None:
    """The first scheduled race after ``asOf``, or None if unknown."""
    if not schedule:
        return None
    races = schedule.get("races") or []
    sched_season = int(schedule.get("season", 0))
    if sched_season == as_of_season:
        upcoming = [r for r in races if int(r["round"]) > as_of_round]
    elif sched_season > as_of_season:
        upcoming = list(races)
    else:
        return None
    if not upcoming:
        return None
    return min(upcoming, key=lambda r: int(r["round"]))


def _v2_next_race_model(
    race_results: list[dict],
    qualifying: list[dict] | None,
    schedule: dict | None,
    grid_ids: list[str],
    driver_cid: dict[str, str],
    seen: set[tuple[str, str, str]],
) -> dict:
    """Filter the full history, then predict the next race for the current grid.

    Returns {"mu_var", "p_fin", "temp", "circuit", "chance_new", "ranked_new",
    "params", "hf", "next_race", "next_season"}.
    """
    params = dict(model_v2.DEFAULT_PARAMS_V2)
    qmap = {(q["season"], q["round"]): q for q in (qualifying or [])}
    ordered = sorted(race_results, key=lambda r: (int(r["season"]), int(r["round"])))
    hf = model_v2.HistoryFilter(params)
    for rr in ordered:
        hf.step(rr, qmap.get((rr["season"], rr["round"])))

    last_season = int(ordered[-1]["season"])
    last_round = int(ordered[-1]["round"])
    next_race = _next_race(schedule, last_season, last_round)
    circuit = next_race.get("circuitId") if next_race else None

    # Between-race dynamics up to the race being predicted.
    sched_season = int(schedule["season"]) if schedule else last_season
    if circuit is not None and sched_season > last_season:
        hf.engine.advance_season(sched_season)
    else:
        hf.engine.advance_race()

    delta = params["chaos_gamma"] * hf.circuits.dnf_logodds_delta(circuit) if circuit else 0.0
    temp = hf.circuits.temp(circuit, params["chaos_eta"]) if circuit else 1.0

    mu_var: dict[str, tuple[float, float]] = {}
    p_fin: dict[str, float] = {}
    for d in grid_ids:
        cid = driver_cid.get(d, "")
        mu_var[d] = hf.engine.combined(d, cid)
        p_fin[d] = hf.p_finish_adjusted(d, cid, delta)

    if len(grid_ids) >= 3:
        out = model_v2.predict_race(
            grid_ids, mu_var, p_fin, temp, params, seen, n_draws=N_DRAWS, seed=SEED
        )
        chance_new, ranked_new = out["p_new"], out["ranked_new"]
    else:
        chance_new, ranked_new = 0.0, []

    return {
        "mu_var": mu_var,
        "p_fin": p_fin,
        "temp": temp,
        "circuit": circuit,
        "chance_new": chance_new,
        "ranked_new": ranked_new,
        "params": params,
        "hf": hf,
        "next_race": next_race,
        "next_season": sched_season,
    }


def _title_from_id(driver_id: str) -> str:
    """Display-name fallback for a driver we've never seen a name for."""
    return " ".join(w.capitalize() for w in driver_id.split("_"))


def _post_quali_block(
    v2: dict,
    qualifying: list[dict] | None,
    seen: set[tuple[str, str, str]],
    nm,
    season_pod: dict[str, int],
    recent_pod: dict[str, int],
    cid_name: dict[str, str],
    con_strength: dict[str, float],
    using_constructors: bool,
) -> dict | None:
    """Grid-aware prediction for the next race, or None before its quali exists.

    Entrants are exactly the qualifying participants with the constructor each
    qualified for (handles seat swaps/substitutes). Two effects on top of the
    already-advanced filter state in ``v2["hf"]``: the quali order through the
    standard rating channel, then grid_offsets folded into the means. Seeded
    with the backtest convention so the output is a deterministic function of
    its inputs.

    NOTE: mutates v2["hf"] (the quali observation) — call only after every
    pre-quali value has been extracted from ``v2``.
    """
    nxt = v2["next_race"]
    if nxt is None or not qualifying:
        return None
    season, rnd = str(v2["next_season"]), str(nxt["round"])
    q = next((e for e in qualifying if e["season"] == season and e["round"] == rnd), None)
    if q is None:
        return None

    hf, params = v2["hf"], v2["params"]
    qpos: dict[str, int] = {}
    qcid: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    for row in sorted(q["results"], key=lambda r: r["position"]):
        d = row["driverId"]
        if d in qpos:
            continue
        qpos[d] = row["position"]
        qcid[d] = row["constructorId"]
        entries.append((d, row["constructorId"]))
    if len(entries) < 3:
        return None

    # Information effect: the fresh quali order through the standard channel.
    hf.engine.observe_order(entries, depth=int(params["depth_qual"]), weight=params["w_qual"])

    circuit = nxt.get("circuitId")
    delta = params["chaos_gamma"] * hf.circuits.dnf_logodds_delta(circuit) if circuit else 0.0
    temp = hf.circuits.temp(circuit, params["chaos_eta"]) if circuit else 1.0
    disp = hf.circuits.disp_ratio(circuit) if circuit else 1.0

    # Causal track-position effect: grid offsets folded into the means.
    offsets = model_v2.grid_offsets(qpos, disp, params)
    mu_var: dict[str, tuple[float, float]] = {}
    p_fin: dict[str, float] = {}
    for d in qpos:
        mu, var = hf.engine.combined(d, qcid[d])
        mu_var[d] = (mu + offsets[d], var)
        p_fin[d] = hf.p_finish_adjusted(d, qcid[d], delta)

    seed = SEED + int(season) * 100 + int(rnd)
    out = model_v2.predict_race(
        sorted(qpos), mu_var, p_fin, temp, params, seen, n_draws=N_DRAWS, seed=seed
    )

    def entry(d: str) -> dict:
        e: dict = {
            "driverId": d,
            "name": nm(d),
            "weight": round(math.exp(mu_var[d][0]), 3),
            "seasonPodiums": season_pod.get(d, 0),
            "recentPodiums": recent_pod.get(d, 0),
            "constructorId": qcid[d],
        }
        if using_constructors:
            e["constructor"] = cid_name.get(qcid[d], "")
            e["constructorStrength"] = round(con_strength.get(d, 0), 3)
        e["finishProb"] = round(p_fin[d], 3)
        e["uncertainty"] = round(math.sqrt(mu_var[d][1]), 3)
        e["gridPosition"] = qpos[d]
        return e

    candidates = [
        {
            "driverIds": list(t),
            "names": [nm(d) for d in t],
            "prob": round(100 * p, 3),
            "perDriver": [entry(d) for d in t],
        }
        for t, p in out["ranked_new"][:TOP_CANDIDATES]
    ]
    driver_form = sorted((entry(d) for d in sorted(qpos)), key=lambda x: -x["weight"])
    return {
        "season": season,
        "round": rnd,
        "raceName": nxt.get("raceName", ""),
        "chanceNextRaceNew": round(100 * out["p_new"], 1),
        "candidates": candidates,
        "driverForm": driver_form,
    }


def compute(
    podiums: list[dict],
    combos: list[dict],
    grid: list[dict],
    constructor_data: dict | None = None,
    race_results: list[dict] | None = None,
    qualifying: list[dict] | None = None,
    schedule: dict | None = None,
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
        return name_by_id.get(d) or grid_name.get(d) or _title_from_id(d)

    con_strength, driver_cid = _build_constructor_strength(constructor_data, current)
    using_constructors = bool(con_strength)
    constructor_name: dict[str, str] = {}
    cid_to_name: dict[str, str] = {}
    if using_constructors:
        cid_to_name = {c["constructorId"]: c["name"] for c in constructor_data["constructors"]}
        constructor_name = {d: cid_to_name.get(driver_cid.get(d, ""), "") for d in grid_ids}

    # v2 engine when the full classifications exist; else the validated v1
    # Plackett-Luce strengths + live constructor overlay.
    v2 = None
    if race_results:
        v2 = _v2_next_race_model(race_results, qualifying, schedule, grid_ids, driver_cid, seen)
        lam = {d: math.exp(v2["mu_var"][d][0]) for d in grid_ids}
    else:
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
        if v2 is not None:
            entry["finishProb"] = round(v2["p_fin"][d], 3)
            entry["uncertainty"] = round(math.sqrt(v2["mu_var"][d][1]), 3)
        return entry

    if v2 is not None:
        ranked_new, chance_new = v2["ranked_new"], v2["chance_new"]
    else:
        set_probs = model.all_set_probs(lam, grid_ids)
        ranked, chance_new = model.rank_and_new(set_probs, seen)
        ranked_new = [(t, p) for t, p in ranked if t not in seen]

    candidates: list[dict] = []
    for t, p in ranked_new:
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

    # Grid-aware prediction once the next race's qualifying is known. MUST come
    # after all pre-quali values are read from v2 — it mutates v2["hf"].
    post_quali = None
    if v2 is not None:
        post_quali = _post_quali_block(
            v2,
            qualifying,
            seen,
            nm,
            season_pod,
            recent_pod,
            cid_to_name,
            con_strength,
            using_constructors,
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

    if v2 is not None:
        params_out: dict = {
            "model": "dbpl-v2",
            **v2["params"],
            "usingQualifying": bool(qualifying),
            "circuitId": v2["circuit"],
            "nDraws": N_DRAWS,
            "seed": SEED,
        }
    else:
        params_out = {
            "model": "plackett-luce",
            "alpha": model.DEFAULT_PARAMS["alpha"],
            "halfLife": model.DEFAULT_PARAMS["halfLife"],
            "offSeason": model.DEFAULT_PARAMS["offSeason"],
            "seasonBoost": model.DEFAULT_PARAMS["seasonBoost"],
            "temperature": model.DEFAULT_PARAMS["temperature"],
            "usingConstructors": using_constructors,
            "carOverlay": using_constructors,
        }

    return {
        "currentSeason": str(current),
        "asOf": {
            "season": last["season"],
            "round": last["round"],
            "raceName": last["raceName"],
        },
        "params": params_out,
        "gridSize": len(grid_ids),
        "chanceNextRaceNew": round(100 * chance_new, 1),
        "candidates": candidates[:TOP_CANDIDATES],
        "driverForm": driver_form,
        "postQuali": post_quali,
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

    race_results = None
    if RACE_RESULTS_PATH.exists():
        race_results = json.loads(RACE_RESULTS_PATH.read_text(encoding="utf-8"))
    qualifying = None
    if QUALIFYING_PATH.exists():
        qualifying = json.loads(QUALIFYING_PATH.read_text(encoding="utf-8"))
    schedule = None
    if SCHEDULE_PATH.exists():
        schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))

    payload = compute(
        podiums,
        combos,
        grid,
        constructor_data,
        race_results=race_results,
        qualifying=qualifying,
        schedule=schedule,
    )
    save_podigami(payload)

    print(f"Wrote {OUT_PATH}")
    print(f"  model: {payload['params']['model']}")
    print(f"  season {payload['currentSeason']} grid: {payload['gridSize']} drivers")
    print(f"  P(next race is a brand-new trio): {payload['chanceNextRaceNew']}%")
    print("  Top 5 predicted new trios:")
    for c in payload["candidates"][:5]:
        print(f"    {c['prob']:5.2f}%  {' / '.join(c['names'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
