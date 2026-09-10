"""Unit tests for the landing page's pure render helpers (no IO)."""

from build import build_podigami_html as bp

TEAM_NAMES = {"mercedes": "Mercedes", "mclaren": "McLaren", "ferrari": "Ferrari"}


def pd(driver_id, name, cid, season_podiums=2):
    return {
        "driverId": driver_id,
        "name": name,
        "constructorId": cid,
        # compute writes the display name alongside the id; the hero labels each
        # driver with it, so the fixture has to carry it too
        "constructor": TEAM_NAMES.get(cid, ""),
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


def test_ordinal_covers_the_teens_and_the_suffix_cycle():
    assert [bp._ordinal(n) for n in (1, 2, 3, 4)] == ["1st", "2nd", "3rd", "4th"]
    assert [bp._ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]
    assert [bp._ordinal(n) for n in (21, 22, 23)] == ["21st", "22nd", "23rd"]


def test_render_hero_carries_the_team_colour():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert "--team:" in out
    assert "55%" in out


def test_render_hero_head_pairs_the_number_with_its_sentence():
    """Number and sentence are one row: the figure sits beside a single text
    block holding the label and the movement line, so they centre against each
    other instead of the figure hanging off the label's first baseline."""
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert 'class="hero-head"' in out
    assert 'class="hero-head-text"' in out
    assert 'class="hc-num">55%' in out
    assert 'class="hc-label"' in out


def test_render_hero_names_the_race_when_given():
    out = bp.render_hero(_hero_top(), 55.0, META, race_name="Italian Grand Prix")
    assert "Italian Grand Prix" in out


def test_render_hero_label_falls_back_without_a_race_name():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert "next race" in out
    assert "Grand Prix" not in out


def test_render_hero_driver_shows_full_name_and_team():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert 'class="hd-name">George Russell' in out
    assert "Mercedes" in out
    # the broadcast chips are gone: no number chip, no TLA block
    assert "hd-id" not in out


def test_render_hero_bills_antonelli_as_kimi():
    """The API lists him as "Andrea Kimi Antonelli"; F1 calls him Kimi Antonelli."""
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert 'class="hd-name">Kimi Antonelli' in out
    assert "Andrea" not in out


def test_render_hero_driver_names_the_grid_slot_after_qualifying():
    top = {
        "prob": 3.5,
        "perDriver": [
            {**pd("russell", "George Russell", "mercedes", 3), "gridPosition": 2},
            {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes", 6), "gridPosition": 21},
            {**pd("norris", "Lando Norris", "mclaren", 2), "gridPosition": 3},
        ],
    }
    out = bp.render_hero(top, 55.0, META, pre_chance=60.0)
    assert "starts 2nd" in out
    assert "starts 3rd" in out
    assert "starts 21st" in out


def test_render_hero_drivers_are_ordered_by_grid_slot():
    """Post-qualifying the trio reads front-to-back, so the row matches the grid
    a reader is looking at rather than the model's internal order."""
    top = {
        "prob": 3.5,
        "perDriver": [
            {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes", 6), "gridPosition": 21},
            {**pd("russell", "George Russell", "mercedes", 3), "gridPosition": 2},
            {**pd("norris", "Lando Norris", "mclaren", 2), "gridPosition": 3},
        ],
    }
    out = bp.render_hero(top, 55.0, META, pre_chance=60.0)
    assert out.index("Russell") < out.index("Norris") < out.index("Antonelli")


def test_render_hero_driver_omits_the_grid_slot_before_qualifying():
    out = bp.render_hero(_hero_top(), 55.0, META)
    assert "starts" not in out


def test_render_hero_pick_label_carries_the_trio_probability():
    """The trio's own probability belongs on the label that introduces it, not
    in a second footnote below the drivers."""
    import re

    out = bp.render_hero(_hero_top(), 55.0, META)
    label = re.search(r'<p class="hp-label">(.*?)</p>', out)
    assert label, "hero must introduce the trio with an hp-label paragraph"
    assert "3.5%" in label.group(1)


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
    assert 'title="Kimi ANTONELLI"' in out  # broadcast full name, as F1 bills him
    assert "Andrea" not in out
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


def test_accuracy_note_states_the_hit_rate_in_plain_words():
    """The backtest result reads as a sentence, not a tracked-out pill — it was
    the last piece of shouting left in an otherwise quiet block."""
    out = bp.render_accuracy_note(EVAL)
    assert "30% of the time" in out
    assert "top three" in out
    assert out.isupper() is False
    assert bp.render_accuracy_note({}) == ""


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
    # Qualifying shares the race's line, and its datetime is exposed so the
    # client can localise it instead of leaving it stranded in UTC.
    out = bp.render_next_race(SCHED_ONE, {"season": "2026", "round": "9"})
    when = out.split('class="nr-date"', 1)[1].split("</span>", 1)[0]
    assert "Quali" in when
    assert "Sat 18 Jul" in when and "14:00 UTC" in when
    assert 'data-quali-datetime="2026-07-18T14:00:00Z"' in out


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
    assert "data-quali-datetime" not in out
    when = out.split('class="nr-date"', 1)[1].split("</span>", 1)[0]
    assert "Quali" not in when


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
    assert "hc-delta-flat" in flat
    # the movement is a plain sentence now, so no arrow glyph rides in front of it
    assert "&#8593;" not in flat and "&#8595;" not in flat


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


def test_faq_items_matches_rendered_faq():
    pairs = bp.faq_items({}, {}, 123, 456, 789, 20, 1950)
    html_out = bp.render_faq({}, {}, 123, 456, 789, 20, 1950)
    # Every question produced by faq_items is rendered verbatim as a <summary>.
    for q, _a in pairs:
        assert f'<summary class="faq-q">{q}</summary>' in html_out
    assert len(pairs) >= 5


# --- stale postQuali guard --------------------------------------------------------


def _pq_data(as_of_round, pq_round, pq_season="2026"):
    return {
        "asOf": {"season": "2026", "round": as_of_round, "raceName": "Hungarian Grand Prix"},
        "postQuali": {"season": pq_season, "round": pq_round, "chanceNextRaceNew": 43.5},
    }


def test_live_post_quali_kept_when_it_leads_the_last_race():
    data = _pq_data("10", "11")
    assert bp.live_post_quali(data) == data["postQuali"]


def test_live_post_quali_dropped_once_that_race_has_run():
    """The grid-aware block is for the *upcoming* race; once asOf reaches that
    round the race is over and its post-quali chance must not stay on the hero."""
    assert bp.live_post_quali(_pq_data("11", "11")) is None


def test_live_post_quali_dropped_when_older_than_the_last_race():
    assert bp.live_post_quali(_pq_data("11", "9")) is None


def test_live_post_quali_none_when_absent():
    assert bp.live_post_quali({"asOf": {"season": "2026", "round": "11"}}) is None
    assert (
        bp.live_post_quali({"asOf": {"season": "2026", "round": "11"}, "postQuali": None}) is None
    )


def test_live_post_quali_kept_across_a_season_rollover():
    """Round numbers restart each season, so the comparison must be numeric on
    (season, round) — not on round alone, which would drop a valid R1 block."""
    data = {
        "asOf": {"season": "2026", "round": "22"},
        "postQuali": {"season": "2027", "round": "1", "chanceNextRaceNew": 40.0},
    }
    assert bp.live_post_quali(data) == data["postQuali"]


def test_live_post_quali_dropped_when_rounds_are_unreadable():
    """Garbage beats a wrong hero: an unparseable block falls back to pre-quali."""
    bad = {"asOf": {"season": "2026", "round": "11"}, "postQuali": {"season": "?", "round": "?"}}
    assert bp.live_post_quali(bad) is None


def test_last_race_step_renders_both_drivers_of_a_shared_car():
    """Dormant today (the last race is always modern) but must not silently
    drop a driver if a podium step is ever shared again."""
    from build.build_podigami_html import render_last_race_drivers

    pod = {
        "p1": {"driverId": "collins", "name": "Peter Collins"},
        "p2": {"driverId": "frere", "name": "Paul Frère"},
        "p3": {"driverId": "perdisa", "name": "Cesare Perdisa"},
        "coDrivers": {"p3": [{"driverId": "moss", "name": "Stirling Moss"}]},
    }
    out = render_last_race_drivers(pod, {}, {})
    assert out.count("lr-driver") == 4
    assert "lr-shared" in out


def test_last_race_step_is_unchanged_for_a_normal_podium():
    from build.build_podigami_html import render_last_race_drivers

    pod = {
        "p1": {"driverId": "hamilton", "name": "Lewis Hamilton"},
        "p2": {"driverId": "max_verstappen", "name": "Max Verstappen"},
        "p3": {"driverId": "bottas", "name": "Valtteri Bottas"},
    }
    out = render_last_race_drivers(pod, {}, {})
    assert out.count("lr-driver") == 3
    assert "lr-shared" not in out


# ── trio board ───────────────────────────────────────────────────────────────
# The panel merges already-happened trios in beside the new ones so a visitor
# can tell "this already happened" from "the model rates this too low to list".

BOARD_FORM = [
    pd("antonelli", "Andrea Kimi Antonelli", "mercedes"),
    pd("norris", "Lando Norris", "mclaren"),
    pd("russell", "George Russell", "mercedes"),
    pd("piastri", "Oscar Piastri", "mclaren"),
]

BOARD_COMBOS = [
    {
        "driverIds": ["antonelli", "norris", "russell"],
        "drivers": ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
        "count": 3,
        "lastRace": {"season": "2026", "round": "12", "raceName": "Dutch Grand Prix"},
    }
]


def _board():
    return [
        {"driverIds": ["antonelli", "norris", "russell"], "prob": 6.23, "happened": True},
        {"driverIds": ["antonelli", "piastri", "russell"], "prob": 3.82, "happened": False},
    ]


def _render_board(**kw):
    kw.setdefault("board", _board())
    kw.setdefault("driver_form", BOARD_FORM)
    kw.setdefault("combos", BOARD_COMBOS)
    return bp.render_candidates(_grid_cands(), META, **kw)


def test_board_renders_happened_and_new_rows():
    out = _render_board()
    assert out.count('class="cand cand-done"') == 1
    assert out.count('class="cand cand-new"') == 1
    assert "ANT" in out and "PIA" in out


def test_board_row_order_follows_the_data():
    out = _render_board()
    assert out.index("cand-done") < out.index("cand-new")


def test_board_marks_new_rows_with_a_pill():
    out = _render_board()
    assert out.count("cand-pill") == 1  # only the never-happened row


def test_board_done_row_carries_history_and_combos_link():
    out = _render_board()
    assert "3 times" in out
    assert "Dutch Grand Prix" in out
    assert "combos.html?d=" in out
    # the link filters the combos table, which lists him as Kimi Antonelli
    assert "d=Kimi+Antonelli" in out


def test_board_new_row_has_no_bubble():
    board = [{"driverIds": ["antonelli", "piastri", "russell"], "prob": 3.82, "happened": False}]
    out = _render_board(board=board)
    assert "trio-bubble" not in out
    assert "trio-tip" not in out


def test_board_done_row_without_combos_match_degrades():
    """combos.json and podiums.json are derived from the same source, so a miss
    means upstream drift — render the row plainly rather than break the build."""
    out = _render_board(combos=[])
    assert "cand-done" in out
    assert "trio-bubble" not in out


def test_board_resolves_display_from_driver_form():
    out = _render_board()
    assert 'title="Oscar PIASTRI"' in out  # name came from driverForm, not the board row
    assert "--team:" in out


def test_board_survives_driver_missing_from_form():
    out = _render_board(driver_form=[])
    assert "cand-done" in out and "cand-new" in out


def test_board_shows_grid_positions_when_grid_aware():
    out = _render_board(grid_aware=True)
    form = [{**d, "gridPosition": i + 1} for i, d in enumerate(BOARD_FORM)]
    out = _render_board(grid_aware=True, driver_form=form)
    assert "cd-grid" in out and ">P1<" in out


def test_board_uses_scroll_window():
    out = _render_board()
    assert "cand-scroll" in out


def test_empty_board_falls_back_to_candidate_list():
    """The live site can run on a podigami.json written before the board existed
    (see the schema note on trioBoard) — that must render today's new-only list."""
    out = _render_board(board=[])
    assert "cand-done" not in out and "cand-pill" not in out
    assert 'class="cand"' in out
    assert "cand-bar" in out


def test_panel_title_is_no_longer_new_only():
    out = _render_board()
    assert "Most likely trios" in out
    assert "Most likely new trios" not in out
