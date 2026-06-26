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


def test_accuracy_badge_shows_top3():
    out = bp.render_accuracy_badge(EVAL)
    assert "top-3 30%" in out
    assert "Backtested" in out
    assert bp.render_accuracy_badge({}) == ""


def test_faq_section_has_questions_and_uses_eval():
    out = bp.render_faq({}, EVAL)
    assert "Frequently asked questions" in out
    assert out.count('class="faq-item"') >= 4
    assert "<summary" in out  # expandable details/summary
    assert "Plackett" in out  # explains the model
    assert "30%" in out  # accuracy figure pulled from EVAL


def test_faq_section_works_without_eval():
    out = bp.render_faq({}, {})
    assert "Frequently asked questions" in out
    assert out.count('class="faq-item"') >= 4


def test_render_form_builds_timing_tower():
    form = [
        {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), "weight": 12.2},
        {**pd("norris", "Lando Norris", "mclaren"), "weight": 8.6},
        # zero-weight driver is filtered out of the tower
        {**pd("zzz", "Zed Zero", ""), "weight": 0.0},
    ]
    out = bp.render_form(form, True, META, half_life=6.0)
    assert out.count('class="tower-row"') == 2
    assert "tr-num" in out and "tr-bar" in out
    assert 'class="tr-code">ANT' in out
    assert "constructor strength" in out  # using_constructors=True extends the sub
    assert "~6 races" in out
    assert "~8 races" not in out


def test_render_form_half_life_default_is_six():
    form = [{**pd("norris", "Lando Norris", "mclaren"), "weight": 5.0}]
    out = bp.render_form(form, False, META)
    assert "~6 races" in out
    assert "~8 races" not in out


def test_faq_fallback_half_life_is_six():
    out = bp.render_faq({}, {})
    assert "~6 races" in out
    assert "~8 races" not in out
