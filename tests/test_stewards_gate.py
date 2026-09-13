"""The stewards' check (src/fetch/stewards_gate.py).

OpenF1 serves a race's classification ~30 min after it ends, before the FIA's
final classification. This check holds the fast lane while the stewards could
still change the podium *trio*.
"""

import gzip
import json
from pathlib import Path

from fetch.stewards_gate import crossing_order, hold_reasons

BACKTEST = Path(__file__).parent / "fixtures" / "openf1" / "gate_backtest.json.gz"


def row(number, position, laps=50, time=5000.0, **flags):
    return {
        "driver_number": number,
        "position": position,
        "number_of_laps": laps,
        "duration": time,
        **flags,
    }


# 1 wins, 4 second, 16 third; 44 is 3 s behind 16; 63 well back.
FINISH = [
    row(1, 1, time=5000.0),
    row(4, 2, time=5010.0),
    row(16, 3, time=5020.0),
    row(44, 4, time=5023.0),
    row(63, 5, time=5040.0),
]


def msg(text, t="2026-09-13T14:00:00+00:00"):
    return {"date": t, "message": text}


def test_a_clean_race_publishes():
    assert hold_reasons(FINISH, []) == []


def test_an_open_incident_on_a_podium_car_holds():
    reasons = hold_reasons(
        FINISH,
        [
            msg(
                "FIA STEWARDS: INCIDENT INVOLVING CAR 16 (LEC) WILL BE INVESTIGATED AFTER THE RACE - IMPEDING"
            )
        ],
    )
    assert len(reasons) == 1 and reasons[0].startswith("#16 open")


def test_an_open_incident_off_the_podium_is_ignored():
    assert (
        hold_reasons(
            FINISH,
            [
                msg(
                    "FIA STEWARDS: INCIDENT INVOLVING CAR 63 (RUS) UNDER INVESTIGATION - UNSAFE RELEASE"
                )
            ],
        )
        == []
    )


def test_a_decision_closes_the_whole_incident():
    """Austin 2024: Norris was penalised; the same incident no longer holds Verstappen."""
    msgs = [
        msg(
            "FIA STEWARDS: TURN 12 INCIDENT INVOLVING CARS 4 (NOR) AND 1 (VER) UNDER "
            "INVESTIGATION - LEAVING THE TRACK AND GAINING AN ADVANTAGE",
            "2026-09-13T14:00:00+00:00",
        ),
        msg(
            "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 4 (NOR) - LEAVING THE TRACK AND "
            "GAINING AN ADVANTAGE",
            "2026-09-13T14:05:00+00:00",
        ),
    ]
    # 5 s puts car 4 on 5015, still ahead of car 16 (5020): the trio stands.
    assert hold_reasons(FINISH, msgs) == []


def test_noted_alone_does_not_block():
    assert (
        hold_reasons(
            FINISH,
            [
                msg(
                    "TURN 10 INCIDENT INVOLVING CARS 16 (LEC) AND 44 (HAM) NOTED - CAUSING A COLLISION"
                )
            ],
        )
        == []
    )


def test_unserved_penalties_that_change_the_trio_hold():
    """Monaco 2026: Gasly's two unserved 5 s penalties dropped him from 3rd to 7th."""
    msgs = [
        msg(
            "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - SPEEDING IN THE PIT LANE (14:02:16)",
            "2026-09-13T14:10:00+00:00",
        ),
        msg(
            "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - SPEEDING IN THE PIT LANE (14:22:57)",
            "2026-09-13T14:36:00+00:00",
        ),
    ]
    assert hold_reasons(FINISH, msgs) == ["unserved time penalties change the trio"]


def test_a_served_penalty_is_not_counted():
    msgs = [
        msg(
            "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - TRACK LIMITS",
            "2026-09-13T14:10:00+00:00",
        ),
        msg(
            "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - TRACK LIMITS",
            "2026-09-13T14:30:00+00:00",
        ),
    ]
    # Unserved, 5 s would put car 16 (5025) behind car 44 (5023).
    assert hold_reasons(FINISH, msgs) == []


def test_an_unserved_drive_through_holds():
    assert hold_reasons(
        FINISH, [msg("FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 4 (NOR) - FALSE START")]
    ) == ["#4 has an unserved drive-through or stop-go"]


def test_positions_that_disagree_with_race_times_hold():
    """Austin 2023 as OpenF1 has it now: Hamilton unclassified but timed in 2nd."""
    rows = [*FINISH[:3], row(44, None, time=5005.0)]
    assert hold_reasons(rows, []) == ["OpenF1's positions disagree with its own race times"]


def test_a_disqualified_car_is_out_of_the_crossing_order():
    assert hold_reasons([*FINISH, row(81, None, time=4990.0, dsq=True)], []) == []


def test_crossing_order_is_laps_then_time():
    rows = [row(1, 2, laps=49, time=4900.0), row(4, 1, laps=50, time=5000.0)]
    assert [r["driver_number"] for r in crossing_order(rows)] == [4, 1]


def test_backtest_holds_what_it_can_see_and_publishes_most_races():
    races = json.load(gzip.open(BACKTEST, "rt", encoding="utf-8"))
    held = {r["label"] for r in races if hold_reasons(r["result"], r["messages"])}
    assert "2026 Monte Carlo" in held  # Gasly's unserved penalties
    assert "2023 Jeddah" in held  # Alonso's post-race penalty (later overturned)
    assert len(races) >= 80
    assert (len(races) - len(held)) / len(races) >= 0.75
