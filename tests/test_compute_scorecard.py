"""The prediction log and its scoring (no IO).

The log is the one dataset that can't be regenerated, so what matters most here
is what must never change it: a race that has started, or one that has finished.
"""

from datetime import UTC, datetime

import pytest

from compute import compute_scorecard as cs
from datalib import REGISTRY

BEFORE_THE_RACE = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)
AFTER_LIGHTS_OUT = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)


def race(rnd, name, date="2026-11-01", time="20:00:00Z"):
    return {"round": rnd, "raceName": name, "date": date, "time": time}


def schedule(*races, season="2026"):
    return {"season": season, "totalRounds": len(races), "races": list(races)}


MEXICO = race("19", "Mexico City Grand Prix")
BRAZIL = race("20", "Sao Paulo Grand Prix", date="2026-11-08")


def prediction(chance=40.0, pick=("a", "b", "c"), prob=5.0, post_quali=None, round_="18"):
    return {
        "asOf": {"season": "2026", "round": round_, "raceName": "United States Grand Prix"},
        "params": {"model": "dbpl-v2"},
        "chanceNextRaceNew": chance,
        "candidates": [
            {
                "driverIds": list(pick),
                "names": [d.upper() for d in pick],
                "prob": prob,
                "perDriver": [],
            }
        ],
        "trioBoard": [{"driverIds": ["a", "b", "x"], "prob": 9.0, "happened": True}],
        "postQuali": post_quali,
    }


def post_quali(chance=30.0, pick=("d", "e", "f"), name="Mexico City Grand Prix"):
    return {
        "season": "2026",
        "round": "19",
        "raceName": name,
        "chanceNextRaceNew": chance,
        "candidates": [{"driverIds": list(pick), "names": [d.upper() for d in pick], "prob": 7.0}],
        "trioBoard": [],
    }


def record(name="Mexico City Grand Prix", rnd="19", chance=40.0, pick=("a", "b", "c"), board=()):
    return {
        "season": "2026",
        "round": rnd,
        "raceName": name,
        "stage": "post-quali",
        "model": "dbpl-v2",
        "chanceNew": chance,
        "candidates": [{"driverIds": list(pick), "names": [d.upper() for d in pick], "prob": 5.0}],
        "board": [{"driverIds": list(t), "prob": p} for t, p in board],
    }


def podium(a, b, c, rnd="19", name="Mexico City Grand Prix", season="2026"):
    def slot(d):
        return {"driverId": d, "name": d.upper()}

    return {
        "season": season,
        "round": rnd,
        "raceName": name,
        "p1": slot(a),
        "p2": slot(b),
        "p3": slot(c),
    }


# ── Logging ─────────────────────────────────────────────────────────────────


def test_the_next_race_is_logged_before_it_starts():
    log = cs.update_log([], prediction(), schedule(MEXICO), set(), BEFORE_THE_RACE)
    assert [(r["round"], r["raceName"], r["stage"]) for r in log] == [
        ("19", "Mexico City Grand Prix", "pre-quali")
    ]
    assert log[0]["chanceNew"] == 40.0
    assert log[0]["candidates"][0] == {
        "driverIds": ["a", "b", "c"],
        "names": ["A", "B", "C"],
        "prob": 5.0,
    }
    assert log[0]["board"] == [{"driverIds": ["a", "b", "x"], "prob": 9.0}]


def test_qualifying_replaces_the_earlier_prediction_for_that_race():
    log = cs.update_log([], prediction(), schedule(MEXICO), set(), BEFORE_THE_RACE)
    pred = prediction(post_quali=post_quali())
    log = cs.update_log(log, pred, schedule(MEXICO), set(), BEFORE_THE_RACE)
    assert len(log) == 1
    assert (log[0]["stage"], log[0]["chanceNew"]) == ("post-quali", 30.0)


def test_nothing_changes_once_the_lights_go_out():
    """A mid-race update drops retired cars, which is not what we said beforehand."""
    log = [record(chance=40.0)]
    pred = prediction(post_quali=post_quali(chance=12.0))
    assert cs.update_log(log, pred, schedule(MEXICO), set(), AFTER_LIGHTS_OUT) == log


def test_a_finished_race_is_never_rewritten():
    log = [record(chance=40.0)]
    pred = prediction(post_quali=post_quali(chance=12.0))
    raced = {("2026", "Mexico City Grand Prix")}
    assert cs.update_log(log, pred, schedule(MEXICO), raced, BEFORE_THE_RACE) == log


def test_logging_the_next_race_keeps_the_earlier_ones():
    log = [record(chance=40.0)]
    pred = prediction(round_="19")
    out = cs.update_log(log, pred, schedule(MEXICO, BRAZIL), set(), BEFORE_THE_RACE)
    assert [r["raceName"] for r in out] == ["Mexico City Grand Prix", "Sao Paulo Grand Prix"]
    assert out[0] == log[0]


def test_logging_twice_changes_nothing():
    """A rerun must leave no churn in the data PR."""
    once = cs.update_log([], prediction(), schedule(MEXICO), set(), BEFORE_THE_RACE)
    assert cs.update_log(once, prediction(), schedule(MEXICO), set(), BEFORE_THE_RACE) == once


def test_a_race_results_feed_ahead_of_the_podiums_moves_the_target_on():
    """The feeds publish out of step, so asOf alone can name a race already run."""
    out = cs.update_log(
        [],
        prediction(),
        schedule(MEXICO, BRAZIL),
        set(),
        BEFORE_THE_RACE,
        results_through=(2026, 19),
    )
    assert [r["raceName"] for r in out] == ["Sao Paulo Grand Prix"]


def test_the_end_of_a_season_logs_nothing():
    pred = prediction(round_="19")
    assert cs.update_log([], pred, schedule(MEXICO), set(), BEFORE_THE_RACE) == []


def test_a_post_quali_block_for_another_season_logs_nothing():
    pred = prediction(post_quali=post_quali())
    assert cs.update_log([], pred, schedule(MEXICO, season="2027"), set(), BEFORE_THE_RACE) == []


def test_a_race_without_a_time_freezes_at_the_start_of_its_day():
    assert cs.race_start(race("1", "X", time="")) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)


# ── Scoring ─────────────────────────────────────────────────────────────────


def score(rec, *drivers, prior=()):
    podiums = [
        *[podium(*t, rnd=str(i + 1), name=f"Race {i}") for i, t in enumerate(prior)],
        podium(*drivers),
    ]
    return cs.compute([rec], podiums)["races"][0]


def test_a_top_pick_that_lands_is_a_hit():
    out = score(record(), "c", "a", "b")
    assert out["topPickHit"] is True
    assert out["driversRight"] == 3


def test_a_top_pick_that_misses_still_counts_the_drivers_it_got_right():
    out = score(record(), "a", "b", "z")
    assert out["topPickHit"] is False
    assert out["driversRight"] == 2


def test_a_trio_is_new_only_if_no_earlier_race_had_it():
    assert score(record(), "a", "b", "z")["isNew"] is True
    assert score(record(), "a", "b", "z", prior=[("z", "a", "b")])["isNew"] is False


def test_the_trio_that_happened_is_found_on_the_board():
    rec = record(board=[(("x", "y", "z"), 9.0), (("a", "b", "z"), 4.0), (("d", "e", "f"), 1.5)])
    out = score(rec, "z", "b", "a")
    assert (out["boardRank"], out["podiumProb"], out["boardFloor"]) == (2, 4.0, 1.5)
    assert out["boardSize"] == 3


def test_a_trio_off_the_board_has_no_probability_but_keeps_the_floor():
    out = score(record(board=[(("x", "y", "z"), 9.0)]), "a", "b", "q")
    assert (out["boardRank"], out["podiumProb"], out["boardFloor"]) == (None, None, 9.0)


def test_before_the_board_existed_a_listed_new_trio_still_has_its_probability():
    out = score(record(), "a", "b", "c")
    assert out["podiumProb"] == 5.0
    assert (out["boardSize"], out["boardRank"], out["boardFloor"]) == (0, None, None)


def test_a_renumbered_race_is_still_matched_by_name():
    """Upstream inserted a race mid-2026, and every later round moved up one."""
    rec = record(name="Singapore Grand Prix", rnd="16")
    out = cs.compute([rec], [podium("a", "b", "c", rnd="17", name="Singapore Grand Prix")])
    assert out["races"][0]["round"] == "17"


def test_a_race_with_no_logged_prediction_is_not_scored():
    assert cs.compute([], [podium("a", "b", "c")])["races"] == []


def test_a_revised_podium_rescores_the_race():
    """The score is derived, so an upstream correction fixes it with no extra step."""
    rec = record()
    assert cs.compute([rec], [podium("a", "b", "c")])["races"][0]["topPickHit"] is True
    assert cs.compute([rec], [podium("a", "b", "z")])["races"][0]["topPickHit"] is False


def test_races_run_newest_first():
    log = [record(name="One", rnd="1"), record(name="Two", rnd="2")]
    podiums = [
        podium("a", "b", "c", rnd="1", name="One"),
        podium("a", "b", "d", rnd="2", name="Two"),
    ]
    assert [r["raceName"] for r in cs.compute(log, podiums)["races"]] == ["Two", "One"]


def test_the_upcoming_race_is_named_and_not_scored():
    log = [record(name="One", rnd="1", chance=33.0), record(name="Two", rnd="2", chance=44.0)]
    out = cs.compute(log, [podium("a", "b", "c", rnd="1", name="One")])
    assert [r["raceName"] for r in out["races"]] == ["One"]
    assert (out["next"]["raceName"], out["next"]["chanceNew"]) == ("Two", 44.0)
    assert out["next"]["topPick"] == ["A", "B", "C"]


# ── Totals ──────────────────────────────────────────────────────────────────


def test_totals_add_up():
    log = [
        record(name="One", rnd="1", chance=50.0, board=[(("a", "b", "c"), 10.0)]),
        record(name="Two", rnd="2", chance=20.0, pick=("x", "y", "z")),
    ]
    podiums = [
        podium("a", "b", "c", rnd="1", name="One"),
        podium("a", "b", "c", rnd="2", name="Two"),
    ]
    t = cs.compute(log, podiums, base_rate=0.5)["totals"]
    assert (t["races"], t["newTrios"]) == (2, 1)
    assert t["meanChanceNew"] == 35.0
    assert t["brierNew"] == pytest.approx(((0.5 - 1) ** 2 + 0.2**2) / 2, abs=1e-4)
    assert t["baselineBrierNew"] == 0.25
    assert t["baseRateNew"] == 50.0
    assert (t["topPickHits"], t["topPickExpected"]) == (1, 0.1)
    assert t["meanDriversRight"] == 1.5
    assert (t["boardRaces"], t["onBoard"], t["boardTopThree"]) == (1, 1, 1)


def test_totals_cope_with_nothing_scored_yet():
    t = cs.compute([], [])["totals"]
    assert t["races"] == 0
    assert (t["meanChanceNew"], t["brierNew"], t["meanDriversRight"]) == (0.0, 0.0, 0.0)


def test_the_payload_fits_its_schema():
    log = [record(board=[(("a", "b", "c"), 10.0)])]
    REGISTRY["prediction_log.json"].validate_python(log)
    REGISTRY["scorecard.json"].validate_python(cs.compute(log, [podium("a", "b", "c")], 0.4))
