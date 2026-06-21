"""Podium-prediction model (pure, no IO).

Two pieces, kept separate so each is testable and swappable:

1. Driver *strengths* λ_d  — a recency-weighted, off-season-decayed, shrinkage-
   floored score from a driver's past podiums (optionally weighted by finishing
   position, plus a current-season boost). Uses only races *before* the
   prediction point, so it is leakage-free for backtesting.

2. *Plackett-Luce* aggregation — the probability a trio is the top-3 *set*, as
   the sum over the 6 podium orderings of sequential pick probabilities
   λ_i / (Σ remaining). This replaces the old "product of weights, normalised
   over all trios", which is not a valid top-3 model.
"""

from __future__ import annotations

from itertools import combinations, permutations

# Locked by the walk-forward backtest (see backtest.py): these values won the
# held-out test window (lowest log-loss, best top-3/top-5) over the grid search.
DEFAULT_PARAMS = {
    "alpha": 0.1,  # strength floor: even a never-podiumed driver can, in principle
    "halfLife": 6.0,  # races; a podium's weight halves every halfLife races
    "offSeason": 0.5,  # extra multiplier applied per season boundary crossed
    "seasonBoost": 0.2,  # added per podium scored in the prediction's season
    "posWeights": (1.0, 0.85, 0.72),  # credit for P1 / P2 / P3
    "temperature": 1.0,  # >1 flattens, <1 sharpens (backtest found 1.0 best)
}

POS_KEYS = ("p1", "p2", "p3")


def trio_key(ids) -> tuple[str, str, str]:
    return tuple(sorted(ids))  # type: ignore[return-value]


def index_podiums(races: list[dict]) -> dict[str, list[tuple[int, int, int]]]:
    """Pre-index every driver's podiums as (race_index, season, position 0..2).

    ``races`` must be in chronological order. Returned once and reused for every
    backtest cut-off, so strengths at any point are cheap to recompute.
    """
    per_driver: dict[str, list[tuple[int, int, int]]] = {}
    for i, r in enumerate(races):
        season = int(r["season"])
        for pos, key in enumerate(POS_KEYS):
            d = r[key]["driverId"]
            per_driver.setdefault(d, []).append((i, season, pos))
    return per_driver


def strengths(
    per_driver: dict[str, list[tuple[int, int, int]]],
    pool: list[str],
    upto: int,
    current_season: int,
    params: dict | None = None,
) -> dict[str, float]:
    """Strength λ_d for each driver in ``pool``, using only podiums at race index
    < ``upto``. ``current_season`` is the season of the race being predicted."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    alpha = p["alpha"]
    half = p["halfLife"]
    off = p["offSeason"]
    boost = p["seasonBoost"]
    pw = p["posWeights"]

    lam: dict[str, float] = {}
    for d in pool:
        score = alpha
        season_pods = 0
        for idx, season, pos in per_driver.get(d, ()):
            if idx >= upto:
                break  # lists are chronological; nothing later counts
            races_ago = upto - idx
            recency = 0.5 ** (races_ago / half)
            seasons_ago = current_season - season
            decay = off**seasons_ago if seasons_ago > 0 else 1.0
            score += pw[pos] * recency * decay
            if season == current_season:
                season_pods += 1
        score += boost * season_pods
        lam[d] = score
    return lam


def temper(lam: dict[str, float], temperature: float) -> dict[str, float]:
    """Temperature-scale strengths: λ^(1/T). T>1 flattens, T<1 sharpens."""
    if temperature == 1.0:
        return lam
    inv = 1.0 / temperature
    return {d: v**inv for d, v in lam.items()}


def pl_set_prob(trio, lam: dict[str, float], pool_total: float) -> float:
    """Plackett-Luce probability that ``trio`` is exactly the top-3 set.

    ``pool_total`` = Σ λ over the full candidate pool. Sums the 6 orderings.
    """
    total = 0.0
    for a, b, c in permutations(trio):
        la, lb, lc = lam[a], lam[b], lam[c]
        z2 = pool_total - la
        if z2 <= 0:
            continue
        z3 = z2 - lb
        if z3 <= 0:
            continue
        total += (la / pool_total) * (lb / z2) * (lc / z3)
    return total


def all_set_probs(lam: dict[str, float], pool: list[str]) -> dict[tuple, float]:
    """P(set) for every 3-subset of ``pool`` (keys are sorted-id tuples)."""
    pool_total = sum(lam[d] for d in pool)
    out: dict[tuple, float] = {}
    if pool_total <= 0:
        return out
    for trio in combinations(sorted(pool), 3):
        out[trio] = pl_set_prob(trio, lam, pool_total)
    return out


def rank_and_new(
    set_probs: dict[tuple, float], seen: set
) -> tuple[list[tuple[tuple, float]], float]:
    """Sort sets by probability (desc) and return (ranked, P(new)) where P(new)
    is the total probability mass on trios not in ``seen``."""
    ranked = sorted(set_probs.items(), key=lambda kv: -kv[1])
    p_new = sum(p for t, p in set_probs.items() if t not in seen)
    return ranked, p_new


# --- live-only car / teammate overlay ----------------------------------------
# Applied to the *current* grid from this season's constructor standings. It is
# NOT part of the backtested score (we have no historical team mapping), so it
# is kept here, separate, and flagged in the output so the UI can disclose it.


def apply_car_overlay(
    lam: dict[str, float],
    driver_cid: dict[str, str],
    strength01: dict[str, float],
    factor: float = 0.5,
    teammate_beta: float = 0.15,
) -> dict[str, float]:
    """Nudge strengths by current constructor strength (``strength01`` is each
    driver's team strength 0..1) and blend a little of each driver's teammate's
    strength in (shared-car "halo"). Live-only; not part of the backtest."""
    out = {d: v * (1.0 + factor * strength01.get(d, 0.0)) for d, v in lam.items()}
    if teammate_beta > 0:
        teams: dict[str, list[str]] = {}
        for d in out:
            cid = driver_cid.get(d, "")
            if cid:
                teams.setdefault(cid, []).append(d)
        blended = dict(out)
        for mates in teams.values():
            if len(mates) == 2:
                a, b = mates
                blended[a] = (1 - teammate_beta) * out[a] + teammate_beta * out[b]
                blended[b] = (1 - teammate_beta) * out[b] + teammate_beta * out[a]
        out = blended
    return out
