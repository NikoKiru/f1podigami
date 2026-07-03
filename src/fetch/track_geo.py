"""Pure helpers to turn open circuit geo-data into an inline SVG outline.

The schedule fetcher matches each race's circuit (by nearest coordinates, so no
brittle id table) to a LineString in the bundled f1-circuits dataset, then
normalises that LineString into a compact SVG path drawn in a fixed viewBox.

No IO and no third-party deps so it is trivially unit-testable.
"""

from __future__ import annotations

VIEW_W = 120
VIEW_H = 72
PAD = 6

# Max centroid distance (degrees) for a circuit to count as "the same circuit".
# Every legitimate match in the current dataset is within ~0.013 deg (~1.4 km);
# beyond this, the race is at a circuit the geojson doesn't have yet, and it is
# better to draw no outline than the wrong track's.
MAX_MATCH_DEG = 0.05


def circuit_centroid(coords: list[list[float]]) -> tuple[float, float]:
    """Return (lat, lon) centroid of a LineString of [lon, lat] points."""
    n = len(coords) or 1
    lon = sum(c[0] for c in coords) / n
    lat = sum(c[1] for c in coords) / n
    return lat, lon


def nearest_circuit(
    lat: float, lon: float, features: list[dict], max_deg: float = MAX_MATCH_DEG
) -> dict | None:
    """Pick the geojson feature whose centroid is closest to (lat, lon).

    Returns ``None`` when no centroid is within ``max_deg`` degrees — a race at a
    circuit the dataset doesn't cover must not borrow another track's outline.
    """
    best = None
    best_d = None
    for f in features:
        geom = f.get("geometry", {})
        if geom.get("type") != "LineString":
            continue
        clat, clon = circuit_centroid(geom["coordinates"])
        d = (clat - lat) ** 2 + (clon - lon) ** 2
        if best_d is None or d < best_d:
            best, best_d = f, d
    if best_d is not None and best_d > max_deg**2:
        return None
    return best


def geo_to_svg_path(
    coords: list[list[float]], width: int = VIEW_W, height: int = VIEW_H, pad: int = PAD
) -> str:
    """Normalise [lon, lat] points into an SVG path string within the viewBox.

    Preserves aspect ratio, centres the shape, flips latitude (north = up), and
    closes the loop. Returns "" for empty input.
    """
    if not coords:
        return ""
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span_x = (maxx - minx) or 1e-9
    span_y = (maxy - miny) or 1e-9

    avail_w = width - 2 * pad
    avail_h = height - 2 * pad
    scale = min(avail_w / span_x, avail_h / span_y)

    off_x = pad + (avail_w - span_x * scale) / 2
    off_y = pad + (avail_h - span_y * scale) / 2

    pts = []
    for lon, lat in coords:
        x = off_x + (lon - minx) * scale
        y = off_y + (maxy - lat) * scale  # flip: higher latitude -> smaller y
        pts.append(f"{x:.1f} {y:.1f}")

    return "M" + " L".join(pts) + " Z"
