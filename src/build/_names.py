"""Driver-name helpers shared by the builders: surnames and season-wide initials."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _layout import driver_name  # noqa: E402  (needs the sys.path entry above)

from compute.shared_drives import slot_drivers  # noqa: E402

PARTICLES = {"de", "da", "di", "del", "della", "van", "von", "der", "den", "la", "le"}
SUFFIXES = {"Jr.", "Sr."}


def surname(name: str) -> str:
    """Surname of a driver, keeping lower-case particles and a Jr./Sr. suffix."""
    parts = driver_name(str(name)).split()
    if not parts:
        return str(name)
    end = len(parts)
    if end > 1 and parts[-1] in SUFFIXES:
        end -= 1
    start = end - 1
    while start > 0 and parts[start - 1] in PARTICLES:
        start -= 1
    return " ".join(parts[start:])


def short_names_by_season(podiums: list[dict]) -> dict[str, dict[str, str]]:
    """Season -> {API full name -> short display name}.

    A surname unique within the season stands alone; shared surnames get a first
    initial, and a clash of initials falls back to the full display name.
    """
    names: dict[str, set[str]] = defaultdict(set)
    for pod in podiums:
        for slot in ("p1", "p2", "p3"):
            if pod.get(slot):
                for d in slot_drivers(pod, slot):
                    names[str(pod["season"])].add(d["name"])
    out: dict[str, dict[str, str]] = {}
    for season, season_names in names.items():
        by_surname: dict[str, list[str]] = defaultdict(list)
        for n in season_names:
            by_surname[surname(n)].append(n)
        short: dict[str, str] = {}
        for sn, group in by_surname.items():
            if len(group) == 1:
                short[group[0]] = sn
                continue
            initials = defaultdict(list)
            for n in group:
                initials[driver_name(n)[:1]].append(n)
            for n in group:
                short[n] = (
                    f"{driver_name(n)[:1]}. {sn}"
                    if len(initials[driver_name(n)[:1]]) == 1
                    else driver_name(n)
                )
        out[season] = short
    return out
