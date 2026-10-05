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
         data/qualifying.json, data/schedule.json, data/grid_penalties.json,
         data/retirements.json, data/starting_grids.json
         (the last six optional)
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

from compute.shared_drives import podium_drivers, podium_trios  # noqa: E402
from datalib import save_podigami  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
COMBOS_PATH = DATA_DIR / "combos.json"
GRID_PATH = DATA_DIR / "current_drivers.json"
CONSTRUCTOR_PATH = DATA_DIR / "constructor_standings.json"
RACE_RESULTS_PATH = DATA_DIR / "race_results.json"
QUALIFYING_PATH = DATA_DIR / "qualifying.json"
SCHEDULE_PATH = DATA_DIR / "schedule.json"
GRID_PENALTIES_PATH = DATA_DIR / "grid_penalties.json"
RETIREMENTS_PATH = DATA_DIR / "retirements.json"
STARTING_GRIDS_PATH = DATA_DIR / "starting_grids.json"
OUT_PATH = DATA_DIR / "podigami.json"

RECENT_WINDOW = 10  # races, for the "recent form" display stat
TOP_CANDIDATES = 12
N_DRAWS = 512  # prediction simulation draws (deterministic seed)
SEED = 20260704

# Trio board: every trio in play for the next race, new and already-seen ranked
# together, so the page can say "this one has happened" instead of leaving a
# visitor to guess whether a missing trio is done or merely unlikely.
BOARD_MIN_PROB = 0.01  # include every trio at >= 1%
BOARD_MIN_ROWS = 12  # floor, so a concentrated era can't leave the card half-built
BOARD_MAX_ROWS = 40  # bound the dataset; needs a sub-2.5% favourite to ever bind


def trio_key(ids) -> tuple[str, str, str]:
    return model.trio_key(ids)


def build_trio_board(
    trio_probs: dict[tuple[str, str, str], float],
    seen: set[tuple[str, str, str]],
    entrants: list[str],
) -> list[dict]:
    """Rank every trio in play for the next race, new and already-seen together.

    ``trio_probs`` is the simulation's own output, so the board is a view of the
    same numbers the candidate list is drawn from — never a second opinion.
    ``seen`` is global history, so it is narrowed to trios all of whose drivers
    are entered: a trio needing a driver who isn't racing cannot happen here and
    must not be flagged as one that already did.

    Rows are every trio at ``BOARD_MIN_PROB`` or better, which lets the board
    shorten itself once qualifying sharpens the odds. ``BOARD_MIN_ROWS`` keeps a
    concentrated era from leaving the card half-built; ``BOARD_MAX_ROWS`` bounds
    the dataset.
    """
    entered = set(entrants)
    seen_here = {t for t in seen if all(d in entered for d in t)}
    ranked = sorted(trio_probs.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = [(t, p) for t, p in ranked if p >= BOARD_MIN_PROB]
    if len(rows) < BOARD_MIN_ROWS:
        rows = ranked[:BOARD_MIN_ROWS]
    return [
        {"driverIds": list(t), "prob": round(100 * p, 3), "happened": t in seen_here}
        for t, p in rows[:BOARD_MAX_ROWS]
    ]


def _latest_seats(race_results: list[dict] | None, season: int) -> dict[str, tuple[int, str]]:
    """driverId → (round, constructorId) of the last race he started in ``season``.

    The latest round wins, so a real mid-season team change overwrites the older
    seat rather than lingering beside it.
    """
    seats: dict[str, tuple[int, str]] = {}
    for rr in race_results or []:
        if int(rr["season"]) != season:
            continue
        rnd = int(rr["round"])
        for row in rr["results"]:
            did = row["driverId"]
            if did not in seats or rnd > seats[did][0]:
                seats[did] = (rnd, row["constructorId"])
    return seats


def _build_constructor_strength(
    constructor_data: dict | None,
    current_season: int,
    race_results: list[dict] | None = None,
) -> tuple[dict[str, float], dict[str, str], dict[str, float]]:
    """Return (driverId → strength 0-1, driverId → constructorId, cid → strength).

    ``driverConstructor`` names only the latest round's starters, so a driver who
    misses a race drops out of it and would be predicted in an unknown — i.e.
    brand-new — car. Seats are therefore layered: the season's race_results give
    each driver his last seen car, and the fetched map overrides it wherever it is
    at least as fresh (the two feeds publish out of step, either way round).

    Returns empty dicts when data is missing or not for the current season.
    """
    if not constructor_data:
        return {}, {}, {}
    if int(constructor_data.get("season", 0)) != current_season:
        return {}, {}, {}
    constructors = constructor_data.get("constructors", [])
    if not constructors:
        return {}, {}, {}

    points_by_cid: dict[str, float] = {}
    for c in constructors:
        points_by_cid[c["constructorId"]] = c["points"]

    max_pts = max(points_by_cid.values()) if points_by_cid else 0
    if max_pts <= 0:
        return {}, {}, {}

    cid_strength = {cid: pts / max_pts for cid, pts in points_by_cid.items()}

    fetched_round = int(constructor_data.get("round", 0) or 0)
    driver_cid: dict[str, str] = dict(constructor_data.get("driverConstructor", {}))
    for did, (rnd, cid) in _latest_seats(race_results, current_season).items():
        if did not in driver_cid or rnd > fetched_round:
            driver_cid[did] = cid

    strength = {did: cid_strength.get(cid, 0.0) for did, cid in driver_cid.items()}

    return strength, driver_cid, cid_strength


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
    as_of: tuple[int, int] | None = None,
) -> dict:
    """Filter the full history, then predict the next race for the current grid.

    ``as_of`` is the latest race podiums.json knows has run. The upstream
    aggregates publish out of step — the podium feeds can carry a race hours
    before the full-classification feed does — so race_results alone is not a
    reliable answer to "which race is next". Taking whichever source is further
    ahead keeps the prediction pointed at a race that has not happened yet; the
    filter state simply misses the newest race until results catch up.

    Returns {"mu_var", "p_fin", "temp", "circuit", "chance_new", "ranked_new",
    "trio_probs", "params", "hf", "next_race", "next_season"}.
    """
    params = dict(model_v2.DEFAULT_PARAMS_V2)
    qmap = {(q["season"], q["round"]): q for q in (qualifying or [])}
    ordered = sorted(race_results, key=lambda r: (int(r["season"]), int(r["round"])))
    hf = model_v2.HistoryFilter(params)
    for rr in ordered:
        hf.step(rr, qmap.get((rr["season"], rr["round"])))

    last_season = int(ordered[-1]["season"])
    last_round = int(ordered[-1]["round"])
    if as_of is not None and as_of > (last_season, last_round):
        last_season, last_round = as_of
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
        trio_probs = out["trio_probs"]
    else:
        chance_new, ranked_new, trio_probs = 0.0, [], {}

    return {
        "mu_var": mu_var,
        "p_fin": p_fin,
        "temp": temp,
        "circuit": circuit,
        "chance_new": chance_new,
        "ranked_new": ranked_new,
        "trio_probs": trio_probs,
        "params": params,
        "hf": hf,
        "next_race": next_race,
        "next_season": sched_season,
    }


def _title_from_id(driver_id: str) -> str:
    """Display-name fallback for a driver we've never seen a name for."""
    return " ".join(w.capitalize() for w in driver_id.split("_"))


def _apply_grid_penalties(qpos: dict[str, int], penalties: list[dict]) -> dict[str, int]:
    """Reconstruct starting slots from the quali classification plus penalties.

    ``penaltyPlaces: N`` pins a driver to exactly N slots below his place in the
    lineup — FIA-style, so unpenalised cars promoted into vacated slots compress
    *around* the pinned slot, never past it (a pin past the field size means the
    back; two cars pinned to the same slot keep their quali order). ``backOfGrid:
    true`` sends a driver behind every other car, back-of-grid drivers keeping
    their quali order among themselves. Directives for drivers not in ``qpos``
    are ignored.
    """
    directive = {p["driverId"]: p for p in penalties if p["driverId"] in qpos}
    if not directive:
        return qpos

    # Back-of-grid cars vacate their slots first; place drops then apply to the
    # positions of the field that actually lines up.
    back = sorted((d for d in qpos if directive.get(d, {}).get("backOfGrid")), key=qpos.get)
    front = sorted((d for d in qpos if d not in set(back)), key=qpos.get)
    eff = {d: i + 1 for i, d in enumerate(front)}

    slot: dict[str, int] = {}
    taken: set[int] = set()
    for d in front:  # quali order, so the earlier qualifier wins a contested slot
        p = directive.get(d)
        if p is None:
            continue
        s = min(eff[d] + p["penaltyPlaces"], len(front))
        while s in taken:
            s += 1
        slot[d] = s
        taken.add(s)
    nxt = 1
    for d in front:
        if d in slot:
            continue
        while nxt in taken:
            nxt += 1
        slot[d] = nxt
        nxt += 1

    order = sorted(front, key=slot.get) + back
    return {d: i + 1 for i, d in enumerate(order)}


def _post_quali_block(
    v2: dict,
    qualifying: list[dict] | None,
    seen: set[tuple[str, str, str]],
    nm,
    season_pod: dict[str, int],
    recent_pod: dict[str, int],
    cid_name: dict[str, str],
    cid_strength: dict[str, float],
    using_constructors: bool,
    grid_penalties: list[dict] | None = None,
    retirements: list[dict] | None = None,
    starting_grids: list[dict] | None = None,
) -> dict | None:
    """Grid-aware prediction for the next race, or None before its quali exists.

    Entrants are the qualifying participants, with the constructor each qualified
    for (handles seat swaps/substitutes). Once F1 has published the official
    starting grid (``starting_grids``), the entrants are exactly that grid's cars:
    a driver with no lap time is added, and a qualifier who won't start leaves.
    Two effects on top of the already-advanced filter state in ``v2["hf"]``: the
    quali order through the standard rating channel, then grid_offsets folded into
    the means. Seeded with the backtest convention so the output is a
    deterministic function of its inputs.

    The quali order feeds the rating channel untouched — a penalised driver
    still demonstrated that pace — but the causal grid term and the displayed
    ``gridPosition`` use the actual starting slots: F1's official grid for this
    season/round when published, else the classification adjusted by any
    ``grid_penalties`` entry.

    A ``retirements`` entry marks cars already out of the *running* race. They
    keep their start slot (the grid offsets stay centred on the grid that
    actually formed) but leave the simulated field, so no trio containing one
    can score and P(new) is recomputed over the cars still circulating.

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

    # Actual starting slots. F1's official grid once it is published: penalties
    # applied, drivers without a lap time on it, a non-starter off it. Until then,
    # the quali classification adjusted for the hand-entered grid penalties.
    official = next(
        (e["grid"] for e in (starting_grids or []) if e["season"] == season and e["round"] == rnd),
        None,
    )
    if official:
        gpos = {row["driverId"]: row["position"] for row in official}
        for row in official:
            qcid.setdefault(row["driverId"], row["constructorId"])
    else:
        pens = next(
            (
                e["penalties"]
                for e in (grid_penalties or [])
                if e["season"] == season and e["round"] == rnd
            ),
            [],
        )
        gpos = _apply_grid_penalties(qpos, pens)

    # Cars already out of the running race: off the entrant list, still on the
    # grid that set the offsets. Unknown driverIds are ignored (a stale or
    # mistyped row must not silently shrink the field).
    retired = {
        d
        for e in (retirements or [])
        if e["season"] == season and e["round"] == rnd
        for d in e["driverIds"]
        if d in gpos
    }
    running = [d for d in sorted(gpos) if d not in retired]
    if len(running) < 3:
        return None

    # Causal track-position effect: grid offsets folded into the means.
    offsets = model_v2.grid_offsets(gpos, disp, params)
    mu_var: dict[str, tuple[float, float]] = {}
    p_fin: dict[str, float] = {}
    for d in running:
        mu, var = hf.engine.combined(d, qcid[d])
        mu_var[d] = (mu + offsets[d], var)
        p_fin[d] = hf.p_finish_adjusted(d, qcid[d], delta)

    seed = SEED + int(season) * 100 + int(rnd)
    out = model_v2.predict_race(
        running, mu_var, p_fin, temp, params, seen, n_draws=N_DRAWS, seed=seed
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
            e["constructorStrength"] = round(cid_strength.get(qcid[d], 0), 3)
        e["finishProb"] = round(p_fin[d], 3)
        e["uncertainty"] = round(math.sqrt(mu_var[d][1]), 3)
        e["gridPosition"] = gpos[d]
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
    driver_form = sorted((entry(d) for d in running), key=lambda x: -x["weight"])
    return {
        "season": season,
        "round": rnd,
        "raceName": nxt.get("raceName", ""),
        "chanceNextRaceNew": round(100 * out["p_new"], 1),
        "candidates": candidates,
        "trioBoard": build_trio_board(out["trio_probs"], seen, running),
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
    grid_penalties: list[dict] | None = None,
    retirements: list[dict] | None = None,
    starting_grids: list[dict] | None = None,
) -> dict:
    """Pure core: returns the podigami.json payload. No file IO."""
    races = sorted(podiums, key=lambda r: (int(r["season"]), int(r["round"])))
    n = len(races)
    current = max(int(r["season"]) for r in races)

    per_driver = model.index_podiums(races)
    name_by_id: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()
    for r in races:
        for d in podium_drivers(r):
            name_by_id[d["driverId"]] = d["name"]
        # A shared car makes one race the origin of several trios; all of them
        # have happened, so none may be reported as new.
        seen.update(podium_trios(r))

    grid_name = {d["driverId"]: d["name"] for d in grid}
    grid_ids = sorted(grid_name)

    def nm(d: str) -> str:
        return name_by_id.get(d) or grid_name.get(d) or _title_from_id(d)

    con_strength, driver_cid, cid_strength = _build_constructor_strength(
        constructor_data, current, race_results
    )
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
        as_of = (int(races[-1]["season"]), int(races[-1]["round"]))
        v2 = _v2_next_race_model(
            race_results, qualifying, schedule, grid_ids, driver_cid, seen, as_of=as_of
        )
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
        trio_probs = v2["trio_probs"]
    else:
        set_probs = model.all_set_probs(lam, grid_ids)
        ranked, chance_new = model.rank_and_new(set_probs, seen)
        ranked_new = [(t, p) for t, p in ranked if t not in seen]
        trio_probs = set_probs

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
            cid_strength,
            using_constructors,
            grid_penalties=grid_penalties,
            retirements=retirements,
            starting_grids=starting_grids,
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
        "trioBoard": build_trio_board(trio_probs, seen, grid_ids),
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
    grid_penalties = None
    if GRID_PENALTIES_PATH.exists():
        grid_penalties = json.loads(GRID_PENALTIES_PATH.read_text(encoding="utf-8"))
    retirements = None
    if RETIREMENTS_PATH.exists():
        retirements = json.loads(RETIREMENTS_PATH.read_text(encoding="utf-8"))
    starting_grids = None
    if STARTING_GRIDS_PATH.exists():
        starting_grids = json.loads(STARTING_GRIDS_PATH.read_text(encoding="utf-8"))

    payload = compute(
        podiums,
        combos,
        grid,
        constructor_data,
        race_results=race_results,
        qualifying=qualifying,
        schedule=schedule,
        grid_penalties=grid_penalties,
        retirements=retirements,
        starting_grids=starting_grids,
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
