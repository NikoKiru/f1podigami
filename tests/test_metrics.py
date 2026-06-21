"""Unit tests for the proper-scoring / accuracy helpers."""

import math

import pytest

from compute import metrics


def test_log_loss_perfect_and_coin_flip():
    assert metrics.log_loss([1.0, 1.0]) == pytest.approx(0.0)
    assert metrics.log_loss([0.5]) == pytest.approx(-math.log(0.5))


def test_brier_binary_known():
    assert metrics.brier_binary([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)
    assert metrics.brier_binary([0.5], [1.0]) == pytest.approx(0.25)


def test_brier_categorical_two_class_uniform():
    # P=[0.5,0.5], true class prob 0.5, Σp^2 = 0.5 -> Brier = 0.5
    assert metrics.brier_categorical([0.5], [0.5]) == pytest.approx(0.5)


def test_top_k_rate_counts_ranks_within_k():
    assert metrics.top_k_rate([1, 2, 5, None], 3) == pytest.approx(0.5)
    assert metrics.top_k_rate([1, 1, 1], 1) == pytest.approx(1.0)


def test_calibration_bins_and_ece():
    # two predictions, one per extreme bin, each perfectly calibrated
    bins = metrics.calibration_bins([0.05, 0.95], [0.0, 1.0], nbins=10)
    filled = [b for b in bins if b["n"]]
    assert len(filled) == 2
    assert metrics.expected_calibration_error([0.05, 0.95], [0.0, 1.0]) == pytest.approx(0.05)
