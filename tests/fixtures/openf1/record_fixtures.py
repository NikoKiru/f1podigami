"""Record the frozen fixtures the fast-lane tests replay (network; run by hand).

    python tests/fixtures/openf1/record_fixtures.py

Writes three gzipped JSON files next to this script:

- openf1_2026.json.gz — every OpenF1 response fetch_openf1 reads for 2026 rounds
  1-13 (race + qualifying sessions, results, drivers, stewards' messages,
  starting grids), trimmed to the fields the code uses.
- jolpica_2026.json.gz — a FROZEN snapshot of origin/main's schedule, current
  drivers, and 2026 rounds 1-13 of podiums / race_results / qualifying: the rows
  the fetcher must reproduce. Never compare against live data/ instead — a later
  Jolpica revision would turn the test into a stall vector.
- gate_backtest.json.gz — result rows + stewards' messages (up to session end +
  30 min) for every Race 2023 onward, for the stewards' check backtest.

Re-recording changes the expectations; commit new files deliberately.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
from fetch import openf1  # noqa: E402

LAST_ROUND = 13
RESULT_KEYS = ("driver_number", "position", "number_of_laps", "duration", "dnf", "dns", "dsq")
DRIVER_KEYS = ("driver_number", "last_name", "team_name")
SESSION_KEYS = ("session_key", "session_name", "date_start", "date_end", "is_cancelled", "location")
SCHEDULE_KEYS = (
    "round",
    "raceName",
    "date",
    "time",
    "qualifyingDate",
    "qualifyingTime",
    "circuitId",
)
STEWARDS_WORDS = (
    "STEWARDS",
    "INCIDENT",
    "PENALTY",
    "DISQUALIF",
    "INVESTIGAT",
    "SUMMON",
    "REPRIMAND",
    "WARNING",
    "NO FURTHER",
    "NOTED",
)


def require(rows: list[dict] | None, what: str) -> list[dict]:
    if rows is None:
        sys.exit(f"OpenF1 {what} failed; no fixtures written")
    return rows


def trim(rows: list[dict] | None, keys: tuple[str, ...]) -> list[dict]:
    return [{k: row.get(k) for k in keys} for row in rows or []]


def stewards(messages: list[dict] | None) -> list[dict]:
    """Only the messages the stewards' check can react to."""
    kept = []
    for m in messages or []:
        text = (m.get("message") or "").upper()
        if "CAR" in text and any(word in text for word in STEWARDS_WORDS):
            kept.append({"date": m.get("date"), "message": m.get("message")})
    return kept


def git_json(path: str):
    out = subprocess.run(
        ["git", "show", f"origin/main:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
        check=True,
    )
    return json.loads(out.stdout)


def write(name: str, payload: dict | list) -> None:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    (HERE / name).write_bytes(gzip.compress(data, mtime=0))
    print(f"wrote {name} ({(HERE / name).stat().st_size // 1024} KB)")


def record_2026(schedule: dict) -> dict:
    races = require(openf1.sessions(2026, "Race"), "sessions(2026, Race)")
    qualis = require(openf1.sessions(2026, "Qualifying"), "sessions(2026, Qualifying)")
    out = {
        "sessions": {"Race": trim(races, SESSION_KEYS), "Qualifying": trim(qualis, SESSION_KEYS)},
        "session_result": {},
        "drivers": {},
        "race_control": {},
        "starting_grid": {},
    }
    for race in schedule["races"]:
        if int(race["round"]) > LAST_ROUND:
            continue
        days = {race["date"], race.get("qualifyingDate")}
        for s in races + qualis:
            if s["date_start"][:10] not in days:
                continue
            key = str(s["session_key"])
            out["session_result"][key] = trim(
                require(openf1.session_result(s["session_key"]), f"session_result({key})"),
                RESULT_KEYS,
            )
            out["drivers"][key] = trim(
                require(openf1.drivers(s["session_key"]), f"drivers({key})"),
                DRIVER_KEYS,
            )
            if s["session_name"] == "Race":
                out["race_control"][key] = stewards(
                    require(openf1.race_control(s["session_key"]), f"race_control({key})")
                )
            else:
                grid = require(openf1.starting_grid(s["session_key"]), f"starting_grid({key})")
                out["starting_grid"][key] = trim(grid, ("driver_number", "position"))
    return out


def record_jolpica(schedule: dict) -> dict:
    rounds = {str(r) for r in range(1, LAST_ROUND + 1)}

    def pick(rows: list[dict]) -> list[dict]:
        return [r for r in rows if r["season"] == "2026" and r["round"] in rounds]

    return {
        "schedule": {
            "season": schedule["season"],
            "races": [{k: r.get(k) for k in SCHEDULE_KEYS} for r in schedule["races"]],
        },
        "current_drivers": git_json("data/current_drivers.json"),
        "podiums": pick(git_json("data/podiums.json")),
        "race_results": pick(git_json("data/race_results.json")),
        "qualifying": pick(git_json("data/qualifying.json")),
    }


def record_backtest() -> list[dict]:
    now = datetime.now(UTC)
    races = []
    for year in range(2023, now.year + 1):
        for s in require(openf1.sessions(year, "Race"), f"sessions({year}, Race)"):
            end = datetime.fromisoformat(s["date_end"])
            if s.get("is_cancelled") or end > now:
                continue
            result = require(
                openf1.session_result(s["session_key"]), f"session_result({s['session_key']})"
            )
            messages = require(
                openf1.race_control(s["session_key"]), f"race_control({s['session_key']})"
            )
            if not result:
                continue
            first_look = end + timedelta(minutes=30)
            races.append(
                {
                    "label": f"{year} {s['location']}",
                    "result": trim(result, RESULT_KEYS),
                    "messages": [
                        m
                        for m in stewards(messages)
                        if datetime.fromisoformat(m["date"]) <= first_look
                    ],
                }
            )
    return races


if __name__ == "__main__":
    openf1.MAX_TOTAL_RETRY_WAIT = float("inf")
    schedule = git_json("data/schedule.json")
    payload_2026 = record_2026(schedule)
    payload_jolpica = record_jolpica(schedule)
    payload_backtest = record_backtest()
    write("openf1_2026.json.gz", payload_2026)
    write("jolpica_2026.json.gz", payload_jolpica)
    write("gate_backtest.json.gz", payload_backtest)
