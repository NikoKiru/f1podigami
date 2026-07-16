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


def test_render_candidates_embeds_form_block_after_list():
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
    form_html = '<details class="form-details">FORM</details>'
    out = bp.render_candidates(cands, META, form_html)
    assert form_html in out
    assert out.index('class="cand-list"') < out.index(form_html)  # after the ranked list
    assert out.rstrip().endswith("</section>")  # inside the panel
    # default keeps the old signature working
    assert "form-details" not in bp.render_candidates(cands, META)


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
    out = bp.render_faq({}, EVAL, 123, 456, 789, 20, 1950)
    assert "Frequently asked questions" in out
    assert out.count('class="faq-item"') >= 4
    assert "<summary" in out  # expandable details/summary
    assert "Plackett" in out  # explains the model
    assert "30%" in out  # accuracy figure pulled from EVAL


def test_faq_section_works_without_eval():
    out = bp.render_faq({}, {}, 123, 456, 789, 20, 1950)
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
    # collapsed <details> block, not a standalone panel
    assert out.startswith('<details class="form-details">')
    assert "<section" not in out
    assert "Show current form" in out and "Hide current form" in out
    assert " open>" not in out  # collapsed by default


def test_render_form_half_life_default_is_six():
    form = [{**pd("norris", "Lando Norris", "mclaren"), "weight": 5.0}]
    out = bp.render_form(form, False, META)
    assert "~6 races" in out
    assert "~8 races" not in out


def test_faq_fallback_half_life_is_six():
    out = bp.render_faq({}, {}, 123, 456, 789, 20, 1950)
    assert "~6 races" in out
    assert "~8 races" not in out


def test_quickpicks_first_record_current():
    out = bp._quickpicks(1950, 2026, {"1950": 3, "1982": 17, "2026": 5})
    assert 'data-year="1950"' in out and "first season" in out
    assert 'data-year="1982"' in out and "17 new" in out
    assert 'data-year="2026"' in out and "this season" in out


def test_quickpicks_record_tie_prefers_earliest_and_dedupes():
    # tie between 1950 and 1982 -> earliest (1950) wins; 1950 is already the
    # "first season" chip, so no separate record chip is emitted
    out = bp._quickpicks(1950, 2026, {"1950": 17, "1982": 17})
    assert out.count('data-year="1950"') == 1
    assert 'data-year="1982"' not in out


def test_quickpicks_empty_counts_and_single_season():
    out = bp._quickpicks(2026, 2026, {})
    assert out.count('class="tl-chip"') == 1  # just the first-season chip


V2_DATA = {"params": {"model": "dbpl-v2", "w_qual": 0.6}}


def test_faq_explains_v2_engine_when_active():
    out = bp.render_faq(V2_DATA, EVAL, 123, 456, 789, 20, 1950)
    assert "rating" in out.lower()  # explains the rating engine...
    assert "Plackett" in out  # ...and still names the aggregation model
    assert "reliability" in out.lower()  # DNF risk is part of the story
    assert "halved every" not in out  # v1 recency copy must be gone


def test_render_form_v2_caption_describes_ratings():
    form = [{**pd("norris", "Lando Norris", "mclaren"), "weight": 5.0}]
    out = bp.render_form(form, True, META, is_v2=True)
    assert "rating" in out.lower()
    assert "~6 races" not in out


SCHED_ONE = {
    "season": "2026",
    "totalRounds": 16,
    "races": [
        {
            "round": "10",
            "raceName": "Belgian Grand Prix",
            "date": "2026-07-19",
            "time": "13:00:00Z",
            "qualifyingDate": "2026-07-18",
            "qualifyingTime": "14:00:00Z",
            "circuitId": "spa",
            "circuitName": "Spa-Francorchamps",
            "locality": "Spa",
            "country": "Belgium",
            "lat": "50",
            "long": "5",
            "url": "",
            "trackPath": "",
            "trackViewBox": "0 0 100 100",
            "lengthKm": 7.004,
        }
    ],
}


def test_next_race_shows_quali_session():
    out = bp.render_next_race(SCHED_ONE, {"season": "2026", "round": "9"})
    assert 'class="nr-quali"' in out
    assert "Qualifying:" in out
    assert "Sat 18 Jul" in out and "14:00 UTC" in out


def test_next_race_without_quali_fields_has_no_line():
    sched = {
        "season": "2026",
        "totalRounds": 16,
        "races": [
            {
                k: v
                for k, v in SCHED_ONE["races"][0].items()
                if k not in ("qualifyingDate", "qualifyingTime")
            }
        ],
    }
    out = bp.render_next_race(sched, {"season": "2026", "round": "9"})
    assert "nr-quali" not in out


def _hero_top():
    return {
        "prob": 3.5,
        "perDriver": [
            pd("antonelli", "Andrea Kimi Antonelli", "mercedes", 6),
            pd("norris", "Lando Norris", "mclaren", 2),
            pd("russell", "George Russell", "mercedes", 3),
        ],
    }


def test_render_hero_post_quali_badge_and_delta_up():
    out = bp.render_hero(_hero_top(), 71.0, META, pre_chance=52.0)
    assert "hc-updated" in out and "Updated after qualifying" in out
    assert "hc-delta-up" in out and "was 52%" in out and "before the grid was set" in out
    assert "71%" in out


def test_render_hero_delta_down_and_flat():
    down = bp.render_hero(_hero_top(), 40.0, META, pre_chance=52.0)
    assert "hc-delta-down" in down
    flat = bp.render_hero(_hero_top(), 52.4, META, pre_chance=52.0)  # both round to 52
    assert "hc-delta-flat" in flat and "&mdash;" in flat


def test_render_hero_default_has_no_post_quali_markup():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert "hc-updated" not in out and "hc-delta" not in out


def _grid_cands():
    return [
        {
            "prob": 3.0,
            "names": ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
            "perDriver": [
                {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), "gridPosition": 3},
                {**pd("norris", "Lando Norris", "mclaren"), "gridPosition": 1},
                {**pd("russell", "George Russell", "mercedes"), "gridPosition": 7},
            ],
        }
    ]


def test_render_candidates_grid_aware_badge_and_chips():
    out = bp.render_candidates(_grid_cands(), META, grid_aware=True)
    assert "panel-badge" in out and "grid-aware" in out
    assert out.count('class="cd-grid"') == 3
    assert ">P1<" in out and ">P3<" in out and ">P7<" in out


def test_render_candidates_default_has_no_grid_markup():
    cands = _grid_cands()
    for p in cands[0]["perDriver"]:
        p.pop("gridPosition")
    out = bp.render_candidates(cands, META)
    assert "panel-badge" not in out and "cd-grid" not in out


EVAL_WITH_POSTQUALI = {
    **EVAL,
    "ladder": EVAL["ladder"]
    + [
        {
            "model": "v2 post-quali (ratings)",
            "n": 159,
            "top1": 0.14,
            "top3": 0.31,
            "top5": 0.43,
            "logLoss": 4.05,
        },
        {
            "model": "v2 post-quali +grid",
            "n": 159,
            "top1": 0.15,
            "top3": 0.33,
            "top5": 0.45,
            "logLoss": 4.01,
        },
    ],
}


def test_faq_post_quali_item_present_for_v2_and_cites_rung():
    out = bp.render_faq(V2_DATA, EVAL_WITH_POSTQUALI, 123, 456, 789, 20, 1950)
    assert "after qualifying" in out
    assert "33%" in out  # cites the "v2 post-quali +grid" rung's top3


def test_faq_post_quali_item_absent_for_v1():
    out = bp.render_faq({}, EVAL, 123, 456, 789, 20, 1950)
    assert "after qualifying" not in out


def test_faq_post_quali_item_tolerates_missing_rung():
    out = bp.render_faq(V2_DATA, EVAL, 123, 456, 789, 20, 1950)  # old eval, no rung
    assert "after qualifying" in out  # item still there, just uncited
