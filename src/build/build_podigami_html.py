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
from _layout import FOOTER, head, nav  # noqa: E402  (needs the sys.path entry above)
from flags import flag_svg  # noqa: E402
from team_colors import team_color, text_on  # noqa: E402

PODIGAMI_PATH = ROOT / "data" / "podigami.json"
CURRENT_DRIVERS_PATH = ROOT / "data" / "current_drivers.json"
SCHEDULE_PATH = ROOT / "data" / "schedule.json"
MODEL_EVAL_PATH = ROOT / "data" / "model_eval.json"
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
        "team": entry.get("constructor", ""),
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


def render_hero(top: dict, chance: float, meta: dict) -> str:
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
    return (
        f'<section class="hero">'
        f'  <div class="hero-head">'
        f'    <div class="hero-chance"><span class="hc-num">{chance:.0f}%</span>'
        f'      <span class="hc-label">chance the next race<br>delivers a brand-new trio</span></div>'
        f"  </div>"
        f'  <div class="hero-pick">'
        f'    <div class="hp-label">Most likely next <span class="accent">podigami</span></div>'
        f'    <div class="hero-drivers">{pd}</div>'
        f'    <div class="hp-prob">{top["prob"]:.1f}% of all possible podiums &mdash; the top never-before trio</div>'
        f"  </div>"
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
        f"  <h2>Most likely next combinations</h2>"
        f'  <p class="panel-sub">Trios that have never shared a podium, ranked by the model\'s probability they do it next.</p>'
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
        f"  <h2>Current form</h2>"
        f'  <p class="panel-sub">{sub}</p>'
        f'  <div class="form-tower">{"".join(rows)}</div>'
        f"</section>"
    )


def render_timeline(data: dict) -> str:
    lo, hi = data["seasonRange"]
    current = int(data["currentSeason"])
    counts = data["seasonCounts"]
    mx = max(counts.values()) if counts else 1
    bars = []
    for y in range(lo, hi + 1):
        n = counts.get(str(y), 0)
        h = round(100 * n / mx) if mx else 0
        bars.append(
            f'<span class="tl-bar" data-season="{y}" title="{y}: {n} new trio(s)" '
            f'style="height:{max(h, 2)}%"></span>'
        )
    return (
        f'<section class="panel timeline">'
        f"  <h2>New podiums through the years</h2>"
        f'  <p class="panel-sub">Every trio that debuted on a podium that season. Drag the slider or click a bar.</p>'
        f'  <div class="tl-spark">{"".join(bars)}</div>'
        f'  <div class="tl-controls">'
        f'    <input type="range" id="tl-slider" min="{lo}" max="{hi}" value="{current}" step="1">'
        f'    <div class="tl-readout"><span id="tl-year">{current}</span>'
        f'      <span class="tl-count" id="tl-count"></span></div>'
        f"  </div>"
        f'  <ul class="tl-list" id="tl-list"></ul>'
        f"</section>"
    )


def render_accuracy_badge(ev: dict) -> str:
    if not ev:
        return ""
    top3 = round(100 * ev["chosen"]["top3"])
    return (
        f'<a class="acc-badge" href="#model-accuracy" title="Backtested model accuracy">'
        f'<span class="acc-badge-k">Backtested</span>'
        f"<b>top-3 {top3}%</b>"
        f'<span class="acc-badge-sep">&middot;</span>calibrated'
        f'<span class="acc-badge-go">method &rarr;</span>'
        f"</a>"
    )


def _reliability_svg(cal: list[dict]) -> str:
    pts = [(b["meanPred"], b["obsRate"]) for b in cal if b["n"] and b["meanPred"] is not None]
    s = 180
    dots = "".join(
        f'<circle cx="{p * s:.1f}" cy="{(1 - o) * s:.1f}" r="3.5" class="acc-dot"/>' for p, o in pts
    )
    return (
        f'<svg class="acc-rel" viewBox="-6 -8 {s + 16} {s + 26}" role="img" '
        f'aria-label="P(new) calibration reliability">'
        f'<rect x="0" y="0" width="{s}" height="{s}" class="acc-frame"/>'
        f'<line x1="0" y1="{s}" x2="{s}" y2="0" class="acc-diag"/>'
        f"{dots}"
        f'<text x="{s / 2}" y="{s + 18}" class="acc-axis" text-anchor="middle">predicted &rarr;</text>'
        f"</svg>"
    )


def render_accuracy(ev: dict) -> str:
    if not ev:
        return ""
    ch = ev["chosen"]
    tw = ev["evalWindow"]["test"]
    mp = ev["modelParams"]
    rows = ""
    for r in ev["ladder"]:
        cls = ' class="acc-chosen"' if r["model"].startswith("PL + tuned") else ""
        rows += (
            f"<tr{cls}><td>{esc(r['model'])}</td>"
            f"<td>{round(100 * r['top1'])}%</td>"
            f"<td>{round(100 * r['top3'])}%</td>"
            f"<td>{round(100 * r['top5'])}%</td>"
            f"<td>{r['logLoss']:.2f}</td></tr>"
        )
    base = ch.get("baseRateNew", 0.0)
    bn = ch.get("brierNew", 0.0)
    bnb = ch.get("brierNewBaseRate", 0.0)
    return (
        f'<section class="panel" id="model-accuracy">'
        f"  <h2>Model accuracy &amp; method</h2>"
        f'  <p class="panel-sub">A Plackett-Luce model over recency-weighted driver strengths, '
        f"tuned and then measured on the {tw[0]}&ndash;{tw[1]} seasons it never saw during "
        f"tuning ({ch['n']} races). Lower log-loss is better.</p>"
        f'  <div class="acc-grid">'
        f'    <div class="acc-tablewrap">'
        f'      <table class="acc-table"><thead><tr><th>Model</th><th>Top-1</th>'
        f"<th>Top-3</th><th>Top-5</th><th>Log-loss</th></tr></thead><tbody>{rows}</tbody></table>"
        f'      <p class="acc-cap">Top-k = how often the real podium trio landed in the model&rsquo;s '
        f"k most likely. The highlighted row is the validated, shipped model.</p>"
        f"    </div>"
        f'    <div class="acc-calwrap">'
        f"      {_reliability_svg(ev['calibration'])}"
        f'      <p class="acc-cap">Calibration of the &ldquo;brand-new trio&rdquo; chance: dots near the '
        f"line = honest. Base-rate {round(100 * base)}%; the headline only just beats it "
        f"(Brier {bn:.3f} vs {bnb:.3f}) &mdash; the model&rsquo;s real edge is <em>ranking</em> "
        f"which trio, not that single %.</p>"
        f"    </div>"
        f"  </div>"
        f'  <p class="acc-note"><b>How it works:</b> each driver earns a strength from their recent '
        f"podiums (halved every {mp['halfLife']:.0f} races, shrunk across winters); Plackett-Luce "
        f"turns those into the probability each trio is the top three. "
        f"<b>What it can&rsquo;t do:</b> F1 podiums are high-variance, so exact-trio hits are rare by "
        f"nature; the live current-season car/teammate nudge is applied to today&rsquo;s grid but is "
        f"<em>not</em> in these backtested figures (no historical team data), and qualifying "
        f"isn&rsquo;t used yet.</p>"
        f"</section>"
    )


def main() -> int:
    data = json.loads(PODIGAMI_PATH.read_text(encoding="utf-8"))
    season = data["currentSeason"]
    chance = data["chanceNextRaceNew"]
    as_of = data["asOf"]
    cands = data["candidates"]
    lo, hi = data["seasonRange"]

    using_constructors = data.get("params", {}).get("usingConstructors", False)

    grid_doc = json.loads(CURRENT_DRIVERS_PATH.read_text(encoding="utf-8"))
    meta = {d["driverId"]: d for d in grid_doc["drivers"]}

    schedule = {}
    if SCHEDULE_PATH.exists():
        schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    next_race = render_next_race(schedule) if schedule else ""

    model_eval = {}
    if MODEL_EVAL_PATH.exists():
        model_eval = json.loads(MODEL_EVAL_PATH.read_text(encoding="utf-8"))

    hero = render_hero(cands[0], chance, meta) if cands else ""
    candidates = render_candidates(cands, meta)
    form = render_form(data["driverForm"], using_constructors, meta)
    timeline = render_timeline(data)
    acc_badge = render_accuracy_badge(model_eval)
    accuracy = render_accuracy(model_eval)

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
            description=f"Which never-before F1 podium trio is most likely next? A scorigami-style predictor for the {season} season, scored from {lo}-{hi} of podium history.",
            page_path="index.html",
            keywords="F1, podigami, Formula 1, podium prediction, scorigami, F1 podium, new podium trio, F1 statistics",
        )
    }
<body>
{nav("index.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Podigami</h1>
        <p class="tagline">Which never-before podium trio is most likely to happen next &mdash; a scorigami-style predictor for the {
        season
    } season, scored from {lo}&ndash;{hi} of podium history.</p>
    </div>
</header>
<main>
    <div class="container">
        {next_race}
        {hero}
        <div class="as-of-row">
            <p class="as-of">Model up to date through the {esc(as_of["season"])} {
        esc(as_of["raceName"])
    } (round {esc(as_of["round"])}).</p>
            {acc_badge}
        </div>
        {candidates}
        {form}
        {timeline}
        {accuracy}
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
