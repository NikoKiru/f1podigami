"""Render data/podigami.json into dist/index.html (the landing page).

Shows the current season's most likely *brand-new* podium trio ("podigami"),
a ranked list of contenders (with a collapsible current-form tower), and a
year-slider timeline of every trio that debuted in each season.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _hooks import (  # noqa: E402
    combos_hook,
    explore_grid,
    overdue_hook,
    soulmates_hook,
    unlikeliest_hook,
)
from _layout import (  # noqa: E402  (needs the sys.path entry above)
    FOOTER,
    SITE_URL,
    asset,
    driver_name,
    head,
    nav,
    organization_schema,
    race_url,
)
from flags import flag_svg  # noqa: E402
from team_colors import team_color, text_on  # noqa: E402

from compute.shared_drives import slot_drivers  # noqa: E402
from datalib import (  # noqa: E402
    DATA_DIR,
    load_combos,
    load_current_drivers,
    load_model_eval,
    load_overdue,
    load_podigami,
    load_podiums,
    load_race_links,
    load_schedule,
    load_soulmates,
    load_unlikeliest,
)

OUT_PATH = ROOT / "dist" / "index.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def display_name(name: str) -> str:
    """Broadcast-style full name: "First MIDDLE? LASTNAME" (surname uppercased)."""
    parts = name.split()
    if not parts:
        return name
    parts[-1] = parts[-1].upper()
    return " ".join(parts)


def driver_view(entry: dict, meta: dict) -> dict:
    """Enrich a podigami driver entry with broadcast fields: surname, TLA code,
    car number, and the team colour (plus a legible ink for text on it)."""
    name = driver_name(entry["name"])
    parts = name.split()
    surname = parts[-1] if parts else name
    m = meta.get(entry.get("driverId", ""), {})
    code = (m.get("code") or surname[:3]).upper()
    color = team_color(entry.get("constructorId", ""))
    return {
        "name": name,
        "surname": surname,
        "code": code,
        "number": m.get("number"),
        "color": color,
        "ink": text_on(color),
        "team": entry.get("constructor") or "",  # absent/None off-season -> no team label
    }


def _ordinal(n: int) -> str:
    """1 -> "1st", 2 -> "2nd", 21 -> "21st" (11-13 stay "th")."""
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def pick_next_race(schedule: dict, asof: dict | None = None) -> dict | None:
    """Return the next race after the latest one we have results for, else None.

    Selection is data-driven, not calendar-driven: ``asof`` is the latest race
    reflected in the data (``podigami.json``'s ``asOf``: ``{"season", "round"}``).
    A race stays "next" until its result is actually in the data, at which point
    the box rolls over to the following round. This keeps the hero correct from
    the moment new data deploys, instead of waiting for the UTC day to flip.
    """
    races = sorted(schedule.get("races", []), key=lambda r: int(r["round"]))
    if not races:
        return None

    have_season = _to_int((asof or {}).get("season"))
    have_round = _to_int((asof or {}).get("round"))
    if have_round is None:
        return races[0]  # no results yet this season -> the opener is next

    sched_season = _to_int(schedule.get("season"))
    if sched_season is not None and have_season is not None and have_season < sched_season:
        return races[0]  # latest result is from a prior season -> round 1 is next

    for r in races:
        if int(r["round"]) > have_round:
            return r
    return None  # we have the final round -> season complete


def _iso_datetime(race: dict) -> str:
    return f"{race['date']}T{race.get('time') or '00:00:00Z'}"


def _session_when(date: str, time: str | None) -> str:
    """One session as "Sun 28 Jun &middot; 13:00 UTC"; empty if the date is unusable."""
    try:
        d = dt.datetime.strptime(date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    base = f"{d:%a} {d.day} {d:%b}"
    return f"{base} &middot; {time[:5]} UTC" if time else base


def _when_line(race: dict) -> str:
    """Race and qualifying on one line, server-rendered in UTC.

    ``podigami.js`` rewrites both halves into the visitor's timezone; this UTC
    form is what a reader without JS gets, and what the page ships in its HTML.
    """
    parts = [f"Race {_session_when(race['date'], race.get('time'))}".strip()]
    quali = _session_when(race.get("qualifyingDate", ""), race.get("qualifyingTime"))
    if quali:
        parts.append(f"Quali {quali}")
    return " &middot; ".join(parts)


def render_next_race(schedule: dict, asof: dict | None = None, links: dict | None = None) -> str:
    nxt = pick_next_race(schedule, asof)
    if not nxt:
        return (
            '<section class="next-race nr-empty">'
            '<span class="nr-tag">Next race</span>'
            '<span class="nr-name">Season complete &mdash; see you next year</span>'
            "</section>"
        )
    fl = flag_svg(nxt["country"])
    name = esc(nxt["raceName"])
    url = race_url(links or {}, schedule.get("season", ""), nxt["round"], nxt["raceName"])
    name_html = f'<a href="{esc(url)}" target="_blank" rel="noopener">{name}</a>'
    # With a track outline the circuit's identity captions the plate; without one
    # there is no plate to caption, so it stays on the locality line rather than
    # disappearing with it.
    place = esc(f"{nxt['locality']}, {nxt['country']}")
    circuit_bits = [esc(nxt["circuitName"])]
    if nxt.get("lengthKm"):
        circuit_bits.append(f"{nxt['lengthKm']} km")
    plate = ""
    if nxt.get("trackPath"):
        plate = (
            f'<div class="nr-art">'
            f'<svg class="nr-track" viewBox="{esc(nxt["trackViewBox"])}" '
            f'fill="none" aria-hidden="true"><path d="{esc(nxt["trackPath"])}"/></svg>'
            f'<div class="nr-plate-cap">{" &middot; ".join(circuit_bits)}</div>'
            f"</div>"
        )
        circuit_line = place
    else:
        circuit_line = " &middot; ".join([circuit_bits[0], place, *circuit_bits[1:]])
    qd = nxt.get("qualifyingDate")
    quali_attr = ""
    if qd and _session_when(qd, nxt.get("qualifyingTime")):
        qt = nxt.get("qualifyingTime") or "00:00:00Z"
        quali_attr = f' data-quali-datetime="{esc(f"{qd}T{qt}")}"'
    return (
        f'<section class="next-race{"" if plate else " nr-noplate"}"'
        f' data-datetime="{esc(_iso_datetime(nxt))}"{quali_attr}>'
        f'  <div class="nr-main">'
        f'    <span class="nr-tag">Next race</span>'
        f'    <div class="nr-head">'
        f"      {fl}"
        f'      <span class="nr-round">Round {esc(nxt["round"])} / {esc(schedule.get("totalRounds", ""))}</span>'
        f"    </div>"
        f'    <h2 class="nr-name">{name_html}</h2>'
        f'    <div class="nr-circuit">{circuit_line}</div>'
        f'    <div class="nr-when">'
        f'      <span class="nr-cd-label">Lights out in</span>'
        f'      <span class="nr-countdown" data-countdown></span>'
        f'      <span class="nr-date">{_when_line(nxt)}</span>'
        f"    </div>"
        f"  </div>"
        f"  {plate}"
        f"</section>"
    )


def combos_link(names: list[str]) -> str:
    """Combos-page URL pre-filtered to a specific trio (driver full names).

    The combos page reads these ``d`` params into its three driver filters, so
    the table lands filtered down to exactly this trio. They carry the names the
    table shows (``driver_name``), which is what its filters match against.
    """
    query = urllib.parse.urlencode([("d", driver_name(n)) for n in names])
    return f"combos.html?{query}"


def _combo_key(driver_ids: list[str]) -> tuple[str, ...]:
    return tuple(sorted(driver_ids))


def _lookup_combo(trio_ids: list[str], combos: list[dict]) -> dict | None:
    key = _combo_key(trio_ids)
    for c in combos:
        if _combo_key(c["driverIds"]) == key:
            return c
    return None


def render_last_race_drivers(pod: dict, constructor_map: dict, meta: dict) -> str:
    """The three podium steps of the last race.

    A step held by a car two drivers shared renders both of them inside that one
    step, marked as shared — the podium stays three steps tall. Dormant for
    modern races; the last shared drive was the 1960 Argentine Grand Prix.
    """
    steps: list[str] = []
    for pos in (1, 2, 3):
        spans = []
        for d in slot_drivers(pod, f"p{pos}"):
            entry = {
                "name": d["name"],
                "driverId": d["driverId"],
                "constructorId": constructor_map.get(d["driverId"], ""),
            }
            v = driver_view(entry, meta)
            spans.append(
                f'<span class="lr-driver" style="--team:{v["color"]}">'
                f'<span class="cd-dot"></span>'
                f'<span class="lr-code">{esc(v["code"])}</span>'
                f"</span>"
            )
        if len(spans) > 1:
            shared_desc = esc("One car, shared by both drivers")
            steps.append(
                f'<span class="lr-step lr-shared"'
                f' title="{shared_desc}" aria-label="{shared_desc}">' + "".join(spans) + "</span>"
            )
        else:
            steps.append(spans[0])
    return '<span class="lr-sep">/</span>'.join(steps)


def render_last_race(
    schedule: dict,
    podiums: list[dict],
    combos: list[dict],
    meta: dict,
    driver_form: list[dict],
    links: dict | None = None,
) -> str:
    links = links or {}
    # The last race is the most recent one we actually have a podium for; this is
    # the same source of truth as podigami.json's asOf, so the box rolls over the
    # instant new results land rather than at the next UTC midnight.
    if not podiums:
        return ""
    pod = max(podiums, key=lambda p: (int(p["season"]), int(p["round"])))
    rnd = pod["round"]
    # Enrich with the schedule entry (flag/country) when the race is on this
    # season's calendar; otherwise fall back to the podium's own race name.
    last = next(
        (
            r
            for r in schedule.get("races", [])
            if r["round"] == rnd and schedule.get("season") == pod["season"]
        ),
        {"country": "", "raceName": pod["raceName"], "round": rnd},
    )

    fl = flag_svg(last["country"])
    name = esc(last["raceName"])
    name_url = race_url(links, pod["season"], last["round"], last["raceName"])

    constructor_map = {d["driverId"]: d.get("constructorId", "") for d in driver_form}
    trio_ids = [pod["p1"]["driverId"], pod["p2"]["driverId"], pod["p3"]["driverId"]]
    trio_names = [pod[f"p{pos}"]["name"] for pos in (1, 2, 3)]
    trio_html = render_last_race_drivers(pod, constructor_map, meta)

    combo = _lookup_combo(trio_ids, combos)

    # If this trio is in the data, link it to its stats on the combos page.
    trio_block = f'<span class="lr-trio">{trio_html}</span>'
    if combo:
        trio_block = (
            f'<a class="combo-link" href="{esc(combos_link(trio_names))}"'
            f' aria-label="See this trio on the combos page"'
            f' title="See this trio on the combos page">{trio_block}</a>'
        )
    if combo and combo["count"] == 1:
        status_html = '<span class="lr-podigami">PODIGAMI</span>'
    elif combo:
        cnt = combo["count"]
        prev = combo.get("races", [])
        second_last = prev[-2] if len(prev) >= 2 else combo["lastRace"]
        repeat_url = race_url(
            links, second_last["season"], second_last["round"], second_last["raceName"]
        )
        status_html = (
            f'<span class="lr-status">{_ordinal(cnt)} time'
            f' &middot; last <a class="lr-link" href="{esc(repeat_url)}"'
            f' target="_blank" rel="noopener">'
            f"{esc(second_last['season'])} R{esc(second_last['round'])} &middot;"
            f" {esc(second_last['raceName'])}</a></span>"
        )
    else:
        status_html = '<span class="lr-podigami">PODIGAMI</span>'

    return (
        f'<section class="last-race">'
        f'<span class="lr-tag">Last race</span>'
        f"{fl}"
        f'<a class="lr-name" href="{esc(name_url)}" target="_blank" rel="noopener">'
        f"R{esc(rnd)} &middot; {name}</a>"
        f"{trio_block}"
        f"{status_html}"
        # The status describes the trio, so it follows it; this spacer takes the
        # slack that used to be handed to a margin-left:auto push to the far edge.
        f'<span class="lr-sp"></span>'
        f"</section>"
    )


def render_hero(
    top: dict,
    chance: float,
    meta: dict,
    acc_note: str = "",
    pre_chance: float | None = None,
    race_name: str = "",
) -> str:
    """One surface, one hairline: the chance and its sentence share a head row,
    the trio sits below it.

    The head is a figure beside a single text block (label + movement line) so
    the two centre against each other; hanging the figure off the label's first
    baseline left it riding high whenever the text ran to two lines.
    """
    # Post-qualifying the trio reads front-to-back, matching the grid a reader
    # is looking at. Pre-qualifying every slot is None, so the model's own order
    # survives (sorted is stable).
    entries = sorted(top["perDriver"], key=lambda p: _to_int(p.get("gridPosition")) or 99)
    cards = []
    for p in entries:
        v = driver_view(p, meta)
        grid = _to_int(p.get("gridPosition"))
        meta_bits = [b for b in (v["team"], f"starts {_ordinal(grid)}" if grid else "") if b]
        cards.append(
            f'<div class="hero-driver" style="--team:{v["color"]};--team-ink:{v["ink"]}">'
            f'<span class="hd-name">{esc(v["name"])}</span>'
            f'<span class="hd-team">{esc(" · ".join(meta_bits))}</span>'
            f"</div>"
        )
    drivers = "".join(cards)

    where = f"at the {esc(race_name)}" if race_name else "at the next race"
    sub = ""
    if pre_chance is not None:
        if round(chance) > round(pre_chance):
            cls = "up"
        elif round(chance) < round(pre_chance):
            cls = "down"
        else:
            cls = "flat"
        sub = (
            f'<p class="hc-sub"><span class="hc-updated">Updated after qualifying</span>'
            f' &middot; <span class="hc-delta hc-delta-{cls}">was {pre_chance:.0f}%'
            f" before the grid was set</span></p>"
        )
    return (
        f'<section class="hero">'
        f'  <div class="hero-head">'
        f'    <span class="hc-num">{chance:.0f}%</span>'
        f'    <div class="hero-head-text">'
        f'      <p class="hc-label">chance of a podium trio Formula&nbsp;1 has never seen {where}'
        f'<span class="info-tip info-tip-sm" tabindex="0" aria-label="More info">'
        f'<span class="info-icon">i</span>'
        f'<span class="info-bubble">The overall probability that any brand-new podium trio appears at the next race, not just the top-ranked one.</span>'
        f"</span>"
        f"      </p>{sub}"
        f"    </div>"
        f"  </div>"
        f'  <div class="hero-pick">'
        f'    <p class="hp-label">Most likely new trio &middot; {top["prob"]:.1f}%</p>'
        f'    <div class="hero-drivers">{drivers}</div>'
        f"  </div>"
        f'  <p class="hp-prob">{acc_note}</p>'
        f"</section>"
    )


def _trio_chips(per_driver: list[dict], meta: dict) -> str:
    """The team-coloured TLA chips shared by candidate rows and board rows."""
    chips = []
    for p in per_driver:
        v = driver_view(p, meta)
        gp = p.get("gridPosition")
        grid_chip = f'<span class="cd-grid">P{gp}</span>' if gp else ""
        chips.append(
            f'<span class="cd" style="--team:{v["color"]}" title="{esc(display_name(v["name"]))}">'
            f'<span class="cd-dot"></span><span class="cd-code">{esc(v["code"])}</span>{grid_chip}'
            f"</span>"
        )
    return '<span class="cd-sep">/</span>'.join(chips)


def _cand_row(names: str, pct: int, prob: float, cls: str = "", extra: str = "") -> str:
    """One board row. No rank column: the list is already ordered, and the bar
    and percentage carry the ranking without spending width on a number."""
    return (
        f'<li class="cand{cls}">'
        f'<div class="cand-body">'
        f'  <div class="cand-names">{names}{extra}</div>'
        f'  <div class="cand-bar-wrap"><div class="cand-bar" style="width:{pct}%"></div></div>'
        f"</div>"
        f'<span class="cand-prob">{prob:.2f}%</span>'
        f"</li>"
    )


def _board_history(row: dict, combos: list[dict] | None) -> tuple[str, str]:
    """The hover/tap bubble for an already-happened trio: how many times and when.

    combos.json and podiums.json are derived from the same source, so a lookup
    miss means upstream drift, not a page that should break — the row then
    renders plainly, with no bubble and nothing to hover.
    """
    combo = _lookup_combo(row["driverIds"], combos or [])
    if not combo:
        return "", ""
    n = combo["count"]
    last = combo.get("lastRace") or {}
    when = f"{last.get('season', '')} {last.get('raceName', '')}".strip()
    times = f"{n} time{'s' if n != 1 else ''}"
    label = f"Happened {times}" + (f" — last: {when}" if when else "")
    link = combos_link(combo.get("drivers") or [])
    bubble = (
        f'<span class="info-bubble trio-bubble">'
        f"<b>Happened {esc(times)}</b>"
        + (f"<br>Last: {esc(when)}" if when else "")
        + f'<br><a href="{esc(link)}">See all &rarr;</a>'
        f"</span>"
    )
    return bubble, label


def _board_rows(board: list[dict], meta: dict, driver_form: list[dict], combos) -> list[str]:
    by_id = {d["driverId"]: d for d in (driver_form or [])}

    def entry(did: str) -> dict:
        # driverForm carries name/constructor (and gridPosition post-quali) for
        # every entrant; meta and the id itself are the fallbacks.
        return by_id.get(did) or {
            "driverId": did,
            "name": meta.get(did, {}).get("name")
            or " ".join(w.capitalize() for w in did.split("_")),
            "constructorId": "",
        }

    top = board[0]["prob"] or 1
    rows = []
    for r in board:
        names = _trio_chips([entry(d) for d in r["driverIds"]], meta)
        pct = round(100 * r["prob"] / top)
        if not r["happened"]:
            rows.append(
                _cand_row(names, pct, r["prob"], " cand-new", '<span class="cand-pill">NEW</span>')
            )
            continue
        bubble, label = _board_history(r, combos)
        if bubble:
            names = (
                f'<span class="trio-tip" tabindex="0" role="button" aria-expanded="false"'
                f' aria-label="{esc(label)}">{names}{bubble}</span>'
            )
        rows.append(_cand_row(names, pct, r["prob"], " cand-done"))
    return rows


def render_candidates(
    cands: list[dict],
    meta: dict,
    form_html: str = "",
    grid_aware: bool = False,
    board: list[dict] | None = None,
    driver_form: list[dict] | None = None,
    combos: list[dict] | None = None,
) -> str:
    """The ranked panel: the trio board when there is one, else the new-only list.

    The fallback is not dead code. deploy.yml builds main from committed data and
    a promotion's three-way merge keeps main's newer data/, so the live site can
    run on a podigami.json written before ``trioBoard`` existed.
    """
    if board:
        rows = _board_rows(board, meta, driver_form or [], combos)
        tip = (
            "Every trio the model rates as a live chance at the next race. "
            "Highlighted ones have never shared a podium; hover or tap the rest "
            "to see when they did."
        )
    elif cands:
        top = cands[0]["prob"] or 1
        rows = [
            _cand_row(_trio_chips(c["perDriver"], meta), round(100 * c["prob"] / top), c["prob"])
            for c in cands
        ]
        tip = (
            "Trios that have never shared a podium, ranked by the model's "
            "probability they do it next."
        )
    else:
        return ""
    badge = '<span class="panel-badge">grid-aware</span>' if grid_aware else ""
    return (
        f'<section class="panel">'
        f"  <h2>Most likely trios"
        f'    <span class="info-tip" tabindex="0" aria-label="More info">'
        f'      <span class="info-icon">i</span>'
        f'      <span class="info-bubble">{tip}</span>'
        f"    </span>"
        f"  {badge}</h2>"
        f'  <div class="cand-board">'
        f'    <div class="cand-scroll">'
        f'      <ol class="cand-list">{"".join(rows)}</ol>'
        f"    </div>"
        f"  </div>"
        f"  {form_html}"
        f"</section>"
    )


def render_form(
    form: list[dict],
    using_constructors: bool,
    meta: dict,
    half_life: float = 6.0,
    is_v2: bool = False,
) -> str:
    """Driver-form tower collapsed behind a <details> toggle.

    The returned block is embedded inside the candidates panel by
    render_candidates(), not emitted as a standalone section.
    """
    show = [d for d in form if d["weight"] > 0][:14]
    mx = max((d["weight"] for d in show), default=1)
    rows = []
    for d in show:
        v = driver_view(d, meta)
        pct = round(100 * d["weight"] / mx)
        rows.append(
            f'<div class="tower-row" style="--team:{v["color"]};--team-ink:{v["ink"]}">'
            f'<span class="tr-num">{esc(v["number"]) if v["number"] else ""}</span>'
            f'<span class="tr-code">{esc(v["code"])}</span>'
            f'<span class="tr-name">{esc(v["surname"])}</span>'
            f'<span class="tr-team">{esc(v["team"])}</span>'
            f'<div class="tr-bar"><i style="width:{pct}%"></i></div>'
            f'<span class="tr-w">{d["weight"]:.1f}</span>'
            f"</div>"
        )
    if is_v2:
        sub = (
            "Each driver's modelled strength &mdash; their own rating plus their car's, "
            "learned race by race from every finishing and qualifying order since 1950."
        )
    else:
        sub = f"Each driver's podium weight &mdash; recent podiums decay over ~{half_life:.0f} races, with a boost for this season"
        if using_constructors:
            sub += " and constructor strength"
        sub += "."
    return (
        f'<details class="form-details">'
        f"<summary>"
        f'<span class="fd-closed">Show current form &#9662;</span>'
        f'<span class="fd-open">Hide current form &#9652;</span>'
        f"</summary>"
        f'<p class="form-caption">{sub}</p>'
        f'<div class="form-tower">{"".join(rows)}</div>'
        f"</details>"
    )


def _quickpicks(lo: int, current: int, counts: dict) -> str:
    """One-tap year chips for the timeline: first season, record season
    (earliest wins ties), and the current season. Duplicates collapse."""
    picks: list[tuple[int, str]] = [(lo, "first season")]
    if counts:
        rec_year_s, rec_n = max(counts.items(), key=lambda kv: (kv[1], -int(kv[0])))
        rec_year = int(rec_year_s)
        if rec_year not in {lo, current}:
            picks.append((rec_year, f"record: {rec_n} new"))
    if current != lo:
        picks.append((current, "this season"))
    chips = "".join(
        f'<button type="button" class="tl-chip" data-year="{y}">{y} &middot; {esc(label)}</button>'
        for y, label in picks
    )
    return f'<div class="tl-chips">{chips}</div>'


def render_timeline(data: dict) -> str:
    lo, hi = data["seasonRange"]
    current = int(data["currentSeason"])
    counts = data["seasonCounts"]
    mx = max(counts.values()) if counts else 1
    bars = []
    options = []
    for y in range(lo, hi + 1):
        n = counts.get(str(y), 0)
        h = round(100 * n / mx) if mx else 0
        bars.append(
            f'<span class="tl-bar" data-season="{y}" title="{y}: {n} new trio(s)" '
            f'style="height:{max(h, 2)}%"></span>'
        )
        sel = " selected" if y == current else ""
        label = f"{y} — {n} new" if n else str(y)
        options.append(f'<option value="{y}"{sel}>{label}</option>')
    # --tl-n drives the CSS that aligns the slider thumb with the bar centers:
    # one bar (and one slider step) per season, so the count must match exactly.
    n_seasons = hi - lo + 1
    return (
        f'<section class="panel timeline" style="--tl-n:{n_seasons}">'
        f'  <div class="tl-header">'
        f"    <h2>New podiums through the years"
        f'      <span class="info-tip" tabindex="0" aria-label="More info">'
        f'        <span class="info-icon">i</span>'
        f'        <span class="info-bubble">Every trio that debuted on a podium that season. Drag the slider or click a bar to explore.</span>'
        f"      </span>"
        f"    </h2>"
        f'    <div class="tl-readout"><span id="tl-year">{current}</span>'
        f'      <span class="tl-count" id="tl-count"></span></div>'
        f"  </div>"
        f"  {_quickpicks(lo, current, counts)}"
        f'  <div class="tl-spark">{"".join(bars)}</div>'
        f'  <div class="tl-controls">'
        f'    <input type="range" id="tl-slider" min="{lo}" max="{hi}" value="{current}" step="1" aria-label="Timeline year">'
        f"  </div>"
        f'  <div class="tl-select-wrap">'
        f'    <select id="tl-select" aria-label="Timeline year">{"".join(options)}</select>'
        f"  </div>"
        f'  <ul class="tl-list" id="tl-list"></ul>'
        f"</section>"
    )


def render_accuracy_note(ev: dict) -> str:
    """The backtest result as a sentence for the hero's footing line.

    Replaces the tracked-out "BACKTESTED top-3 x%" pill: it was the only shouting
    left in the block, and the same fact reads fine in plain words.
    """
    if not ev:
        return ""
    top3 = round(100 * ev["chosen"]["top3"])
    return (
        f'<span title="Backtested model accuracy">Across every race since '
        f"{ev['evalWindow']['test'][0]} the model put the real trio in its "
        f"top three {top3}% of the time.</span>"
    )


def faq_items(
    data: dict,
    ev: dict,
    total_combos: int,
    total_races: int,
    possible_trios: int,
    grid_size: int,
    lo: int,
) -> list[tuple[str, str]]:
    """Ordered (question, answer-HTML) FAQ pairs — the single source feeding both
    the visible FAQ (``render_faq``) and the FAQPage schema (``json_ld_schemas``)."""
    mp = ev.get("modelParams", {}) if ev else {}
    half_life = mp.get("halfLife", 6)
    is_v2 = (data.get("params") or {}).get("model") == "dbpl-v2"
    if is_v2:
        how_it_works = (
            "A <strong>Bayesian rating engine</strong> keeps a skill rating for every driver "
            "and every car, updated after each qualifying session and race since 1950 "
            "(uncertainty widens between seasons and when the rules change). For the next race "
            "it blends those ratings with each car&rsquo;s reliability record (DNF risk) and "
            "the circuit&rsquo;s character, then simulates the podium hundreds of times with a "
            "<strong>Plackett&ndash;Luce model</strong> to rank the never-before-seen trios."
        )
    else:
        how_it_works = (
            f"A <strong>Plackett&ndash;Luce model</strong> estimates each driver&rsquo;s current "
            f"strength from their recent podium finishes, weighted toward recency (halved every "
            f"~{half_life:.0f} races). It then calculates the probability of every possible trio and "
            f"ranks the never-before-seen ones from most to least likely."
        )
    items = [
        ("How does the prediction model work?", how_it_works),
        (
            "What does the headline percentage mean?",
            "It&rsquo;s the overall probability that <em>any</em> brand-new podium trio appears at "
            "the next race &mdash; not just the top-ranked one, but any combination that has never "
            "happened before.",
        ),
        (
            "How accurate is the model?",
            f"Backtested on seasons it never saw during tuning, the model places the actual podium "
            f"trio in its top&nbsp;3 predictions {round(100 * ev['chosen']['top3'])}% of the time. "
            f"F1 podiums are inherently high-variance, so exact-trio hits are rare by nature."
            if ev and ev.get("chosen")
            else "The model is backtested on historical seasons it never saw during tuning. "
            "F1 podiums are inherently high-variance, so exact-trio hits are rare by nature.",
        ),
        (
            "What is &ldquo;current form&rdquo; based on?",
            "Each driver&rsquo;s strength is their own rating plus their car&rsquo;s, learned "
            "from every finishing and qualifying order &mdash; so a driver can rate higher than "
            "their recent podium count suggests when the car underneath them is quick."
            if is_v2
            else "Each driver&rsquo;s podium weight uses a recency decay &mdash; recent podiums "
            "count more than older ones. The weight also includes a boost for the current "
            "season and can factor in constructor strength.",
        ),
        (
            "What does &ldquo;podigami&rdquo; mean?",
            f"Podigami blends &ldquo;podium&rdquo; and &ldquo;"
            f'<a href="https://en.wikipedia.org/wiki/Scorigami" target="_blank" rel="noopener">scorigami</a>'
            f"&rdquo; &mdash; it&rsquo;s the practice of tracking F1 podium trios that have never "
            f'happened before. Since {lo}, <a href="combos.html"><strong>{total_combos:,}</strong></a> unique trios have '
            f"appeared across <strong>{total_races:,}</strong> races. Today&rsquo;s {grid_size}-driver "
            f"grid can produce <strong>{possible_trios:,}</strong> different trios per race, so most "
            f"combinations simply haven&rsquo;t come up yet.",
        ),
        (
            "Why do some 1950s podiums list four drivers?",
            "Until 1960 a driver could hand his car to a team-mate mid-race, and both were "
            "classified at the finishing position. The 1956 Belgian Grand Prix is the clearest "
            "case: Cesare Perdisa and Stirling Moss shared the third-placed Maserati, so that "
            "race put two different trios on the podium at once. Eighteen races in history work "
            "this way, and every trio they produced counts as having happened.",
        ),
        (
            "What else is on this site?",
            'Four deeper dives: <a href="combos.html">Combinations</a> lists every unique '
            'podium trio in history; <a href="overdue.html">Overdue</a> ranks the trios that '
            'keep almost happening; <a href="unlikeliest.html">Unlikeliest</a> celebrates the '
            'podiums that defied the odds; and <a href="soulmates.html">Soulmates</a> maps '
            "which drivers keep meeting on the podium.",
        ),
    ]
    if is_v2:
        rung = next(
            (r for r in (ev.get("ladder") or []) if r.get("model") == "v2 post-quali +grid"),
            None,
        )
        cite = (
            f" In backtests, the grid-aware update places the actual podium trio in its "
            f"top&nbsp;3 {round(100 * rung['top3'])}% of the time."
            if rung
            else ""
        )
        items.insert(
            2,
            (
                "Why does the prediction update after qualifying?",
                "Qualifying is the most informative pre-race session: it reveals current pace "
                "and fixes the starting grid, whose track-position advantage has strong "
                "historical precedent. Once the grid is set, the model feeds the qualifying "
                "order through its rating engine and adds a grid-position term scaled by how "
                "processional the circuit historically is &mdash; stronger where overtaking "
                "is hard, weaker where the grid gets shuffled." + cite,
            ),
        )
    return items


def render_faq(
    data: dict,
    ev: dict,
    total_combos: int,
    total_races: int,
    possible_trios: int,
    grid_size: int,
    lo: int,
) -> str:
    items = faq_items(data, ev, total_combos, total_races, possible_trios, grid_size, lo)
    entries = []
    for q, a in items:
        entries.append(
            f'<details class="faq-item">'
            f'<summary class="faq-q">{q}</summary>'
            f'<div class="faq-a"><p>{a}</p></div>'
            f"</details>"
        )
    return (
        f'<section class="panel faq-section">'
        f"  <h2>Frequently asked questions</h2>"
        f"  {''.join(entries)}"
        f"</section>"
    )


def _plain(text: str) -> str:
    """Strip HTML tags and unescape entities -> plain text for JSON-LD answers."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def json_ld_schemas(
    schedule: dict,
    asof: dict | None,
    description: str,
    faq: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """Structured data for the landing page: the organisation and site, the FAQ
    (as a FAQPage), plus, when the season is still running, the next Grand Prix
    as a SportsEvent."""
    schemas: list[dict] = [
        organization_schema(),
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "F1 Podigami",
            "url": f"{SITE_URL}/",
            "description": description,
        },
    ]
    if faq:
        schemas.append(
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": _plain(q),
                        "acceptedAnswer": {"@type": "Answer", "text": _plain(a)},
                    }
                    for q, a in faq
                ],
            }
        )
    nxt = pick_next_race(schedule, asof) if schedule else None
    if nxt:
        schemas.append(
            {
                "@context": "https://schema.org",
                "@type": "SportsEvent",
                "name": nxt["raceName"],
                "sport": "Formula 1",
                "url": f"{SITE_URL}/",
                "eventStatus": "https://schema.org/EventScheduled",
                "startDate": _iso_datetime(nxt),
                "location": {
                    "@type": "Place",
                    "name": nxt["circuitName"],
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": nxt["locality"],
                        "addressCountry": nxt["country"],
                    },
                },
            }
        )
    return schemas


def live_post_quali(data: dict) -> dict | None:
    """The postQuali block only while it still describes an *upcoming* race.

    The block predicts the race after ``asOf``. If ``asOf`` has caught up to (or
    passed) that round the race is already over, so the grid-aware chance is
    history and the hero must fall back to the pre-quali numbers. Compared
    numerically on (season, round) — rounds restart each season, and "9" > "10"
    as strings. Anything unreadable is dropped: a pre-quali hero is always
    defensible, a post-quali hero for a finished race never is.
    """
    post = data.get("postQuali")
    if not post:
        return None
    try:
        covers = (int(post["season"]), int(post["round"]))
        as_of = (int(data["asOf"]["season"]), int(data["asOf"]["round"]))
    except (KeyError, TypeError, ValueError):
        return None
    return post if covers > as_of else None


def main() -> int:
    data = load_podigami().model_dump()
    season = data["currentSeason"]
    chance = data["chanceNextRaceNew"]
    cands = data["candidates"]
    # Post-quali overrides the pre-quali headline once the grid is set; the
    # top-level `chance` stays the pre-quali number the delta line cites.
    post = live_post_quali(data)
    active_chance = post["chanceNextRaceNew"] if post else chance
    active_cands = post["candidates"] if post else cands
    active_form = post["driverForm"] if post else data["driverForm"]
    lo, hi = data["seasonRange"]

    using_constructors = data.get("params", {}).get("usingConstructors", False)

    combos_list = load_combos()
    podiums_list = load_podiums()
    total_combos = len(combos_list)
    total_races = len(podiums_list)
    grid_size = data["gridSize"]
    possible_trios = grid_size * (grid_size - 1) * (grid_size - 2) // 6

    grid_doc = load_current_drivers()
    meta = {d.driverId: d.model_dump() for d in grid_doc.drivers}

    schedule = {}
    if (DATA_DIR / "schedule.json").exists():
        schedule = load_schedule().model_dump()
    links = load_race_links()
    # Enrich the timeline entries with official F1 result URLs (wiki fallback) so the
    # client-side slider (podigami.js) links out to F1 like the rest of the page,
    # and give them the driver names the rest of the site shows.
    # Build-time only — the committed podigami.json is left untouched.
    for _season, _trios in data["bySeason"].items():
        for _trio in _trios:
            _trio["names"] = [driver_name(n) for n in _trio["names"]]
            fr = _trio.get("firstRace")
            if fr:
                fr["url"] = race_url(links, _season, fr["round"], fr["raceName"])
    next_race = render_next_race(schedule, data.get("asOf"), links) if schedule else ""
    combos_dicts = [c.model_dump() for c in combos_list]
    podiums_dicts = [p.model_dump() for p in podiums_list]
    last_race = (
        render_last_race(schedule, podiums_dicts, combos_dicts, meta, data["driverForm"], links)
        if schedule
        else ""
    )

    model_eval = {}
    if (DATA_DIR / "model_eval.json").exists():
        model_eval = load_model_eval().model_dump()

    # Discovery hooks: tolerant loads (like schedule/model_eval above) so a
    # missing dataset degrades to a stat-less card instead of failing the build.
    soulmates_data = load_soulmates() if (DATA_DIR / "soulmates.json").exists() else None
    overdue_data = load_overdue() if (DATA_DIR / "overdue.json").exists() else None
    unlikeliest_data = load_unlikeliest() if (DATA_DIR / "unlikeliest.json").exists() else None

    hook_combos = combos_hook(total_combos, lo)
    hook_soulmates = soulmates_hook(soulmates_data)
    hook_row = (
        f'<div class="hook-row">{overdue_hook(overdue_data)}'
        f"{unlikeliest_hook(unlikeliest_data)}</div>"
    )
    explore = explore_grid()

    acc_note = render_accuracy_note(model_eval)
    # The hero predicts the race after asOf — the same one the next-race box names.
    hero_race = pick_next_race(schedule, data.get("asOf")) if schedule else None
    hero = (
        render_hero(
            active_cands[0],
            active_chance,
            meta,
            acc_note,
            pre_chance=chance if post else None,
            race_name=hero_race["raceName"] if hero_race else "",
        )
        if active_cands
        else ""
    )
    form = render_form(
        active_form,
        using_constructors,
        meta,
        data["params"].get("halfLife", 6.0),
        is_v2=data["params"].get("model") == "dbpl-v2",
    )
    active_board = (post or data).get("trioBoard") or []
    candidates = render_candidates(
        active_cands,
        meta,
        form,
        grid_aware=bool(post),
        board=active_board,
        driver_form=active_form,
        combos=combos_dicts,
    )
    timeline = render_timeline(data)
    faq_pairs = faq_items(
        data, model_eval, total_combos, total_races, possible_trios, grid_size, lo
    )
    faq = render_faq(data, model_eval, total_combos, total_races, possible_trios, grid_size, lo)

    # Embedded data for the slider (only what the client needs).
    # `</script>`-neutralized so an embedded string can never prematurely close the tag.
    embed = json.dumps(
        {
            "bySeason": data["bySeason"],
            "seasonCounts": data["seasonCounts"],
            "currentSeason": season,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    meta_description = (
        f"F1 podium scorigami: tracking the podium trios Formula 1 has never seen. "
        f"A model predicts the most likely brand-new trio for the next {season} race."
    )
    page = f"""{
        head(
            "F1 Podium Scorigami — New Trio Tracker & Predictions",
            "podigami.css",
            description=meta_description,
            page_path="index.html",
            json_ld=json_ld_schemas(schedule, data.get("asOf"), meta_description, faq_pairs),
        )
    }
<body>
{nav("index.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Podigami</h1>
        <p class="tagline">Keeping track of every F1 podium trio ever
        and predicting the next one.</p>
    </div>
</header>
<main>
    <div class="container">
        {next_race}
        {last_race}
        {hero}
        {candidates}
        {hook_combos}
        {hook_soulmates}
        {timeline}
        {hook_row}
        {faq}
        {explore}
    </div>
</main>
{FOOTER}
<script type="application/json" id="podigami-data">{embed}</script>
<script src="{asset("podigami.js")}"></script>
<script src="{asset("theme.js")}"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(
        f"  season {season}: P(new)={active_chance}%, "
        f"{len(active_cands)} candidates, seasons {lo}-{hi}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
