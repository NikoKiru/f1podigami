"""Tests for the next-race track drawing: rotation to fill the band, and its SVG."""

import json
import re
from pathlib import Path

from build import track_art

REPO = Path(__file__).resolve().parents[1]

# The box's own shape, axis-aligned: it already fills the box exactly, so any turn
# only makes it smaller.
FLAT = [(0.0, 0.0), (28.0, 0.0), (28.0, 10.0), (0.0, 10.0)]
# The same shape tilted 45 degrees clockwise: turning it back is the best fit.
DIAGONAL = [(0.0, 0.0), (19.8, 19.8), (12.7, 26.9), (-7.1, 7.1)]


def _coords(d: str) -> list[tuple[float, float]]:
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2], strict=False))


def test_parse_path_reads_the_stored_outline():
    assert track_art.parse_path("M1.5 2.0 L-3.0 4.5 L6 7 Z") == [
        (1.5, 2.0),
        (-3.0, 4.5),
        (6.0, 7.0),
    ]


def test_best_angle_lays_a_diagonal_track_flat():
    assert track_art.best_angle(DIAGONAL) == -45


def test_best_angle_leaves_a_track_that_already_fits():
    assert track_art.best_angle(FLAT) == 0


def test_best_angle_needs_a_ten_percent_gain_to_turn():
    # Tilted just enough to make a small gain from straightening it: below the 10%
    # bar the track keeps its north-up orientation.
    slight = track_art.rotate(FLAT, 1)
    assert track_art.best_angle(slight) == 0


def test_best_angle_stays_within_a_half_turn():
    for pts in (DIAGONAL, FLAT, track_art.rotate(DIAGONAL, 80)):
        assert -90 <= track_art.best_angle(pts) < 90


def test_flipped_circuit_turns_a_further_half_turn():
    plain = _coords(track_art.track_svg("M0 0 L10 10 L11 9 L1 -1 Z", "x_not_flipped")[1])
    flipped = _coords(track_art.track_svg("M0 0 L10 10 L11 9 L1 -1 Z", "yas_marina")[1])
    # Same shape, turned 180 degrees: every point mirrored through the centre.
    cx = (min(x for x, _ in plain) + max(x for x, _ in plain)) / 2
    cy = (min(y for _, y in plain) + max(y for _, y in plain)) / 2
    fcx = (min(x for x, _ in flipped) + max(x for x, _ in flipped)) / 2
    fcy = (min(y for _, y in flipped) + max(y for _, y in flipped)) / 2
    for (x, y), (fx, fy) in zip(plain, flipped, strict=True):
        assert abs((x - cx) + (fx - fcx)) < 0.15
        assert abs((y - cy) + (fy - fcy)) < 0.15


def test_owner_picked_flips_are_listed():
    assert track_art.FLIPPED == {
        "suzuka",
        "shanghai",
        "miami",
        "villeneuve",
        "monza",
        "madring",
        "rodriguez",
        "vegas",
        "yas_marina",
    }


def test_track_svg_viewbox_hugs_the_drawing():
    view_box, d = track_art.track_svg("M0 0 L10 10 L11 9 L1 -1 Z", "x")
    x, y, w, h = (float(v) for v in view_box.split())
    pts = _coords(d)
    margin = track_art.MARGIN
    assert abs(x - (min(p[0] for p in pts) - margin)) < 0.11
    assert abs(y - (min(p[1] for p in pts) - margin)) < 0.11
    assert abs(x + w - (max(p[0] for p in pts) + margin)) < 0.11
    assert abs(y + h - (max(p[1] for p in pts) + margin)) < 0.11
    assert d.startswith("M") and d.endswith(" Z")


def test_track_svg_is_deterministic():
    path = "M41.7 42.3 L34.8 30.8 L32.0 26.3 L60.2 11.0 L70.5 50.1 Z"
    assert track_art.track_svg(path, "losail") == track_art.track_svg(path, "losail")


def test_track_svg_blank_path_draws_nothing():
    assert track_art.track_svg("", "x") is None
    assert track_art.track_svg(None, "x") is None


def test_every_committed_circuit_gets_a_drawing():
    # Every outline on the committed calendar renders, and a rotated one is never
    # smaller in the band's box than north-up.
    sched = json.loads((REPO / "data" / "schedule.json").read_text(encoding="utf-8"))
    for race in sched["races"]:
        if not race.get("trackPath"):
            continue
        view_box, d = track_art.track_svg(race["trackPath"], race["circuitId"])
        _, _, w, h = (float(v) for v in view_box.split())
        assert w > 0 and h > 0 and len(_coords(d)) > 10, race["raceName"]
        pts = track_art.parse_path(race["trackPath"])
        assert track_art.fit_scale(track_art.rotate(pts, track_art.best_angle(pts))) >= (
            track_art.fit_scale(pts) - 1e-9
        )
