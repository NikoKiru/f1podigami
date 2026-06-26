"""Tests for the next-race box: geo→SVG, flags, race picker, and rendering."""

from build import build_podigami_html as bp
from build import flags
from fetch import track_geo

# --- geo helpers --------------------------------------------------------------

SQUARE = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]


def test_geo_to_svg_path_stays_in_viewbox():
    path = track_geo.geo_to_svg_path(SQUARE, width=120, height=72, pad=6)
    assert path.startswith("M") and path.endswith(" Z")
    coords = [
        float(tok)
        for seg in path[1:-2].replace("L", " ").split()
        for tok in [seg]
        if tok.replace(".", "", 1).isdigit()
    ]
    xs, ys = coords[0::2], coords[1::2]
    assert min(xs) >= 0 and max(xs) <= 120
    assert min(ys) >= 0 and max(ys) <= 72


def test_geo_to_svg_path_empty_is_blank():
    assert track_geo.geo_to_svg_path([]) == ""


def test_nearest_circuit_picks_closest():
    feats = [
        {"geometry": {"type": "LineString", "coordinates": [[0, 0], [0, 1], [1, 1]]}, "id": "a"},
        {"geometry": {"type": "LineString", "coordinates": [[50, 50], [50, 51]]}, "id": "b"},
    ]
    near = track_geo.nearest_circuit(0.3, 0.3, feats)
    assert near["id"] == "a"


# --- flags --------------------------------------------------------------------


def test_flag_svg_returns_markup_for_known_country():
    out = flags.flag_svg("Austria")
    assert out.startswith("<svg") and 'class="nr-flag"' in out


def test_flag_svg_blank_for_unknown_country():
    assert flags.flag_svg("Atlantis") == ""


# --- race picker --------------------------------------------------------------

SCHED = {
    "season": "2026",
    "totalRounds": 3,
    "races": [
        {
            "round": "1",
            "raceName": "A GP",
            "date": "2026-03-01",
            "country": "Austria",
            "circuitName": "X",
            "locality": "L",
            "url": "",
            "time": "13:00:00Z",
            "trackPath": "M0 0 L1 1 Z",
            "trackViewBox": "0 0 120 72",
            "lengthKm": 5.0,
        },
        {
            "round": "2",
            "raceName": "B GP",
            "date": "2026-06-28",
            "country": "Austria",
            "circuitName": "Red Bull Ring",
            "locality": "Spielberg",
            "url": "http://x",
            "time": "13:00:00Z",
            "trackPath": "M0 0 L1 1 Z",
            "trackViewBox": "0 0 120 72",
            "lengthKm": 4.318,
        },
        {
            "round": "3",
            "raceName": "C GP",
            "date": "2026-09-01",
            "country": "Italy",
            "circuitName": "Z",
            "locality": "M",
            "url": "",
            "time": "",
            "trackPath": "",
            "trackViewBox": "0 0 120 72",
            "lengthKm": None,
        },
    ],
}


def test_pick_next_race_returns_first_upcoming():
    nxt = bp.pick_next_race(SCHED, today="2026-04-01")
    assert nxt["round"] == "2"


def test_pick_next_race_on_race_day_picks_that_race():
    nxt = bp.pick_next_race(SCHED, today="2026-06-28")
    assert nxt["round"] == "2"


def test_pick_next_race_none_after_season():
    assert bp.pick_next_race(SCHED, today="2026-12-01") is None


# --- rendering ----------------------------------------------------------------


def test_render_next_race_box_contents():
    html = bp.render_next_race(SCHED, today="2026-04-01")
    assert 'class="next-race"' in html
    assert 'data-datetime="2026-06-28T13:00:00Z"' in html
    assert "Round 2 / 3" in html
    assert "Red Bull Ring" in html and "4.318 km" in html
    assert "<svg" in html  # flag + track outline
    assert "nr-track" in html
    assert 'href="http://x"' in html  # wiki link
    assert "data-countdown" in html


def test_render_next_race_season_complete_fallback():
    html = bp.render_next_race(SCHED, today="2027-01-01")
    assert "Season complete" in html


# --- render_last_race fallback -----------------------------------------------

_SCHED_LAG = {
    "season": "2026",
    "totalRounds": 2,
    "races": [
        {
            "round": "1",
            "raceName": "Bahrain GP",
            "date": "2026-03-01",
            "country": "Bahrain",
            "circuitName": "Bahrain International Circuit",
            "locality": "Sakhir",
            "url": "",
            "time": "15:00:00Z",
            "trackPath": "",
            "trackViewBox": "0 0 120 72",
            "lengthKm": None,
        },
        {
            "round": "2",
            "raceName": "Saudi GP",
            "date": "2026-12-01",
            "country": "Saudi Arabia",
            "circuitName": "Jeddah Corniche Circuit",
            "locality": "Jeddah",
            "url": "",
            "time": "",
            "trackPath": "",
            "trackViewBox": "0 0 120 72",
            "lengthKm": None,
        },
    ],
}

_PODIUMS_LAG = [
    {
        "season": "2025",
        "round": "22",
        "raceName": "Abu Dhabi GP",
        "p1": {"driverId": "norris", "name": "Lando Norris"},
        "p2": {"driverId": "russell", "name": "George Russell"},
        "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
    }
]


def test_render_last_race_falls_back_when_scheduled_round_has_no_podium():
    # Round 1 is in the past (today=2026-04-01) but has no podium yet.
    # Should fall back to the most recent podium in the dataset (2025 R22).
    html = bp.render_last_race(_SCHED_LAG, _PODIUMS_LAG, [], {}, [], today="2026-04-01")
    assert html != "", "should render a section, not return empty"
    assert "Abu Dhabi GP" in html
    assert 'class="last-race"' in html


def test_render_last_race_returns_empty_when_no_podiums_at_all():
    html = bp.render_last_race(_SCHED_LAG, [], [], {}, [], today="2026-04-01")
    assert html == ""
