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
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import metrics  # noqa: E402
import model  # noqa: E402

from datalib import save_model_eval  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PODIUMS_PATH = DATA_DIR / "podiums.json"
DRIVER_RACES_PATH = DATA_DIR / "driver_races.json"
OUT_PATH = DATA_DIR / "model_eval.json"

EVAL_START = 2010  # modern era
VAL_END = 2018  # tune on [EVAL_START, VAL_END]; test on (VAL_END, latest]
RECENT_WINDOW = 20  # races, for the recent-frequency baseline

CURRENT_PARAMS = {  # replicates today's shipped model
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


def evaluate(races, active, test) -> dict:
    """Score the ladder on the untouched test window using the LOCKED
    model.DEFAULT_PARAMS as the chosen model (deterministic, no tuning)."""
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

    base_rate = sum(r["is_new"] for r in rf) / max(len(rf), 1)
    brier_new_base = metrics.brier_binary([base_rate] * len(ch), [r["is_new"] for r in ch])
    cal = metrics.calibration_bins([r["q_new"] for r in ch], [r["is_new"] for r in ch])
    ece = metrics.expected_calibration_error([r["q_new"] for r in ch], [r["is_new"] for r in ch])

    chosen = dict(ladder[-1][1])
    chosen.update(
        baseRateNew=round(base_rate, 4),
        brierNewBaseRate=round(brier_new_base, 4),
        ece=round(ece, 4),
    )
    return {
        "ladder": ladder,
        "chosen": chosen,
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

    res = evaluate(races, active, test)
    ladder, chosen, cal = res["ladder"], res["chosen"], res["calibration"]
    params = {
        k: model.DEFAULT_PARAMS[k]
        for k in ("halfLife", "offSeason", "seasonBoost", "posWeights", "temperature")
    }

    payload = {
        "evalWindow": {"validation": list(val), "test": list(test)},
        "modelParams": params,
        "ladder": [{"model": name, **m} for name, m in ladder],
        "chosen": chosen,
        "calibration": cal,
        "poolNote": "candidate pools = drivers active that race (driver_races) + the actual podium",
    }
    save_model_eval(payload)

    print(f"Model params: {params}")
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
