"""Pure scoring helpers for the predictor backtest (no IO).

These are the proper scoring rules and accuracy metrics used to compare models
honestly: log-loss and Brier reward putting probability mass on what actually
happened; top-k hit-rate measures ranking; calibration bins check that stated
probabilities match observed frequencies.
"""

from __future__ import annotations

import math

EPS = 1e-12


def log_loss(p_true: list[float]) -> float:
    """Mean negative log-likelihood of the actually-observed outcome.

    ``p_true[i]`` is the probability the model assigned to what really happened
    in race ``i``. Lower is better; a perfect model scores 0.
    """
    if not p_true:
        return float("nan")
    return -sum(math.log(min(max(p, EPS), 1.0)) for p in p_true) / len(p_true)


def brier_categorical(sum_sq: list[float], p_true: list[float]) -> float:
    """Mean multiclass Brier score over a categorical outcome.

    For one race, Brier = Σ_T (P(T) - 1[T=actual])^2 = (Σ_T P(T)^2) - 2·P(actual) + 1.
    ``sum_sq[i]`` = Σ_T P(T)^2 for race ``i``; ``p_true[i]`` = P(actual). Lower is better.
    """
    if not p_true:
        return float("nan")
    return sum(s - 2 * p + 1 for s, p in zip(sum_sq, p_true, strict=True)) / len(p_true)


def brier_binary(pred: list[float], actual: list[float]) -> float:
    """Mean squared error of a probability against a 0/1 outcome (lower better)."""
    if not pred:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(pred, actual, strict=True)) / len(pred)


def top_k_rate(ranks: list[int | None], k: int) -> float:
    """Fraction of races where the actual outcome ranked within the top ``k``.

    ``ranks[i]`` is the 1-based rank the model gave the actual outcome (or None
    if it was outside the considered pool).
    """
    if not ranks:
        return float("nan")
    hit = sum(1 for r in ranks if r is not None and r <= k)
    return hit / len(ranks)


def calibration_bins(pred: list[float], actual: list[float], nbins: int = 10) -> list[dict]:
    """Reliability bins: group predictions into ``nbins`` and compare the mean
    predicted probability to the observed frequency in each bin."""
    bins = []
    for b in range(nbins):
        lo = b / nbins
        hi = (b + 1) / nbins
        idx = [
            i for i, p in enumerate(pred) if (p >= lo and p < hi) or (b == nbins - 1 and p == 1.0)
        ]
        if not idx:
            bins.append({"lo": lo, "hi": hi, "n": 0, "meanPred": None, "obsRate": None})
            continue
        mean_pred = sum(pred[i] for i in idx) / len(idx)
        obs = sum(actual[i] for i in idx) / len(idx)
        bins.append(
            {
                "lo": round(lo, 3),
                "hi": round(hi, 3),
                "n": len(idx),
                "meanPred": round(mean_pred, 4),
                "obsRate": round(obs, 4),
            }
        )
    return bins


def expected_calibration_error(pred: list[float], actual: list[float], nbins: int = 10) -> float:
    """Weighted average gap between predicted probability and observed rate."""
    bins = calibration_bins(pred, actual, nbins)
    n = len(pred) or 1
    return sum(
        (b["n"] / n) * abs(b["meanPred"] - b["obsRate"])
        for b in bins
        if b["n"] and b["meanPred"] is not None
    )
