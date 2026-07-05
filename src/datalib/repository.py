"""Typed load/save for the committed ``data/*.json`` datasets.

``load_*`` returns validated model objects (builders use attribute access:
``combo.count``, ``combo.lastRace.season``). ``save_*`` validates the data the
compute scripts build, then writes it **verbatim** — validation is a gate, the
bytes on disk are unchanged, so regenerating a dataset never reformats it.

The bulky raw datasets in ``COMPACT`` are written single-line (no indent) to
keep the repo lean; everything else stays human-readable ``indent=2``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .schemas import (
    Combo,
    ConstructorStandings,
    CurrentDrivers,
    DriverRaces,
    ModelEval,
    Overdue,
    Podigami,
    Podium,
    QualifyingEntry,
    RaceLink,
    RaceResult,
    Schedule,
    Soulmates,
    Unlikeliest,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# filename -> adapter for the whole-file shape (lists for podiums/combos, models otherwise)
REGISTRY: dict[str, TypeAdapter] = {
    "podiums.json": TypeAdapter(list[Podium]),
    "combos.json": TypeAdapter(list[Combo]),
    "soulmates.json": TypeAdapter(Soulmates),
    "current_drivers.json": TypeAdapter(CurrentDrivers),
    "driver_races.json": TypeAdapter(DriverRaces),
    "overdue.json": TypeAdapter(Overdue),
    "unlikeliest.json": TypeAdapter(Unlikeliest),
    "schedule.json": TypeAdapter(Schedule),
    "podigami.json": TypeAdapter(Podigami),
    "model_eval.json": TypeAdapter(ModelEval),
    "constructor_standings.json": TypeAdapter(ConstructorStandings),
    "f1_race_links.json": TypeAdapter(dict[str, dict[str, RaceLink]]),
    "race_results.json": TypeAdapter(list[RaceResult]),
    "qualifying.json": TypeAdapter(list[QualifyingEntry]),
}

# Bulky raw datasets written single-line to keep the repo (and git deltas) lean.
COMPACT = {"race_results.json", "qualifying.json"}


def _load(name: str) -> Any:
    raw = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    return REGISTRY[name].validate_python(raw)


def _save(name: str, data: Any) -> None:
    """Validate ``data`` against the schema, then write it verbatim."""
    REGISTRY[name].validate_python(data)
    if name in COMPACT:
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False)
    (DATA_DIR / name).write_text(text, encoding="utf-8")


def load_podiums() -> list[Podium]:
    return _load("podiums.json")


def save_podiums(data: Any) -> None:
    _save("podiums.json", data)


def load_combos() -> list[Combo]:
    return _load("combos.json")


def save_combos(data: Any) -> None:
    _save("combos.json", data)


def load_soulmates() -> Soulmates:
    return _load("soulmates.json")


def save_soulmates(data: Any) -> None:
    _save("soulmates.json", data)


def load_current_drivers() -> CurrentDrivers:
    return _load("current_drivers.json")


def save_current_drivers(data: Any) -> None:
    _save("current_drivers.json", data)


def load_driver_races() -> DriverRaces:
    return _load("driver_races.json")


def save_driver_races(data: Any) -> None:
    _save("driver_races.json", data)


def load_overdue() -> Overdue:
    return _load("overdue.json")


def save_overdue(data: Any) -> None:
    _save("overdue.json", data)


def load_unlikeliest() -> Unlikeliest:
    return _load("unlikeliest.json")


def save_unlikeliest(data: Any) -> None:
    _save("unlikeliest.json", data)


def load_schedule() -> Schedule:
    return _load("schedule.json")


def save_schedule(data: Any) -> None:
    _save("schedule.json", data)


def load_podigami() -> Podigami:
    return _load("podigami.json")


def save_podigami(data: Any) -> None:
    _save("podigami.json", data)


def load_model_eval() -> ModelEval:
    return _load("model_eval.json")


def save_model_eval(data: Any) -> None:
    _save("model_eval.json", data)


def load_constructor_standings() -> ConstructorStandings:
    return _load("constructor_standings.json")


def save_constructor_standings(data: Any) -> None:
    _save("constructor_standings.json", data)


def load_race_links() -> dict[str, dict[str, RaceLink]]:
    return _load("f1_race_links.json")


def save_race_links(data: Any) -> None:
    _save("f1_race_links.json", data)


def load_race_results() -> list[RaceResult]:
    return _load("race_results.json")


def save_race_results(data: Any) -> None:
    _save("race_results.json", data)


def load_qualifying() -> list[QualifyingEntry]:
    return _load("qualifying.json")


def save_qualifying(data: Any) -> None:
    _save("qualifying.json", data)
