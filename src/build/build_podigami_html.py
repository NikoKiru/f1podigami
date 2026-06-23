"""Render data/podigami.json into dist/index.html (the landing page).

Shows the current season's most likely *brand-new* podium trio ("podigami"),
a ranked list of contenders, the current-form grid, and a year-slider timeline
of every trio that debuted in each season.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _layout import FOOTER, head, nav  # noqa: E402  (needs the sys.path entry above)
from flags import flag_svg  # noqa: E402
from team_colors import team_color, text_on  # noqa: E402

from datalib import (  # noqa: E402
    DATA_DIR,
    load_combos,
    load_current_drivers,
    load_model_eval,
    load_podigami,
    load_podiums,
    load_schedule,
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
    name = entry["name"]
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


def _num_chip(v: dict) -> str:
    return f'<span class="d-num">{esc(v["number"])}</span>' if v["number"] else ""


def pick_next_race(schedule: dict, today: str | None = None) -> dict | None:
    """Return the next race whose date is today or later, else None."""
    today = today or dt.date.today().isoformat()
    races = sorted(schedule.get("races", []), key=lambda r: int(r["round"]))
    for r in races:
        if r["date"] >= today:
            return r
    return None


def pick_last_race(schedule: dict, today: str | None = None) -> dict | None:
    """Return the race immediately before the next upcoming one, else None."""
    today = today or dt.date.today().isoformat()
    races = sorted(schedule.get("races", []), key=lambda r: int(r["round"]))
    prev = None
    for r in races:
        if r["date"] >= today:
            return prev
        prev = r
    return prev


def _iso_datetime(race: dict) -> str:
    return f"{race['date']}T{race.get('time') or '00:00:00Z'}"


def _fallback_when(race: dict) -> str:
    d = dt.datetime.strptime(race["date"], "%Y-%m-%d")
    base = f"{d:%a} {d.day} {d:%b}"
    t = race.get("time", "")
    return f"{base} &middot; {t[:5]} UTC" if t else base


def render_next_race(schedule: dict, today: str | None = None) -> str:
    nxt = pick_next_race(schedule, today)
    if not nxt:
        return (
            '<section class="next-race nr-empty">'
            '<span class="nr-tag">Next race</span>'
            '<span class="nr-name">Season complete &mdash; see you next year</span>'
            "</section>"
        )
    fl = flag_svg(nxt["country"])
    name = esc(nxt["raceName"])
    name_html = (
        f'<a href="{esc(nxt["url"])}" target="_blank" rel="noopener">{name}</a>'
        if nxt.get("url")
        else name
    )
    parts = [esc(nxt["circuitName"]), esc(f"{nxt['locality']}, {nxt['country']}")]
    if nxt.get("lengthKm"):
        parts.append(f"{nxt['lengthKm']} km")
    circuit_line = " &middot; ".join(parts)
    track = ""
    if nxt.get("trackPath"):
        track = (
            f'<svg class="nr-track" viewBox="{esc(nxt["trackViewBox"])}" '
            f'fill="none" aria-hidden="true"><path d="{esc(nxt["trackPath"])}"/></svg>'
        )
    return (
        f'<section class="next-race" data-datetime="{esc(_iso_datetime(nxt))}">'
        f'  <div class="nr-main">'
        f'    <span class="nr-tag">Next race</span>'
        f'    <div class="nr-head">'
        f"      {fl}"
        f'      <span class="nr-round">Round {esc(nxt["round"])} / {esc(schedule.get("totalRounds", ""))}</span>'
        f"    </div>"
        f'    <h2 class="nr-name">{name_html}</h2>'
        f'    <div class="nr-circuit">{circuit_line}</div>'
        f'    <div class="nr-when">'
        f'      <span class="nr-date">{_fallback_when(nxt)}</span>'
        f'      <span class="nr-countdown" data-countdown></span>'
        f"    </div>"
        f"  </div>"
        f'  <div class="nr-art">{track}</div>'
        f"</section>"
    )


def _combo_key(driver_ids: list[str]) -> tuple[str, ...]:
    return tuple(sorted(driver_ids))


def _lookup_combo(trio_ids: list[str], combos: list[dict]) -> dict | None:
    key = _combo_key(trio_ids)
    for c in combos:
        if _combo_key(c["driverIds"]) == key:
            return c
    return None


def render_last_race(
    schedule: dict,
    podiums: list[dict],
    combos: list[dict],
    meta: dict,
    driver_form: list[dict],
    today: str | None = None,
) -> str:
    last = pick_last_race(schedule, today)
    if not last:
        return ""
    season = schedule.get("season", "")
    rnd = last["round"]
    pod = None
    for p in reversed(podiums):
        if p["season"] == season and p["round"] == rnd:
            pod = p
            break
    if not pod:
        return ""

    fl = flag_svg(last["country"])
    name = esc(last["raceName"])

    constructor_map = {d["driverId"]: d.get("constructorId", "") for d in driver_form}
    trio_ids = [pod["p1"]["driverId"], pod["p2"]["driverId"], pod["p3"]["driverId"]]
    drivers_html = []
    for pos, pid in enumerate(trio_ids, 1):
        entry = {
            "name": pod[f"p{pos}"]["name"],
            "driverId": pid,
            "constructorId": constructor_map.get(pid, ""),
        }
        v = driver_view(entry, meta)
        drivers_html.append(
            f'<span class="lr-driver" style="--team:{v["color"]}">'
            f'<span class="cd-dot"></span>'
            f'<span class="lr-code">{esc(v["code"])}</span>'
            f"</span>"
        )
    trio_html = '<span class="lr-sep">/</span>'.join(drivers_html)

    combo = _lookup_combo(trio_ids, combos)
    if combo and combo["count"] == 1:
        status_html = '<span class="lr-podigami">PODIGAMI</span>'
    elif combo:
        cnt = combo["count"]
        prev = combo.get("races", [])
        second_last = prev[-2] if len(prev) >= 2 else combo["lastRace"]
        wiki = (
            "https://en.wikipedia.org/wiki/"
            + f"{second_last['season']}_{second_last['raceName']}".replace(" ", "_")
        )
        status_html = (
            f'<span class="lr-status">Happened {cnt} time{"s" if cnt != 1 else ""}'
            f' &middot; last time <a class="lr-link" href="{esc(wiki)}"'
            f' target="_blank" rel="noopener">'
            f"R{esc(second_last['round'])} &middot;"
            f" {esc(second_last['raceName'])}</a></span>"
        )
    else:
        status_html = '<span class="lr-podigami">PODIGAMI</span>'

    return (
        f'<section class="last-race">'
        f'<span class="lr-tag">Last race</span>'
        f"{fl}"
        f'<span class="lr-name">R{esc(rnd)} &middot; {name}</span>'
        f'<span class="lr-trio">{trio_html}</span>'
        f"{status_html}"
        f"</section>"
    )


def render_hero(
    top: dict, chance: float, meta: dict, as_of_html: str = "", acc_badge: str = ""
) -> str:
    cards = []
    for p in top["perDriver"]:
        v = driver_view(p, meta)
        sp = p["seasonPodiums"]
        cards.append(
            f'<div class="hero-driver" style="--team:{v["color"]};--team-ink:{v["ink"]}">'
            f'<div class="hd-id">{_num_chip(v)}<span class="d-code">{esc(v["code"])}</span></div>'
            f'<div class="hd-name">{esc(v["surname"])}</div>'
            f'<div class="hd-team">{esc(v["team"])}</div>'
            f'<div class="hd-stat">{sp} podium{"s" if sp != 1 else ""} this season</div>'
            f"</div>"
        )
    pd = "".join(cards)
    # Provenance + backtest badge live as a footer of the prediction card so they
    # read as a caption on the headline, not as loose text floating between cards.
    meta_row = (
        f'<div class="hero-meta">{as_of_html}{acc_badge}</div>' if (as_of_html or acc_badge) else ""
    )
    return (
        f'<section class="hero">'
        f'  <div class="hero-head">'
        f'    <div class="hero-chance"><span class="hc-num">{chance:.0f}%</span>'
        f'      <span class="hc-label">chance the next race<br>delivers a brand-new trio'
        f'        <span class="info-tip info-tip-sm" tabindex="0" aria-label="More info">'
        f'          <span class="info-icon">i</span>'
        f'          <span class="info-bubble">The overall probability that any brand-new podium trio appears at the next race, not just the top-ranked one.</span>'
        f"        </span>"
        f"      </span></div>"
        f"  </div>"
        f'  <div class="hero-pick">'
        f'    <div class="hp-label">Most likely next <span class="accent">podigami</span></div>'
        f'    <div class="hero-drivers">{pd}</div>'
        f'    <div class="hp-prob">{top["prob"]:.1f}% of all possible podiums &mdash; the top never-before trio</div>'
        f"  </div>"
        f"  {meta_row}"
        f"</section>"
    )


def render_candidates(cands: list[dict], meta: dict) -> str:
    if not cands:
        return ""
    top = cands[0]["prob"] or 1
    rows = []
    for i, c in enumerate(cands, 1):
        pct = round(100 * c["prob"] / top)
        chips = []
        for p in c["perDriver"]:
            v = driver_view(p, meta)
            chips.append(
                f'<span class="cd" style="--team:{v["color"]}" title="{esc(display_name(v["name"]))}">'
                f'<span class="cd-dot"></span><span class="cd-code">{esc(v["code"])}</span>'
                f"</span>"
            )
        names = '<span class="cd-sep">/</span>'.join(chips)
        rows.append(
            f'<li class="cand">'
            f'<span class="cand-rank">{i}</span>'
            f'<div class="cand-body">'
            f'  <div class="cand-names">{names}</div>'
            f'  <div class="cand-bar-wrap"><div class="cand-bar" style="width:{pct}%"></div></div>'
            f"</div>"
            f'<span class="cand-prob">{c["prob"]:.2f}%</span>'
            f"</li>"
        )
    return (
        f'<section class="panel">'
        f"  <h2>Most likely next combinations"
        f'    <span class="info-tip" tabindex="0" aria-label="More info">'
        f'      <span class="info-icon">i</span>'
        f'      <span class="info-bubble">Trios that have never shared a podium, ranked by the model\'s probability they do it next.</span>'
        f"    </span>"
        f"  </h2>"
        f'  <ol class="cand-list">{"".join(rows)}</ol>'
        f"</section>"
    )


def render_form(form: list[dict], using_constructors: bool, meta: dict) -> str:
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
    sub = "Each driver's podium weight &mdash; recent podiums decay over ~8 races, with a boost for this season"
    if using_constructors:
        sub += " and constructor strength"
    sub += "."
    return (
        f'<section class="panel">'
        f"  <h2>Current form"
        f'    <span class="info-tip" tabindex="0" aria-label="More info">'
        f'      <span class="info-icon">i</span>'
        f'      <span class="info-bubble">{sub}</span>'
        f"    </span>"
        f"  </h2>"
        f'  <div class="form-tower">{"".join(rows)}</div>'
        f"</section>"
    )


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
    return (
        f'<section class="panel timeline">'
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
        f'  <div class="tl-spark">{"".join(bars)}</div>'
        f'  <div class="tl-controls">'
        f'    <input type="range" id="tl-slider" min="{lo}" max="{hi}" value="{current}" step="1">'
        f"  </div>"
        f'  <div class="tl-select-wrap">'
        f'    <select id="tl-select">{"".join(options)}</select>'
        f"  </div>"
        f'  <ul class="tl-list" id="tl-list"></ul>'
        f"</section>"
    )


def render_accuracy_badge(ev: dict) -> str:
    if not ev:
        return ""
    top3 = round(100 * ev["chosen"]["top3"])
    return (
        f'<span class="acc-badge" title="Backtested model accuracy">'
        f'<span class="acc-badge-k">Backtested</span>'
        f"<b>top-3 {top3}%</b>"
        f'<span class="acc-badge-sep">&middot;</span>calibrated'
        f"</span>"
    )


def render_faq(data: dict, ev: dict) -> str:
    mp = ev.get("modelParams", {}) if ev else {}
    half_life = mp.get("halfLife", 8)
    items = [
        (
            "How does the prediction model work?",
            f"A <strong>Plackett&ndash;Luce model</strong> estimates each driver&rsquo;s current "
            f"strength from their recent podium finishes, weighted toward recency (halved every "
            f"~{half_life:.0f} races). It then calculates the probability of every possible trio and "
            f"ranks the never-before-seen ones from most to least likely.",
        ),
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
            "Each driver&rsquo;s podium weight uses a recency decay &mdash; recent podiums count "
            "more than older ones. The weight also includes a boost for the current season and "
            "can factor in constructor strength.",
        ),
        (
            "Why haven&rsquo;t most trios happened yet?",
            "Even with decades of racing, the number of possible three-driver combinations from "
            "a 20-driver grid is enormous. Most trios are still podigamis waiting to happen.",
        ),
    ]
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


def main() -> int:
    data = load_podigami().model_dump()
    season = data["currentSeason"]
    chance = data["chanceNextRaceNew"]
    as_of = data["asOf"]
    cands = data["candidates"]
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
    next_race = render_next_race(schedule) if schedule else ""
    combos_dicts = [c.model_dump() for c in combos_list]
    podiums_dicts = [p.model_dump() for p in podiums_list]
    last_race = (
        render_last_race(schedule, podiums_dicts, combos_dicts, meta, data["driverForm"])
        if schedule
        else ""
    )

    model_eval = {}
    if (DATA_DIR / "model_eval.json").exists():
        model_eval = load_model_eval().model_dump()

    acc_badge = render_accuracy_badge(model_eval)
    as_of_html = (
        f'<p class="as-of">Model up to date through the {esc(as_of["season"])} '
        f"{esc(as_of['raceName'])} (round {esc(as_of['round'])}).</p>"
    )
    # The provenance + badge ride inside the hero card; when there's no hero
    # (no candidates), fall back to a standalone meta strip so they still show.
    hero = render_hero(cands[0], chance, meta, as_of_html, acc_badge) if cands else ""
    as_of_row = "" if cands else f'<div class="as-of-row">{as_of_html}{acc_badge}</div>'
    candidates = render_candidates(cands, meta)
    form = render_form(data["driverForm"], using_constructors, meta)
    timeline = render_timeline(data)
    faq = render_faq(data, model_eval)

    # Embedded data for the slider (only what the client needs).
    embed = json.dumps(
        {
            "bySeason": data["bySeason"],
            "seasonCounts": data["seasonCounts"],
            "currentSeason": season,
        },
        ensure_ascii=False,
    )

    page = f"""{
        head(
            f"F1 Podigami - Next Likely New Podium ({season})",
            "podigami.css",
            description=(
                f"Podigami is the art of spotting F1 podium trios that have never happened before. "
                f"Only {total_combos:,} unique trios have appeared in {total_races:,} races since {lo}. "
                f"A statistical model predicts which brand-new trio is most likely next in the {season} season."
            ),
            page_path="index.html",
            keywords="F1, podigami, Formula 1, podium prediction, scorigami, F1 podium, new podium trio, F1 statistics",
        )
    }
<body>
{nav("index.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Podigami</h1>
        <p class="tagline">Podigami &mdash; a blend of &ldquo;podium&rdquo; and
        &ldquo;<a href="https://en.wikipedia.org/wiki/Scorigami" target="_blank" rel="noopener">scorigami</a>&rdquo;
        &mdash; tracks F1 podium trios that have never happened before. Only <strong>{
        total_combos:,}</strong> unique combinations have appeared across <strong>{
        total_races:,}</strong> races since {lo}, yet today&rsquo;s {grid_size}-driver grid
        produces <strong>{possible_trios:,}</strong> possible trios per race. A statistical model
        predicts which brand-new trio is most likely next in the {season} season.</p>
    </div>
</header>
<main>
    <div class="container">
        {next_race}
        {last_race}
        {hero}
        {as_of_row}
        {candidates}
        {form}
        {timeline}
        {faq}
    </div>
</main>
{FOOTER}
<script type="application/json" id="podigami-data">{embed}</script>
<script src="podigami.js"></script>
<script src="theme.js"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  season {season}: P(new)={chance}%, {len(cands)} candidates, seasons {lo}-{hi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
