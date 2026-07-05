"""Walk-forward backtest of the podium predictor (the integrity core).

For every modern race we build driver strengths from *only* the races before it,
rank every possible podium set, and score how well the model did with proper
scoring rules (log-loss, Brier), top-k hit-rate, and P(new)-trio calibration.

A ladder of models is compared so improvements are earned, not assumed:
  base-rate -> recent-frequency -> current product model -> Plackett-Luce
  -> PL + tuned strengths -> + temperature calibration.

Hyper-parameters are tuned on an earlier validation window and the head-to-head
numbers are reported on a later, untouched test window (no leakage). Writes
data/model_eval.json and prints the ladder.
"""

from __future__ import annotations

import json
import math
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import metrics  # noqa: E402
import model  # noqa: E402
import model_v2  # noqa: E402

from datalib import save_model_eval  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
DRIVER_RACES_PATH = DATA_DIR / "driver_races.json"
RACE_RESULTS_PATH = DATA_DIR / "race_results.json"
QUALIFYING_PATH = DATA_DIR / "qualifying.json"
OUT_PATH = DATA_DIR / "model_eval.json"

EVAL_START = 2010  # modern era
VAL_END = 2018  # tune on [EVAL_START, VAL_END]; test on (VAL_END, latest]
RECENT_WINDOW = 20  # races, for the recent-frequency baseline

CURRENT_PARAMS = {  # legacy product baseline — ladder rung for head-to-head comparison
    "alpha": 0.1,
    "halfLife": 8.0,
    "offSeason": 1.0,
    "seasonBoost": 0.5,
    "posWeights": (1.0, 1.0, 1.0),
    "temperature": 1.0,
}

# Coarse tuning grid (kept small to avoid overfitting).
TUNE_GRID = [
    {"halfLife": h, "offSeason": o, "seasonBoost": s, "posWeights": pw}
    for h in (6.0, 8.0, 12.0)
    for o in (0.5, 0.65, 1.0)
    for s in (0.2, 0.4)
    for pw in ((1.0, 1.0, 1.0), (1.0, 0.85, 0.72))
]
TEMPS = (0.7, 0.85, 1.0, 1.2, 1.5, 2.0)


def load():
    races = sorted(
        json.loads(PODIUMS_PATH.read_text(encoding="utf-8")),
        key=lambda r: (int(r["season"]), int(r["round"])),
    )
    dr = json.loads(DRIVER_RACES_PATH.read_text(encoding="utf-8"))["drivers"]
    active: dict[int, set[str]] = {}
    for d, info in dr.items():
        for k in info.get("races", []):
            active.setdefault(int(k), set()).add(d)
    return races, active


def season_key(r: dict) -> int:
    return int(r["season"]) * 1000 + int(r["round"])


def pool_for(r: dict, active: dict[int, set[str]]) -> list[str]:
    base = set(active.get(season_key(r), set()))
    base.update(r[k]["driverId"] for k in model.POS_KEYS)
    return sorted(base)


# --- strength functions for each ladder rung ---------------------------------


def lam_recent_freq(per_driver, pool, upto, _cs):
    lam = {}
    for d in pool:
        c = sum(1 for idx, _s, _p in per_driver.get(d, ()) if upto - RECENT_WINDOW <= idx < upto)
        lam[d] = 0.1 + c
    return lam


def lam_current(per_driver, pool, upto, cs):
    return model.strengths(per_driver, pool, upto, cs, CURRENT_PARAMS)


def make_lam_tuned(params):
    def fn(per_driver, pool, upto, cs):
        return model.strengths(per_driver, pool, upto, cs, params)

    return fn


# --- aggregation -------------------------------------------------------------


def set_probs_product(lam, pool):
    out = {}
    tot = 0.0
    for trio in combinations(sorted(pool), 3):
        w = lam[trio[0]] * lam[trio[1]] * lam[trio[2]]
        out[trio] = w
        tot += w
    if tot > 0:
        for t in out:
            out[t] /= tot
    return out


def set_probs_pl(lam, pool):
    return model.all_set_probs(lam, pool)


# --- scoring a window --------------------------------------------------------


def score_window(races, active, lam_fn, agg, window, temperature=1.0):
    """Return per-race records over the (lo, hi] season window."""
    per_driver = model.index_podiums(races)
    seen: set = set()
    recs = []
    for i, r in enumerate(races):
        key = model.trio_key(r[k]["driverId"] for k in model.POS_KEYS)
        is_new = key not in seen
        if window[0] <= int(r["season"]) <= window[1]:
            pool = pool_for(r, active)
            lam = lam_fn(per_driver, pool, i, int(r["season"]))
            if temperature != 1.0:
                lam = model.temper(lam, temperature)
            sp = agg(lam, pool)
            if sp:
                ranked = sorted(sp.items(), key=lambda kv: -kv[1])
                rank = next((j + 1 for j, (t, _) in enumerate(ranked) if t == key), None)
                p_true = sp.get(key, 0.0)
                sum_sq = sum(p * p for p in sp.values())
                q_new = sum(p for t, p in sp.items() if t not in seen)
                recs.append(
                    {
                        "rank": rank,
                        "p_true": p_true,
                        "sum_sq": sum_sq,
                        "q_new": q_new,
                        "is_new": 1.0 if is_new else 0.0,
                    }
                )
        seen.add(key)
    return recs


def summarize(recs: list[dict]) -> dict:
    ranks = [r["rank"] for r in recs]
    return {
        "n": len(recs),
        "top1": round(metrics.top_k_rate(ranks, 1), 4),
        "top3": round(metrics.top_k_rate(ranks, 3), 4),
        "top5": round(metrics.top_k_rate(ranks, 5), 4),
        "logLoss": round(metrics.log_loss([r["p_true"] for r in recs]), 4),
        "brierSet": round(
            metrics.brier_categorical([r["sum_sq"] for r in recs], [r["p_true"] for r in recs]), 4
        ),
        "brierNew": round(
            metrics.brier_binary([r["q_new"] for r in recs], [r["is_new"] for r in recs]), 4
        ),
    }


def tune(races, active, val) -> dict:
    """Grid-search PL strengths (then temperature) on the validation window,
    minimising log-loss. Used to *choose* model.DEFAULT_PARAMS during dev."""
    best, best_ll = None, float("inf")
    for params in TUNE_GRID:
        recs = score_window(races, active, make_lam_tuned(params), set_probs_pl, val)
        ll = metrics.log_loss([r["p_true"] for r in recs])
        if ll < best_ll:
            best_ll, best = ll, params
    best_t, best_tll = 1.0, float("inf")
    for t in TEMPS:
        recs = score_window(races, active, make_lam_tuned(best), set_probs_pl, val, temperature=t)
        ll = metrics.log_loss([r["p_true"] for r in recs])
        if ll < best_tll:
            best_tll, best_t = ll, t
    return {**model.DEFAULT_PARAMS, **best, "temperature": best_t}


# --- v2: dynamic Bayesian rating engine over full classifications -------------

# Ablation ladder: each rung switches one v2 channel on (overrides on top of
# the tuned DEFAULT_PARAMS_V2; reliability is core and stays on in all rungs).
RUNGS_V2 = [
    (
        "v2 pace",
        {"w_attr": 0.0, "w_qual": 0.0, "chaos_gamma": 0.0, "chaos_eta": 0.0, "p_wild": 0.0},
    ),
    ("v2 +attrition", {"w_qual": 0.0, "chaos_gamma": 0.0, "chaos_eta": 0.0, "p_wild": 0.0}),
    ("v2 +chaos", {"w_qual": 0.0}),
    ("v2 full", {}),
]

# Per-knob grids for --tune-v2 coordinate descent (2 sweeps, validation window).
V2_TUNE_GRID: dict[str, list] = {
    "sigma0_drv": [0.5, 0.7, 1.0],
    "sigma0_con": [0.8, 1.2, 1.6],
    "rookie_mu": [-0.8, -0.4, 0.0],
    "newteam_mu": [-1.2, -0.8, -0.4],
    "tau_drv": [0.02, 0.04, 0.08],
    "tau_con": [0.04, 0.08, 0.15],
    "season_var_drv": [0.01, 0.03, 0.08],
    "season_var_con": [0.05, 0.1, 0.2],
    "reg_var_con": [0.2, 0.5, 1.0],
    "depth_race": [3, 6, 10],
    "w_attr": [0.0, 0.25, 0.5, 1.0],
    "depth_qual": [3, 6, 10],
    "w_qual": [0.0, 0.15, 0.3, 0.6],
    "rel_half_life": [10.0, 20.0, 40.0],
    "chaos_gamma": [0.0, 0.5, 1.0],
    "chaos_eta": [0.0, 0.35, 0.7],
    "p_wild": [0.0, 0.05, 0.1],
    "t_wild": [1.5, 2.5],
}


def load_v2():
    """Load (race_results, quali_map) for the v2 rungs, or None if not fetched."""
    if not RACE_RESULTS_PATH.exists():
        return None
    rresults = sorted(
        json.loads(RACE_RESULTS_PATH.read_text(encoding="utf-8")),
        key=lambda r: (int(r["season"]), int(r["round"])),
    )
    quali_map = {}
    if QUALIFYING_PATH.exists():
        for e in json.loads(QUALIFYING_PATH.read_text(encoding="utf-8")):
            quali_map[(e["season"], e["round"])] = e
    return rresults, quali_map


def trio_keys_from(races) -> dict[tuple[str, str], tuple]:
    """(season, round) -> actual podium trio key, from podiums.json records."""
    return {
        (r["season"], r["round"]): model.trio_key(r[k]["driverId"] for k in model.POS_KEYS)
        for r in races
    }


def score_window_v2(
    rresults, quali_map, trio_keys, window, params, *, draws=64, rank_draws=16, with_rank=False
):
    """One HistoryFilter pass over the whole history; score races in the window.

    The fine pass (``draws``) tracks the actual trio plus every seen trio, so
    p_true and q_new (the exact novelty complement) carry only skill-noise MC
    error. Rank/top-k/brierSet need all-trio probabilities, so ``with_rank``
    adds a coarser all-trio pass (``rank_draws``) — ordinal metrics only.
    """
    hf = model_v2.HistoryFilter(params)
    seen: set = set()
    recs = []
    for race in rresults:
        rk = (race["season"], race["round"])
        key = trio_keys.get(rk)
        snap = hf.step(race, quali_map.get(rk))
        if (
            key is not None
            and window[0] <= int(race["season"]) <= window[1]
            and len(snap["drivers"]) >= 3
        ):
            entrants = sorted(snap["drivers"])
            mu_var = {d: (v[0], v[1]) for d, v in snap["drivers"].items()}
            p_fin = {d: v[2] for d, v in snap["drivers"].items()}
            seed = 20260704 + int(race["season"]) * 100 + int(race["round"])
            fine = model_v2.predict_race(
                entrants,
                mu_var,
                p_fin,
                snap["temp"],
                params,
                seen | {key},  # ensure the actual trio is tracked exactly
                n_draws=draws,
                seed=seed,
                screen=0,
            )
            q_new = 1.0 - sum(
                fine["trio_probs"][t] for t in sorted(seen) if t in fine["trio_probs"]
            )
            rank = None
            sum_sq = None
            if with_rank:
                coarse = model_v2.predict_race(
                    entrants,
                    mu_var,
                    p_fin,
                    snap["temp"],
                    params,
                    set(),
                    n_draws=rank_draws,
                    seed=seed,
                    screen=10**9,
                )
                ranked = sorted(coarse["trio_probs"].items(), key=lambda kv: (-kv[1], kv[0]))
                rank = next((j + 1 for j, (t, _) in enumerate(ranked) if t == key), None)
                sum_sq = sum(p * p for p in coarse["trio_probs"].values())
            recs.append(
                {
                    "rank": rank,
                    "p_true": fine["trio_probs"].get(key, 0.0),
                    "sum_sq": sum_sq,
                    "q_new": q_new,
                    "is_new": 0.0 if key in seen else 1.0,
                }
            )
        if key is not None:
            seen.add(key)
    return recs


def v2_objective(recs) -> float:
    """Tuning objective: trio log-loss + binary novelty log-loss (both lower-better)."""
    eps = 1e-9
    ll_trio = metrics.log_loss([r["p_true"] for r in recs])
    ll_new = -sum(
        r["is_new"] * math.log(max(r["q_new"], eps))
        + (1.0 - r["is_new"]) * math.log(max(1.0 - r["q_new"], eps))
        for r in recs
    ) / max(len(recs), 1)
    return ll_trio + ll_new


def tune_v2(rresults, quali_map, trio_keys, val, *, sweeps=2, verbose=True) -> dict:
    """Coordinate descent over V2_TUNE_GRID on the validation window."""
    best = dict(model_v2.DEFAULT_PARAMS_V2)
    best_j = v2_objective(score_window_v2(rresults, quali_map, trio_keys, val, best))
    if verbose:
        print(f"start J={best_j:.4f}")
    for sweep in range(sweeps):
        for knob, grid in V2_TUNE_GRID.items():
            for value in grid:
                if value == best[knob]:
                    continue
                trial = dict(best, **{knob: value})
                j = v2_objective(score_window_v2(rresults, quali_map, trio_keys, val, trial))
                if j < best_j:
                    best_j, best = j, trial
            if verbose:
                print(f"  sweep {sweep + 1} {knob} -> {best[knob]}  (J={best_j:.4f})")
    return best


def evaluate(races, active, test, v2_data=None) -> dict:
    """Score the ladder on the untouched test window using the LOCKED
    model.DEFAULT_PARAMS / model_v2.DEFAULT_PARAMS_V2 (deterministic, no tuning)."""
    chosen_params = model.DEFAULT_PARAMS
    temp = chosen_params["temperature"]

    ladder = []
    rf = score_window(races, active, lam_recent_freq, set_probs_pl, test)
    ladder.append(("recent-frequency", summarize(rf)))
    pr = score_window(races, active, lam_current, set_probs_product, test)
    ladder.append(("current (product)", summarize(pr)))
    pl = score_window(races, active, lam_current, set_probs_pl, test)
    ladder.append(("plackett-luce", summarize(pl)))
    ch = score_window(
        races, active, make_lam_tuned(chosen_params), set_probs_pl, test, temperature=temp
    )
    ladder.append(("PL + tuned (chosen)", summarize(ch)))

    chosen_recs, chosen_name = ch, "PL + tuned (chosen)"
    chosen_model_params = {
        k: chosen_params[k]
        for k in ("halfLife", "offSeason", "seasonBoost", "posWeights", "temperature")
    }
    if v2_data is not None:
        rresults, quali_map = v2_data
        keys = trio_keys_from(races)
        v2_full_recs = None
        for name, overrides in RUNGS_V2:
            params = dict(model_v2.DEFAULT_PARAMS_V2, **overrides)
            recs = score_window_v2(rresults, quali_map, keys, test, params, with_rank=True)
            ladder.append((name, summarize(recs)))
            if name == "v2 full":
                v2_full_recs = recs
        v1, v2 = dict(ladder[3][1]), dict(ladder[-1][1])
        # Acceptance gate: v2 ships only if it wins BOTH headline scores.
        if v2["logLoss"] <= v1["logLoss"] and v2["brierNew"] <= v1["brierNew"]:
            chosen_recs, chosen_name = v2_full_recs, "v2 full"
            chosen_model_params = dict(model_v2.DEFAULT_PARAMS_V2)

    base_rate = sum(r["is_new"] for r in rf) / max(len(rf), 1)
    brier_new_base = metrics.brier_binary(
        [base_rate] * len(chosen_recs), [r["is_new"] for r in chosen_recs]
    )
    cal = metrics.calibration_bins(
        [r["q_new"] for r in chosen_recs], [r["is_new"] for r in chosen_recs]
    )
    ece = metrics.expected_calibration_error(
        [r["q_new"] for r in chosen_recs], [r["is_new"] for r in chosen_recs]
    )

    chosen = dict(summarize(chosen_recs))
    chosen.update(
        baseRateNew=round(base_rate, 4),
        brierNewBaseRate=round(brier_new_base, 4),
        ece=round(ece, 4),
    )
    return {
        "ladder": ladder,
        "chosen": chosen,
        "chosenName": chosen_name,
        "chosenParams": chosen_model_params,
        "calibration": cal,
        "baseRate": base_rate,
        "brierNewBase": brier_new_base,
        "ece": ece,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tune",
        action="store_true",
        help="grid-search params on the validation window and print the winner",
    )
    ap.add_argument(
        "--tune-v2",
        action="store_true",
        help="coordinate-descent v2 knobs on the validation window and print the winner",
    )
    args = ap.parse_args(argv)

    races, active = load()
    latest = max(int(r["season"]) for r in races)
    val, test = (EVAL_START, VAL_END), (VAL_END + 1, latest)

    if args.tune:
        winner = tune(races, active, val)
        print("Best validation params (lock these into model.DEFAULT_PARAMS):")
        print(
            {
                k: winner[k]
                for k in ("halfLife", "offSeason", "seasonBoost", "posWeights", "temperature")
            }
        )
        return 0

    v2_data = load_v2()

    if args.tune_v2:
        if v2_data is None:
            print("race_results.json missing - run src/fetch/fetch_race_results.py first")
            return 1
        winner = tune_v2(v2_data[0], v2_data[1], trio_keys_from(races), val)
        print("Best validation params (lock these into model_v2.DEFAULT_PARAMS_V2):")
        print(winner)
        return 0

    res = evaluate(races, active, test, v2_data)
    ladder, chosen, cal = res["ladder"], res["chosen"], res["calibration"]
    params = res["chosenParams"]

    payload = {
        "evalWindow": {"validation": list(val), "test": list(test)},
        "modelParams": params,
        "ladder": [{"model": name, **m} for name, m in ladder],
        "chosen": chosen,
        "calibration": cal,
        "poolNote": "candidate pools = drivers active that race (driver_races) + the actual podium",
    }
    if v2_data is not None:
        payload["chosenModel"] = res["chosenName"]
    save_model_eval(payload)

    print(f"Chosen model: {res['chosenName']}\nModel params: {params}")
    print(f"Validation {val}  Test {test}  ({chosen['n']} test races)\n")
    hdr = f"{'model':22} {'top1':>6} {'top3':>6} {'top5':>6} {'logLoss':>8} {'brierNew':>9}"
    print(hdr)
    print("-" * len(hdr))
    for name, m in ladder:
        print(
            f"{name:22} {m['top1']:>6.3f} {m['top3']:>6.3f} {m['top5']:>6.3f} "
            f"{m['logLoss']:>8.3f} {m['brierNew']:>9.3f}"
        )
    print(
        f"\nP(new) base-rate {res['baseRate']:.3f} | brierNew base {res['brierNewBase']:.3f} "
        f"vs model {chosen['brierNew']:.3f} | ECE {res['ece']:.3f}"
    )
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
