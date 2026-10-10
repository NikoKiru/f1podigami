"""Record F1's official starting grid for the next race, from OpenF1.

The post-qualifying prediction needs the grid the race will really start from.
F1 publishes it on formula1.com a few hours after qualifying, once the FIA has
applied grid penalties. It updates it on race morning when a car moves to a
pit-lane start or takes new power-unit elements (4 of the first 16 rounds of
2026). OpenF1's ``starting_grid`` mirrors that page, keyed by the qualifying
session. In all 16 rounds it matched the grid each race actually started from,
pit-lane starters included. This writes it to data/starting_grids.json, where
compute_podigami uses it instead of the hand-entered data/grid_penalties.json.

Fail closed, always. Any of these writes nothing, and the prediction keeps
using the qualifying order plus grid_penalties.json:

- OpenF1 is unreachable or hasn't published the grid yet;
- no single qualifying session matches;
- a car number, surname or team won't map;
- the positions aren't exactly 1..N;
- the grid isn't exactly the cars that took part in qualifying.

``fresh_grid`` is the one comparison that decides whether anything is new. This
script writes what it returns, and the watcher (wait_for_results.py) ends a watch
on it, so the two can never disagree about whether the grid changed.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from check_update_due import session_start  # noqa: E402
from datalib import (  # noqa: E402
    REGISTRY,
    load_current_drivers,
    load_podiums,
    load_qualifying,
    load_schedule,
    load_starting_grids,
    repository,
    save_starting_grids,
)
from fetch import openf1  # noqa: E402
from fetch.fetch_openf1 import map_drivers, match_session, newest_started  # noqa: E402

DATASET = "starting_grids.json"


def target_race(schedule: dict, podiums: list[dict], now: datetime) -> dict | None:
    """The race whose grid matters now: qualifying started, race not yet. Else None.

    That is the newest scheduled race whose qualifying has started, unless it has
    already been classified or its scheduled start has passed. Once the lights go
    out the grid is history, and OpenF1 is closed to free clients while a session
    is live anyway.
    """
    race = newest_started(schedule, now, "qualifyingDate", "qualifyingTime")
    if race is None:
        return None
    key = (str(schedule["season"]), race["round"])
    if any((p["season"], p["round"]) == key for p in podiums):
        return None
    start = session_start(race.get("date") or "", race.get("time") or "")
    if start is None or now >= start:
        return None
    return race


def build_grid(race: dict, season: str, current: list[dict], client=openf1) -> dict | None:
    """``{"season", "round", "grid"}`` from OpenF1, or None to write nothing.

    ``current`` is current_drivers.json's ``drivers``. Cars are mapped through the
    qualifying session's entrants, which list every car on the grid, including
    one that set no lap time.
    """
    rnd = race["round"]
    quali = match_session(
        client.sessions(int(season), "Qualifying") or [],
        race.get("qualifyingDate") or "",
        race.get("qualifyingTime"),
    )
    if quali is None:
        print(f"  OpenF1: no single qualifying session matches round {rnd}")
        return None
    rows = client.starting_grid(quali["session_key"])
    if not rows:
        print(f"  OpenF1: no starting grid for round {rnd} yet")
        return None
    drivers = map_drivers(client.drivers(quali["session_key"]) or [], current)
    if drivers is None:
        return None
    grid = []
    for row in rows:
        car, position = row.get("driver_number"), row.get("position")
        if car not in drivers or not isinstance(position, int):
            print(f"  OpenF1: unusable starting-grid row {row!r} for round {rnd}")
            return None
        mapped = drivers[car]
        grid.append(
            {
                "driverId": mapped["driverId"],
                "constructorId": mapped["constructorId"],
                "position": position,
            }
        )
    grid.sort(key=lambda g: g["position"])
    if [g["position"] for g in grid] != list(range(1, len(grid) + 1)):
        print(f"  OpenF1: the round {rnd} grid positions don't run 1..{len(grid)}")
        return None
    if sorted(row["driver_number"] for row in rows) != sorted(drivers):
        print(f"  OpenF1: the round {rnd} grid isn't exactly the cars that qualified")
        return None
    return {"season": season, "round": rnd, "grid": grid}


def committed_grid(grids: list[dict], season: str, rnd: str) -> dict | None:
    """The grid data/starting_grids.json already holds for a round, if any."""
    return next((g for g in grids if (g["season"], g["round"]) == (season, rnd)), None)


def fresh_grid(
    race: dict, season: str, current: list[dict], grids: list[dict], client=openf1
) -> dict | None:
    """OpenF1's grid for ``race`` when it differs from the committed one, else None."""
    built = build_grid(race, season, current, client)
    if built is None:
        return None
    ours = committed_grid(grids, season, race["round"])
    if ours is not None and ours["grid"] == built["grid"]:
        return None
    return built


def upsert(grids: list[dict], entry: dict) -> list[dict]:
    """``grids`` with ``entry`` in place of its round's grid, in round order."""
    key = (entry["season"], entry["round"])
    kept = [g for g in grids if (g["season"], g["round"]) != key]
    return sorted([*kept, entry], key=lambda g: (int(g["season"]), int(g["round"])))


def moved(entry: dict, qualifying: list[dict]) -> list[str]:
    """For the log: every driver who starts behind where he qualified, or set no time.

    Those are the penalties (and pit-lane starts) F1 applied. A car promoted into a
    slot a penalised driver vacated is left out: listing every one of those would
    bury the few names that matter.
    """
    key = (entry["season"], entry["round"])
    quali = next((q for q in qualifying if (q["season"], q["round"]) == key), None)
    if quali is None:
        return []
    qpos = {row["driverId"]: row["position"] for row in quali["results"]}
    return [
        f"{g['driverId']} P{qpos[g['driverId']]} -> P{g['position']}"
        if g["driverId"] in qpos
        else f"{g['driverId']} (no lap time) P{g['position']}"
        for g in entry["grid"]
        if g["driverId"] not in qpos or g["position"] > qpos[g["driverId"]]
    ]


def _log_moves(entry: dict) -> None:
    """Print who starts behind where he qualified. Never raises."""
    try:
        shifted = moved(entry, [q.model_dump() for q in load_qualifying()])
    except Exception:  # noqa: BLE001 - this is only a log line
        return
    if shifted:
        print("  Starting behind where they qualified: " + ", ".join(shifted))


def main(argv: list[str] | None = None, client=openf1) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--now", help="ISO-8601 instant to act as 'now' (rehearsals)")
    args = ap.parse_args(argv)
    if os.environ.get("JOLPICA_ONLY") == "true":
        # update.yml sets this when an earlier data PR is still unmerged after the
        # in-flight wait: this checkout may lack that PR's grid, and writing it again
        # would only re-push the same rows and restart the PR's checks.
        print("Official starting grid: skipped (an earlier data PR is still open).")
        return 0
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:  # a rehearsal --now without an offset means UTC
        now = now.replace(tzinfo=UTC)

    schedule = load_schedule().model_dump()
    race = target_race(schedule, [p.model_dump() for p in load_podiums()], now)
    if race is None:
        print("Official starting grid: no race between its qualifying and its start.")
        return 0
    season = str(schedule["season"])
    has_file = (repository.DATA_DIR / DATASET).exists()
    grids = [g.model_dump() for g in load_starting_grids()] if has_file else []
    current = [d.model_dump() for d in load_current_drivers().drivers]

    try:
        entry = fresh_grid(race, season, current, grids, client)
        payload = upsert(grids, entry) if entry is not None else None
        if payload is not None:
            REGISTRY[DATASET].validate_python(payload)
    except Exception:  # noqa: BLE001 - a grid surprise must never break the pipeline
        traceback.print_exc()
        print("Official starting grid: failed; data/starting_grids.json left as it was.")
        return 0
    if payload is None:
        print(f"Official starting grid for round {race['round']}: nothing new.")
        return 0

    save_starting_grids(payload)
    print(f"Official starting grid for round {race['round']}: {len(entry['grid'])} cars written.")
    _log_moves(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
