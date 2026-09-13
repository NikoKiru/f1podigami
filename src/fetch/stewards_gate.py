"""Would a stewards' decision still change this race's podium trio?

OpenF1 serves a race's classification ~30 min after it ends — before the FIA's
final classification. Across the 83 races of 2023-2026 the trio that crossed the
line first was not the final one four times: three post-race scrutineering
disqualifications (Austin 2023, Spa 2024, Las Vegas 2025), which nothing in the
feed announces, and Monaco 2026, where Gasly's two unserved 5 s penalties dropped
him from 3rd to 7th — which the feed does show.

This check holds the fast lane while the stewards could still change the trio:
a car that crossed the line in the top 3 with an open incident, an unserved
drive-through or stop-go, or unserved time penalties big enough to push it out
of the top 3. Order inside the podium doesn't matter — the verdict is about the
trio. A decision closes the incident it refers to (matched on the infringement
text and its ``(HH:MM:SS)`` tag) for every car in it; ``NOTED`` alone does not
block. Backtested on those 83 races it publishes 78% at the first look and holds
Monaco 2026 and Jeddah 2023 (Alonso's post-race penalty, later overturned).

Pure: OpenF1 ``session_result`` rows and ``race_control`` messages in, reasons out.
"""

from __future__ import annotations

import re

CARS = re.compile(r"(\d+) \([A-Z]{3}\)")
TAG = re.compile(r"\((\d{2}:\d{2}:\d{2})\)")
SECONDS = re.compile(r"(\d+) SECOND TIME PENALTY")
OPENS = ("UNDER INVESTIGATION", "WILL BE INVESTIGATED", "SUMMONED", "DISQUALIF")
DECIDES = ("PENALTY", "NO FURTHER", "REPRIMAND", "WARNING", "NO ACTION")
STOPS = ("DRIVE THROUGH", "STOP AND GO", "STOP/GO")


def _race_time(row: dict) -> float | None:
    value = row.get("duration")
    if isinstance(value, list):
        value = value[-1] if value else None
    return float(value) if isinstance(value, (int, float)) else None


def crossing_order(rows: list[dict]) -> list[dict]:
    """Cars in the order they took the flag: most laps, then least time.

    A car OpenF1 already marks disqualified is out of the classification, so it
    is left out here too.
    """
    timed = [r for r in rows if not r.get("dsq") and _race_time(r) is not None]
    return sorted(timed, key=lambda r: (-(r.get("number_of_laps") or 0), _race_time(r)))


def _infringement(text: str) -> str:
    """The infringement after the last ' - ', without its '(HH:MM:SS)' tag."""
    if " - " not in text:
        return ""
    return TAG.sub("", text.rsplit(" - ", 1)[1]).strip()


def stewards_state(
    messages: list[dict],
) -> tuple[dict[int, str], dict[int, list[int]], dict[int, int]]:
    """Per car number: open incidents, unserved time penalties (s), unserved stop penalties."""
    incidents: list[dict] = []
    seconds: dict[int, list[int]] = {}
    stops: dict[int, int] = {}
    for m in sorted(messages, key=lambda m: m.get("date") or ""):
        text = (m.get("message") or "").upper()
        if "FIA STEWARDS" not in text and "INCIDENT" not in text:
            continue
        cars = {int(c) for c in CARS.findall(text)}
        if not cars:
            continue
        tag_match = TAG.search(text)
        tag = tag_match.group(1) if tag_match else None
        infr = _infringement(text)
        timed = SECONDS.search(text)
        stop = any(word in text for word in STOPS)
        if "PENALTY SERVED" in text:
            for c in cars:
                if timed and int(timed.group(1)) in seconds.get(c, []):
                    seconds[c].remove(int(timed.group(1)))
                elif stop:
                    stops[c] = stops.get(c, 0) - 1
            continue
        if any(word in text for word in DECIDES):
            for c in cars:
                if timed:
                    seconds.setdefault(c, []).append(int(timed.group(1)))
                elif stop:
                    stops[c] = stops.get(c, 0) + 1
            for inc in incidents:
                if inc["open"] and (
                    (tag is not None and inc["tag"] == tag)
                    or (infr and inc["infr"] == infr and inc["cars"] & cars)
                    or (not infr and inc["cars"] & cars)
                ):
                    inc["open"] = False
            continue
        if any(word in text for word in OPENS):
            incidents.append(
                {
                    "cars": cars,
                    "infr": infr,
                    "tag": tag,
                    "open": True,
                    "text": (m.get("message") or "")[:100],
                }
            )
    open_by_car: dict[int, str] = {}
    for inc in incidents:
        if inc["open"]:
            for c in inc["cars"]:
                open_by_car[c] = inc["text"]
    return open_by_car, seconds, stops


def hold_reasons(rows: list[dict], messages: list[dict]) -> list[str]:
    """Why the stewards could still change the podium trio; empty means publish."""
    order = crossing_order(rows)
    if len(order) < 3:
        return ["fewer than three timed finishers"]
    top3 = [r["driver_number"] for r in order[:3]]
    listed = {r.get("driver_number") for r in rows if r.get("position") in (1, 2, 3)}
    if listed != set(top3):
        return ["OpenF1's positions disagree with its own race times"]
    open_by_car, seconds, stops = stewards_state(messages)
    reasons = []
    for car in top3:
        if car in open_by_car:
            reasons.append(f"#{car} open: {open_by_car[car]}")
        if stops.get(car, 0) > 0:
            reasons.append(f"#{car} has an unserved drive-through or stop-go")
    adjusted = sorted(
        order,
        key=lambda r: (
            -(r.get("number_of_laps") or 0),
            _race_time(r) + sum(seconds.get(r["driver_number"], [])),
        ),
    )
    if {r["driver_number"] for r in adjusted[:3]} != set(top3):
        reasons.append("unserved time penalties change the trio")
    return reasons
