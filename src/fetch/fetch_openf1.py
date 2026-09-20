"""Fill the newest round from OpenF1 before Jolpica publishes it.

Jolpica — the only source for the 1950-onwards history — publishes a race 1-7h
after the flag (batch ingestion). OpenF1 (https://openf1.org), derived from the
official timing feed, serves the same classification ~30 min after the session
ends. This runs after the Jolpica fetchers in update.py and, for the newest race
and qualifying session Jolpica does not have yet, writes OpenF1's result into the
same datasets in Jolpica's exact row shape. Everything downstream (combos, stats,
prediction, pages) then rolls forward straight away; when Jolpica publishes the
round its fetchers overwrite these rows — byte-identical when the sources agree
(verified for every 2026 round the stewards' check lets through), and a changed
podium raises the revision alert.

Fail closed, always. Any doubt — OpenF1 unreachable or still inside its live
window, a session that doesn't match exactly one scheduled round, a car number,
surname or team we can't map, a stewards' decision still pending on the podium —
writes nothing, leaving the Jolpica path exactly as before. Every written round
is recorded in data/unconfirmed.json until Jolpica confirms it.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from check_update_due import session_start  # noqa: E402
from datalib import (  # noqa: E402
    REGISTRY,
    load_current_drivers,
    load_podiums,
    load_qualifying,
    load_race_results,
    load_schedule,
    load_unconfirmed,
    repository,
    save_podiums,
    save_qualifying,
    save_race_results,
    save_unconfirmed,
)
from fetch import openf1  # noqa: E402
from fetch.stewards_gate import hold_reasons  # noqa: E402

# OpenF1 team_name -> Jolpica constructorId, verified 1:1 against every 2026
# Jolpica row. A name not listed (a rebrand, a new team) fails closed until added.
TEAM_TO_CONSTRUCTOR = {
    "Alpine": "alpine",
    "Aston Martin": "aston_martin",
    "Audi": "audi",
    "Cadillac": "cadillac",
    "Ferrari": "ferrari",
    "Haas F1 Team": "haas",
    "McLaren": "mclaren",
    "Mercedes": "mercedes",
    "Racing Bulls": "rb",
    "Red Bull Racing": "red_bull",
    "Williams": "williams",
}

# A session is the scheduled one if it starts on the same UTC date and within this
# window. Not exact on purpose: Miami 2026 ran at 17:00Z while Jolpica's schedule
# still says 20:00Z. Country and circuit names are not used — they differ between
# the sources ("USA" / "United States"; 2026 R16 is "Bahrain" in Kuala Lumpur).
MATCH_WINDOW = timedelta(hours=6)

# OpenF1's free tier opens a session's data 30 min after it ends.
FREE_AFTER = timedelta(minutes=30)


def _instant(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _surname_key(name: str) -> str:
    words = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().split()
    return words[-1] if words else ""


def match_session(sessions: list[dict], date: str, time: str | None) -> dict | None:
    """The one non-cancelled session on the scheduled UTC date within MATCH_WINDOW."""
    scheduled = session_start(date, time or "")
    if scheduled is None:
        return None
    found = []
    for s in sessions:
        begins = _instant(s.get("date_start"))
        if (
            begins is not None
            and not s.get("is_cancelled")
            and begins.date() == scheduled.date()
            and abs(begins - scheduled) <= MATCH_WINDOW
        ):
            found.append(s)
    return found[0] if len(found) == 1 else None


def map_drivers(entrants: list[dict], current: list[dict]) -> dict[int, dict] | None:
    """OpenF1 car number -> our driver and team, or None if any car won't map exactly.

    ``current`` is current_drivers.json's ``drivers``. The number must be known,
    OpenF1's last name must equal the last word of the committed name (accent- and
    case-insensitive), and the team must be in TEAM_TO_CONSTRUCTOR.
    """
    by_number = {str(d["number"]): d for d in current if d.get("number")}
    mapped: dict[int, dict] = {}
    for e in entrants:
        number = e.get("driver_number")
        ours = by_number.get(str(number))
        if ours is None:
            print(f"  OpenF1: car #{number} is not in current_drivers.json")
            return None
        if _surname_key(e.get("last_name") or "") != _surname_key(ours["name"]):
            print(f"  OpenF1: car #{number} is {e.get('last_name')!r}; we have {ours['name']!r}")
            return None
        team = TEAM_TO_CONSTRUCTOR.get(e.get("team_name") or "")
        if team is None:
            print(f"  OpenF1: unknown team {e.get('team_name')!r} for car #{number}")
            return None
        mapped[number] = {"driverId": ours["driverId"], "name": ours["name"], "constructorId": team}
    return mapped


def _status(row: dict, lead_laps: int) -> str:
    """Jolpica's status vocabulary (verified row-for-row for 2026 rounds 1-13)."""
    if row.get("dsq"):
        return "Disqualified"
    if row.get("dns"):
        return "Did not start"
    if row.get("dnf"):
        return "Retired"
    if (row.get("number_of_laps") or 0) < lead_laps:
        return "Lapped"
    return "Finished"


def _row_order(row: dict) -> tuple[bool, int, int]:
    """Classified cars by position, then the rest by laps completed: Jolpica's order."""
    position = row.get("position")
    classified = isinstance(position, int)
    return (not classified, position if classified else 0, -(row.get("number_of_laps") or 0))


def race_rows(
    result: list[dict], drivers: dict[int, dict], grid: dict[int, int]
) -> list[dict] | None:
    lead_laps = max((r.get("number_of_laps") or 0) for r in result)
    rows = []
    for r in sorted(result, key=_row_order):
        d = drivers.get(r.get("driver_number"))
        if d is None:
            print(f"  OpenF1: a result for unmapped car #{r.get('driver_number')}")
            return None
        position = r.get("position")
        rows.append(
            {
                "driverId": d["driverId"],
                "constructorId": d["constructorId"],
                "grid": grid.get(r["driver_number"], 0),
                "position": position if isinstance(position, int) else None,
                "laps": r.get("number_of_laps") or 0,
                "status": _status(r, lead_laps),
            }
        )
    return rows


def _session(client, season: str, name: str, date: str, time: str | None, now: datetime):
    """The matched session if its free data should be available, else None."""
    session = match_session(client.sessions(int(season), name) or [], date, time)
    if session is None:
        print(f"  OpenF1: no single {name} session matches {date}")
        return None
    ended = _instant(session.get("date_end"))
    if ended is None or now < ended + FREE_AFTER:
        print(f"  OpenF1: the {date} {name} is still inside OpenF1's live window")
        return None
    return session


def build_race(
    race: dict, season: str, current: list[dict], now: datetime, client=openf1
) -> dict | None:
    """``{"podium", "race", "sessionEnd"}`` for a scheduled race, or None to write nothing."""
    session = _session(client, season, "Race", race.get("date", ""), race.get("time"), now)
    if session is None:
        return None
    key = session["session_key"]
    result = client.session_result(key)
    if not result:
        print(f"  OpenF1: no result yet for round {race['round']}")
        return None
    drivers = map_drivers(client.drivers(key) or [], current)
    if drivers is None:
        return None
    messages = client.race_control(key)
    if messages is None:
        print("  OpenF1: race control unavailable, so the stewards' check can't clear")
        return None
    reasons = hold_reasons(result, messages)
    if reasons:
        print(f"  OpenF1: holding round {race['round']}: " + "; ".join(reasons))
        return None
    grid: dict[int, int] = {}
    quali = match_session(
        client.sessions(int(season), "Qualifying") or [],
        race.get("qualifyingDate") or "",
        race.get("qualifyingTime"),
    )
    if quali is not None:
        for g in client.starting_grid(quali["session_key"]) or []:
            if isinstance(g.get("position"), int):
                grid[g["driver_number"]] = g["position"]
    rows = race_rows(result, drivers, grid)
    if rows is None:
        return None
    by_position = {r["position"]: r for r in rows if r["position"] in (1, 2, 3)}
    if sorted(by_position) != [1, 2, 3]:
        print(f"  OpenF1: no complete podium for round {race['round']}")
        return None
    names = {d["driverId"]: d["name"] for d in drivers.values()}
    podium: dict = {"season": season, "round": race["round"], "raceName": race["raceName"]}
    for p in (1, 2, 3):
        driver_id = by_position[p]["driverId"]
        podium[f"p{p}"] = {"driverId": driver_id, "name": names[driver_id]}
    return {
        "podium": podium,
        "race": {
            "season": season,
            "round": race["round"],
            "raceName": race["raceName"],
            "date": race["date"],
            "circuitId": race["circuitId"],
            "results": rows,
        },
        "sessionEnd": session["date_end"],
    }


def build_qualifying(
    race: dict, season: str, current: list[dict], now: datetime, client=openf1
) -> dict | None:
    """``{"entry", "sessionEnd"}`` for a race's qualifying, or None to write nothing."""
    session = _session(
        client,
        season,
        "Qualifying",
        race.get("qualifyingDate") or "",
        race.get("qualifyingTime"),
        now,
    )
    if session is None:
        return None
    key = session["session_key"]
    result = client.session_result(key)
    if not result:
        print(f"  OpenF1: no qualifying result yet for round {race['round']}")
        return None
    drivers = map_drivers(client.drivers(key) or [], current)
    if drivers is None:
        return None
    rows = []
    classified = (r for r in result if isinstance(r.get("position"), int))
    for r in sorted(classified, key=lambda r: r["position"]):
        d = drivers.get(r.get("driver_number"))
        if d is None:
            print(f"  OpenF1: a qualifying result for unmapped car #{r.get('driver_number')}")
            return None
        rows.append(
            {
                "driverId": d["driverId"],
                "constructorId": d["constructorId"],
                "position": r["position"],
            }
        )
    if len(rows) < 3:
        return None
    return {
        "entry": {"season": season, "round": race["round"], "results": rows},
        "sessionEnd": session["date_end"],
    }


def newest_started(schedule: dict, now: datetime, date_key: str, time_key: str) -> dict | None:
    """The newest scheduled race whose race (or qualifying) session has started by now."""
    newest = None
    for race in schedule.get("races", []):
        start = session_start(race.get(date_key) or "", race.get(time_key) or "")
        if start is None or start > now:
            continue
        if newest is None or int(race["round"]) > int(newest["round"]):
            newest = race
    return newest


def _rounds(rows: list[dict]) -> set[tuple[str, str]]:
    return {(r["season"], r["round"]) for r in rows}


def _record(unconfirmed: list[dict], entry: dict) -> None:
    """List ``entry`` in ``unconfirmed`` unless its season, round and kind already are.

    A --full run rebuilds the datasets from Jolpica, dropping a fast round Jolpica
    hasn't confirmed, and fill then writes that round again. A second identical
    entry would stop unconfirmed.json from being a fixed point.
    """
    key = (entry["season"], entry["round"], entry["kind"])
    if all((u["season"], u["round"], u["kind"]) != key for u in unconfirmed):
        unconfirmed.append(entry)


def fill(
    schedule: dict,
    current: list[dict],
    podiums: list[dict],
    race_results: list[dict],
    qualifying: list[dict],
    unconfirmed: list[dict],
    now: datetime,
    client=openf1,
) -> set[str]:
    """Write the newest race and qualifying Jolpica lacks into the lists, in place.

    Returns the kinds written ({"race", "qualifying"}); each written round is
    listed in ``unconfirmed`` (once). A race is only written when *both* podiums
    and race_results lack it, so a round never mixes sources.
    """
    season = str(schedule["season"])
    written: set[str] = set()

    race = newest_started(schedule, now, "date", "time")
    if race is not None:
        key = (season, race["round"])
        if key not in _rounds(podiums) and key not in _rounds(race_results):
            built = build_race(race, season, current, now, client)
            if built is not None:
                podiums.append(built["podium"])
                race_results.append(built["race"])
                _record(
                    unconfirmed,
                    {
                        "season": season,
                        "round": race["round"],
                        "kind": "race",
                        "pending": ["podiums", "race_results"],
                        "since": built["sessionEnd"],
                    },
                )
                written.add("race")

    quali = newest_started(schedule, now, "qualifyingDate", "qualifyingTime")
    if quali is not None and (season, quali["round"]) not in _rounds(qualifying):
        built = build_qualifying(quali, season, current, now, client)
        if built is not None:
            qualifying.append(built["entry"])
            _record(
                unconfirmed,
                {
                    "season": season,
                    "round": quali["round"],
                    "kind": "qualifying",
                    "pending": ["qualifying"],
                    "since": built["sessionEnd"],
                },
            )
            written.add("qualifying")

    for rows in (podiums, race_results, qualifying):
        rows.sort(key=lambda r: (int(r["season"]), int(r["round"])))
    return written


def _to_write(
    written: set[str],
    podiums: list[dict],
    race_results: list[dict],
    qualifying: list[dict],
    unconfirmed: list[dict],
) -> list[tuple[str, list[dict]]]:
    """``(dataset, payload)`` for every file this run would save, in save order."""
    pairs: list[tuple[str, list[dict]]] = []
    if "race" in written:
        pairs += [("podiums.json", podiums), ("race_results.json", race_results)]
    if "qualifying" in written:
        pairs.append(("qualifying.json", qualifying))
    if written:
        pairs.append(("unconfirmed.json", unconfirmed))
    return pairs


def report_filled(written: set[str]) -> None:
    """Tell update.yml which kinds this run wrote ("race", "qualifying"), if any.

    The confirmation hand-over keys off this output, not off "a session is
    pending": a fast run whose fill failed closed wrote nothing and must not hand
    over without a hold. Writes nothing when nothing was filled (the output stays
    unset, i.e. empty in the workflow).
    """
    out = os.environ.get("GITHUB_OUTPUT")
    if out and written:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"filled={','.join(sorted(written))}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--now", help="ISO-8601 instant to act as 'now' (rehearsals)")
    args = ap.parse_args(argv)
    if os.environ.get("JOLPICA_ONLY") == "true":
        # update.yml sets this when an earlier data PR is still unmerged after the
        # in-flight wait: main may lack that fast result, so filling the round again
        # would only re-push the same rows and restart the PR's checks. Jolpica's turn.
        print("OpenF1 fast lane: skipped (an earlier data PR is still open).")
        return 0
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)

    schedule = load_schedule().model_dump()
    current = [d.model_dump() for d in load_current_drivers().drivers]
    podiums = [p.model_dump() for p in load_podiums()]
    race_results = [r.model_dump() for r in load_race_results()]
    qualifying = [q.model_dump() for q in load_qualifying()]
    has_file = (repository.DATA_DIR / "unconfirmed.json").exists()
    unconfirmed = [u.model_dump() for u in load_unconfirmed()] if has_file else []

    try:
        written = fill(schedule, current, podiums, race_results, qualifying, unconfirmed, now)
    except Exception:  # noqa: BLE001 - the fast lane must never break the Jolpica path
        traceback.print_exc()
        print("OpenF1 fast lane failed; leaving the round to Jolpica.")
        return 0

    # Validate every payload before writing any of them. Saving podiums.json and then
    # failing on race_results.json would leave the two disagreeing about the round,
    # and the uncaught error would abort update.py before the rest of the pipeline.
    for name, payload in _to_write(written, podiums, race_results, qualifying, unconfirmed):
        try:
            REGISTRY[name].validate_python(payload)
        except Exception:  # noqa: BLE001 - any doubt about the payload writes nothing
            traceback.print_exc()
            print(f"OpenF1 fast lane: {name} failed validation; leaving the round to Jolpica.")
            return 0

    # The saves stay outside the guard on purpose: every payload has validated, so a
    # failure here is an I/O error. Swallowing it once podiums.json is written would
    # publish skewed data silently, while a crash makes the run red and loud.
    if "race" in written:
        save_podiums(podiums)
        save_race_results(race_results)
    if "qualifying" in written:
        save_qualifying(qualifying)
    if written:
        save_unconfirmed(unconfirmed)
        print(f"OpenF1 filled: {', '.join(sorted(written))} (awaiting Jolpica)")
    else:
        print("OpenF1 fast lane: nothing to fill.")
    report_filled(written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
