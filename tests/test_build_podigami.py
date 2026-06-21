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


EVAL = {
    "evalWindow": {"validation": [2010, 2018], "test": [2019, 2026]},
    "modelParams": {
        "halfLife": 6.0,
        "offSeason": 0.5,
        "seasonBoost": 0.2,
        "posWeights": [1.0, 0.85, 0.72],
        "temperature": 1.0,
    },
    "ladder": [
        {
            "model": "recent-frequency",
            "n": 159,
            "top1": 0.13,
            "top3": 0.27,
            "top5": 0.37,
            "logLoss": 4.31,
        },
        {
            "model": "current (product)",
            "n": 159,
            "top1": 0.13,
            "top3": 0.28,
            "top5": 0.40,
            "logLoss": 4.20,
        },
        {
            "model": "PL + tuned (chosen)",
            "n": 159,
            "top1": 0.13,
            "top3": 0.30,
            "top5": 0.42,
            "logLoss": 4.08,
        },
    ],
    "chosen": {
        "n": 159,
        "top1": 0.126,
        "top3": 0.296,
        "top5": 0.415,
        "logLoss": 4.081,
        "brierNew": 0.239,
        "baseRateNew": 0.409,
        "brierNewBaseRate": 0.242,
        "ece": 0.086,
    },
    "calibration": [
        {"lo": 0.3, "hi": 0.4, "n": 20, "meanPred": 0.35, "obsRate": 0.40},
        {"lo": 0.4, "hi": 0.5, "n": 0, "meanPred": None, "obsRate": None},
    ],
}


def test_accuracy_badge_shows_top3_and_links():
    out = bp.render_accuracy_badge(EVAL)
    assert 'href="#model-accuracy"' in out
    assert "top-3 30%" in out
    assert bp.render_accuracy_badge({}) == ""


def test_accuracy_section_has_table_chart_and_caveats():
    out = bp.render_accuracy(EVAL)
    assert 'id="model-accuracy"' in out
    assert 'class="acc-table"' in out
    assert 'class="acc-chosen"' in out  # the chosen row is highlighted
    assert "acc-rel" in out  # reliability chart
    assert "What it can" in out  # honest limitations note
    assert "2019" in out and "2026" in out  # test window disclosed
    assert bp.render_accuracy({}) == ""


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
