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


def test_pick_next_race_returns_round_after_latest_result():
    # We have results through round 1 -> the next race is round 2.
    nxt = bp.pick_next_race(SCHED, asof={"season": "2026", "round": "1"})
    assert nxt["round"] == "2"


def test_pick_next_race_rolls_over_once_result_is_in():
    # The just-finished race (round 2) is now in the data -> roll over to round 3,
    # instead of clinging to round 2 until the calendar day flips. This is the bug.
    nxt = bp.pick_next_race(SCHED, asof={"season": "2026", "round": "2"})
    assert nxt["round"] == "3"


def test_pick_next_race_no_results_yet_returns_first():
    assert bp.pick_next_race(SCHED, asof=None)["round"] == "1"
    assert bp.pick_next_race(SCHED, asof={})["round"] == "1"


def test_pick_next_race_none_when_final_round_done():
    assert bp.pick_next_race(SCHED, asof={"season": "2026", "round": "3"}) is None


def test_pick_next_race_previous_season_result_returns_first():
    # Off-season: latest result is last year's finale -> next is round 1 this year.
    nxt = bp.pick_next_race(SCHED, asof={"season": "2025", "round": "24"})
    assert nxt["round"] == "1"


# --- rendering ----------------------------------------------------------------


def test_render_next_race_box_contents():
    html = bp.render_next_race(SCHED, asof={"season": "2026", "round": "1"})
    assert 'class="next-race"' in html
    assert 'data-datetime="2026-06-28T13:00:00Z"' in html
    assert "Round 2 / 3" in html
    assert "Red Bull Ring" in html and "4.318 km" in html
    assert "<svg" in html  # flag + track outline
    assert "nr-track" in html
    assert 'href="http://x"' in html  # wiki link
    assert "data-countdown" in html


def test_render_next_race_season_complete_fallback():
    html = bp.render_next_race(SCHED, asof={"season": "2026", "round": "3"})
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
    # This season's rounds have no podium yet; the latest result we hold is last
    # season's finale (2025 R22). The box should show that, not return empty.
    html = bp.render_last_race(_SCHED_LAG, _PODIUMS_LAG, [], {}, [])
    assert html != "", "should render a section, not return empty"
    assert "Abu Dhabi GP" in html
    assert 'class="last-race"' in html


def test_render_last_race_returns_empty_when_no_podiums_at_all():
    html = bp.render_last_race(_SCHED_LAG, [], [], {}, [])
    assert html == ""


def test_render_last_race_uses_latest_podium_in_current_season():
    # We have a podium for round 2 (B GP) this season -> the last-race box shows it,
    # enriched from the schedule entry (its real race name).
    podiums = [
        {
            "season": "2026",
            "round": "2",
            "raceName": "B GP",
            "p1": {"driverId": "russell", "name": "George Russell"},
            "p2": {"driverId": "verstappen", "name": "Max Verstappen"},
            "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
        }
    ]
    html = bp.render_last_race(SCHED, podiums, [], {}, [])
    assert 'class="last-race"' in html
    assert "B GP" in html


def test_render_last_race_name_links_to_schedule_url_when_present():
    # Same behavior as the next-race box: the race name should be clickable,
    # linking out to the schedule's wiki URL when the race is on this season's
    # calendar and has one.
    podiums = [
        {
            "season": "2026",
            "round": "2",
            "raceName": "B GP",
            "p1": {"driverId": "russell", "name": "George Russell"},
            "p2": {"driverId": "verstappen", "name": "Max Verstappen"},
            "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
        }
    ]
    html = bp.render_last_race(SCHED, podiums, [], {}, [])
    assert '<a class="lr-name" href="http://x"' in html


def test_render_last_race_name_links_to_constructed_wiki_url_when_off_schedule():
    # The fallback path (last race isn't on this season's schedule) has no
    # schedule "url" field -> fall back to a constructed Wikipedia URL, the
    # same trick already used for the "last time" link elsewhere in this box.
    html = bp.render_last_race(_SCHED_LAG, _PODIUMS_LAG, [], {}, [])
    assert '<a class="lr-name" href="https://en.wikipedia.org/wiki/2025_Abu_Dhabi_GP"' in html


# --- combos_link helper + last-race trio links -------------------------------


def test_combos_link_builds_prefilled_combos_url():
    url = bp.combos_link(["Max Verstappen", "Lando Norris", "Charles Leclerc"])
    assert url == "combos.html?d=Max+Verstappen&d=Lando+Norris&d=Charles+Leclerc"


_PODIUM_TRIO = {
    "season": "2026",
    "round": "2",
    "raceName": "B GP",
    "p1": {"driverId": "russell", "name": "George Russell"},
    "p2": {"driverId": "verstappen", "name": "Max Verstappen"},
    "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
}


def _combo_for_trio(count: int) -> dict:
    races = [{"season": "2026", "round": "2", "raceName": "B GP"}] * count
    return {
        "driverIds": ["antonelli", "russell", "verstappen"],
        "drivers": ["George Russell", "Max Verstappen", "Andrea Kimi Antonelli"],
        "count": count,
        "races": races,
        "lastRace": {"season": "2026", "round": "2", "raceName": "B GP"},
        "lastRaceKey": 202602,
    }


def test_render_last_race_trio_links_to_combos_page_when_combo_exists():
    # The trio exists in combos.json -> the whole trio becomes a link that
    # pre-filters the combos page to exactly that trio (drivers in podium order).
    html = bp.render_last_race(SCHED, [_PODIUM_TRIO], [_combo_for_trio(3)], {}, [])
    assert 'class="combo-link"' in html
    assert "combos.html?d=George+Russell" in html
    assert "d=Max+Verstappen" in html
    assert "d=Andrea+Kimi+Antonelli" in html
    # the link wraps the trio (codes live inside the anchor)
    anchor = html.split('class="combo-link"', 1)[1]
    assert "lr-trio" in anchor.split("</a>", 1)[0]


def test_render_last_race_trio_links_even_for_brand_new_podigami():
    # A brand-new trio (count == 1) has still happened -> still linkable.
    html = bp.render_last_race(SCHED, [_PODIUM_TRIO], [_combo_for_trio(1)], {}, [])
    assert "lr-podigami" in html  # status still says PODIGAMI
    assert 'class="combo-link"' in html
    assert "combos.html?d=George+Russell" in html


def test_render_last_race_trio_not_linked_when_combo_missing():
    # No matching combo in the data -> no link (nothing to point at).
    html = bp.render_last_race(SCHED, [_PODIUM_TRIO], [], {}, [])
    assert 'class="combo-link"' not in html
    assert "combos.html?d=" not in html
