"""The next race's circuit, turned to fill the right side of the race band.

The stored outline (``schedule.json``'s ``trackPath``) is north-up. On the landing
page it is drawn large beside the next-race and last-race rows, in a box much wider
than tall, so each circuit is turned to the angle that makes it biggest there.
Turning is build-time geometry over committed data: it follows the next race on
every build and never needs a refetch.

Pure: no IO, deterministic output.
"""

from __future__ import annotations

import math
import re

# The band's drawing box: width over height on a desktop landing page.
BOX_ASPECT = 2.8
# Turn only when the track gets at least this much bigger, so a circuit that
# already fits keeps the north-up shape people know.
MIN_GAIN = 1.10
# viewBox breathing room around the drawing, in path units.
MARGIN = 2.0

# Circuits that read better the other way up: turning by a further 180 degrees
# costs no size, so this is purely what fans are used to seeing. Chosen by the
# site's owner, one circuit at a time. A circuit not listed (a new venue) keeps
# the computed angle until someone adds it.
FLIPPED = frozenset(
    {
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
)

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def parse_path(d: str) -> list[tuple[float, float]]:
    """The points of a stored ``M x y L x y ... Z`` outline."""
    nums = [float(n) for n in _NUM.findall(d)]
    return list(zip(nums[0::2], nums[1::2], strict=False))


def rotate(points: list[tuple[float, float]], degrees: float) -> list[tuple[float, float]]:
    """Turn points about the origin. SVG's y axis points down, so positive is clockwise."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def fit_scale(points: list[tuple[float, float]]) -> float:
    """How big the points draw when fitted into the band's box (bigger is better)."""
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    w = (max(xs) - min(xs)) or 1e-9
    h = (max(ys) - min(ys)) or 1e-9
    return min(BOX_ASPECT / w, 1.0 / h)


def best_angle(points: list[tuple[float, float]]) -> int:
    """Whole degrees in [-90, 90) that draw the track biggest, or 0 below MIN_GAIN.

    Ties go to the angle nearest upright. A half turn draws the same size, so the
    range stops at 90; FLIPPED supplies the other half.
    """
    best = max(range(-90, 90), key=lambda d: (round(fit_scale(rotate(points, d)), 9), -abs(d)))
    if fit_scale(rotate(points, best)) < MIN_GAIN * fit_scale(points):
        return 0
    return best


def track_svg(path: str | None, circuit_id: str) -> tuple[str, str] | None:
    """``(viewBox, d)`` for the circuit turned to fill the band, or None without an outline."""
    points = parse_path(path or "")
    if len(points) < 2:
        return None
    angle = best_angle(points) + (180 if circuit_id in FLIPPED else 0)
    turned = rotate(points, angle)
    xs = [x for x, _ in turned]
    ys = [y for _, y in turned]
    view_box = (
        f"{min(xs) - MARGIN:.1f} {min(ys) - MARGIN:.1f} "
        f"{max(xs) - min(xs) + 2 * MARGIN:.1f} {max(ys) - min(ys) + 2 * MARGIN:.1f}"
    )
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in turned) + " Z"
    return view_box, d
