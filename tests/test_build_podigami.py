"""Unit tests for the landing page's pure render helpers (no IO)."""

from build import build_podigami_html as bp


def pd(driver_id, name, cid, season_podiums=2):
    return {
        "driverId": driver_id,
        "name": name,
        "constructorId": cid,
        "seasonPodiums": season_podiums,
        "weight": 5.0,
    }


META = {
    "antonelli": {"code": "ANT", "number": "12"},
    "norris": {"code": "NOR", "number": "1"},
    "russell": {"code": "RUS", "number": "63"},
}


def test_driver_view_enriches_with_code_number_colour():
    v = bp.driver_view(pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), META)
    assert v["code"] == "ANT"
    assert v["number"] == "12"
    assert v["surname"] == "Antonelli"
    assert v["color"].startswith("#")
    assert v["ink"] in ("#0b0d12", "#ffffff")


def test_driver_view_falls_back_without_meta_or_team():
    v = bp.driver_view({"driverId": "x", "name": "Foo Barberini", "constructorId": ""}, {})
    assert v["code"] == "BAR"  # surname[:3].upper()
    assert v["number"] is None
    assert v["color"].startswith("#")  # neutral fallback


def test_num_chip_present_and_absent():
    with_num = bp.driver_view(pd("norris", "Lando Norris", "mclaren"), META)
    no_num = bp.driver_view({"driverId": "z", "name": "Zoe Zephyr", "constructorId": ""}, {})
    assert bp._num_chip(with_num) != ""
    assert bp._num_chip(no_num) == ""


def test_render_hero_has_chip_code_surname_and_team_var():
    top = {
        "prob": 3.5,
        "perDriver": [
            pd("antonelli", "Andrea Kimi Antonelli", "mercedes", 6),
            pd("norris", "Lando Norris", "mclaren", 2),
            pd("russell", "George Russell", "mercedes", 3),
        ],
    }
    out = bp.render_hero(top, 55.0, META)
    assert "--team:" in out
    assert 'class="d-code">ANT' in out
    assert "Antonelli" in out  # surname only in the hero
    assert "55%" in out


def test_render_candidates_dots_and_broadcast_tooltip():
    cands = [
        {
            "prob": 3.0,
            "names": ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
            "perDriver": [
                pd("antonelli", "Andrea Kimi Antonelli", "mercedes"),
                pd("norris", "Lando Norris", "mclaren"),
                pd("russell", "George Russell", "mercedes"),
            ],
        }
    ]
    out = bp.render_candidates(cands, META)
    assert 'class="cd"' in out
    assert 'title="Andrea Kimi ANTONELLI"' in out  # broadcast full name
    assert "cand-bar" in out


def test_render_candidates_empty_is_blank():
    assert bp.render_candidates([], META) == ""


def test_render_form_builds_timing_tower():
    form = [
        {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), "weight": 12.2},
        {**pd("norris", "Lando Norris", "mclaren"), "weight": 8.6},
        # zero-weight driver is filtered out of the tower
        {**pd("zzz", "Zed Zero", ""), "weight": 0.0},
    ]
    out = bp.render_form(form, True, META)
    assert out.count('class="tower-row"') == 2
    assert "tr-num" in out and "tr-bar" in out
    assert 'class="tr-code">ANT' in out
    assert "constructor strength" in out  # using_constructors=True extends the sub
