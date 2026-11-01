"""Remember what the site predicted, and score it against what actually happened.

Every data update rewrites the landing page's prediction, so nothing else keeps
what it said about a race once that race has run. This step copies the current
prediction into data/prediction_log.json for as long as its race is still ahead,
which leaves each record frozen at the last version published before lights out.
That file can't be regenerated. It's the only record of what the site said at the
time, seeded once from the git history of data/podigami.json.

data/scorecard.json is the derived view: each finished race's record against its
real podium, plus the totals the scorecard page opens with. It only ever reads
published predictions, never a replay, so it can't flatter the model the way a
backtest rerun with today's code could.

Inputs : data/podigami.json, data/schedule.json, data/podiums.json,
         data/race_results.json, data/model_eval.json, data/prediction_log.json
Output : data/prediction_log.json, data/scorecard.json
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import compute_podigami  # noqa: E402
import metrics  # noqa: E402
import model  # noqa: E402

from compute.shared_drives import podium_trios  # noqa: E402
from datalib import save_prediction_log, save_scorecard  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def race_start(race: dict) -> datetime:
    """Lights out, in UTC. A race with no published time counts from midnight, so
    the log freezes too early rather than too late."""
    return datetime.fromisoformat(f"{race['date']}T{race.get('time') or '00:00:00Z'}")


def target_race(
    podigami: dict, schedule: dict, results_through: tuple[int, int] = (0, 0)
) -> dict | None:
    """The race the current prediction is about, or None if there isn't one.

    A post-qualifying block names its race. Otherwise it's the race after the
    newest one any dataset knows has run, the same reconciliation compute_podigami
    does, because the feeds publish out of step.
    """
    post_quali = podigami.get("postQuali")
    if post_quali:
        if post_quali["season"] != schedule["season"]:
            return None
        return next((r for r in schedule["races"] if r["raceName"] == post_quali["raceName"]), None)
    as_of = podigami["asOf"]
    latest = max((int(as_of["season"]), int(as_of["round"])), results_through)
    return compute_podigami._next_race(schedule, *latest)


def snapshot(podigami: dict, season: str, race: dict) -> dict:
    """The record for ``race``: what the page says about it right now."""
    post_quali = podigami.get("postQuali")
    block = post_quali or podigami
    return {
        "season": season,
        "round": race["round"],
        "raceName": race["raceName"],
        "stage": "post-quali" if post_quali else "pre-quali",
        "model": podigami["params"]["model"],
        "chanceNew": block["chanceNextRaceNew"],
        "candidates": [
            {"driverIds": c["driverIds"], "names": c["names"], "prob": c["prob"]}
            for c in block["candidates"]
        ],
        "board": [
            {"driverIds": row["driverIds"], "prob": row["prob"]}
            for row in block.get("trioBoard") or []
        ],
    }


def _record_key(record: dict) -> tuple[str, str]:
    """Records match races by name: upstream has renumbered rounds mid-season."""
    return record["season"], record["raceName"]


def _race_order(record: dict) -> tuple[int, int]:
    return int(record["season"]), int(record["round"])


def update_log(
    log: list[dict],
    podigami: dict,
    schedule: dict,
    raced: set[tuple[str, str]],
    now: datetime,
    results_through: tuple[int, int] = (0, 0),
) -> list[dict]:
    """Return the log with the upcoming race's record brought up to date.

    A race that has started or finished is never touched, whatever a later run
    computes: a mid-race update drops retired cars from the prediction, and that
    must not be mistaken for what the site said beforehand.
    """
    race = target_race(podigami, schedule, results_through)
    if race is None:
        return log
    season = schedule["season"]
    if (season, race["raceName"]) in raced or now >= race_start(race):
        return log
    record = snapshot(podigami, season, race)
    if not record["candidates"]:
        return log
    kept = [r for r in log if _record_key(r) != _record_key(record)]
    return sorted([*kept, record], key=_race_order)


def score_race(record: dict, podium: dict, is_new: bool) -> dict:
    """One finished race: what was said against what happened."""
    actual = model.trio_key(podium[slot]["driverId"] for slot in model.POS_KEYS)
    top = record["candidates"][0]
    board = record["board"]
    keyed = [(model.trio_key(row["driverIds"]), row["prob"]) for row in board]
    on_board = next((i for i, (trio, _) in enumerate(keyed) if trio == actual), None)
    listed = [c["prob"] for c in record["candidates"] if model.trio_key(c["driverIds"]) == actual]

    podium_prob = None
    if on_board is not None:
        podium_prob = keyed[on_board][1]
    elif listed:
        podium_prob = listed[0]

    return {
        "season": podium["season"],
        "round": podium["round"],
        "raceName": podium["raceName"],
        "stage": record["stage"],
        "model": record["model"],
        "podium": [podium[slot]["name"] for slot in model.POS_KEYS],
        "isNew": is_new,
        "chanceNew": record["chanceNew"],
        "topPick": top["names"],
        "topPickProb": top["prob"],
        "topPickHit": model.trio_key(top["driverIds"]) == actual,
        "driversRight": len(set(top["driverIds"]) & set(actual)),
        "podiumProb": podium_prob,
        "boardSize": len(board),
        "boardRank": on_board + 1 if on_board is not None else None,
        "boardFloor": min((row["prob"] for row in board), default=None),
    }


def totals(scored: list[dict], base_rate: float | None) -> dict:
    """The headline numbers. ``base_rate`` is the long-run share of new trios, the
    guess a model has to beat; it's a fraction, the percentages here are not."""
    n = len(scored)
    outcomes = [1.0 if r["isNew"] else 0.0 for r in scored]
    said = [r["chanceNew"] / 100 for r in scored]
    with_board = [r for r in scored if r["boardSize"]]
    baseline = None
    if n and base_rate is not None:
        baseline = round(metrics.brier_binary([base_rate] * n, outcomes), 4)
    return {
        "races": n,
        "newTrios": sum(r["isNew"] for r in scored),
        "meanChanceNew": round(100 * sum(said) / n, 1) if n else 0.0,
        "brierNew": round(metrics.brier_binary(said, outcomes), 4) if n else 0.0,
        "baselineBrierNew": baseline,
        "baseRateNew": round(100 * base_rate, 1) if base_rate is not None else None,
        "topPickHits": sum(r["topPickHit"] for r in scored),
        "topPickExpected": round(sum(r["topPickProb"] for r in scored) / 100, 2),
        "meanDriversRight": round(sum(r["driversRight"] for r in scored) / n, 2) if n else 0.0,
        "boardRaces": len(with_board),
        "onBoard": sum(r["boardRank"] is not None for r in with_board),
        "boardTopThree": sum(
            r["boardRank"] is not None and r["boardRank"] <= 3 for r in with_board
        ),
    }


def compute(log: list[dict], podiums: list[dict], base_rate: float | None = None) -> dict:
    """Pure core: returns the scorecard.json payload. No file IO."""
    records = {_record_key(r): r for r in log}
    raced = {(p["season"], p["raceName"]) for p in podiums}
    seen: set[tuple[str, str, str]] = set()
    scored = []
    for podium in sorted(podiums, key=_race_order):
        trios = podium_trios(podium)
        record = records.get((podium["season"], podium["raceName"]))
        if record is not None:
            actual = model.trio_key(podium[slot]["driverId"] for slot in model.POS_KEYS)
            scored.append(score_race(record, podium, actual not in seen))
        seen.update(trios)

    upcoming = [r for r in log if _record_key(r) not in raced]
    next_race = None
    if upcoming:
        record = max(upcoming, key=_race_order)
        top = record["candidates"][0]
        next_race = {
            "season": record["season"],
            "round": record["round"],
            "raceName": record["raceName"],
            "stage": record["stage"],
            "chanceNew": record["chanceNew"],
            "topPick": top["names"],
            "topPickProb": top["prob"],
        }

    return {
        "totals": totals(scored, base_rate),
        "races": scored[::-1],
        "next": next_race,
    }


def _read(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def main() -> int:
    podigami, schedule, podiums = (
        _read(name) for name in ("podigami.json", "schedule.json", "podiums.json")
    )
    results = _read("race_results.json")
    results_through = max(((int(r["season"]), int(r["round"])) for r in results), default=(0, 0))
    log_path = DATA_DIR / "prediction_log.json"
    log = _read("prediction_log.json") if log_path.exists() else []

    raced = {(p["season"], p["raceName"]) for p in podiums}
    log = update_log(log, podigami, schedule, raced, datetime.now(UTC), results_through)
    save_prediction_log(log)

    base_rate = _read("model_eval.json")["chosen"]["baseRateNew"]
    payload = compute(log, podiums, base_rate)
    save_scorecard(payload)

    t = payload["totals"]
    print(f"Logged {len(log)} predictions, scored {t['races']} races")
    print(f"  top new pick: {t['topPickHits']} hits, {t['topPickExpected']} expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
