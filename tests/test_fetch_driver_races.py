"""Tests for the driver-race-history fetch target pool (#147)."""

from fetch import fetch_driver_races as fdr


def _podium(p1, p2, p3):
    return {"p1": {"driverId": p1}, "p2": {"driverId": p2}, "p3": {"driverId": p3}}


def test_pool_includes_top_podium_getters():
    podiums = [_podium("top", f"filler2_{i}", f"filler3_{i}") for i in range(5)] + [
        _podium("other", f"filler2b_{i}", f"filler3b_{i}") for i in range(2)
    ]
    targets = fdr.target_driver_ids(podiums, grid_drivers=[], combos=[], pool_n=1)
    assert "top" in targets
    assert "other" not in targets


def test_pool_includes_current_grid():
    targets = fdr.target_driver_ids(
        podiums=[], grid_drivers=[{"driverId": "rookie", "name": "Rookie"}], combos=[]
    )
    assert "rookie" in targets


def test_pool_includes_every_combo_driver_even_outside_top_n():
    """A driver who appears in a historical combos.json trio must always get a
    race-history entry, even if their raw podium count is outside the top-N
    pool — otherwise compute_unlikeliest silently skips that trio (#147)."""
    # "star" dominates the podium-count pool; the combo drivers never podiumed.
    podiums = [_podium("star", f"filler2_{i}", f"filler3_{i}") for i in range(10)]
    combos = [{"driverIds": ["obscure_a", "obscure_b", "obscure_c"]}]
    targets = fdr.target_driver_ids(podiums, grid_drivers=[], combos=combos, pool_n=1)
    assert {"obscure_a", "obscure_b", "obscure_c"} <= targets
