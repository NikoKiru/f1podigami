"""The scorecard page's render helpers: it has to report the numbers honestly,
whichever way they fall."""

from build import build_scorecard_html as bs
from datalib import ScorecardNext, ScorecardTotals, ScoredRace


def race(**kw):
    base = {
        "season": "2026",
        "round": "12",
        "raceName": "Dutch Grand Prix",
        "stage": "post-quali",
        "model": "dbpl-v2",
        "podium": ["Lando Norris", "Oscar Piastri", "Max Verstappen"],
        "isNew": False,
        "chanceNew": 47.4,
        "topPick": ["Lando Norris", "Oscar Piastri", "Charles Leclerc"],
        "topPickProb": 11.9,
        "topPickHit": False,
        "driversRight": 2,
        "boardSize": 0,
    }
    return ScoredRace(**{**base, **kw})


def totals(**kw):
    base = {
        "races": 11,
        "newTrios": 4,
        "meanChanceNew": 40.5,
        "brierNew": 0.217,
        "baselineBrierNew": 0.25,
        "baseRateNew": 38.0,
        "topPickHits": 2,
        "topPickExpected": 0.65,
        "meanDriversRight": 1.82,
        "boardRaces": 5,
        "onBoard": 5,
        "boardTopThree": 3,
    }
    return ScorecardTotals(**{**base, **kw})


# ── What the site gave the trio ─────────────────────────────────────────────


def test_odds_show_the_published_probability():
    assert (
        bs.format_odds(race(podiumProb=6.04, boardSize=25, boardRank=4, boardFloor=1.2)) == "6.0%"
    )


def test_a_trio_off_the_board_is_described_as_under_it():
    assert bs.format_odds(race(boardSize=25, boardFloor=1.2)) == "under 1.2%"


def test_a_repeat_from_before_the_board_shows_a_dash():
    """Only new trios were ranked then, so there's no number to report."""
    assert bs.format_odds(race()) == "&mdash;"


# ── Rows ────────────────────────────────────────────────────────────────────


def test_a_new_trio_is_tagged():
    assert "New trio" in bs.render_race(race(isNew=True), {})
    assert "New trio" not in bs.render_race(race(), {})


def test_a_top_pick_that_landed_gets_the_rail_and_the_tag():
    called = bs.render_race(race(topPickHit=True, driversRight=3), {})
    assert "rankrow-hero" in called and "Called it" in called
    missed = bs.render_race(race(), {})
    assert "rankrow-hero" not in missed and "Called it" not in missed


def test_a_row_shows_the_prediction_and_leads_on():
    out = bs.render_race(race(), {})
    assert "47%" in out
    assert "L. Norris / O. Piastri / C. Leclerc" in out
    assert "2 of 3" in out
    assert "After qualifying" in out
    assert "combos.html?d=Lando+Norris&amp;d=Oscar+Piastri&amp;d=Max+Verstappen" in out


def test_a_row_reports_its_board_place_only_once_the_board_exists():
    assert "Trio board" not in bs.render_race(race(), {})
    assert "#4 of 25" in bs.render_race(race(boardSize=25, boardRank=4, boardFloor=1.0), {})
    assert "Not on it" in bs.render_race(race(boardSize=25, boardFloor=1.0), {})


def test_only_the_earlier_model_is_called_out():
    assert "The earlier one" in bs.render_race(race(model="plackett-luce"), {})
    assert "The earlier one" not in bs.render_race(race(), {})


def test_no_races_yet_is_said_plainly():
    assert "No races scored yet" in bs.render_races([], {})


# ── The headline numbers ────────────────────────────────────────────────────


def _detail(card, label):
    return next(f["detail"] for f in bs.fact_cards(card) if f["label"] == label)


def test_a_better_brier_score_says_beats():
    assert "beats" in _detail(totals(brierNew=0.2, baselineBrierNew=0.25), "New or repeat")


def test_a_worse_brier_score_says_trails():
    """The page doesn't get to pick its own verdict."""
    assert "trails" in _detail(totals(brierNew=0.3, baselineBrierNew=0.25), "New or repeat")


def test_no_baseline_means_no_verdict():
    out = _detail(totals(baselineBrierNew=None, baseRateNew=None), "New or repeat")
    assert "Brier" not in out


def test_hits_are_put_next_to_what_the_odds_expected():
    out = _detail(totals(topPickHits=2, topPickExpected=0.65), "Top new pick")
    assert "twice" in out and "0.7" in out
    assert "never" in _detail(totals(topPickHits=0), "Top new pick")


def test_the_board_card_waits_for_the_board():
    assert "Trio board" not in [f["label"] for f in bs.fact_cards(totals(boardRaces=0))]


def test_nothing_scored_yet_does_not_divide_by_zero():
    bs.fact_cards(totals(races=0, newTrios=0, boardRaces=0))


# ── Next up ─────────────────────────────────────────────────────────────────


def test_the_next_race_is_named():
    nxt = ScorecardNext(
        season="2026",
        round="19",
        raceName="Mexico City Grand Prix",
        stage="post-quali",
        chanceNew=39.6,
        topPick=["Lando Norris", "Oscar Piastri", "Charles Leclerc"],
        topPickProb=3.0,
    )
    out = bs.render_next(nxt)
    assert "Next up: Mexico City Grand Prix" in out
    assert "40%" in out and "3.0%" in out
    assert 'href="index.html"' in out


def test_no_next_race_renders_nothing():
    assert bs.render_next(None) == ""


# ── Whole page ──────────────────────────────────────────────────────────────


def test_the_built_page_is_in_the_nav_and_says_how_it_works(dist):
    html = (dist / "scorecard.html").read_text(encoding="utf-8")
    assert "Prediction Scorecard" in html
    assert "frozen there and never rewritten" in html
    nav = html[html.index('<nav class="nav">') : html.index("</nav>")]
    assert 'href="scorecard.html" class="active"' in nav
